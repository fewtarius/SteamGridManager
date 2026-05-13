#!/usr/bin/env python3
"""Reconcile Steam shortcuts and grid art with reality.

Detects and cleans up orphaned entries:
- Shortcuts whose ROM/exe no longer exists on disk
- Grid art files whose app ID has no matching shortcut
- Empty Steam collections

This is the "housekeeping" module that keeps the Steam library
in sync with what's actually installed.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class OrphanedShortcut:
    """A shortcut whose target no longer exists."""
    appname: str
    appid: int
    exe: str
    reason: str  # "rom_missing", "exe_missing", "heroic_uninstalled"
    system_tag: str = ""  # e.g. "Atari 2600", "Heroic"


@dataclass
class OrphanedArt:
    """A grid art file with no matching shortcut."""
    filename: str
    app_id: str  # The numeric app ID prefix
    art_type: str  # "tall", "wide", "hero", "logo", "icon"
    size_bytes: int = 0
    is_symlink: bool = False


@dataclass
class ReconcileReport:
    """Full reconciliation report."""
    orphaned_shortcuts: List[OrphanedShortcut] = field(default_factory=list)
    orphaned_art: List[OrphanedArt] = field(default_factory=list)
    empty_collections: List[str] = field(default_factory=list)
    total_shortcuts: int = 0
    total_art_files: int = 0
    total_collections: int = 0

    @property
    def orphaned_art_bytes(self) -> int:
        return sum(a.size_bytes for a in self.orphaned_art)

    @property
    def orphaned_shortcut_count(self) -> int:
        return len(self.orphaned_shortcuts)

    @property
    def orphaned_art_count(self) -> int:
        return len(self.orphaned_art)


# ═══════════════════════════════════════════════════════════════════════
# Art Type Detection
# ═══════════════════════════════════════════════════════════════════════

# Regex patterns for grid image filenames
# Tall capsule: {appid}p.png  (or .jpg)
# Wide capsule: {appid}.png   (or .jpg)
# Hero:         {appid}_hero.png
# Logo:         {appid}_logo.png
# Icon:         {appid}_icon.png
_ART_PATTERNS = [
    (re.compile(r'^(\d+)_hero\.(png|jpg)$'), 'hero'),
    (re.compile(r'^(\d+)_logo\.(png|jpg)$'), 'logo'),
    (re.compile(r'^(\d+)_icon\.(png|jpg)$'), 'icon'),
    (re.compile(r'^(\d+)p\.(png|jpg)$'), 'tall'),
    (re.compile(r'^(\d+)\.(png|jpg)$'), 'wide'),
]


def classify_art_file(filename: str) -> Optional[Tuple[str, str]]:
    """Classify a grid art file by its filename.

    Args:
        filename: Just the filename (not full path).

    Returns:
        Tuple of (app_id, art_type) or None if not a recognized art file.
    """
    for pattern, art_type in _ART_PATTERNS:
        match = pattern.match(filename)
        if match:
            return match.group(1), art_type
    return None


# ═══════════════════════════════════════════════════════════════════════
# ROM Path Extraction
# ═══════════════════════════════════════════════════════════════════════

def extract_rom_path(exe: str) -> Optional[Path]:
    """Extract the ROM file path from a shortcut exe string.

    RetroArch shortcuts look like:
        "/usr/bin/flatpak" run org.libretro.RetroArch -L /core.so "/path/to/rom.ext"
    Standalone emulators look like:
        "/path/to/emulator" "/path/to/rom.ext"
    Heroic shortcuts look like:
        "/home/deck/.local/share/heroic/tools/..." (no ROM path)

    Args:
        exe: The exe field from a SteamShortcut.

    Returns:
        Path to the ROM file if detected, None otherwise.
    """
    import shlex

    # Known library extensions that are NOT ROM files
    _lib_exts = {'.so', '.dll', '.dylib'}

    # Find all quoted paths in the exe string
    quoted_paths = re.findall(r'"([^"]+)"', exe)

    # Check from the end backwards - ROM paths are typically last
    for candidate in reversed(quoted_paths):
        p = Path(candidate)
        if p.suffix.lower() not in _lib_exts and '/' in candidate:
            return p

    # Try unquoted tokens
    try:
        for token in reversed(shlex.split(exe)):
            p = Path(token)
            if p.suffix.lower() not in _lib_exts and '/' in token:
                return p
    except ValueError:
        pass

    return None


# ═══════════════════════════════════════════════════════════════════════
# Known System Tags
# ═══════════════════════════════════════════════════════════════════════

def get_known_rom_tags() -> Set[str]:
    """Get all known ROM system category tags from systems.py.

    Returns:
        Set of tag strings like {"Atari 2600", "NES", "SNES", ...}
    """
    try:
        from systems import SYSTEMS
        tags = set()
        for sys_def in SYSTEMS.values():
            tags.update(sys_def.all_category_tags())
        return tags
    except Exception:
        return set()


def is_heroic_shortcut(shortcut) -> bool:
    """Check if a shortcut is a Heroic game import.

    Args:
        shortcut: A SteamShortcut object.

    Returns:
        True if the shortcut has a 'Heroic' tag.
    """
    return any(str(v).lower() == 'heroic' for v in shortcut.tags.values())


# ═══════════════════════════════════════════════════════════════════════
# Core Detection Functions
# ═══════════════════════════════════════════════════════════════════════

def find_orphaned_shortcuts(
    shortcuts: list,
    heroic_games: Optional[list] = None,
    rom_tags: Optional[Set[str]] = None,
) -> List[OrphanedShortcut]:
    """Find shortcuts whose targets no longer exist.

    Checks each shortcut to see if its ROM file or executable is still
    present on disk. Heroic shortcuts are checked against the Heroic
    game library.

    Args:
        shortcuts: List of SteamShortcut objects.
        heroic_games: List of Heroic game dicts (from heroic.py), or None.
        rom_tags: Set of known ROM system tags, or None to auto-detect.

    Returns:
        List of OrphanedShortcut entries.
    """
    if rom_tags is None:
        rom_tags = get_known_rom_tags()

    # Build set of installed Heroic game titles for quick lookup
    heroic_titles: Set[str] = set()
    if heroic_games:
        heroic_titles = {g['title'].lower() for g in heroic_games}

    orphans = []

    for sc in shortcuts:
        tag_values = [str(v) for v in sc.tags.values()]
        is_rom = any(t in rom_tags for t in tag_values)
        is_heroic = is_heroic_shortcut(sc)

        if is_heroic:
            # Check against Heroic game library
            if heroic_titles and sc.appname.lower() not in heroic_titles:
                orphans.append(OrphanedShortcut(
                    appname=sc.appname,
                    appid=sc.appid,
                    exe=sc.exe,
                    reason="heroic_uninstalled",
                    system_tag="Heroic",
                ))
                continue
            # If we can't check Heroic, skip (assume still installed)
            continue

        if is_rom:
            # ROM shortcut - check if ROM file exists
            rom_path = extract_rom_path(sc.exe)
            if rom_path is not None:
                if not rom_path.exists():
                    orphans.append(OrphanedShortcut(
                        appname=sc.appname,
                        appid=sc.appid,
                        exe=sc.exe,
                        reason="rom_missing",
                        system_tag=tag_values[0] if tag_values else "",
                    ))
            # If we can't extract a ROM path, we can't check - skip
            continue

        # Non-ROM, non-Heroic shortcut - check if exe exists
        # Extract the actual executable path (first quoted path)
        exe_match = re.search(r'"([^"]+)"', sc.exe)
        if exe_match:
            exe_path = Path(exe_match.group(1))
            # Only flag as orphan if the exe path looks like a local file
            # (not /usr/bin/flatpak which is always present)
            if not str(exe_path).startswith(('/usr/', '/bin/', '/sbin/')):
                if not exe_path.exists():
                    orphans.append(OrphanedShortcut(
                        appname=sc.appname,
                        appid=sc.appid,
                        exe=sc.exe,
                        reason="exe_missing",
                        system_tag=tag_values[0] if tag_values else "",
                    ))

    return orphans


def find_orphaned_art(
    grid_path: Path,
    shortcut_app_ids: Set[str],
) -> List[OrphanedArt]:
    """Find grid art files that have no matching shortcut.

    Args:
        grid_path: Path to the Steam grid folder.
        shortcut_app_ids: Set of short app ID strings from shortcuts.vdf.

    Returns:
        List of OrphanedArt entries.
    """
    orphans = []

    if not grid_path.exists():
        return orphans

    for entry in grid_path.iterdir():
        if not entry.is_file() and not entry.is_symlink():
            continue

        result = classify_art_file(entry.name)
        if result is None:
            continue

        app_id, art_type = result

        # Check if this app ID has a matching shortcut
        if app_id not in shortcut_app_ids:
            size = 0
            try:
                if entry.is_symlink():
                    # For symlinks, get size of target if possible
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                else:
                    size = entry.stat().st_size
            except OSError:
                size = 0

            orphans.append(OrphanedArt(
                filename=entry.name,
                app_id=app_id,
                art_type=art_type,
                size_bytes=size,
                is_symlink=entry.is_symlink(),
            ))

    return orphans


def find_empty_collections(steam_path: Path, user_id: Optional[str] = None) -> List[str]:
    """Find Steam collections that have zero members.

    Args:
        steam_path: Path to Steam installation.
        user_id: Specific user ID, or None to auto-detect.

    Returns:
        List of collection names that are empty.
    """
    try:
        from shortcuts import read_cloud_collections
        collections = read_cloud_collections(steam_path, user_id)
        empty = []
        for c in collections:
            if not c.is_deleted and c.name:
                # A collection is empty if it has no added entries
                if not c.added:
                    empty.append(c.name)
        return empty
    except Exception as e:
        logger.debug(f"Could not read collections: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════
# Cleanup Functions
# ═══════════════════════════════════════════════════════════════════════

def remove_orphaned_shortcuts(
    steam_path: Path,
    all_shortcuts: list,
    orphans: List[OrphanedShortcut],
    user_id: Optional[str] = None,
) -> int:
    """Remove orphaned shortcuts from shortcuts.vdf.

    Args:
        steam_path: Path to Steam installation.
        all_shortcuts: Current list of all shortcuts.
        orphans: List of orphaned shortcuts to remove.
        user_id: Specific user ID, or None to auto-detect.

    Returns:
        Number of shortcuts removed.
    """
    from shortcuts import write_shortcuts_vdf, find_shortcuts_vdf

    orphan_ids = {sc.appid for sc in orphans}
    keep = [sc for sc in all_shortcuts if sc.appid not in orphan_ids]

    try:
        vdf_path = find_shortcuts_vdf(steam_path, user_id)
        write_shortcuts_vdf(vdf_path, keep)
        return len(orphans)
    except Exception as e:
        logger.error(f"Failed to write shortcuts.vdf: {e}")
        return 0


def remove_orphaned_art(
    grid_path: Path,
    orphans: List[OrphanedArt],
) -> Tuple[int, int]:
    """Remove orphaned art files from the grid folder.

    Args:
        grid_path: Path to the Steam grid folder.
        orphans: List of orphaned art entries to remove.

    Returns:
        Tuple of (files_removed, errors).
    """
    removed = 0
    errors = 0

    for orphan in orphans:
        path = grid_path / orphan.filename
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
                removed += 1
        except OSError as e:
            logger.warning(f"Could not delete {path.name}: {e}")
            errors += 1

    return removed, errors


def remove_empty_collections(
    steam_path: Path,
    collection_names: List[str],
    user_id: Optional[str] = None,
) -> int:
    """Remove empty Steam collections.

    Args:
        steam_path: Path to Steam installation.
        collection_names: List of collection names to remove.
        user_id: Specific user ID, or None to auto-detect.

    Returns:
        Number of collections removed.
    """
    from shortcuts import read_cloud_collections, delete_cloud_collection

    try:
        collections = read_cloud_collections(steam_path, user_id)
    except Exception:
        return 0

    removed = 0
    for name in collection_names:
        target = None
        for c in collections:
            if not c.is_deleted and c.name == name:
                target = c
                break
        if target:
            if delete_cloud_collection(steam_path, target.coll_id, user_id):
                removed += 1

    return removed


# ═══════════════════════════════════════════════════════════════════════
# Full Reconciliation
# ═══════════════════════════════════════════════════════════════════════

def reconcile(
    steam_path: Path,
    grid_path: Path,
    user_id: Optional[str] = None,
    check_heroic: bool = True,
) -> ReconcileReport:
    """Run a full reconciliation of shortcuts, art, and collections.

    Args:
        steam_path: Path to Steam installation.
        grid_path: Path to the grid folder.
        user_id: Specific user ID, or None to auto-detect.
        check_heroic: Whether to check Heroic game library.

    Returns:
        ReconcileReport with all findings.
    """
    from shortcuts import get_existing_shortcuts

    report = ReconcileReport()

    # 1. Load shortcuts
    shortcuts = get_existing_shortcuts(steam_path, user_id)
    report.total_shortcuts = len(shortcuts)

    # Build set of app IDs from shortcuts (unsigned 32-bit)
    shortcut_app_ids = {str(sc.appid & 0xFFFFFFFF) for sc in shortcuts}

    # 2. Check Heroic games if available
    heroic_games = None
    if check_heroic:
        try:
            from heroic import find_heroic_config, get_heroic_games
            heroic_config = find_heroic_config()
            if heroic_config:
                heroic_games = get_heroic_games(heroic_config)
        except Exception:
            logger.debug("Heroic not available, skipping Heroic game check")

    # 3. Find orphaned shortcuts
    report.orphaned_shortcuts = find_orphaned_shortcuts(
        shortcuts, heroic_games=heroic_games
    )

    # 4. Find orphaned art
    report.total_art_files = sum(
        1 for f in grid_path.iterdir()
        if f.is_file() or f.is_symlink()
    ) if grid_path.exists() else 0
    report.orphaned_art = find_orphaned_art(grid_path, shortcut_app_ids)

    # 5. Find empty collections
    try:
        from shortcuts import read_cloud_collections
        collections = read_cloud_collections(steam_path, user_id)
        report.total_collections = len([c for c in collections if not c.is_deleted])
        report.empty_collections = find_empty_collections(steam_path, user_id)
    except Exception:
        logger.debug("Could not check collections")

    return report


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:0.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):0.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):0.1f} GB"