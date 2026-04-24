#!/usr/bin/env python3
"""Configuration management for SGM.

Handles creation, reading, validation, and interactive setup
of the SGM configuration file at ~/.config/sgm/config.json.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from steam import find_steam_path, find_user_ids, find_srm_artwork_cache

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / '.config' / 'sgm'
CONFIG_FILE = CONFIG_DIR / 'config.json'
DATA_DIR = Path.home() / '.local' / 'share' / 'sgm'
BACKUP_DIR = DATA_DIR / 'backups'
STATE_FILE = DATA_DIR / 'state.json'
LOG_FILE = DATA_DIR / 'sgm.log'

DEFAULT_CONFIG = {
    'version': 1,
    'api_key': '',
    'screenscraper_devid': '',
    'screenscraper_devpassword': '',
    'screenscraper_ssid': '',
    'screenscraper_sspassword': '',
    'thegamesdb_apikey': '',
    'steam_path': '',
    'steam_user_id': 'auto',
    'backup_path': str(BACKUP_DIR),
    'srm_artwork_cache': '',
    'auto_restore': True,
    'auto_restore_threshold': 0.5,
    'batch_size': 50,
    'log_level': 'info',
    'log_file': str(LOG_FILE),
    'vita3k_path': '',  # Vita3K data directory (auto-detected if empty)
}


def get_config_path() -> Path:
    """Return the config file path."""
    return CONFIG_FILE


def config_exists() -> bool:
    """Check if a config file exists."""
    return CONFIG_FILE.exists()


def load_config() -> dict:
    """Load configuration from file.
    
    Returns:
        Configuration dictionary. Falls back to defaults for missing keys.
    
    Raises:
        FileNotFoundError: If config file doesn't exist.
    """
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            "Run 'sgm config init' to create one."
        )
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Merge with defaults for any missing keys
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    
    return merged


def save_config(config: dict) -> None:
    """Save configuration to file.
    
    Args:
        config: Configuration dictionary to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"Config saved to {CONFIG_FILE}")


