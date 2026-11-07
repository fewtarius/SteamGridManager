#!/usr/bin/env python3
"""Tests for flatpak sandbox permission handling in permissions.py."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import permissions as P


HOME = Path("/home/deck")
ROMS = Path("/home/deck/Roms/ps2")


class TestContextParsing:
    """flatpak emits a keyfile; only [Context] filesystems matter."""

    def test_parses_semicolon_list(self):
        text = "[Context]\nshared=network;\nfilesystems=/a;home;xdg-config/x:ro;\n"
        assert P._parse_context_filesystems(text) == ["/a", "home", "xdg-config/x:ro"]

    def test_ignores_other_sections(self):
        text = "[Instance]\nfilesystems=/nope;\n[Context]\nfilesystems=/yes;\n"
        assert P._parse_context_filesystems(text) == ["/yes"]

    def test_empty_input(self):
        assert P._parse_context_filesystems("") == []

    def test_missing_filesystems_key(self):
        assert P._parse_context_filesystems("[Context]\nshared=network;\n") == []


class TestCoverage:
    """Deciding whether an app can already read and write a path."""

    def test_host_writes(self):
        assert P.covers_path_rw(["host"], ROMS, HOME)

    def test_host_read_only_is_not_enough(self):
        assert not P.covers_path_rw(["host:ro"], ROMS, HOME)

    def test_home_writes(self):
        assert P.covers_path_rw(["home"], ROMS, HOME)

    def test_home_read_only_is_not_enough(self):
        """PCSX2's default: it can read the ISO but cannot write its cache."""
        assert not P.covers_path_rw(["home:ro"], ROMS, HOME)

    def test_explicit_parent_dir(self):
        assert P.covers_path_rw(["/home/deck/Roms"], ROMS, HOME)

    def test_explicit_exact_dir(self):
        assert P.covers_path_rw(["/home/deck/Roms/ps2"], ROMS, HOME)

    def test_unrelated_dir_does_not_count(self):
        assert not P.covers_path_rw(["/home/deck/Other"], ROMS, HOME)

    def test_child_dir_does_not_cover_parent(self):
        assert not P.covers_path_rw(["/home/deck/Roms/ps2/games"], ROMS, HOME)

    def test_read_write_suffix_counts(self):
        assert P.covers_path_rw(["/home/deck/Roms:rw"], ROMS, HOME)

    def test_negation_revokes_broader_grant(self):
        assert not P.covers_path_rw(["home", "!home"], ROMS, HOME)

    def test_negation_of_something_else_is_ignored(self):
        assert P.covers_path_rw(["home", "!/tmp"], ROMS, HOME)

    def test_xdg_aliases_are_not_resolved(self):
        assert not P.covers_path_rw(["xdg-download"], ROMS, HOME)

    def test_read_only_entry_does_not_block_explicit_grant(self):
        assert P.covers_path_rw(["home:ro", "/home/deck/Roms"], ROMS, HOME)


