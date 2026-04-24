#!/usr/bin/env python3
"""Tests for rom_scanner.py — PS Vita scanning and SFO parsing."""

import struct
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from rom_scanner import parse_sfo, scan_vita3k_apps, RomEntry


# ── SFO Parser Tests ─────────────────────────────────────────────────────────

def _make_sfo(entries: dict) -> bytes:
    """Build a minimal SFO binary from a dict of key-value pairs.

    Creates a valid SFO file with the given entries for testing.
    """
    # SFO format:
    # Header: magic(4) + version(4) + key_offset(4) + data_offset(4) + num_entries(4)
    # Key table: null-terminated strings
    # Data table: values (strings null-terminated, uint32 as 4 bytes)

    keys = list(entries.keys())
    values = list(entries.values())
    num_entries = len(keys)

    # Calculate offsets
    header_size = 0x14
    entry_table_size = num_entries * 0x10

    # Key table starts after entry table
    key_table_offset = header_size + entry_table_size

    # Build key table
    key_data = b''
    key_offsets = []
    for key in keys:
        key_offsets.append(len(key_data))
        key_data += key.encode('utf-8') + b'\x00'

    # Pad key table to 4-byte alignment
    while len(key_data) % 4:
        key_data += b'\x00'

    # Data table starts after key table
    data_table_offset = key_table_offset + len(key_data)

    # Build data table
    data_items = []
    for value in values:
        if isinstance(value, int):
            data_items.append((0x0002, struct.pack('<I', value), 4))
        else:
            encoded = value.encode('utf-8') + b'\x00'
            # Pad to 4-byte alignment
            while len(encoded) % 4:
                encoded += b'\x00'
            data_items.append((0x0004, encoded, len(encoded)))

    # Build entry table
    entry_table = b''
    data_offset = 0
    for i, (data_fmt, data_bytes, data_len) in enumerate(data_items):
        entry = struct.pack('<HHIII',
                           key_offsets[i],   # key_name_offset
                           data_fmt,          # data_fmt
                           data_len,          # data_len
                           data_len,          # data_max_len
                           data_offset)       # data_entry_offset
        entry_table += entry
        data_offset += len(data_bytes)

    # Build data section
    data_section = b''
    for _, data_bytes, _ in data_items:
        data_section += data_bytes

    # Build header
    header = struct.pack('<4sIIII',
                        b'\x00PSF',         # magic
                        0x00000101,          # version
                        key_table_offset,
                        data_table_offset,
                        num_entries)

    return header + entry_table + key_data + data_section


class TestSfoParser:
    """Test SFO file parsing."""

    def test_parse_basic_sfo(self):
        """Parse a basic SFO file with TITLE and CATEGORY."""
        sfo_data = _make_sfo({
            'TITLE': 'Spelunky',
            'CATEGORY': 'gd',
            'APP_VER': '01.00',
            'TITLE_ID': 'PCSE00317',
        })
        with tempfile.NamedTemporaryFile(suffix='.sfo', delete=False) as f:
            f.write(sfo_data)
            f.flush()
            result = parse_sfo(Path(f.name))

        assert result is not None
        assert result['TITLE'] == 'Spelunky'
        assert result['CATEGORY'] == 'gd'
        assert result['APP_VER'] == '01.00'
        assert result['TITLE_ID'] == 'PCSE00317'

    def test_parse_sfo_with_integer(self):
        """Parse SFO file with integer values."""
        sfo_data = _make_sfo({
            'TITLE': 'Test Game',
            'VERSION': 0x00000101,
        })
        with tempfile.NamedTemporaryFile(suffix='.sfo', delete=False) as f:
            f.write(sfo_data)
            f.flush()
            result = parse_sfo(Path(f.name))

        assert result is not None
        assert result['TITLE'] == 'Test Game'
        assert result['VERSION'] == '257'  # 0x101

    def test_parse_empty_file(self):
        """Empty file returns None."""
        with tempfile.NamedTemporaryFile(suffix='.sfo', delete=False) as f:
            f.write(b'')
            f.flush()
            result = parse_sfo(Path(f.name))

        assert result is None

    def test_parse_invalid_magic(self):
        """File with wrong magic returns None."""
        with tempfile.NamedTemporaryFile(suffix='.sfo', delete=False) as f:
            f.write(b'INVALID_DATA_HERE')
            f.flush()
            result = parse_sfo(Path(f.name))

        assert result is None

    def test_parse_nonexistent_file(self):
        """Non-existent file returns None."""
        result = parse_sfo(Path('/nonexistent/path/param.sfo'))
        assert result is None

    def test_parse_real_vita_sfo(self):
        """Parse a realistic PS Vita SFO file."""
        sfo_data = _make_sfo({
            'TITLE': 'Terraria',
            'CATEGORY': 'gd',
            'APP_VER': '01.00',
            'TITLE_ID': 'PCSE00317',
            'CONTENT_ID': 'EP4113-PCSE00317_00-TERRARIAFULL0001',
        })
        with tempfile.NamedTemporaryFile(suffix='.sfo', delete=False) as f:
            f.write(sfo_data)
            f.flush()
            result = parse_sfo(Path(f.name))

        assert result is not None
        assert result['TITLE'] == 'Terraria'
        assert result['TITLE_ID'] == 'PCSE00317'


