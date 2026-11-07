#!/usr/bin/env python3
"""Tests guarding the ScreenScraper platform identifiers in the defaults.

ScreenScraper assigns each platform a fixed systemeid. Several were originally
filled in by enumeration rather than lookup, which produced collisions and made
every hash lookup for those systems fail with a 404: the ROM hash is correct
but is being searched on the wrong console. These tests pin the verified values
and enforce the invariants that would have caught the mistake.
"""

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import emulators


DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "emulators.json"


# Values confirmed against ScreenScraper's systemesListe.php.
VERIFIED_IDS = {
    "amiga": 64,
    "atari2600": 26,
    "atari5200": 40,
    "atari7800": 41,
    "atarilynx": 28,
    "c64": 66,
    "coleco": 48,
    "dreamcast": 23,
    "gamecube": 13,
    "infocom": 215,
    "intellivision": 115,
    "neogeo": 142,
    "pc": 135,
    "pcengine": 31,
    "ps2": 58,
    "psp": 61,
    "psvita": 62,
    "psx": 57,
    "saturn": 22,
    "segacd": 20,
    "vic20": 73,
    "wii": 16,
    "wiiu": 18,
    "xbox": 32,
}

# ScreenScraper has no generic Arcade entry; arcade releases are catalogued
# per board (CPS1/2/3, Cave, Atomiswave and so on), so lookups run unscoped.
UNSCOPED_SYSTEMS = {"arcade"}


@pytest.fixture(scope="module")
def defaults():
    """The shipped default configuration."""
    return json.loads(DEFAULTS_PATH.read_text())


@pytest.fixture(scope="module")
def systems(defaults):
    """The systems section."""
    return defaults["systems"]


class TestVerifiedIds:
    """Corrected identifiers must not drift back."""

    @pytest.mark.parametrize("slug,expected", sorted(VERIFIED_IDS.items()))
    def test_system_has_verified_id(self, systems, slug, expected):
        assert systems[slug]["screenscraper_id"] == expected

    def test_ps2_is_not_3ds(self, systems):
        """The regression that started this: PS2 was mapped to Nintendo 3DS."""
        assert systems["ps2"]["screenscraper_id"] != 17


class TestIdInvariants:
    """Structural checks that catch enumeration mistakes."""

    def test_no_two_systems_share_an_id(self, systems):
        """A shared id means at least one of the pair is certainly wrong."""
        seen = {}
        for slug, definition in systems.items():
            identifier = definition.get("screenscraper_id", 0)
            if not identifier or slug in UNSCOPED_SYSTEMS:
                continue
            assert identifier not in seen, (
                f"{slug} and {seen[identifier]} both claim screenscraper_id "
                f"{identifier}"
            )
            seen[identifier] = slug

    def test_zero_only_for_unscoped(self, systems):
        """An absent id disables platform scoping, so it must be deliberate."""
        for slug, definition in systems.items():
            if definition.get("screenscraper_id", 0) == 0:
                assert slug in UNSCOPED_SYSTEMS, (
                    f"{slug} has no screenscraper id; lookups would run "
                    f"unscoped across every platform"
                )

    def test_ids_are_positive_integers(self, systems):
        for slug, definition in systems.items():
            identifier = definition.get("screenscraper_id", 0)
            assert isinstance(identifier, int)
            assert identifier >= 0, f"{slug} has a negative screenscraper_id"


class TestChdCoverage:
    """Disc-based systems must accept CHD dumps."""

    # Systems whose media is optical and where CHD is the standard compression.
    DISC_SYSTEMS = {
        "arcade", "gamecube", "ps2", "psp", "psx", "saturn", "wii", "wiiu", "xbox",
    }

    @pytest.mark.parametrize("slug", sorted(DISC_SYSTEMS))
    def test_disc_system_accepts_chd(self, systems, slug):
        assert ".chd" in systems[slug]["extensions"], (
            f"{slug} is disc-based but rejects .chd dumps"
        )


class TestRegistryAgreement:
    """The registry must expose the same values the file contains."""

    def test_registry_matches_defaults(self, systems):
        emulators.reset_registry()
        registry = emulators.get_registry()
        for slug, expected in VERIFIED_IDS.items():
            plugin = registry.get_system(slug)
            assert plugin is not None, f"{slug} missing from registry"
            assert plugin.screenscraper_id == expected

    def test_every_default_system_is_registered(self, systems):
        emulators.reset_registry()
        registry = emulators.get_registry()
        assert set(systems) <= set(registry.list_systems())
