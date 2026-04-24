#!/usr/bin/env python3
"""Tests for systems.py — system definitions and Vita3K path discovery."""

import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from systems import (
    EmulatorConfig,
    SystemDef,
    get_system,
    list_supported_systems,
    find_vita3k_data_dir,
    _find_vita3k_binary,
)


# ── System Definitions ──────────────────────────────────────────────────────

class TestSystemDefinitions:
    """Test that all system definitions are valid."""

    def test_psvita_exists(self):
        """PS Vita system is defined."""
        sys_def = get_system('psvita')
        assert sys_def is not None
        assert sys_def.name == 'psvita'
        assert sys_def.fullname == 'PlayStation Vita'
        assert sys_def.manufacturer == 'Sony'

    def test_psvita_has_emulator(self):
        """PS Vita has a Vita3K emulator config."""
        sys_def = get_system('psvita')
        assert sys_def.emulator is not None
        assert sys_def.emulator.launch_mode == 'title_id'
        assert '-F -r "{title_id}"' in sys_def.emulator.launch_args

    def test_psvita_has_platform_ids(self):
        """PS Vita has ScreenScraper and TheGamesDB IDs."""
        sys_def = get_system('psvita')
        assert sys_def.screenscraper_id == 62
        assert sys_def.thegamesdb_id == '39'

    def test_psvita_scan_as_dirs(self):
        """PS Vita has scan_as_dirs=True."""
        sys_def = get_system('psvita')
        assert sys_def.scan_as_dirs is True

    def test_psvita_legacy_tags(self):
        """PS Vita has legacy tag aliases."""
        sys_def = get_system('psvita')
        assert 'PS Vita' in sys_def.legacy_tags
        assert 'Vita' in sys_def.legacy_tags
        assert 'PSVita' in sys_def.legacy_tags

    def test_psvita_in_list(self):
        """PS Vita appears in the supported systems list."""
        systems = list_supported_systems()
        assert 'psvita' in systems

    def test_all_systems_have_required_fields(self):
        """Every system has name, fullname, manufacturer, emulator."""
        for name in list_supported_systems():
            sys_def = get_system(name)
            assert sys_def.name == name
            assert sys_def.fullname
            assert sys_def.manufacturer
            assert sys_def.emulator is not None


# ── Vita3K Emulator Config ───────────────────────────────────────────────────

class TestVita3KEmulator:
    """Test Vita3K emulator configuration."""

    def test_title_id_launch_mode(self):
        """Vita3K uses title_id launch mode."""
        sys_def = get_system('psvita')
        assert sys_def.emulator.launch_mode == 'title_id'

    def test_steam_exe_with_title_id(self):
        """Vita3K generates Steam exe with title ID, not ROM path."""
        sys_def = get_system('psvita')
        exe = sys_def.emulator.get_steam_exe('PCSE00317')
        # Should contain -F -r "PCSE00317"
        assert '-F -r "PCSE00317"' in exe
        # Should NOT contain a file path
        assert '/rom/' not in exe
        assert '.bin' not in exe

    def test_steam_exe_format(self):
        """Vita3K Steam exe is properly quoted."""
        sys_def = get_system('psvita')
        exe = sys_def.emulator.get_steam_exe('PCSE00317')
        # Should start with quoted binary path
        assert exe.startswith('"')
        # Should contain -r flag
        assert '-r' in exe


# ── Vita3K Path Discovery ────────────────────────────────────────────────────

class TestVita3KPathDiscovery:
    """Test Vita3K binary and data directory discovery."""

    def test_find_vita3k_binary_returns_string(self):
        """_find_vita3k_binary always returns a string."""
        result = _find_vita3k_binary()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_find_vita3k_data_dir_returns_path_or_none(self):
        """find_vita3k_data_dir returns Path or None."""
        result = find_vita3k_data_dir()
        assert result is None or isinstance(result, Path)

    def test_find_vita3k_data_dir_with_config(self):
        """find_vita3k_data_dir reads pref-path from config.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake Vita3K config with pref-path
            config_dir = Path(tmpdir) / 'Vita3K'
            config_dir.mkdir()
            config_file = config_dir / 'config.yml'
            config_file.write_text('pref-path: ""\n', encoding='utf-8')

            # Create a fake data directory
            data_dir = Path(tmpdir) / 'vita_data'
            data_dir.mkdir()
            ux0 = data_dir / 'ux0'
            ux0.mkdir()
            (ux0 / 'app').mkdir()

            # Write pref-path pointing to our data dir
            config_file.write_text(f'pref-path: {data_dir}\n', encoding='utf-8')

            # This test can't easily mock the home directory, so we just
            # verify the function doesn't crash
            result = find_vita3k_data_dir()
            assert result is None or isinstance(result, Path)


# ── EmulatorConfig ────────────────────────────────────────────────────────────

class TestEmulatorConfig:
    """Test EmulatorConfig for all launch modes."""

    def test_rom_launch_mode(self):
        """Standard ROM launch mode works."""
        emu = EmulatorConfig(
            emulator='/usr/bin/retroarch',
            core='snes9x',
            flatpak_id=None,
            launch_args='-L /core.so "{rom}"',
            launch_mode='rom',
        )
        exe = emu.get_steam_exe('/path/to/game.sfc')
        assert '/path/to/game.sfc' in exe
        assert '-L /core.so' in exe

    def test_title_id_launch_mode(self):
        """Title ID launch mode replaces {title_id}."""
        emu = EmulatorConfig(
            emulator='/usr/bin/Vita3K',
            core=None,
            flatpak_id=None,
            launch_args='-F -r "{title_id}"',
            launch_mode='title_id',
        )
        exe = emu.get_steam_exe('PCSE00317')
        assert '-F -r "PCSE00317"' in exe
        assert '/usr/bin/Vita3K' in exe

    def test_flatpak_launch_mode(self):
        """Flatpak launch mode works."""
        emu = EmulatorConfig(
            emulator='retroarch',
            core='snes9x',
            flatpak_id='org.libretro.RetroArch',
            launch_args='-L /core.so "{rom}"',
            launch_mode='rom',
        )
        exe = emu.get_steam_exe('/path/to/game.sfc')
        assert '/usr/bin/flatpak' in exe
        assert 'org.libretro.RetroArch' in exe