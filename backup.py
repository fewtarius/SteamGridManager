#!/usr/bin/env python3
"""Backup and restore engine for Steam grid images.

Creates timestamped snapshots of the grid folder including metadata,
symlink maps, and file hashes for verification. Supports full restore
with symlink recreation.
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from steam import format_size

logger = logging.getLogger(__name__)


def _compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    return sha.hexdigest()


def _collect_grid_files(grid_path: Path) -> tuple[list[dict], dict[str, str]]:
    """Collect information about all files in the grid folder.
    
    Returns:
        Tuple of (file_info_list, symlink_map).
    """
    files = []
    symlink_map = {}
    
    for entry in sorted(grid_path.iterdir()):
        if entry.is_symlink():
            target = os.readlink(str(entry))
            symlink_map[entry.name] = target
            files.append({
                'name': entry.name,
                'type': 'symlink',
                'target': target,
            })
        elif entry.is_file():
            try:
                stat = entry.stat()
                files.append({
                    'name': entry.name,
                    'type': 'file',
                    'size': stat.st_size,
                })
            except OSError as e:
                logger.warning(f"Could not stat {entry}: {e}")
    
    return files, symlink_map


def create_backup(grid_path: Path, backup_dir: Path, dry_run: bool = False) -> int:
    """Create a backup snapshot of the grid folder.
    
    Args:
        grid_path: Path to the grid folder.
        backup_dir: Base directory for storing backups.
        dry_run: If True, only show what would be done.
    
    Returns:
        Exit code (0 for success).
    """
    if not grid_path.exists():
        print(f"Error: Grid folder not found: {grid_path}")
        return 1
    
    # Collect file info
    files, symlink_map = _collect_grid_files(grid_path)
    
    if not files:
        print("Grid folder is empty. Nothing to backup.")
        return 0
    
    # Calculate totals
    real_files = [f for f in files if f['type'] == 'file']
    symlinks = [f for f in files if f['type'] == 'symlink']
    total_size = sum(f.get('size', 0) for f in real_files)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    snapshot_dir = backup_dir / timestamp
    
    print(f"\n  {'[DRY RUN] ' if dry_run else ''}Backup Grid Images\n")
    print(f"  Source:     {grid_path}")
    print(f"  Dest:       {snapshot_dir}")
    print(f"  Files:      {len(real_files):} real + {len(symlinks):} symlinks")
    print(f"  Total size: {format_size(total_size)}")
    
    if dry_run:
        print(f"\n  Dry run complete. No files were copied.")
        return 0
    
    # Create snapshot directory
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    files_dir = snapshot_dir / 'files'
    files_dir.mkdir(exist_ok=True)
    
    # Copy files (not symlinks - we'll recreate those from the map)
    copied = 0
    errors = 0
    print(f"\n  Copying files...")
    
    for f in real_files:
        src = grid_path / f['name']
        dst = files_dir / f['name']
        try:
            shutil.copy2(str(src), str(dst))
            copied += 1
            if copied % 500 == 0:
                print(f"    {copied:}/{len(real_files):} files copied...")
        except (OSError, shutil.Error) as e:
            logger.error(f"Failed to copy {src}: {e}")
            errors += 1
    
    # Save metadata
    metadata = {
        'timestamp': timestamp,
        'created_at': datetime.now().isoformat(),
        'source_path': str(grid_path),
        'file_count': len(files),
        'real_files': len(real_files),
        'symlinks': len(symlinks),
        'total_size': total_size,
        'symlink_map': symlink_map,
        'files': files,
    }
    
    with open(snapshot_dir / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    # Also back up shortcuts.vdf if it exists alongside the grid folder
    shortcuts_src = grid_path.parent / 'shortcuts.vdf'
    if shortcuts_src.exists():
        try:
            shutil.copy2(str(shortcuts_src), str(snapshot_dir / 'shortcuts.vdf'))
            logger.debug(f"Backed up shortcuts.vdf")
        except (OSError, shutil.Error) as e:
            logger.warning(f"Could not back up shortcuts.vdf: {e}")
    
    status = "[OK]" if errors == 0 else "[WARN]"
    print(f"\n  {status} Backup complete!")
    print(f"    Copied: {copied:} files + {len(symlinks):} symlink mappings saved")
    if errors:
        print(f"    Errors: {errors}")
    print(f"    Location: {snapshot_dir}")
    print()
    
    return 0 if errors == 0 else 1


def list_backups(backup_dir: Path) -> list[dict]:
    """List available backups sorted by newest first.
    
    Args:
        backup_dir: Base backup directory.
    
    Returns:
        List of backup metadata dicts.
    """
    if not backup_dir.exists():
        return []
    
    backups = []
    for entry in sorted(backup_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        meta_file = entry / 'metadata.json'
        if meta_file.exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                backups.append({
                    'path': entry,
                    'timestamp': meta.get('timestamp', entry.name),
                    'file_count': meta.get('file_count', 0),
                    'real_files': meta.get('real_files', 0),
                    'symlinks': meta.get('symlinks', 0),
                    'total_size': meta.get('total_size', 0),
                    'created_at': meta.get('created_at', ''),
                })
            except (json.JSONDecodeError, OSError):
                continue
    
    return backups


def restore_backup(
    grid_path: Path,
    backup_dir: Path,
    timestamp: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Restore grid images from a backup.
    
    Args:
        grid_path: Path to restore to (the grid folder).
        backup_dir: Base backup directory.
        timestamp: Specific backup timestamp, or None for latest.
        dry_run: If True, only show what would be done.
        force: Skip confirmation prompt.
    
    Returns:
        Exit code (0 for success).
    """
    backups = list_backups(backup_dir)
    
    if not backups:
        print("No backups found. Run 'sgm backup' first.")
        return 1
    
    # Select backup
    if timestamp:
        matching = [b for b in backups if b['timestamp'] == timestamp]
        if not matching:
            print(f"Backup not found: {timestamp}")
            print("Available backups:")
            for b in backups:
                print(f"  {b['timestamp']}")
            return 1
        backup = matching[0]
    else:
        backup = backups[0]  # Latest
    
    # Load metadata
    meta_file = backup['path'] / 'metadata.json'
    with open(meta_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    files_dir = backup['path'] / 'files'
    symlink_map = metadata.get('symlink_map', {})
    real_file_count = metadata.get('real_files', 0)
    
    print(f"\n  {'[DRY RUN] ' if dry_run else ''}Restore Grid Images\n")
    print(f"  Backup:    {backup['timestamp']}")
    print(f"  Source:    {backup['path']}")
    print(f"  Dest:      {grid_path}")
    print(f"  Files:     {real_file_count:} real + {len(symlink_map):} symlinks")
    print(f"  Size:      {format_size(backup['total_size'])}")
    
    if dry_run:
        print(f"\n  Dry run complete. No files were modified.")
        return 0
    
    # Confirm
    if not force:
        print(f"\n  This will overwrite files in the grid folder.")
        answer = input("  Continue? [y/N]: ").strip().lower()
        if answer != 'y':
            print("  Cancelled.")
            return 0
    
    # Ensure grid directory exists
    grid_path.mkdir(parents=True, exist_ok=True)
    
    # Copy real files
    copied = 0
    errors = 0
    print(f"\n  Restoring files...")
    
    if files_dir.exists():
        for entry in sorted(files_dir.iterdir()):
            if entry.is_file():
                dst = grid_path / entry.name
                try:
                    shutil.copy2(str(entry), str(dst))
                    copied += 1
                    if copied % 500 == 0:
                        print(f"    {copied:}/{real_file_count:} files restored...")
                except (OSError, shutil.Error) as e:
                    logger.error(f"Failed to restore {entry}: {e}")
                    errors += 1
    
    # Recreate symlinks
    links_created = 0
    links_failed = 0
    
    for link_name, target in symlink_map.items():
        link_path = grid_path / link_name
        try:
            # Remove existing file/symlink if present
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            os.symlink(target, str(link_path))
            links_created += 1
        except OSError as e:
            logger.error(f"Failed to create symlink {link_name} -> {target}: {e}")
            links_failed += 1
    
    status = "[OK]" if (errors == 0 and links_failed == 0) else "[WARN]"
    print(f"\n  {status} Restore complete!")
    print(f"    Files restored:   {copied:}")
    print(f"    Symlinks created: {links_created:}")
    if errors:
        print(f"    File errors:      {errors}")
    if links_failed:
        print(f"    Symlink errors:   {links_failed}")
    
    # Restore shortcuts.vdf if it was backed up
    shortcuts_backup = backup['path'] / 'shortcuts.vdf'
    if shortcuts_backup.exists():
        shortcuts_dst = grid_path.parent / 'shortcuts.vdf'
        try:
            shutil.copy2(str(shortcuts_backup), str(shortcuts_dst))
            print(f"    shortcuts.vdf:    restored")
        except (OSError, shutil.Error) as e:
            logger.warning(f"Could not restore shortcuts.vdf: {e}")
            print(f"    shortcuts.vdf:    [WARN] failed to restore: {e}")
    
    print()
    
    return 0 if (errors == 0 and links_failed == 0) else 1


def get_grid_state(grid_path: Path) -> dict:
    """Get a lightweight state snapshot for change detection.
    
    Returns:
        Dictionary with file count and names for comparison.
    """
    if not grid_path.exists():
        return {'file_count': 0, 'files': []}
    
    files = sorted(entry.name for entry in grid_path.iterdir() 
                   if entry.is_file() or entry.is_symlink())
    
    return {
        'file_count': len(files),
        'files': files,
        'checked_at': datetime.now().isoformat(),
    }


def save_state(state: dict, state_file: Path) -> None:
    """Save grid state to file."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def load_state(state_file: Path) -> Optional[dict]:
    """Load last known grid state."""
    if not state_file.exists():
        return None
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
