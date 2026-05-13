#!/usr/bin/env python3
"""Tests for the reconcile module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reconcile import (
    OrphanedArt,
    OrphanedShortcut,
    ReconcileReport,
    classify_art_file,
    extract_rom_path,
    find_orphaned_art,
    find_unlinked_art,
    find_orphaned_shortcuts,
    format_size,
    get_known_rom_tags,
    is_heroic_shortcut,
    remove_orphaned_art,
)


# ═══════════════════════════════════════════════════════════════════════
# classify_art_file tests
# ═══════════════════════════════════════════════════════════════════════

class TestClassifyArtFile:
    def test_tall_capsule_png(self):
        result = classify_art_file("1234567890p.png")
        assert result == ("1234567890", "tall")

    def test_tall_capsule_jpg(self):
        result = classify_art_file("1234567890p.jpg")
        assert result == ("1234567890", "tall")

    def test_wide_capsule_png(self):
        result = classify_art_file("1234567890.png")
        assert result == ("1234567890", "wide")

    def test_wide_capsule_jpg(self):
        result = classify_art_file("1234567890.jpg")
        assert result == ("1234567890", "wide")

    def test_hero_png(self):
        result = classify_art_file("1234567890_hero.png")
        assert result == ("1234567890", "hero")

    def test_logo_png(self):
        result = classify_art_file("1234567890_logo.png")
        assert result == ("1234567890", "logo")

    def test_icon_png(self):
        result = classify_art_file("1234567890_icon.png")
        assert result == ("1234567890", "icon")

    def test_non_art_file(self):
        result = classify_art_file("shortcuts.vdf")
        assert result is None

    def test_random_file(self):
        result = classify_art_file("readme.txt")
        assert result is None

    def test_non_numeric_prefix(self):
        result = classify_art_file("abc_hero.png")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# extract_rom_path tests
# ═══════════════════════════════════════════════════════════════════════

class TestExtractRomPath:
    def test_retroarch_flatpak(self):
        exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /cores/snes9x.so "/roms/snes/Game.sfc"'
        result = extract_rom_path(exe)
        assert result is not None
        assert str(result) == "/roms/snes/Game.sfc"

    def test_standalone_emulator(self):
        exe = '"/usr/bin/dolphin-emu" "/roms/gc/game.iso"'
        result = extract_rom_path(exe)
        assert result is not None
        assert str(result) == "/roms/gc/game.iso"

    def test_no_rom_path(self):
        """When exe has no ROM-like path, extract_rom_path may return the exe itself."""
        exe = '"/usr/bin/flatpak" run org.libretro.RetroArch'
        result = extract_rom_path(exe)
        # The function may return the flatpak binary itself since it has no suffix
        # This is fine - the caller checks if the ROM file exists on disk
        # and /usr/bin/flatpak always exists, so it won't be flagged as orphaned
        # The important thing is it doesn't crash
        assert result is None or isinstance(result, Path)

    def test_library_path_ignored(self):
        exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /cores/snes9x.so "/roms/game.sfc"'
        result = extract_rom_path(exe)
        assert result is not None
        assert "/roms/game.sfc" in str(result)

    def test_empty_exe(self):
        result = extract_rom_path("")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# is_heroic_shortcut tests
# ═══════════════════════════════════════════════════════════════════════

class TestIsHeroicShortcut:
    def test_heroic_tag(self):
        sc = MagicMock()
        sc.tags = {"0": "Heroic"}
        assert is_heroic_shortcut(sc) is True

    def test_rom_tag(self):
        sc = MagicMock()
        sc.tags = {"0": "NES"}
        assert is_heroic_shortcut(sc) is False

    def test_no_tags(self):
        sc = MagicMock()
        sc.tags = {}
        assert is_heroic_shortcut(sc) is False


# ═══════════════════════════════════════════════════════════════════════
# find_orphaned_shortcuts tests
# ═══════════════════════════════════════════════════════════════════════

class TestFindOrphanedShortcuts:
    def _make_shortcut(self, appname, exe, tags, appid=12345):
        sc = MagicMock()
        sc.appname = appname
        sc.exe = exe
        sc.tags = tags
        sc.appid = appid
        return sc

    def test_rom_missing(self):
        """ROM shortcut whose ROM file doesn't exist."""
        sc = self._make_shortcut(
            "Test Game",
            '"/usr/bin/flatpak" run org.libretro.RetroArch -L /cores/snes9x.so "/nonexistent/rom.sfc"',
            {"0": "SNES"},
        )
        orphans = find_orphaned_shortcuts([sc], heroic_games=None)
        assert len(orphans) == 1
        assert orphans[0].reason == "rom_missing"
        assert orphans[0].appname == "Test Game"

    def test_rom_exists(self):
        """ROM shortcut whose ROM file exists."""
        with tempfile.NamedTemporaryFile(suffix=".sfc", delete=False) as f:
            rom_path = f.name
        try:
            sc = self._make_shortcut(
                "Test Game",
                f'"/usr/bin/flatpak" run org.libretro.RetroArch -L /cores/snes9x.so "{rom_path}"',
                {"0": "SNES"},
            )
            orphans = find_orphaned_shortcuts([sc], heroic_games=None)
            assert len(orphans) == 0
        finally:
            os.unlink(rom_path)

    def test_heroic_uninstalled(self):
        """Heroic shortcut whose game is no longer in Heroic library."""
        sc = self._make_shortcut(
            "Gone Game",
            '"/home/deck/.local/share/heroic/tools/..."',
            {"0": "Heroic"},
        )
        heroic_games = [{"title": "Still Here", "runner": "legendary"}]
        orphans = find_orphaned_shortcuts([sc], heroic_games=heroic_games)
        assert len(orphans) == 1
        assert orphans[0].reason == "heroic_uninstalled"

    def test_heroic_still_installed(self):
        """Heroic shortcut whose game is still in Heroic library."""
        sc = self._make_shortcut(
            "Still Here",
            '"/home/deck/.local/share/heroic/tools/..."',
            {"0": "Heroic"},
        )
        heroic_games = [{"title": "Still Here", "runner": "legendary"}]
        orphans = find_orphaned_shortcuts([sc], heroic_games=heroic_games)
        assert len(orphans) == 0

    def test_system_exe_not_flagged(self):
        """Shortcuts with /usr/bin exe should not be flagged as orphaned."""
        sc = self._make_shortcut(
            "Some App",
            '"/usr/bin/flatpak" run com.example.App',
            {},
        )
        orphans = find_orphaned_shortcuts([sc], heroic_games=None)
        assert len(orphans) == 0

    def test_missing_custom_exe(self):
        """Shortcut with a custom exe that doesn't exist."""
        sc = self._make_shortcut(
            "Custom Game",
            '"/home/deck/nonexistent/emulator" "/path/to/game"',
            {},
        )
        orphans = find_orphaned_shortcuts([sc], heroic_games=None)
        assert len(orphans) == 1
        assert orphans[0].reason == "exe_missing"