class TestGrantPath:
    """Applying a grant, including the dry-run and failure paths."""

    def test_not_installed_is_skipped(self):
        grant = P.grant_path("com.example.App", ROMS, installed={"other.App"})
        assert grant.action == P.NOT_INSTALLED

    def test_already_covered_makes_no_change(self):
        with patch.object(P, "effective_filesystems", return_value=["home"]):
            grant = P.grant_path("a.App", ROMS, installed={"a.App"})
        assert grant.action == P.ALREADY_OK
        assert not grant.changed

    def test_dry_run_reports_without_applying(self):
        with patch.object(P, "effective_filesystems", return_value=["home:ro"]), \
             patch.object(P.subprocess, "run") as run:
            grant = P.grant_path("a.App", ROMS, dry_run=True, installed={"a.App"})

        assert grant.action == P.WOULD_GRANT
        assert grant.changed
        run.assert_not_called()

    def test_grant_invokes_override(self):
        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(P, "effective_filesystems", return_value=["home:ro"]), \
             patch.object(P.subprocess, "run", return_value=ok) as run:
            grant = P.grant_path("a.App", ROMS, installed={"a.App"})

        assert grant.action == P.GRANTED
        cmd = run.call_args[0][0]
        assert cmd[0] == "flatpak"
        assert "override" in cmd
        assert "--user" in cmd
        assert f"--filesystem={ROMS}" in cmd
        assert cmd[-1] == "a.App"

    def test_failure_is_reported_with_detail(self):
        bad = MagicMock(returncode=1, stdout="", stderr="no permission")
        with patch.object(P, "effective_filesystems", return_value=["home:ro"]), \
             patch.object(P.subprocess, "run", return_value=bad):
            grant = P.grant_path("a.App", ROMS, installed={"a.App"})

        assert grant.action == P.FAILED
        assert grant.changed
        assert "no permission" in grant.detail

    def test_subprocess_error_is_reported(self):
        with patch.object(P, "effective_filesystems", return_value=["home:ro"]), \
             patch.object(P.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("flatpak", 3)):
            grant = P.grant_path("a.App", ROMS, installed={"a.App"})

        assert grant.action == P.FAILED


class TestEnsureRomAccess:
    """Bulk entry point used by import and the audit command."""

    def test_no_apps_is_a_no_op(self):
        assert P.ensure_rom_access([], [ROMS]) == []

    def test_no_roots_is_a_no_op(self):
        assert P.ensure_rom_access(["a.App"], []) == []

    def test_missing_flatpak_is_reported(self):
        with patch.object(P, "flatpak_available", return_value=False):
            grants = P.ensure_rom_access(["a.App", "b.App"], [ROMS])
        assert len(grants) == 2
        assert all(g.action == P.UNAVAILABLE for g in grants)

    def test_covers_every_app_path_pair(self):
        with patch.object(P, "flatpak_available", return_value=True), \
             patch.object(P, "installed_apps", return_value={"a.App", "b.App"}), \
             patch.object(P, "grant_path") as grant:
            grant.side_effect = lambda app, root, dry_run=False, installed=None: \
                P.PermissionGrant(app, str(root), P.ALREADY_OK)
            grants = P.ensure_rom_access(["a.App", "b.App"], [ROMS, HOME])

        assert len(grants) == 4

    def test_duplicate_apps_collapse(self):
        with patch.object(P, "flatpak_available", return_value=True), \
             patch.object(P, "installed_apps", return_value={"a.App"}), \
             patch.object(P, "grant_path") as grant:
            grant.side_effect = lambda app, root, dry_run=False, installed=None: \
                P.PermissionGrant(app, str(root), P.ALREADY_OK)
            grants = P.ensure_rom_access(["a.App", "a.App"], [ROMS])

        assert len(grants) == 1


class TestConfiguredApps:
    """Collecting flatpak ids from the emulator registry."""

    class _Plugin:
        def __init__(self, app_id, name):
            self.flatpak_id = app_id
            self.display_name = name

    class _Registry:
        def __init__(self, plugins):
            self._plugins = plugins

        def list_emulators(self):
            return self._plugins

    def test_maps_ids_to_names(self):
        registry = self._Registry({
            "pcsx2": self._Plugin("net.pcsx2.PCSX2", "PCSX2"),
        })
        assert P.configured_flatpak_apps(registry) == {"net.pcsx2.PCSX2": "PCSX2"}

    def test_non_flatpak_emulators_are_skipped(self):
        registry = self._Registry({
            "native": self._Plugin(None, "Native Tool"),
        })
        assert P.configured_flatpak_apps(registry) == {}

    def test_shared_app_id_is_listed_once(self):
        registry = self._Registry({
            "a": self._Plugin("org.libretro.RetroArch", "RetroArch"),
            "b": self._Plugin("org.libretro.RetroArch", "Another Core"),
        })
        apps = P.configured_flatpak_apps(registry)
        assert list(apps) == ["org.libretro.RetroArch"]
