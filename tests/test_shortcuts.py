#!/usr/bin/env python3
"""Tests for shortcuts.py — VDF read/write correctness."""

import json
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
    _read_localconfig_collections,
    _write_localconfig_collections,
    _get_collection_name_from_localconfig,
    _update_localconfig_collection,
    _unescape_vdf_json,
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


# ── localconfig.vdf user-collections helpers ──────────────────────────────────
# Regression coverage for the read/unescape/write/update helpers that were
# previously inlined (and partially broken: _get/_update could not parse
# VDF-escaped JSON, and _update wiped unrelated collections).

def _make_localconfig_vdf(collections: dict) -> Path:
    """Write a temp localconfig.vdf containing a user-collections entry."""
    BQ = chr(92)
    q = chr(34)
    tab = chr(9)
    nl = chr(10)
    raw_json = json.dumps(collections, separators=(",", ":"))
    escaped = raw_json.replace(BQ, BQ + BQ).replace(q, BQ + q)
    line = tab + tab + q + "user-collections" + q + tab + tab + q + escaped + q + nl
    content = (
        "{" + nl
        + tab + q + "UserLocalConfigStore" + q + nl
        + tab + "{" + nl
        + tab + tab + q + "config" + q + nl
        + tab + tab + "{" + nl
        + line
        + tab + tab + "}" + nl
        + tab + "}" + nl
        + "}" + nl
    )
    f = tempfile.NamedTemporaryFile(suffix=".vdf", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


def test_read_localconfig_parses_vdf_escaped_json():
    """_read_localconfig_collections must unescape and parse VDF-embedded JSON."""
    colls = {
        "collA": {"id": "collA", "added": [1], "removed": [], "name": "Col A"},
        "collB": {"id": "collB", "added": [2, 3], "removed": [], "name": "Col B"},
    }
    path = _make_localconfig_vdf(colls)
    try:
        parsed = _read_localconfig_collections(path)
        assert parsed == colls, f"expected {colls}, got {parsed}"
    finally:
        path.unlink(missing_ok=True)


def test_read_localconfig_returns_none_when_key_absent():
    """A localconfig without user-collections yields None (not {})."""
    f = tempfile.NamedTemporaryFile(suffix=".vdf", delete=False, mode="w", encoding="utf-8")
    f.write("{\n\t" + chr(34) + "other" + chr(34) + "\n}\n")
    f.close()
    path = Path(f.name)
    try:
        assert _read_localconfig_collections(path) is None
    finally:
        path.unlink(missing_ok=True)


def test_get_collection_name_returns_name():
    """_get_collection_name_from_localconfig must return the stored name."""
    path = _make_localconfig_vdf({"colA": {"id": "colA", "added": [1], "removed": [], "name": "Col A"}})
    try:
        assert _get_collection_name_from_localconfig(path, "colA") == "Col A"
        assert _get_collection_name_from_localconfig(path, "missing") == ""
    finally:
        path.unlink(missing_ok=True)


def test_update_preserves_other_collections():
    """_update must not wipe collections other than the one being updated."""
    colls = {
        "colA": {"id": "colA", "added": [1], "removed": [], "name": "Col A"},
        "colB": {"id": "colB", "added": [2], "removed": [], "name": "Col B"},
        "colC": {"id": "colC", "added": [], "removed": [], "name": "Col C"},
    }
    path = _make_localconfig_vdf(colls)
    try:
        _update_localconfig_collection(path, "colC", {"id": "colC", "added": [999], "removed": [], "name": "Col C updated"})
        after = _read_localconfig_collections(path)
        assert set(after.keys()) == {"colA", "colB", "colC"}, f"keys wiped: {sorted(after.keys())}"
        assert after["colC"]["added"] == [999]
    finally:
        path.unlink(missing_ok=True)


def test_unescape_roundtrip_stable():
    """Unescape then re-escape must reproduce the original escaped string."""
    raw = json.dumps({"x": {"name": "A", "added": [1]}}, separators=(",", ":"))
    BQ = chr(92)
    q = chr(34)
    vdf = raw.replace(BQ, BQ + BQ).replace(q, BQ + q)
    obj = json.loads(_unescape_vdf_json(vdf))
    assert obj == {"x": {"name": "A", "added": [1]}}
    reescaped = json.dumps(obj, separators=(",", ":")).replace(BQ, BQ + BQ).replace(q, BQ + q)
    assert reescaped == vdf


def test_write_then_read_is_idempotent():
    """Writing a parsed dict back and re-reading must yield the same dict."""
    colls = {"colA": {"id": "colA", "added": [7], "removed": [], "name": "Col A"}}
    path = _make_localconfig_vdf(colls)
    try:
        _write_localconfig_collections(path, colls)
        assert _read_localconfig_collections(path) == colls
    finally:
        path.unlink(missing_ok=True)


def test_write_read_roundtrip_with_embedded_quotes_and_backslashes():
    """Production _write must produce VDE-escaping that _read can invert.

    This fails on naive quote-only escaping (which corrupts values that
    contain quotes or backslashes) and guards the VDF escape/unescape parity.
    """
    name = 'He said "hi" \\ backslash'
    colls = {"colA": {"id": "colA", "added": [1], "removed": [], "name": name}}
    path = _make_localconfig_vdf(colls)
    try:
        _write_localconfig_collections(path, colls)
        parsed = _read_localconfig_collections(path)
        assert parsed == colls, f"round-trip mismatch: {parsed!r}"
    finally:
        path.unlink(missing_ok=True)
