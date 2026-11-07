#!/usr/bin/env python3
"""Tests for ROM container selection and de-duplication in rom_scanner.py."""

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import rom_scanner as R


@pytest.fixture
def ps2_folder(tmp_path):
    """Factory that creates named files in a throwaway PS2 folder."""
    folder = tmp_path / "ps2"
    folder.mkdir()

    def build(*names):
        for name in names:
            (folder / name).write_bytes(b"\x00" * 64)
        return folder

    return build


def titles(roms):
    """Map clean title to the file chosen for it."""
    return {rom.clean_title: rom.filename for rom in roms}


class TestContainerRank:
    """Container preference used when several files are one game."""

    def test_chd_beats_everything(self):
        assert R._container_rank(".chd") > R._container_rank(".cue")

    def test_cue_beats_bin(self):
        assert R._container_rank(".cue") > R._container_rank(".bin")

    def test_case_insensitive(self):
        assert R._container_rank(".CUE") == R._container_rank(".cue")

    def test_dot_optional(self):
        assert R._container_rank("chd") == R._container_rank(".chd")

    def test_unknown_ranks_lowest(self):
        assert R._container_rank(".bin") > R._container_rank(".weird")
        assert R._container_rank("") == 1


class TestBinCuePair:
    """A bin/cue pair is one game, and the cue sheet is the right half."""

    def test_single_entry(self, ps2_folder):
        folder = ps2_folder("Gauntlet - Dark Legacy (USA).bin",
                            "Gauntlet - Dark Legacy (USA).cue")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1

    def test_cue_is_chosen(self, ps2_folder):
        folder = ps2_folder("Gauntlet - Dark Legacy (USA).bin",
                            "Gauntlet - Dark Legacy (USA).cue")
        roms = R.scan_rom_folder("ps2", folder)
        assert roms[0].filename.endswith(".cue")

    def test_cue_wins_when_seen_second(self, ps2_folder):
        """Order independence: the better container wins however it arrives."""
        folder = ps2_folder("Zeta (USA).iso", "Zeta (USA).cue")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].filename.endswith(".cue")

    def test_worse_container_does_not_replace(self, ps2_folder):
        folder = ps2_folder("Alpha (USA).cue", "Alpha (USA).bin")
        roms = R.scan_rom_folder("ps2", folder)
        assert roms[0].filename.endswith(".cue")

    def test_uppercase_extensions_match(self, ps2_folder):
        folder = ps2_folder("Star Trek Conquest.CUE", "Star Trek Conquest.ISO")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].filename.endswith(".CUE")


class TestMultiDisc:
    """Extra discs flag the first entry rather than adding shortcuts."""

    def test_extra_disc_marks_multi(self, ps2_folder):
        folder = ps2_folder("Xeno (USA) (Disc 1).iso", "Xeno (USA) (Disc 2).iso")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].is_multi_disc is True
        assert roms[0].filename.endswith("Disc 1).iso")

    def test_multi_disc_bin_cue_pairs(self, ps2_folder):
        folder = ps2_folder(
            "Xeno (USA) (Disc 1).bin", "Xeno (USA) (Disc 1).cue",
            "Xeno (USA) (Disc 2).bin", "Xeno (USA) (Disc 2).cue",
        )
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].is_multi_disc is True
        assert roms[0].filename.endswith("Disc 1).cue")

    def test_upgrade_keeps_multi_flag(self, ps2_folder):
        """A better container arriving late must not lose the disc flag."""
        folder = ps2_folder(
            "Y (USA) (Disc 1).iso",
            "Y (USA) (Disc 2).iso",
            "Y (USA) (Disc 1).cue",
        )
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].is_multi_disc is True


class TestChdSupport:
    """CHD dumps are real ROMs and must be found and preferred."""

    def test_chd_discovered(self, ps2_folder):
        folder = ps2_folder("Bards Tale The (USA).chd")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].extension == ".chd"

    def test_chd_preferred_over_iso(self, ps2_folder):
        folder = ps2_folder("Game (USA).chd", "Game (USA).iso")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 1
        assert roms[0].filename.endswith(".chd")

    def test_title_cleaned_from_chd_name(self, ps2_folder):
        folder = ps2_folder("Need for Speed - Carbon (USA).chd")
        roms = R.scan_rom_folder("ps2", folder)
        assert roms[0].clean_title == "Need for Speed - Carbon"


class TestDistinctGamesUnaffected:
    """De-duplication must not swallow genuinely different games."""

    def test_different_titles_both_kept(self, ps2_folder):
        folder = ps2_folder("Dark Cloud (USA).iso", "Dark Cloud 2 (USA).iso")
        roms = R.scan_rom_folder("ps2", folder)
        assert len(roms) == 2

    def test_mixed_library(self, ps2_folder):
        folder = ps2_folder(
            "A (USA).bin", "A (USA).cue",
            "B (USA).iso",
            "C (USA).chd", "C (USA).iso",
        )
        roms = R.scan_rom_folder("ps2", folder)
        chosen = titles(roms)
        assert len(roms) == 3
        assert chosen["A"].endswith(".cue")
        assert chosen["B"].endswith(".iso")
        assert chosen["C"].endswith(".chd")
