#!/usr/bin/env python3
"""Tests for the defaults/user-config merge policy in emulators.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import emulators


MINIMAL_DEFAULTS = {
    "version": 3,
    "_comment": "shipped defaults",
    "emulators": {
        "dolphin": {
            "display_name": "Dolphin",
            "type": "standalone",
            "flatpak_id": "org.DolphinEmu.dolphin-emu",
        },
    },
    "retroarch_cores": {},
    "systems": {
        "ps2": {
            "fullname": "PlayStation 2",
            "manufacturer": "Sony",
            "extensions": [".iso", ".chd"],
            "screenscraper_id": 58,
            "thegamesdb_id": "9",
            "default_emulator": "pcsx2",
            "steam_category": "PS2",
        },
        "n64": {
            "fullname": "Nintendo 64",
            "manufacturer": "Nintendo",
            "extensions": [".z64"],
            "screenscraper_id": 14,
            "default_emulator": "mupen64plus",
        },
    },
}


@pytest.fixture
def config_env(tmp_path):
    """Isolated defaults + user config directories."""
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    defaults_file = defaults_dir / "emulators.json"
    defaults_file.write_text(json.dumps(MINIMAL_DEFAULTS))

    user_dir = tmp_path / "config"
    user_dir.mkdir()
    user_file = user_dir / "emulators.json"

    with patch.object(emulators, "DEFAULT_CONFIG", defaults_file), \
         patch.object(emulators, "CONFIG_DIR", user_dir), \
         patch.object(emulators, "EMULATORS_CONFIG", user_file):
        emulators.reset_registry()
        yield {"defaults": defaults_file, "user": user_file, "dir": user_dir}
        emulators.reset_registry()


def write_user(path, payload):
    """Write a user emulators.json."""
    path.write_text(json.dumps(payload))


class TestCodeOwnedKeys:
    """Upstream identifiers and hardware facts must come from defaults."""

    def test_stale_user_id_is_ignored(self, config_env):
        """An outdated screenscraper_id in the user file cannot win."""
        write_user(config_env["user"], {
            "version": 1,
            "systems": {"ps2": {"screenscraper_id": 17}},
        })
        registry = emulators.get_registry()
        assert registry.get_system("ps2").screenscraper_id == 58

    def test_stale_extensions_are_ignored(self, config_env):
        """Extensions the defaults later changed must not be pinned by users."""
        write_user(config_env["user"], {
            "systems": {"ps2": {"extensions": [".iso"]}},
        })
        registry = emulators.get_registry()
        assert ".chd" in registry.get_system("ps2").extensions

    def test_user_behaviour_overrides_still_apply(self, config_env):
        """Genuine preferences remain overridable."""
        write_user(config_env["user"], {
            "systems": {"ps2": {"steam_category": "Sony PS2"}},
        })
        registry = emulators.get_registry()
        assert registry.get_system("ps2").steam_category == "Sony PS2"

    def test_custom_system_is_preserved(self, config_env):
        """A system the user added themselves survives the merge."""
        write_user(config_env["user"], {
            "systems": {"mybox": {"fullname": "My Box", "extensions": [".bin"]}},
        })
        registry = emulators.get_registry()
        assert "mybox" in registry.list_systems()
        assert registry.get_system("mybox").fullname == "My Box"


class TestSparseSave:
    """The user file should hold only what the user changed."""

    def test_identical_config_saves_empty(self, config_env):
        """A config copied verbatim from defaults prunes to nothing."""
        write_user(config_env["user"], dict(MINIMAL_DEFAULTS))
        registry = emulators.get_registry()
        sparse = registry.sparse_config()

        assert "systems" not in sparse
        assert "emulators" not in sparse
        assert sparse["version"] == 3

    def test_only_the_override_is_written(self, config_env):
        """A single changed key produces a single-key entry."""
        write_user(config_env["user"], {
            "systems": {"ps2": {"default_emulator": "my_pcsx2"}},
        })
        registry = emulators.get_registry()
        registry.save_config()

        saved = json.loads(config_env["user"].read_text())
        assert saved["systems"] == {"ps2": {"default_emulator": "my_pcsx2"}}

    def test_comment_matching_defaults_is_dropped(self, config_env):
        """A copied _comment is not worth persisting."""
        write_user(config_env["user"], {"_comment": "shipped defaults"})
        registry = emulators.get_registry()
        assert "_comment" not in registry.sparse_config()

    def test_round_trip_preserves_behaviour(self, config_env):
        """Saving sparse and reloading yields the same effective config."""
        write_user(config_env["user"], {
            "systems": {"ps2": {"steam_category": "Custom"}},
        })
        first = emulators.get_registry().get_system("ps2").steam_category

        emulators.get_registry().save_config()
        emulators.reset_registry()

        assert emulators.get_registry().get_system("ps2").steam_category == first
        assert first == "Custom"


class TestNoSeedOnFirstRun:
    """Absent user config means no customisations, not a full copy."""

    def test_missing_user_file_is_not_created(self, config_env):
        """Loading defaults must not materialise a user config."""
        assert not config_env["user"].exists()
        registry = emulators.get_registry()
        assert len(registry.list_systems()) == 2
        assert not config_env["user"].exists()

    def test_defaults_are_usable_without_user_file(self, config_env):
        """Everything still resolves with no user config at all."""
        registry = emulators.get_registry()
        assert registry.get_system("ps2").screenscraper_id == 58


class TestInitConfig:
    """init_config writes a stub, not a frozen copy of the defaults."""

    def test_stub_only_holds_version(self, config_env):
        """The initialised file carries no definitions."""
        assert emulators.init_config() is True
        saved = json.loads(config_env["user"].read_text())
        assert saved == {"version": 3}

    def test_existing_file_is_left_alone(self, config_env):
        """init_config never overwrites a real config."""
        write_user(config_env["user"], {"systems": {"ps2": {"steam_category": "X"}}})
        assert emulators.init_config() is False


class TestCorruptUserConfig:
    """A broken user file must not take the whole tool down."""

    def test_falls_back_to_defaults(self, config_env):
        """Invalid JSON falls back to defaults."""
        config_env["user"].write_text("{not json")
        registry = emulators.get_registry()
        assert registry.get_system("ps2").screenscraper_id == 58