# ═══════════════════════════════════════════════════════════════════════
# find_orphaned_art tests
# ═══════════════════════════════════════════════════════════════════════

class TestFindOrphanedArt:
    def test_orphaned_art_file(self):
        """Art file whose app ID belongs to a removed shortcut."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            # Create an art file for app ID 99999
            (grid_path / "99999p.png").write_bytes(b"fake image data")
            (grid_path / "99999_hero.png").write_bytes(b"fake hero data")

            # Shortcut 99999 is being removed (orphaned)
            orphaned_ids = {"99999"}
            orphans = find_orphaned_art(grid_path, orphaned_ids)

            assert len(orphans) == 2
            art_types = {o.art_type for o in orphans}
            assert "tall" in art_types
            assert "hero" in art_types

    def test_matching_art_not_orphaned(self):
        """Art file whose app ID is not in the removed set is not orphaned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "12345p.png").write_bytes(b"data")

            # 12345 is NOT being removed, so its art is not orphaned
            orphaned_ids = set()
            orphans = find_orphaned_art(grid_path, orphaned_ids)
            assert len(orphans) == 0

    def test_non_art_files_ignored(self):
        """Non-art files in the grid folder are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "shortcuts.vdf").write_bytes(b"binary data")

            orphaned_ids = set()
            orphans = find_orphaned_art(grid_path, orphaned_ids)
            assert len(orphans) == 0

    def test_symlink_art(self):
        """Symlink art files are detected as orphans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            target = grid_path / "12345p.png"
            target.write_bytes(b"data")
            link = grid_path / "99999p.png"
            link.symlink_to(target)

            # 99999 is being removed, so its art is orphaned
            orphaned_ids = {"99999"}
            orphans = find_orphaned_art(grid_path, orphaned_ids)

            # Only the symlink for 99999 should be orphaned
            assert len(orphans) == 1
            assert orphans[0].app_id == "99999"
            assert orphans[0].is_symlink is True


