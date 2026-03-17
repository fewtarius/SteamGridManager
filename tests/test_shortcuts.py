#!/usr/bin/env python3
"""Tests for shortcuts.py — VDF read/write correctness."""

import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shortcuts import (
    SteamShortcut,
    read_shortcuts_vdf,
    write_shortcuts_vdf,
    generate_app_id,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_shortcut(**kwargs) -> SteamShortcut:
    defaults = dict(
        appid=12345,
        appname="Test Game",
        exe='"/usr/bin/retroarch"',
        start_dir='"/usr/bin"',
        icon="",
        shortcut_path="",
        launch_options="-L core.so /rom/game.sfc",
        is_hidden=0,
        allow_desktop_config=1,
        allow_overlay=1,
        openvr=0,
        devkit=0,
        devkit_game_id="",
        devkit_override_app_id=0,
        last_play_time=0,
        flatpak_appid="",
        tags={},
    )
    defaults.update(kwargs)
    return SteamShortcut(**defaults)


def roundtrip(shortcuts: list) -> list:
    """Write shortcuts to a temp file and read them back."""
    with tempfile.NamedTemporaryFile(suffix=".vdf", delete=False) as f:
        path = Path(f.name)
    try:
        write_shortcuts_vdf(path, shortcuts)
        return read_shortcuts_vdf(path)
    finally:
        path.unlink(missing_ok=True)
        bak = path.with_suffix(".vdf.bak")
        bak.unlink(missing_ok=True)


# ── Terminator tests (the critical bug) ──────────────────────────────────────

def test_vdf_ends_with_four_end_bytes():
    """Written VDF must end with exactly 4 x 0x08 bytes (Steam requirement)."""
    sc = make_shortcut()
    with tempfile.NamedTemporaryFile(suffix=".vdf", delete=False) as f:
        path = Path(f.name)
    try:
        write_shortcuts_vdf(path, [sc])
        data = path.read_bytes()
        trailing = len(data) - len(data.rstrip(b"\x08"))
        assert trailing == 4, (
            f"Expected 4 trailing 0x08 bytes, got {trailing}. "
            "Steam will silently discard the file if this is wrong."
        )
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix(".vdf.bak").unlink(missing_ok=True)


def test_vdf_starts_with_shortcuts_header():
    """Written VDF must start with \\x00shortcuts\\x00."""
    sc = make_shortcut()
    with tempfile.NamedTemporaryFile(suffix=".vdf", delete=False) as f:
        path = Path(f.name)
    try:
        write_shortcuts_vdf(path, [sc])
        data = path.read_bytes()
        assert data[:11] == b"\x00shortcuts\x00", (
            f"Unexpected header: {data[:12]!r}"
        )
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix(".vdf.bak").unlink(missing_ok=True)


# ── Round-trip tests ─────────────────────────────────────────────────────────

def test_roundtrip_single():
    """A single shortcut survives write → read intact."""
    original = make_shortcut(appname="Super Mario World", launch_options="-L snes.so /rom/smw.sfc")
    result = roundtrip([original])
    assert len(result) == 1
    assert result[0].appname == "Super Mario World"
    assert result[0].launch_options == "-L snes.so /rom/smw.sfc"


def test_roundtrip_many():
    """Many shortcuts survive write → read with correct count."""
    shortcuts = [make_shortcut(appname=f"Game {i}", appid=i) for i in range(100)]
    result = roundtrip(shortcuts)
    assert len(result) == 100
    assert result[0].appname == "Game 0"
    assert result[99].appname == "Game 99"


def test_roundtrip_unicode():
    """Unicode titles and paths survive the round-trip."""
    original = make_shortcut(
        appname="Castlevania: 悪魔城ドラキュラ",
        launch_options="-L snes.so /roms/日本語/game.sfc",
    )
    result = roundtrip([original])
    assert result[0].appname == "Castlevania: 悪魔城ドラキュラ"
    assert "日本語" in result[0].launch_options


def test_roundtrip_empty_list():
    """An empty shortcut list writes and reads back as empty."""
    result = roundtrip([])
    assert result == []


def test_roundtrip_tags():
    """Tags survive the round-trip."""
    original = make_shortcut(tags={0: "Favorites", 1: "SNES"})
    result = roundtrip([original])
    # Tag keys are stored/read back as strings
    tags = result[0].tags
    assert "Favorites" in tags.values()
    assert "SNES" in tags.values()


def test_roundtrip_heroic_shortcut():
    """Heroic-style flatpak shortcuts survive the round-trip."""
    original = make_shortcut(
        appname="9 Years of Shadows",
        exe='"flatpak"',
        start_dir='"/home/deck"',
        launch_options='run com.heroicgameslauncher.hgl --no-gui --no-sandbox "heroic://launch?appName=abc123&runner=gog"',
        flatpak_appid="",
    )
    result = roundtrip([original])
    assert result[0].appname == "9 Years of Shadows"
    assert "heroicgameslauncher" in result[0].launch_options


def test_roundtrip_special_chars_in_path():
    """Paths with spaces, quotes, and apostrophes survive."""
    original = make_shortcut(
        exe='"/usr/bin/flatpak" run info.cemu.Cemu -f -g "/run/media/deck/primary/Roms/wiiu/Yoshi\'s Woolly World (US).wua"',
    )
    result = roundtrip([original])
    assert "Yoshi" in result[0].exe


# ── App ID generation ────────────────────────────────────────────────────────

def test_app_id_deterministic():
    """Same exe+name always produces the same app ID."""
    id1 = generate_app_id("/usr/bin/retroarch", "Super Mario World")
    id2 = generate_app_id("/usr/bin/retroarch", "Super Mario World")
    assert id1 == id2


def test_app_id_different_for_different_names():
    """Different names produce different app IDs."""
    id1 = generate_app_id("/usr/bin/retroarch", "Game A")
    id2 = generate_app_id("/usr/bin/retroarch", "Game B")
    assert id1 != id2


def test_app_id_is_large_number():
    """Generated ID should be a large non-Steam shortcut ID (> 2^32)."""
    app_id = generate_app_id("/usr/bin/retroarch", "Super Mario World")
    # generate_app_id returns a string; convert to int for comparison
    assert int(app_id) > 0x80000000, f"App ID {app_id} is unexpectedly small"