def ensure_dirs() -> None:
    """Create required directories if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def auto_detect_config() -> dict:
    """Auto-detect configuration values from the system.
    
    Returns:
        Dictionary of auto-detected values.
    """
    detected = DEFAULT_CONFIG.copy()
    
    # Detect Steam path
    try:
        steam_path = find_steam_path()
        detected['steam_path'] = str(steam_path)
        
        # Detect user ID
        user_ids = find_user_ids(steam_path)
        if user_ids:
            detected['steam_user_id'] = user_ids[0]
            if len(user_ids) > 1:
                print(f"  Multiple Steam users found: {', '.join(user_ids)}")
                print(f"  Using first: {user_ids[0]}")
    except FileNotFoundError as e:
        logger.warning(f"Could not auto-detect Steam path: {e}")
    
    # Detect SRM artwork cache
    srm_cache = find_srm_artwork_cache()
    if srm_cache:
        detected['srm_artwork_cache'] = str(srm_cache)
    
    return detected


def interactive_setup() -> dict:
    """Run interactive configuration setup.
    
    Returns:
        Configuration dictionary.
    """
    print("\n🎮 SteamGrid Manager (sgm) - First Time Setup\n")
    print("=" * 50)
    
    # Start with auto-detected values
    config = auto_detect_config()
    
    # Show auto-detected values
    print(f"\n📂 Steam path: {config['steam_path'] or 'NOT FOUND'}")
    print(f"👤 Steam user: {config['steam_user_id']}")
    print(f"📦 SRM cache:  {config['srm_artwork_cache'] or 'NOT FOUND'}")
    print(f"💾 Backups:    {config['backup_path']}")
    
    # Prompt for API key
    print(f"\n🔑 SteamGridDB API Key")
    print(f"   Get yours free at: https://www.steamgriddb.com/profile/preferences/api")
    api_key = input("   Enter API key (or press Enter to skip): ").strip()
    if api_key:
        config['api_key'] = api_key
    
    # Confirm or override Steam path
    if config['steam_path']:
        override = input(f"\n   Steam path OK? [{config['steam_path']}] (Enter=yes, or type path): ").strip()
        if override:
            config['steam_path'] = override
    else:
        steam_path = input("\n   Enter Steam path: ").strip()
        config['steam_path'] = steam_path
    
    # Confirm auto-restore
    auto_restore = input(f"\n   Enable auto-restore after Steam wipes? [Y/n]: ").strip().lower()
    config['auto_restore'] = auto_restore != 'n'
    
    # Save
    ensure_dirs()
    save_config(config)
    
    print(f"\n✅ Config saved to {CONFIG_FILE}")
    print(f"   Run 'sgm backup' to create your first backup!")
    
    return config


def show_config() -> None:
    """Display current configuration."""
    if not config_exists():
        print("No configuration found. Run 'sgm config init' to create one.")
        return
    
    config = load_config()
    print("\n🎮 SGM Configuration\n")
    print(f"   Config file: {CONFIG_FILE}")
    print(f"   {'─' * 45}")
    
    # Mask API key
    api_display = config.get('api_key', '')
    if api_display:
        api_display = api_display[:8] + '...' + api_display[-4:]
    else:
        api_display = '(not set)'
    
    print(f"   API Key:           {api_display}")
    print(f"   Steam Path:        {config.get('steam_path', 'auto')}")
    print(f"   Steam User ID:     {config.get('steam_user_id', 'auto')}")
    print(f"   Backup Path:       {config.get('backup_path', '')}")
    print(f"   SRM Artwork Cache: {config.get('srm_artwork_cache', 'not found')}")
    print(f"   Auto-Restore:      {config.get('auto_restore', True)}")
    print(f"   Restore Threshold: {config.get('auto_restore_threshold', 0.5)}")
    print(f"   Batch Size:        {config.get('batch_size', 50)}")
    print(f"   Log Level:         {config.get('log_level', 'info')}")
    
    # Vita3K path
    from systems import find_vita3k_data_dir
    vita3k_config = config.get('vita3k_path', '')
    if vita3k_config:
        print(f"   Vita3K Path:       {vita3k_config}")
    else:
        vita3k_detected = find_vita3k_data_dir()
        print(f"   Vita3K Path:       {vita3k_detected or '(not found)'}")


def set_config_value(key: str, value: str) -> None:
    """Set a single configuration value.
    
    Args:
        key: Configuration key to set.
        value: Value to set (will be type-converted).
    """
    if not config_exists():
        print("No configuration found. Run 'sgm config init' first.")
        return
    
    config = load_config()
    
    if key not in DEFAULT_CONFIG:
        print(f"Unknown config key: {key}")
        print(f"Valid keys: {', '.join(DEFAULT_CONFIG.keys())}")
        return
    
    # Type conversion based on default type
    default_type = type(DEFAULT_CONFIG[key])
    try:
        if default_type == bool:
            config[key] = value.lower() in ('true', '1', 'yes', 'on')
        elif default_type == int:
            config[key] = int(value)
        elif default_type == float:
            config[key] = float(value)
        else:
            config[key] = value
    except ValueError:
        print(f"Invalid value for {key}: {value} (expected {default_type.__name__})")
        return
    
    save_config(config)
    print(f"Set {key} = {config[key]}")


def get_resolved_config() -> dict:
    """Load config with auto-detection for 'auto' values.
    
    Returns:
        Configuration with all paths and IDs resolved.
    """
    config = load_config()
    
    # Resolve steam path
    steam_path = config.get('steam_path', '')
    if not steam_path:
        steam_path = str(find_steam_path())
        config['steam_path'] = steam_path
    
    # Resolve user ID
    if config.get('steam_user_id', 'auto') == 'auto':
        user_ids = find_user_ids(Path(steam_path))
        if user_ids:
            config['steam_user_id'] = user_ids[0]
    
    # Resolve SRM cache path
    if not config.get('srm_artwork_cache'):
        srm = find_srm_artwork_cache()
        if srm:
            config['srm_artwork_cache'] = str(srm)
    
    # Resolve Vita3K data path
    if not config.get('vita3k_path'):
        from systems import find_vita3k_data_dir
        vita3k_dir = find_vita3k_data_dir()
        if vita3k_dir:
            config['vita3k_path'] = str(vita3k_dir)
    
    return config