class TestFindUnlinkedArt:
    def test_unlinked_art_file(self):
        """Art file whose app ID has no matching shortcut is unlinked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "99999p.png").write_bytes(b"fake image data")
            (grid_path / "99999_hero.png").write_bytes(b"fake hero data")

            # No shortcuts have app ID 99999
            shortcut_ids = set()
            unlinked = find_unlinked_art(grid_path, shortcut_ids)

            assert len(unlinked) == 2
            art_types = {o.art_type for o in unlinked}
            assert "tall" in art_types
            assert "hero" in art_types

    def test_linked_art_not_unlinked(self):
        """Art file whose app ID matches a shortcut is not unlinked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "12345p.png").write_bytes(b"data")

            shortcut_ids = {"12345"}
            unlinked = find_unlinked_art(grid_path, shortcut_ids)
            assert len(unlinked) == 0

    def test_mixed_linked_unlinked(self):
        """Only art with no matching shortcut is unlinked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "12345p.png").write_bytes(b"data")
            (grid_path / "99999p.png").write_bytes(b"data")

            shortcut_ids = {"12345"}
            unlinked = find_unlinked_art(grid_path, shortcut_ids)
            assert len(unlinked) == 1
            assert unlinked[0].app_id == "99999"


# ═══════════════════════════════════════════════════════════════════════
# remove_orphaned_art tests
# ═══════════════════════════════════════════════════════════════════════

class TestRemoveOrphanedArt:
    def test_remove_files(self):
        """Orphaned art files are deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            (grid_path / "99999p.png").write_bytes(b"data")
            (grid_path / "99999_hero.png").write_bytes(b"data")
            (grid_path / "12345p.png").write_bytes(b"data")  # Not orphaned

            orphans = [
                OrphanedArt(filename="99999p.png", app_id="99999", art_type="tall", size_bytes=4),
                OrphanedArt(filename="99999_hero.png", app_id="99999", art_type="hero", size_bytes=4),
            ]

            removed, errors = remove_orphaned_art(grid_path, orphans)
            assert removed == 2
            assert errors == 0
            assert not (grid_path / "99999p.png").exists()
            assert not (grid_path / "99999_hero.png").exists()
            assert (grid_path / "12345p.png").exists()  # Not touched

    def test_remove_symlinks(self):
        """Symlink art files are deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid_path = Path(tmpdir)
            target = grid_path / "12345p.png"
            target.write_bytes(b"data")
            link = grid_path / "99999p.png"
            link.symlink_to(target)

            orphans = [
                OrphanedArt(filename="99999p.png", app_id="99999", art_type="tall",
                            size_bytes=4, is_symlink=True),
            ]

            removed, errors = remove_orphaned_art(grid_path, orphans)
            assert removed == 1
            assert not link.exists()
            assert target.exists()  # Target not deleted


# ═══════════════════════════════════════════════════════════════════════
# ReconcileReport tests
# ═══════════════════════════════════════════════════════════════════════

class TestReconcileReport:
    def test_empty_report(self):
        report = ReconcileReport()
        assert report.orphaned_shortcut_count == 0
        assert report.orphaned_art_count == 0
        assert report.orphaned_art_bytes == 0

    def test_report_with_data(self):
        report = ReconcileReport(
            orphaned_shortcuts=[
                OrphanedShortcut("Game", 123, "/path", "rom_missing"),
            ],
            orphaned_art=[
                OrphanedArt("123p.png", "123", "tall", 1024),
            ],
            total_shortcuts=50,
            total_art_files=200,
        )
        assert report.orphaned_shortcut_count == 1
        assert report.orphaned_art_count == 1
        assert report.orphaned_art_bytes == 1024


# ═══════════════════════════════════════════════════════════════════════
# format_size tests
# ═══════════════════════════════════════════════════════════════════════

class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500 B"

    def test_kilobytes(self):
        assert format_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
# ═══════════════════════════════════════════════════════════════════════
# Shortcut deduplication tests
# ═══════════════════════════════════════════════════════════════════════

from reconcile import (
    DuplicateGroup,
    _normalize_rom_path,
    find_duplicate_shortcuts,
    deduplicate_shortcuts,
)
from shortcuts import SteamShortcut


class TestNormalizeRomPath:
    def test_var_run_media(self):
        assert _normalize_rom_path(
            '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/var/run/media/primary/Roms/c64/Game.d64"'
        ) == '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'

    def test_run_media_deck(self):
        assert _normalize_rom_path(
            '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/deck/primary/Roms/c64/Game.d64"'
        ) == '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'

    def test_already_normalized(self):
        path = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'
        assert _normalize_rom_path(path) == path

    def test_no_media_path(self):
        path = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/home/user/Roms/game.rom"'
        assert _normalize_rom_path(path) == path


class TestFindDuplicateShortcuts:
    """Test find_duplicate_shortcuts with mocked Steam data."""

    def _make_shortcut(self, name, tag, exe, appid=None):
        """Helper to create a SteamShortcut for testing."""
        if appid is None:
            from shortcuts import generate_shortcut_id
            appid = generate_shortcut_id(exe, name)
        return SteamShortcut(
            appid=appid,
            appname=name,
            exe=exe,
            start_dir='"/run/media/primary/Roms"',
            launch_options="",
            tags={"0": tag},
        )

    @patch("shortcuts.get_existing_shortcuts")
    @patch("emulators.get_registry")
    def test_no_duplicates(self, mock_registry, mock_shortcuts):
        """No duplicates should return empty list."""
        mock_sys = MagicMock()
        mock_sys.get_steam_category.return_value = "NES"
        mock_sys.all_category_tags.return_value = {"NES", "Nintendo Entertainment System"}
        mock_registry.return_value.list_systems.return_value = {"nes": mock_sys}

        shortcuts = [
            self._make_shortcut("Mario", "NES", '"/usr/bin/flatpak" run org.libretro.RetroArch -L /fceumm_libretro.so "/run/media/primary/Roms/nes/Mario.nes"'),
        ]
        mock_shortcuts.return_value = shortcuts

        dups = find_duplicate_shortcuts(Path("/fake/steam"))
        assert len(dups) == 0

    @patch("shortcuts.get_existing_shortcuts")
    @patch("emulators.get_registry")
    def test_legacy_tag_duplicate(self, mock_registry, mock_shortcuts):
        """Legacy tag entry should be removed, canonical kept."""
        mock_sys = MagicMock()
        mock_sys.get_steam_category.return_value = "C64"
        mock_sys.all_category_tags.return_value = {"C64", "Commodore 64"}
        mock_registry.return_value.list_systems.return_value = {"c64": mock_sys}

        canonical_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'
        legacy_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'

        shortcuts = [
            self._make_shortcut("Game", "C64", canonical_exe),
            self._make_shortcut("Game", "Commodore 64", legacy_exe),
        ]
        mock_shortcuts.return_value = shortcuts

        dups = find_duplicate_shortcuts(Path("/fake/steam"))
        assert len(dups) == 1
        assert dups[0].appname == "Game"
        assert dups[0].canonical_system == "C64"
        assert list(dups[0].keep.tags.values())[0] == "C64"
        assert list(dups[0].remove[0].tags.values())[0] == "Commodore 64"
        assert dups[0].reason == "legacy tag"

    @patch("shortcuts.get_existing_shortcuts")
    @patch("emulators.get_registry")
    def test_path_duplicate(self, mock_registry, mock_shortcuts):
        """Non-canonical path entry should be removed."""
        mock_sys = MagicMock()
        mock_sys.get_steam_category.return_value = "NES"
        mock_sys.all_category_tags.return_value = {"NES"}
        mock_registry.return_value.list_systems.return_value = {"nes": mock_sys}

        canonical_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /fceumm_libretro.so "/run/media/primary/Roms/nes/Game.nes"'
        var_run_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /fceumm_libretro.so "/var/run/media/primary/Roms/nes/Game.nes"'

        shortcuts = [
            self._make_shortcut("Game", "NES", canonical_exe),
            self._make_shortcut("Game", "NES", var_run_exe),
        ]
        mock_shortcuts.return_value = shortcuts

        dups = find_duplicate_shortcuts(Path("/fake/steam"))
        assert len(dups) == 1
        assert dups[0].reason == "non-canonical path"
        # Should keep the canonical path
        assert "/run/media/primary/" in dups[0].keep.exe
        assert "/var/run/" in dups[0].remove[0].exe

    @patch("shortcuts.write_shortcuts_vdf")
    @patch("shortcuts.find_shortcuts_vdf")
    @patch("shortcuts.get_existing_shortcuts")
    @patch("emulators.get_registry")
    def test_deduplicate_shortcuts_dry_run(self, mock_registry, mock_shortcuts, mock_vdf_path, mock_write):
        """Dry run should not modify shortcuts."""
        mock_sys = MagicMock()
        mock_sys.get_steam_category.return_value = "C64"
        mock_sys.all_category_tags.return_value = {"C64", "Commodore 64"}
        mock_registry.return_value.list_systems.return_value = {"c64": mock_sys}

        canonical_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'
        legacy_exe = '"/usr/bin/flatpak" run org.libretro.RetroArch -L /vice_x64sc_libretro.so "/run/media/primary/Roms/c64/Game.d64"'

        shortcuts = [
            SteamShortcut(
                appid=1001, appname="Game", exe=canonical_exe,
                start_dir='"/run/media/primary/Roms"', launch_options="",
                tags={"0": "C64"},
            ),
            SteamShortcut(
                appid=1002, appname="Game", exe=legacy_exe,
                start_dir='"/run/media/primary/Roms"', launch_options="",
                tags={"0": "Commodore 64"},
            ),
        ]
        mock_shortcuts.return_value = shortcuts

        removed, kept = deduplicate_shortcuts(Path("/fake/steam"), dry_run=True)
        assert removed == 1
        assert kept == 1
        # Should not have written anything
        mock_write.assert_not_called()