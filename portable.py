#!/usr/bin/env python3
"""Cross-device portable backup and transfer system.

Creates self-contained backup bundles that include:
- Grid images (all 5 types per game)
- Shortcut metadata (titles, launch configs)
- System mappings for re-import on another device

Bundles are stored as directories with a manifest.json for portability.
"""

import hashlib
import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExportManifest:
    """Manifest for a portable backup bundle."""
    version: int = 2
    created: str = ""
    source_device: str = ""
    steam_user_id: str = ""
    total_games: int = 0
    total_images: int = 0
    total_size_bytes: int = 0
    systems: Dict[str, int] = None      # system -> game count
    games: List[dict] = None            # Per-game metadata

    def __post_init__(self):
        if self.systems is None:
            self.systems = {}
        if self.games is None:
            self.games = []

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created": self.created,
            "source_device": self.source_device,
            "steam_user_id": self.steam_user_id,
            "total_games": self.total_games,
            "total_images": self.total_images,
            "total_size_bytes": self.total_size_bytes,
            "systems": self.systems,
            "games": self.games,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExportManifest":
        return cls(
            version=data.get("version", 1),
            created=data.get("created", ""),
            source_device=data.get("source_device", ""),
            steam_user_id=data.get("steam_user_id", ""),
            total_games=data.get("total_games", 0),
            total_images=data.get("total_images", 0),
            total_size_bytes=data.get("total_size_bytes", 0),
            systems=data.get("systems", {}),
            games=data.get("games", []),
        )


def export_bundle(grid_path: Path,
                  shortcuts: list,
                  output_dir: Path,
                  bundle_name: Optional[str] = None,
                  systems_filter: Optional[Set[str]] = None,
                  steam_user_id: str = "",
                  device_name: str = "") -> Path:
    """Create a portable backup bundle from current grid images and shortcuts.

    Args:
        grid_path: Path to Steam grid folder.
        shortcuts: List of SteamShortcut objects to export.
        output_dir: Directory to create the bundle in.
        bundle_name: Name for the bundle (auto-generated if None).
        systems_filter: Only export these systems (None = all).
        steam_user_id: Steam user ID for metadata.
        device_name: Source device name for metadata.

    Returns:
        Path to the created bundle directory.
    """
    import socket

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    if not bundle_name:
        bundle_name = f"sgm_export_{timestamp}"

    bundle_path = output_dir / bundle_name
    images_dir = bundle_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    manifest = ExportManifest(
        created=time.strftime("%Y-%m-%dT%H:%M:%S"),
        source_device=device_name or socket.gethostname(),
        steam_user_id=steam_user_id,
    )

    total_size = 0
    total_images = 0

    # Build shortcut lookup by app ID
    shortcut_map = {}
    for sc in shortcuts:
        # Use the short app ID (unsigned) for grid file matching
        unsigned_id = sc.appid if sc.appid >= 0 else sc.appid + 0x100000000
        shortcut_map[str(unsigned_id)] = sc

    # Image type suffixes
    suffixes = {
        "": "tall",
        "p": "wide",
        "_hero": "hero",
        "_logo": "logo",
        "_icon": "icon",
    }

    # Scan grid folder and group by app ID
    app_images: Dict[str, Dict[str, Path]] = {}

    if grid_path.exists():
        for img_file in sorted(grid_path.iterdir()):
            if img_file.is_dir():
                continue
            if img_file.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue

            stem = img_file.stem
            # Parse out the app ID and type suffix
            app_id = None
            art_type = None

            for suffix, atype in suffixes.items():
                if suffix and stem.endswith(suffix):
                    app_id = stem[:-len(suffix)]
                    art_type = atype
                    break

            if app_id is None:
                # No suffix = tall capsule
                app_id = stem
                art_type = "tall"

            if not app_id.isdigit():
                continue

            if app_id not in app_images:
                app_images[app_id] = {}
            app_images[app_id][art_type] = img_file

    # Process each app
    for app_id in sorted(app_images.keys()):
        images = app_images[app_id]
        sc = shortcut_map.get(app_id)

        # Detect system from shortcut tags or launch options
        system = ""
        title = f"Unknown Game ({app_id})"
        exe = ""
        launch_options = ""

        if sc:
            title = sc.appname
            exe = sc.exe
            launch_options = sc.launch_options
            # Try to detect system from tags
            for tag_val in sc.tags.values():
                system = tag_val
                break

        # Apply system filter
        if systems_filter and system and system not in systems_filter:
            continue

        # Count by system
        if system:
            manifest.systems[system] = manifest.systems.get(system, 0) + 1

        # Copy images to bundle
        game_images = {}
        for art_type, img_path in images.items():
            if img_path.is_symlink():
                # Resolve symlinks - copy the actual file
                real_path = img_path.resolve()
                if real_path.exists():
                    dest = images_dir / img_path.name
                    shutil.copy2(real_path, dest)
                    game_images[art_type] = img_path.name
                    total_size += real_path.stat().st_size
                    total_images += 1
            elif img_path.exists():
                dest = images_dir / img_path.name
                shutil.copy2(img_path, dest)
                game_images[art_type] = img_path.name
                total_size += img_path.stat().st_size
                total_images += 1

        game_entry = {
            "app_id": app_id,
            "title": title,
            "system": system,
            "exe": exe,
            "launch_options": launch_options,
            "images": game_images,
        }
        manifest.games.append(game_entry)

    manifest.total_games = len(manifest.games)
    manifest.total_images = total_images
    manifest.total_size_bytes = total_size

    # Write manifest
    manifest_path = bundle_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))

    # Include shortcuts.vdf for full cross-device restore
    shortcuts_src = grid_path.parent / 'shortcuts.vdf'
    if shortcuts_src.exists():
        try:
            shutil.copy2(shortcuts_src, bundle_path / 'shortcuts.vdf')
            logger.debug("Included shortcuts.vdf in bundle")
        except (OSError, shutil.Error) as e:
            logger.warning(f"Could not include shortcuts.vdf in bundle: {e}")

    logger.info(
        f"Exported bundle: {bundle_path}\n"
        f"  Games: {manifest.total_games}\n"
        f"  Images: {manifest.total_images}\n"
        f"  Size: {total_size / 1024 / 1024:0.1f} MB"
    )

    return bundle_path


