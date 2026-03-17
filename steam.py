#!/usr/bin/env python3
"""Steam path and userdata discovery.

Finds the Steam installation, userdata directory, grid folder,
and identifies the active Steam user ID.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_steam_path() -> Path:
    """Find the Steam installation directory.
    
    Checks common locations on Linux/SteamOS.
    
    Returns:
        Path to Steam installation.
    
    Raises:
        FileNotFoundError: If Steam installation is not found.
    """
    candidates = [
        Path.home() / '.steam' / 'steam',
        Path.home() / '.local' / 'share' / 'Steam',
        Path('/usr/share/steam'),
    ]
    
    for path in candidates:
        if path.exists() and (path / 'userdata').exists():
            logger.debug(f"Found Steam at: {path}")
            return path
    
    raise FileNotFoundError(
        "Steam installation not found. Checked:\n"
        + "\n".join(f"  - {p}" for p in candidates)
    )


def find_user_ids(steam_path: Path) -> list[str]:
    """Find all Steam user IDs in the userdata directory.
    
    Args:
        steam_path: Path to Steam installation.
    
    Returns:
        List of Steam32 user IDs as strings.
    
    Raises:
        FileNotFoundError: If userdata directory doesn't exist.
    """
    userdata = steam_path / 'userdata'
    if not userdata.exists():
        raise FileNotFoundError(f"Userdata directory not found: {userdata}")
    
    user_ids = []
    for entry in sorted(userdata.iterdir()):
        if entry.is_dir() and entry.name.isdigit():
            # Verify it has a config/grid directory
            grid = entry / 'config' / 'grid'
            if grid.exists():
                user_ids.append(entry.name)
                logger.debug(f"Found user ID with grid folder: {entry.name}")
    
    return user_ids


def find_grid_path(steam_path: Path, user_id: Optional[str] = None) -> Path:
    """Find the grid folder for a specific or first available user.
    
    Args:
        steam_path: Path to Steam installation.
        user_id: Specific user ID, or None to auto-detect.
    
    Returns:
        Path to the grid folder.
    
    Raises:
        FileNotFoundError: If no grid folder is found.
    """
    if user_id:
        grid = steam_path / 'userdata' / user_id / 'config' / 'grid'
        if grid.exists():
            return grid
        raise FileNotFoundError(f"Grid folder not found for user {user_id}: {grid}")
    
    # Auto-detect: use first user with a grid folder
    user_ids = find_user_ids(steam_path)
    if not user_ids:
        raise FileNotFoundError("No Steam users with grid folders found")
    
    user_id = user_ids[0]
    if len(user_ids) > 1:
        logger.warning(
            f"Multiple Steam users found: {user_ids}. Using first: {user_id}"
        )
    
    return steam_path / 'userdata' / user_id / 'config' / 'grid'


def find_srm_artwork_cache() -> Optional[Path]:
    """Find the Steam ROM Manager artwork cache file.
    
    Returns:
        Path to artworkCache.json, or None if not found.
    """
    candidates = [
        # Flatpak SRM
        Path.home() / '.var' / 'app' / 'com.steamgriddb.steam-rom-manager' / 
            'config' / 'steam-rom-manager' / 'userData' / 'artworkCache.json',
        # AppImage/native SRM
        Path.home() / '.config' / 'steam-rom-manager' / 'userData' / 'artworkCache.json',
    ]
    
    for path in candidates:
        if path.exists():
            logger.debug(f"Found SRM artwork cache: {path}")
            return path
    
    logger.debug("SRM artwork cache not found")
    return None


def get_grid_stats(grid_path: Path) -> dict:
    """Get statistics about the grid folder.
    
    Args:
        grid_path: Path to the grid folder.
    
    Returns:
        Dictionary with image statistics.
    """
    stats = {
        'total_files': 0,
        'real_files': 0,
        'symlinks': 0,
        'total_size': 0,
        'by_type': {
            'tall': 0,     # {appid}.png/jpg
            'wide': 0,     # {appid}p.png/jpg
            'hero': 0,     # {appid}_hero.png/jpg
            'logo': 0,     # {appid}_logo.png/jpg
            'icon': 0,     # {appid}_icon.png/jpg
            'other': 0,
        },
        'unique_app_ids': set(),
    }
    
    if not grid_path.exists():
        return stats
    
    for entry in grid_path.iterdir():
        if not entry.is_file() and not entry.is_symlink():
            continue
        
        stats['total_files'] += 1
        
        if entry.is_symlink():
            stats['symlinks'] += 1
        else:
            stats['real_files'] += 1
            try:
                stats['total_size'] += entry.stat().st_size
            except OSError:
                pass
        
        name = entry.name
        # Classify by type
        if '_hero.' in name:
            stats['by_type']['hero'] += 1
        elif '_logo.' in name:
            stats['by_type']['logo'] += 1
        elif '_icon.' in name:
            stats['by_type']['icon'] += 1
        elif name[0].isdigit() and 'p.' in name:
            # Check for wide capsule pattern: {appid}p.png
            base = name.split('.')[0]
            if base.endswith('p') and base[:-1].isdigit():
                stats['by_type']['wide'] += 1
            else:
                stats['by_type']['other'] += 1
        elif name[0].isdigit():
            base = name.split('.')[0]
            if base.isdigit():
                stats['by_type']['tall'] += 1
            else:
                stats['by_type']['other'] += 1
        else:
            stats['by_type']['other'] += 1
        
        # Extract app ID
        import re
        match = re.match(r'^(\d+)', name)
        if match:
            stats['unique_app_ids'].add(match.group(1))
    
    return stats


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
