"""Tests for rom_scanner.clean_title and metadata extraction.

These are characterization tests: they lock in the observable behavior of the
title-cleaning pipeline (No-Intro, GoodTools, multi-disc, etc.) so refactors
cannot silently regress user-facing shortcut titles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rom_scanner import clean_title, extract_region, extract_disc_number


class TestCleanTitle:
    def test_StripNoIntro_with_region_and_bang(self):
        # No-Intro: "Game Title (Region) [flags]"
        assert clean_title("The Legend of Zelda (USA) (Rev 1) [!]") == "The Legend of Zelda"

    def test_StripNoIntro_world_region(self):
        assert clean_title("Super Mario Bros. (World) (Rev 1) [!]") == "Super Mario Bros."

    def test_goodtools_year_in_parens(self):
        # GoodTools: "Game (2000)(Publisher)(NTSC)(US)[!]"
        # The year tag (2000) and region tags are stripped; a Title-Case
        # publisher parenthetical is preserved by the current conservative
        # cleaning rules (locked-in behavior).
        result = clean_title("Game (2000)(Publisher)(NTSC)(US)[!]")
        assert result == "Game (Publisher)"

    def test_goodtools_full_dump(self):
        # The v1.001 (2000) cut point and region/[!] flags are all stripped.
        assert clean_title("Game v1.001 (2000)(Publisher)(NTSC)(US)[!]") == "Game"

    def test_multidisc_disc_number_removed(self):
        assert clean_title("Game (Disc 2)") == "Game"
        assert extract_disc_number("Game (Disc 2)") == 2

    def test_extract_disc_number_without_parens(self):
        assert extract_disc_number("Game Disc 3") == 3
        assert extract_disc_number("No Disc Here") is None

    def test_removes_version_tag(self):
        # (v1.01) style version tag should not appear in the clean title
        result = clean_title("Game Title (USA) (v1.01)")
        assert "v1" not in result.lower()
        assert result == "Game Title"

    def test_keeps_subtitle_with_lowercase(self):
        # A parenthetical subtitle with lowercase letters is a real subtitle,
        # not metadata, and must be preserved.
        assert clean_title("Game (The Legend of Zelda)") == "Game (The Legend of Zelda)"

    def test_underscores_to_spaces(self):
        assert clean_title("Game_Title_USS") == "Game Title USS"

    def test_strips_extension(self):
        assert clean_title("Game Name (USA).zip") == "Game Name"

    def test_empty_after_cleaning_returns_empty(self):
        # All-metadata filename should yield an empty (or whitespace) title
        result = clean_title("(USA)")
        assert result.strip() == ""


class TestRegion:
    def test_usa_region(self):
        assert extract_region("Game (USA)") == "USA"

    def test_europe_region(self):
        assert extract_region("Game (Europe)") == "EUR"

    def test_japan_region(self):
        assert extract_region("Game (Japan)") == "JPN"

    def test_multiregion_first_wins(self):
        assert extract_region("Game (NTSC)(US)") == "USA"

    def test_no_region_returns_none(self):
        assert extract_region("Game Title") is None