def import_bundle(bundle_path: Path,
                  grid_path: Path,
                  mode: str = "merge",
                  systems_filter: Optional[Set[str]] = None,
                  remap_ids: Optional[Dict[str, str]] = None,
                  dry_run: bool = False,
                  with_shortcuts: bool = False) -> Tuple[int, int, int]:
    """Import a portable backup bundle into the current Steam grid folder.

    Args:
        bundle_path: Path to the bundle directory.
        grid_path: Steam grid folder path.
        mode: "merge" (keep existing, add new), "replace" (overwrite all),
              or "missing" (only add missing art types).
        systems_filter: Only import these systems (None = all).
        remap_ids: Dict mapping old app_id -> new app_id for cross-device.
        dry_run: If True, don't actually copy files.
        with_shortcuts: Also restore shortcuts.vdf from the bundle.

    Returns:
        Tuple of (imported_count, skipped_count, error_count).
    """
    manifest_path = bundle_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json found in {bundle_path}")

    manifest = ExportManifest.from_dict(
        json.loads(manifest_path.read_text())
    )
    images_dir = bundle_path / "images"

    imported = 0
    skipped = 0
    errors = 0

    # Image type -> filename suffix
    suffix_map = {
        "tall": "",
        "wide": "p",
        "hero": "_hero",
        "logo": "_logo",
        "icon": "_icon",
    }

    for game in manifest.games:
        system = game.get("system", "")
        if systems_filter and system and system not in systems_filter:
            skipped += 1
            continue

        old_app_id = game["app_id"]
        new_app_id = remap_ids.get(old_app_id, old_app_id) if remap_ids else old_app_id
        title = game.get("title", "")

        for art_type, img_filename in game.get("images", {}).items():
            suffix = suffix_map.get(art_type, "")
            src_path = images_dir / img_filename

            if not src_path.exists():
                logger.warning(f"Missing image: {img_filename}")
                errors += 1
                continue

            # Determine output filename
            ext = src_path.suffix
            dest_name = f"{new_app_id}{suffix}{ext}"
            dest_path = grid_path / dest_name

            # Apply mode logic
            if dest_path.exists() and mode == "merge":
                skipped += 1
                continue
            if dest_path.exists() and mode == "missing":
                skipped += 1
                continue

            if dry_run:
                logger.info(f"  [DRY-RUN] Would copy: {img_filename} -> {dest_name}")
                imported += 1
                continue

            try:
                shutil.copy2(src_path, dest_path)
                imported += 1
            except Exception as e:
                logger.error(f"Failed to copy {img_filename}: {e}")
                errors += 1

    logger.info(
        f"Import complete: {imported} imported, {skipped} skipped, {errors} errors"
    )

    # Optionally restore shortcuts.vdf from the bundle
    if with_shortcuts:
        shortcuts_src = bundle_path / 'shortcuts.vdf'
        if shortcuts_src.exists():
            shortcuts_dst = grid_path.parent / 'shortcuts.vdf'
            if dry_run:
                logger.info(f"  [DRY-RUN] Would restore shortcuts.vdf -> {shortcuts_dst}")
            else:
                try:
                    shutil.copy2(shortcuts_src, shortcuts_dst)
                    logger.info(f"Restored shortcuts.vdf to {shortcuts_dst}")
                except (OSError, shutil.Error) as e:
                    logger.error(f"Failed to restore shortcuts.vdf: {e}")
                    errors += 1
        else:
            logger.warning("Bundle does not contain shortcuts.vdf — skipping shortcut restore")

    return imported, skipped, errors


def list_bundles(backup_dir: Path) -> List[dict]:
    """List available backup bundles.

    Args:
        backup_dir: Directory containing bundles.

    Returns:
        List of bundle info dicts with path, created, games, size.
    """
    bundles = []
    if not backup_dir.exists():
        return bundles

    for item in sorted(backup_dir.iterdir()):
        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            data = json.loads(manifest_path.read_text())
            bundles.append({
                "path": str(item),
                "name": item.name,
                "created": data.get("created", ""),
                "source_device": data.get("source_device", ""),
                "total_games": data.get("total_games", 0),
                "total_images": data.get("total_images", 0),
                "total_size_mb": data.get("total_size_bytes", 0) / 1024 / 1024,
                "systems": data.get("systems", {}),
            })
        except Exception as e:
            logger.debug(f"Error reading bundle {item}: {e}")

    return bundles