# ── Vita3K Scanner Tests ──────────────────────────────────────────────────────

class TestVita3KScanner:
    """Test Vita3K app scanning."""

    def _create_fake_vita3k_app(self, base_dir: Path, title_id: str,
                                title: str = None) -> Path:
        """Create a fake Vita3K app directory with param.sfo."""
        app_dir = base_dir / 'ux0' / 'app' / title_id
        app_dir.mkdir(parents=True, exist_ok=True)

        # Create eboot.bin (required marker file)
        (app_dir / 'eboot.bin').write_bytes(b'\x00' * 16)

        # Create sce_sys/param.sfo
        if title is None:
            title = title_id  # Fall back to title ID
        sfo_data = _make_sfo({
            'TITLE': title,
            'TITLE_ID': title_id,
            'CATEGORY': 'gd',
        })
        sfo_dir = app_dir / 'sce_sys'
        sfo_dir.mkdir(exist_ok=True)
        (sfo_dir / 'param.sfo').write_bytes(sfo_data)

        return app_dir

    def test_scan_empty_directory(self):
        """Scanning empty directory returns no games."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # Create ux0/app but empty
            (base / 'ux0' / 'app').mkdir(parents=True)
            roms = scan_vita3k_apps(base)
            assert roms == []

    def test_scan_single_game(self):
        """Scanning finds a single installed game."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_fake_vita3k_app(base, 'PCSE00317', 'Spelunky')
            roms = scan_vita3k_apps(base)

            assert len(roms) == 1
            assert roms[0].title_id == 'PCSE00317'
            assert roms[0].clean_title == 'Spelunky'
            assert roms[0].system == 'psvita'
            assert roms[0].region == 'USA'  # PCSE = Americas

    def test_scan_multiple_games(self):
        """Scanning finds multiple installed games."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_fake_vita3k_app(base, 'PCSE00317', 'Spelunky')
            self._create_fake_vita3k_app(base, 'PCSB00123', 'Wipeout 2048')
            self._create_fake_vita3k_app(base, 'PCSG00001', 'Gravity Daze')
            roms = scan_vita3k_apps(base)

            assert len(roms) == 3
            titles = {r.clean_title for r in roms}
            assert 'Spelunky' in titles
            assert 'Wipeout 2048' in titles
            assert 'Gravity Daze' in titles

    def test_scan_region_detection(self):
        """Region is detected from title ID prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_fake_vita3k_app(base, 'PCSE00317', 'Game USA')
            self._create_fake_vita3k_app(base, 'PCSB00123', 'Game EUR')
            self._create_fake_vita3k_app(base, 'PCSG00001', 'Game JPN')
            roms = scan_vita3k_apps(base)

            regions = {r.title_id: r.region for r in roms}
            assert regions['PCSE00317'] == 'USA'
            assert regions['PCSB00123'] == 'EUR'
            assert regions['PCSG00001'] == 'JPN'

    def test_scan_skips_non_title_id_dirs(self):
        """Directories that don't match title ID format are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_fake_vita3k_app(base, 'PCSE00317', 'Real Game')
            # Create a non-title-ID directory
            fake_dir = base / 'ux0' / 'app' / 'savedata'
            fake_dir.mkdir(parents=True, exist_ok=True)
            (fake_dir / 'eboot.bin').write_bytes(b'\x00')

            roms = scan_vita3k_apps(base)
            assert len(roms) == 1
            assert roms[0].title_id == 'PCSE00317'

    def test_scan_skips_dirs_without_eboot(self):
        """Directories without eboot.bin are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            app_dir = base / 'ux0' / 'app' / 'PCSE99999'
            app_dir.mkdir(parents=True)
            # No eboot.bin

            roms = scan_vita3k_apps(base)
            assert len(roms) == 0

    def test_scan_falls_back_to_title_id(self):
        """When param.sfo is missing, title ID is used as the game title."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            app_dir = base / 'ux0' / 'app' / 'PCSE00317'
            app_dir.mkdir(parents=True)
            (app_dir / 'eboot.bin').write_bytes(b'\x00')
            # No sce_sys/param.sfo

            roms = scan_vita3k_apps(base)
            assert len(roms) == 1
            assert roms[0].clean_title == 'PCSE00317'

    def test_scan_none_data_dir(self):
        """Passing None for data_dir triggers auto-detection."""
        # This will likely return None or empty list since we're not
        # on a real Vita3K installation
        roms = scan_vita3k_apps(None)
        # Should not crash; result depends on system state
        assert isinstance(roms, list)

    def test_scan_nonexistent_data_dir(self):
        """Passing a nonexistent path returns empty list."""
        roms = scan_vita3k_apps(Path('/nonexistent/path'))
        assert roms == []

    def test_rom_entry_has_title_id(self):
        """RomEntry for Vita games has title_id set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._create_fake_vita3k_app(base, 'PCSE00317', 'Spelunky')
            roms = scan_vita3k_apps(base)

            assert len(roms) == 1
            assert roms[0].title_id == 'PCSE00317'
            assert roms[0].extension == ''  # No file extension for installed apps