#!/usr/bin/env python3
"""Heroic Games Launcher integration for SGM.

Reads Heroic's installed game database (Epic/GOG/Amazon), creates Steam
shortcuts, and downloads artwork from SteamGridDB. Supports both the
Flatpak and native Heroic installations.

Heroic stores game data at:
  Flatpak: ~/.var/app/com.heroicgameslauncher.hgl/config/heroic/
  Native:  ~/.config/heroic/
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Standard Heroic config locations (tried in order)
HEROIC_CONFIG_PATHS = [
    Path.home() / '.var' / 'app' / 'com.heroicgameslauncher.hgl' / 'config' / 'heroic',
    Path.home() / '.config' / 'heroic',
    Path.home() / 'snap' / 'heroic-games-launcher' / 'current' / '.config' / 'heroic',
]


def find_heroic_config() -> Optional[Path]:
    """Find the Heroic configuration directory.

    Returns:
        Path to Heroic config directory, or None if not found.
    """
    for p in HEROIC_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _build_gog_title_map(heroic_config: Path) -> dict[str, str]:
    """Build a mapping from GOG appName -> title using the library cache.

    Args:
        heroic_config: Path to Heroic config directory.

    Returns:
        Dict mapping appName to title.
    """
    cache_file = heroic_config / 'store_cache' / 'gog_library.json'
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding='utf-8'))
        games = data.get('games', [])
        return {g['app_name']: g['title'] for g in games if 'app_name' in g and 'title' in g}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read GOG library cache: {e}")
        return {}


def _build_amazon_title_map(heroic_config: Path) -> dict[str, str]:
    """Build a mapping from Amazon/Nile appName -> title using library cache."""
    cache_file = heroic_config / 'store_cache' / 'nile_library.json'
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding='utf-8'))
        if isinstance(data, list):
            games = data
        elif isinstance(data, dict):
            games = data.get('games', [])
        else:
            return {}
        return {g.get('app_name', g.get('id', '')): g.get('title', '') for g in games if g}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read Amazon library cache: {e}")
        return {}


def get_heroic_games(heroic_config: Optional[Path] = None) -> list[dict]:
    """Get all installed Heroic games across all stores.

    Args:
        heroic_config: Path to Heroic config dir. Auto-detected if None.

    Returns:
        List of game dicts with keys:
            - app_name: Store-specific game ID
            - title: Display name
            - runner: 'legendary' (Epic), 'gog', or 'nile' (Amazon)
            - install_path: Where the game is installed
            - is_dlc: Whether this is a DLC entry
    """
    if heroic_config is None:
        heroic_config = find_heroic_config()
    if heroic_config is None:
        logger.warning("Heroic config directory not found")
        return []

    games = []

    # --- Epic Games (Legendary) ---
    legendary_installed = heroic_config / 'legendaryConfig' / 'legendary' / 'installed.json'
    if legendary_installed.exists():
        try:
            data = json.loads(legendary_installed.read_text(encoding='utf-8'))
            for app_name, info in data.items():
                if info.get('is_dlc', False):
                    continue
                games.append({
                    'app_name': app_name,
                    'title': info.get('title', app_name),
                    'runner': 'legendary',
                    'install_path': info.get('install_path', ''),
                    'is_dlc': False,
                    'platform': info.get('platform', ''),
                })
            logger.debug(f"Found {len([g for g in games if g['runner']=='legendary'])} Epic games")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read Legendary installed.json: {e}")

    # --- GOG Games ---
    gog_installed = heroic_config / 'gog_store' / 'installed.json'
    if gog_installed.exists():
        try:
            data = json.loads(gog_installed.read_text(encoding='utf-8'))
            installed = data.get('installed', []) if isinstance(data, dict) else data
            gog_titles = _build_gog_title_map(heroic_config)

            for info in installed:
                if info.get('is_dlc', False):
                    continue
                app_name = info.get('appName', '')
                if not app_name:
                    continue
                title = gog_titles.get(app_name, '')
                # Fall back: derive title from install_path folder name
                if not title:
                    install_path = info.get('install_path', '')
                    if install_path:
                        title = Path(install_path).name
                if not title:
                    title = app_name
                games.append({
                    'app_name': app_name,
                    'title': title,
                    'runner': 'gog',
                    'install_path': info.get('install_path', ''),
                    'is_dlc': False,
                    'platform': info.get('platform', ''),
                })
            logger.debug(f"Found {len([g for g in games if g['runner']=='gog'])} GOG games")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read GOG installed.json: {e}")

    # --- Amazon Games (Nile) ---
    nile_installed = heroic_config / 'nile_store' / 'installed.json'
    if nile_installed.exists():
        try:
            data = json.loads(nile_installed.read_text(encoding='utf-8'))
            installed = data.get('installed', []) if isinstance(data, dict) else data
            amazon_titles = _build_amazon_title_map(heroic_config)

            for info in installed:
                if not isinstance(info, dict):
                    continue
                app_name = info.get('app_name', info.get('id', ''))
                if not app_name:
                    continue
                title = amazon_titles.get(app_name, info.get('title', ''))
                if not title:
                    title = app_name
                games.append({
                    'app_name': app_name,
                    'title': title,
                    'runner': 'nile',
                    'install_path': info.get('install_path', ''),
                    'is_dlc': False,
                    'platform': info.get('platform', ''),
                })
            logger.debug(f"Found {len([g for g in games if g['runner']=='nile'])} Amazon games")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not read Nile installed.json: {e}")

    return games


def make_heroic_launch_options(app_name: str, runner: str, is_flatpak: bool = True) -> tuple[str, str]:
    """Generate the Steam shortcut exe and launch options for a Heroic game.

    Args:
        app_name: The game's app name from the store.
        runner: 'legendary', 'gog', or 'nile'.
        is_flatpak: Whether Heroic is installed as a Flatpak.

    Returns:
        Tuple of (exe, launch_options).
    """
    url = f'heroic://launch?appName={app_name}&runner={runner}'
    base_args = f'--no-gui --no-sandbox "{url}"'

    if is_flatpak:
        exe = '"flatpak"'
        launch_options = f'run com.heroicgameslauncher.hgl {base_args}'
    else:
        exe = '"heroic"'
        launch_options = base_args

    return exe, launch_options


def is_heroic_flatpak() -> bool:
    """Detect whether Heroic is installed as a Flatpak."""
    flatpak_config = Path.home() / '.var' / 'app' / 'com.heroicgameslauncher.hgl'
    return flatpak_config.exists()
