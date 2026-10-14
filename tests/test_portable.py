#!/usr/bin/env python3
"""Tests for portable.py bundle export/import suffix handling.

Regression coverage for the Steam grid naming convention:
  {appid}.png  = wide capsule  (landscape)
  {appid}p.png = tall capsule  (portrait)
  {appid}_hero.png / _logo.png / _icon.png
"""

import json

from portable import export_bundle, import_bundle
from shortcuts import SteamShortcut


def _make_shortcut(appid=100, name="Test Game", system="NES"):
    return SteamShortcut(
        appid=appid,
        appname=name,
        exe="/bin/retroarch",
        start_dir="/roms",
        launch_options="",
        tags={"Category": system},
    )


class TestExportClassification:
    def test_tall_and_wide_not_swapped(self, tmp_path):
        """Regression: bare suffix = wide, 'p' suffix = tall."""
        grid = tmp_path / "grid"
        grid.mkdir()
        (grid / "100.png").write_bytes(b"wide")
        (grid / "100p.png").write_bytes(b"tall")
        (grid / "100_hero.png").write_bytes(b"hero")

        out = tmp_path / "out"
        out.mkdir()
        bundle = export_bundle(
            grid, [_make_shortcut()], out, steam_user_id="1", device_name="dev"
        )
        manifest = json.loads((bundle / "manifest.json").read_text())
        game = manifest["games"][0]
        assert game["images"]["wide"] == "100.png"
        assert game["images"]["tall"] == "100p.png"
        assert game["images"]["hero"] == "100_hero.png"


class TestImportFilename:
    def test_import_writes_correct_filenames(self, tmp_path):
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        images = bundle / "images"
        images.mkdir()
        (images / "100.png").write_bytes(b"wide")
        (images / "100p.png").write_bytes(b"tall")

        manifest = {
            "version": 2,
            "created": "x",
            "source_device": "d",
            "steam_user_id": "1",
            "total_games": 1,
            "total_images": 2,
            "total_size_bytes": 2,
            "systems": {},
            "games": [
                {
                    "app_id": "100",
                    "title": "Test",
                    "system": "NES",
                    "exe": "",
                    "launch_options": "",
                    "images": {"wide": "100.png", "tall": "100p.png"},
                }
            ],
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest))

        grid = tmp_path / "grid"
        grid.mkdir()
        imported, skipped, errors = import_bundle(bundle, grid, mode="merge")
        assert errors == 0
        assert (grid / "100.png").exists()   # wide
        assert (grid / "100p.png").exists()  # tall
        assert imported == 2

    def test_round_trip_preserves_filenames(self, tmp_path):
        grid = tmp_path / "grid"
        grid.mkdir()
        (grid / "100.png").write_bytes(b"wide")
        (grid / "100p.png").write_bytes(b"tall")
        (grid / "100_hero.png").write_bytes(b"hero")

        out = tmp_path / "out"
        out.mkdir()
        bundle = export_bundle(
            grid, [_make_shortcut()], out, steam_user_id="1", device_name="dev"
        )

        grid2 = tmp_path / "grid2"
        grid2.mkdir()
        import_bundle(bundle, grid2, mode="merge")
        assert (grid2 / "100.png").exists()
        assert (grid2 / "100p.png").exists()
        assert (grid2 / "100_hero.png").exists()
