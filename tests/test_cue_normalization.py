#!/usr/bin/env python3
"""Tests for CUE sheet normalization in rom_scanner.py."""

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import rom_scanner as R


@pytest.fixture
def cue_folder(tmp_path):
    """A folder holding cue sheets for normalization tests."""
    folder = tmp_path / "ps2"
    folder.mkdir()
    return folder


class TestNormalizeCueFile:
    """CUE sheets must end up LF-only so PCSX2 can parse them."""

    def test_crlf_is_converted(self, cue_folder):
        cue = cue_folder / "game (USA).cue"
        cue.write_bytes(b'FILE "game.bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n')
        assert R.normalize_cue_file(cue) is True
        assert b"\r" not in cue.read_bytes()

    def test_cr_only_is_converted(self, cue_folder):
        cue = cue_folder / "game (USA).cue"
        cue.write_bytes(b'FILE "game.bin" BINARY\r  TRACK 01 MODE2/2352\r')
        assert R.normalize_cue_file(cue) is True
        assert b"\r" not in cue.read_bytes()

    def test_lf_only_is_untouched(self, cue_folder):
        cue = cue_folder / "game (USA).cue"
        original = b'FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n'
        cue.write_bytes(original)
        assert R.normalize_cue_file(cue) is False
        assert cue.read_bytes() == original

    def test_idempotent(self, cue_folder):
        cue = cue_folder / "game (USA).cue"
        cue.write_bytes(b'FILE "game.bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n')
        R.normalize_cue_file(cue)
        assert R.normalize_cue_file(cue) is False

    def test_filename_token_has_no_trailing_cr(self, cue_folder):
        """The exact bug: a \\r in the FILE token breaks PCSX2's lookup."""
        cue = cue_folder / "RC Revenge Pro (USA).cue"
        cue.write_bytes(
            b'FILE "RC Revenge Pro (USA).bin" BINARY\r\n'
            b'  TRACK 01 MODE2/2352\r\n'
            b'    INDEX 01 00:00:00\r\n'
        )
        R.normalize_cue_file(cue)
        text = cue.read_text()
        assert 'RC Revenge Pro (USA).bin"' in text
        assert 'RC Revenge Pro (USA).bin\r"' not in text

    def test_mixed_endings_are_unified(self, cue_folder):
        cue = cue_folder / "game (USA).cue"
        cue.write_bytes(b'FILE "game.bin" BINARY\r\n  TRACK\r01\r\n')
        R.normalize_cue_file(cue)
        assert b"\r" not in cue.read_bytes()

    def test_empty_file_is_untouched(self, cue_folder):
        cue = cue_folder / "empty.cue"
        cue.write_bytes(b"")
        assert R.normalize_cue_file(cue) is False
