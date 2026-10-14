#!/usr/bin/env python3
"""Tests for steam.py path discovery and grid statistics."""

import tempfile
from pathlib import Path

from steam import get_grid_stats


class TestGetGridStatsClassification:
    """Regression coverage for grid folder image classification.

    Steam grid naming convention (authoritative, see reconcile.classify_art_file):
      - {appid}.png   -> wide capsule  (920x430, horizontal banner)
      - {appid}p.png  -> tall capsule  (600x900, vertical poster)
      - {appid}_hero.png / _logo.png / _icon.png
    """

    def _make_grid(self, names):
        tmp = tempfile.mkdtemp()
        for n in names:
            (Path(tmp) / n).write_bytes(b"x" * 100)
        return Path(tmp)

    def test_tall_and_wide_not_swapped(self):
        """Regression: tall must be the 'p' files, wide the bare files.

        Two tall + one wide is deliberately asymmetric so that a tall<->wide
        swap (the original bug) produces counts 1 tall / 2 wide and fails
        these assertions.
        """
        grid = self._make_grid([
            "100p.png",   # tall
            "200p.png",   # tall
            "300.png",    # wide
        ])
        stats = get_grid_stats(grid)
        assert stats["by_type"]["tall"] == 2, f"tall={stats['by_type']['tall']}"
        assert stats["by_type"]["wide"] == 1, f"wide={stats['by_type']['wide']}"
        assert stats["by_type"]["other"] == 0

    def test_hero_logo_icon(self):
        grid = self._make_grid([
            "200_hero.png", "200_logo.png", "200_icon.png",
        ])
        stats = get_grid_stats(grid)
        assert stats["by_type"]["hero"] == 1
        assert stats["by_type"]["logo"] == 1
        assert stats["by_type"]["icon"] == 1

    def test_non_numeric_prefixed_is_other(self):
        grid = self._make_grid(["manifest.json", "thumb.jpg"])
        stats = get_grid_stats(grid)
        assert stats["by_type"]["other"] == 2

    def test_total_and_symlink_accounting(self):
        grid = self._make_grid(["100.png", "100p.png"])
        stats = get_grid_stats(grid)
        assert stats["total_files"] == 2
        assert stats["real_files"] == 2
        assert stats["symlinks"] == 0
