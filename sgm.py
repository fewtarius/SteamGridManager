#!/usr/bin/env python3
"""SteamGrid Manager (sgm) - Protect your custom Steam library artwork.

CLI tool that backs up, restores, and refreshes custom game images
on SteamOS/Linux. Prevents loss of artwork after Steam client updates.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

__version__ = '1.0.0'


def setup_logging(level: str = 'info', log_file: str = None) -> None:
    """Configure logging for the application."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler(sys.stderr)]
    
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )


def notify_steam_reload() -> None:
    """Tell a running Steam client to reload shortcuts, or print a hint if not running."""
    from steam import is_steam_running, reload_steam_shortcuts
    if is_steam_running():
        if reload_steam_shortcuts():
            print("\nSteam is running — shortcuts reloaded. Your games should appear shortly.\n")
        else:
            print("\nDone! Restart Steam to see your games in the library.\n")
    else:
        print("\nDone! Start Steam to see your games in the library.\n")


def cmd_status(args: argparse.Namespace) -> int:
    """Show current status of grid images and backups."""
    from config import config_exists, load_config, get_resolved_config
    from steam import find_steam_path, find_grid_path, get_grid_stats, format_size
    from backup import list_backups
    
    print(f"\n SteamGrid Manager (sgm) v{__version__}\n")
    
    # Load config or auto-detect
    try:
        if config_exists():
            config = get_resolved_config()
        else:
            steam_path = find_steam_path()
            config = {
                'steam_path': str(steam_path),
                'steam_user_id': 'auto',
                'api_key': '',
            }
    except FileNotFoundError as e:
        print(f"  Error: {e}")
        return 1
    
    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    
    print(f"  Steam User: {user_id}")
    
    # Find grid path
    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
        print(f"  Grid Path:  {grid_path}\n")
    except FileNotFoundError as e:
        print(f"  Grid Path:  NOT FOUND ({e})\n")
        return 1
    
    # Grid stats
    stats = get_grid_stats(grid_path)
    print(f"  Current Grid Images:")
    print(f"    Tall capsules:  {stats['by_type']['tall']:>5}")
    print(f"    Wide capsules:  {stats['by_type']['wide']:>5}")
    print(f"    Hero banners:   {stats['by_type']['hero']:>5}")
    print(f"    Logos:          {stats['by_type']['logo']:>5}")
    print(f"    Icons:          {stats['by_type']['icon']:>5}")
    if stats['by_type']['other']:
        print(f"    Other:          {stats['by_type']['other']:>5}")
    print(f"    Symlinks:       {stats['symlinks']:>5}")
    print(f"    Total:          {stats['total_files']:>5} ({format_size(stats['total_size'])})")
    print(f"    Unique App IDs: {len(stats['unique_app_ids']):>5}")
    
    # Backup info
    print()
    try:
        backup_path = Path(config.get('backup_path', str(Path.home() / '.local' / 'share' / 'sgm' / 'backups')))
        backups = list_backups(backup_path)
        if backups:
            latest = backups[0]
            print(f"  Backups:")
            print(f"    Latest:  {latest['timestamp']} ({latest['file_count']:} files, {format_size(latest['total_size'])})")
            print(f"    Total:   {len(backups)} backup(s)")
        else:
            print(f"  Backups:  None (run 'sgm backup' to create one)")
    except Exception:
        print(f"  Backups:  None (run 'sgm backup' to create one)")
    
    # SRM cache
    from steam import find_srm_artwork_cache
    srm_cache = find_srm_artwork_cache()
    if srm_cache:
        try:
            import json
            with open(srm_cache, 'r') as f:
                cache_data = json.load(f)
            art = cache_data.get('sgdbToArt', {})
            total_mappings = sum(len(v) for v in art.values())
            print(f"  SRM Cache: Found ({total_mappings:} mappings)")
        except Exception:
            print(f"  SRM Cache: Found (could not read)")
    else:
        print(f"  SRM Cache: Not found")
    
    # API key
    api_key = config.get('api_key', '')
    api_status = "Configured" if api_key else "Not set (run 'sgm config init')"
    print(f"  API Key:   {api_status}")

    # Art cache stats
    try:
        from art_scraper import DEFAULT_CACHE_DIR
        cache_dir = Path(config.get('art_cache_dir', '') or DEFAULT_CACHE_DIR).expanduser()
        if cache_dir.exists():
            cache_files = list(cache_dir.glob('*.json'))
            print(f"  Art Cache: {len(cache_files)} game(s) cached")
        else:
            print(f"  Art Cache: Empty (populated during rom art scrape)")
    except Exception:
        pass

    # Auto-monitor
    from monitor import is_monitor_installed
    monitor_status = "Active" if is_monitor_installed() else "Not installed"
    print(f"  Monitor:   {monitor_status}")
    
    print()
    return 0

def cmd_backup(args: argparse.Namespace) -> int:
    """Create a backup of the grid folder."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from backup import create_backup
    
    try:
        if config_exists():
            config = get_resolved_config()
        else:
            steam_path = find_steam_path()
            config = {
                'steam_path': str(steam_path),
                'steam_user_id': 'auto',
                'backup_path': str(Path.home() / '.local' / 'share' / 'sgm' / 'backups'),
            }
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    backup_path = Path(config.get('backup_path', str(Path.home() / '.local' / 'share' / 'sgm' / 'backups')))
    
    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    return create_backup(grid_path, backup_path, dry_run=args.dry_run)


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore grid images from a backup."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from backup import restore_backup, list_backups
    
    try:
        if config_exists():
            config = get_resolved_config()
        else:
            steam_path = find_steam_path()
            config = {
                'steam_path': str(steam_path),
                'steam_user_id': 'auto',
                'backup_path': str(Path.home() / '.local' / 'share' / 'sgm' / 'backups'),
            }
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    backup_path = Path(config.get('backup_path', str(Path.home() / '.local' / 'share' / 'sgm' / 'backups')))
    
    # List mode
    if args.list:
        backups = list_backups(backup_path)
        if not backups:
            print("No backups found.")
            return 0
        print(f"\nAvailable backups:\n")
        for b in backups:
            from steam import format_size
            print(f"  {b['timestamp']}  ({b['file_count']:} files, {format_size(b['total_size'])})")
        print()
        return 0
    
    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    
    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    result = restore_backup(
        grid_path, backup_path,
        timestamp=args.timestamp,
        dry_run=args.dry_run,
        force=args.force,
    )
    if result == 0 and not args.dry_run:
        notify_steam_reload()
    return result


def _cmd_refresh_shortcuts(
    config: dict,
    steam_path: Path,
    grid_path: Path,
    image_type: Optional[str],
    dry_run: bool,
) -> int:
    """Scrape SteamGridDB art for non-ROM shortcuts that are missing images.

    Covers Heroic games, flatpak apps, Wine/exe games — anything not tagged
    with a known ROM system category.
    """
    from shortcuts import read_shortcuts_vdf, generate_short_app_id
    from art_scraper import CascadeScraper, save_grid_images, ART_TYPES

    # Known ROM system tags — shortcuts with any of these are skipped
    ROM_TAGS = {
        'Atari 2600', 'Master System', 'VIC-20', 'Game Gear',
        'Nintendo Entertainment System', 'Super Nintendo', 'ColecoVision',
        'Arcade', 'Genesis', 'Atari 5200', 'Atari Lynx', 'Commodore 64',
        'Atari 7800', 'Game Boy Advance', 'Infocom / Z-Machine', 'Z-Machine',
        'Amiga', 'Game Boy', 'Intellivision', 'GameCube', 'PlayStation Portable',
        'Wii U', 'Game Boy Color', 'Dreamcast', 'PlayStation 2', 'Nintendo DS',
        'Xbox', 'DOS', 'Neo Geo', 'PlayStation', 'Wii', 'Nintendo 64',
        'Sega Saturn', 'SNES', 'NES', 'PC Engine', 'TurboGrafx-16',
    }

    # Find shortcuts.vdf
    user_id = config.get('steam_user_id', 'auto')
    uid = user_id if user_id != 'auto' else None
    vdf_path = grid_path.parent / 'shortcuts.vdf'
    if not vdf_path.exists():
        print("No shortcuts.vdf found.")
        return 1

    shortcuts = read_shortcuts_vdf(vdf_path)

    # Filter to non-ROM shortcuts
    non_rom = [
        sc for sc in shortcuts
        if not any(str(v) in ROM_TAGS for v in sc.tags.values())
    ]

    # Determine which art types to look for
    wanted_types: set[str]
    if image_type:
        wanted_types = {image_type}
    else:
        wanted_types = set(ART_TYPES)

    # Collect suffix map for existence checks
    suffix_map = {
        'tall': 'p', 'wide': '', 'hero': '_hero', 'logo': '_logo', 'icon': '_icon'
    }
    suffix_map_filtered = {k: v for k, v in suffix_map.items() if k in wanted_types}

    # Find which non-ROM shortcuts are missing art.
    # Use the appid already stored in shortcuts.vdf (as unsigned 32-bit) for the
    # grid filename prefix — this matches whatever ID SRM/Steam already assigned,
    # regardless of how generate_short_app_id() would compute it.
    def grid_id_for(sc) -> str:
        """Return the grid filename prefix for an existing shortcut."""
        if sc.appid:
            # appid is stored as signed 32-bit in VDF; convert to unsigned
            return str(sc.appid & 0xFFFFFFFF)
        return generate_short_app_id(sc.exe, sc.appname)

    to_scrape = []
    for sc in non_rom:
        grid_id = grid_id_for(sc)
        missing_types = set()
        for art_type, suffix in suffix_map_filtered.items():
            has = any(
                (grid_path / f"{grid_id}{suffix}{ext}").exists()
                for ext in ('.png', '.jpg')
            )
            if not has:
                missing_types.add(art_type)
        if missing_types:
            to_scrape.append((sc, grid_id, missing_types))

    if not to_scrape:
        print("All non-ROM shortcuts already have artwork.")
        return 0

    print(f"\n  Refresh Shortcut Art\n")
    print(f"  Shortcuts to scrape: {len(to_scrape)}")
    if dry_run:
        print()
        for sc, short_id, missing in sorted(to_scrape, key=lambda x: x[0].appname):
            print(f"  [WOULD SCRAPE] {sc.appname}  (missing: {', '.join(sorted(missing))})")
        print(f"\n  (dry run — no changes made)\n")
        return 0

    # Initialize scraper
    try:
        scraper = CascadeScraper(config)
    except Exception as e:
        print(f"Error initializing art scraper: {e}")
        return 1

    total_downloaded = 0
    total_failed = 0
    total_skipped = 0

    print()
    for sc, short_id, missing_types in sorted(to_scrape, key=lambda x: x[0].appname):
        print(f"  {sc.appname}", end='', flush=True)
        try:
            artwork = scraper.scrape_game(sc.appname, wanted_types=missing_types)
            if artwork:
                saved = save_grid_images(short_id, artwork, grid_path)
                total_downloaded += len(saved)
                missing_after = missing_types - set(saved.keys())
                if missing_after:
                    total_failed += len(missing_after)
                    print(f"  [{len(saved)} saved, {len(missing_after)} not found]")
                else:
                    print(f"  [{len(saved)} saved]")
            else:
                total_skipped += 1
                print("  [no match]")
        except Exception as e:
            total_failed += 1
            logging.debug(f"Scrape failed for {sc.appname}: {e}")
            print(f"  [error: {e}]")

    print()
    print(f"  Results:")
    print(f"    Downloaded:  {total_downloaded}")
    print(f"    Not found:   {total_skipped}")
    if total_failed:
        print(f"    Failed:      {total_failed}")
    print()
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """Refresh / re-scrape artwork for all game types.

    Covers all three populations in one pass unless filtered:
      1. SRM-managed games  (artworkCache.json entries -> SteamGridDB)
      2. Non-ROM shortcuts  (Heroic, Wine, flatpaks -> full cascade)
      3. ROM shortcuts      (SGM-imported ROMs -> full cascade)

    Filters: --srm-only, --shortcuts-only, --roms-only, --system X, --game NAME
    Scope:   --all re-downloads even existing art; default = missing only
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from refresh import refresh_images

    try:
        if config_exists():
            config = get_resolved_config()
        else:
            print("Error: Config required for refresh. Run 'sgm config init' first.")
            return 1
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    if not config.get('api_key'):
        print("Error: SteamGridDB API key required for refresh.")
        print("Run 'sgm config set api_key YOUR_KEY' or 'sgm config init'")
        print("Get a free key at: https://www.steamgriddb.com/profile/preferences/api")
        return 1

    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')

    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    force_all   = getattr(args, 'all', False)
    mode        = 'all' if force_all else 'missing'
    image_type  = getattr(args, 'type', None)
    system_filter = getattr(args, 'system', None)
    game_filter   = getattr(args, 'game', None)
    srm_only      = getattr(args, 'srm_only', False)
    shortcuts_only = getattr(args, 'shortcuts_only', False)
    roms_only     = getattr(args, 'roms_only', False)
    dry_run       = args.dry_run

    # Determine which populations to process
    # --system or --game implies ROM scope; --shortcuts-only or --srm-only narrow further
    do_srm       = not shortcuts_only and not roms_only
    do_shortcuts = not srm_only and not roms_only and not system_filter and not game_filter
    do_roms      = not srm_only and not shortcuts_only

    if system_filter or game_filter or roms_only:
        do_srm = False
        do_shortcuts = False

    overall_rc = 0

    # ── Population 1: SRM artworkCache entries ──────────────────
    if do_srm:
        print(f"\n  ── SRM-managed art (artworkCache.json) ──")
        rc = refresh_images(
            grid_path=grid_path,
            api_key=config['api_key'],
            srm_cache_path=config.get('srm_artwork_cache', ''),
            mode=mode,
            image_type=image_type,
            batch_size=config.get('batch_size', 50),
            dry_run=dry_run,
        )
        if rc != 0:
            overall_rc = rc

    # ── Population 2: Non-ROM shortcuts (Heroic, Wine, flatpaks) ─
    if do_shortcuts:
        print(f"\n  ── Non-ROM shortcuts (Heroic / other) ──")
        rc = _cmd_refresh_shortcuts(
            config=config,
            steam_path=steam_path,
            grid_path=grid_path,
            image_type=image_type,
            dry_run=dry_run,
        )
        if rc != 0:
            overall_rc = rc

    # ── Population 3: ROM shortcuts ──────────────────────────────
    if do_roms:
        # Reuse the ROM art scrape logic by synthesising a compatible args object
        class _RomArgs:
            pass
        rom_args = _RomArgs()
        rom_args.system  = system_filter
        rom_args.game    = game_filter
        rom_args.all     = force_all
        rom_args.dry_run = dry_run
        if not (system_filter or game_filter):
            print(f"\n  ── ROM shortcuts ──")
        rc = _cmd_rom_art_scrape(rom_args)
        if rc != 0:
            overall_rc = rc

    return overall_rc


def cmd_config(args: argparse.Namespace) -> int:
    """Manage configuration."""
    from config import interactive_setup, show_config, set_config_value
    
    sub = args.config_action
    
    if sub == 'init':
        interactive_setup()
        return 0
    elif sub == 'show':
        show_config()
        return 0
    elif sub == 'set':
        if not args.key or not args.value:
            print("Usage: sgm config set <key> <value>")
            return 1
        set_config_value(args.key, args.value)
        return 0
    else:
        # Default: show config
        show_config()
        return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Manage the auto-detection monitor."""
    from monitor import install_monitor, uninstall_monitor, monitor_status, run_monitor_check
    
    sub = args.monitor_action
    
    if sub == 'install':
        return install_monitor()
    elif sub == 'uninstall':
        return uninstall_monitor()
    elif sub == 'status':
        return monitor_status()
    elif sub == 'run':
        return run_monitor_check()
    else:
        return monitor_status()


def cmd_rom_art(args: argparse.Namespace) -> int:
    """Handle `sgm rom art` subcommands."""
    art_action = getattr(args, 'rom_art_action', None)

    if art_action == 'remap':
        return _cmd_rom_art_remap(args)

    if art_action == 'fix-mount':
        return _cmd_rom_art_fix_mount(args)

    if art_action == 'clear':
        return _cmd_rom_art_clear(args)

    if art_action == 'scrape':
        return _cmd_rom_art_scrape(args)

    print("Usage: sgm rom art <clear|scrape|remap|fix-mount> [options]")
    return 1


def _extract_rom_path_from_exe(exe: str) -> Optional[Path]:
    """Extract the ROM file path from a RetroArch/emulator shortcut exe string.

    RetroArch shortcuts generated by SGM take the form:
        "/usr/bin/flatpak" run org.libretro.RetroArch -L /core.so "/path/to/rom.ext"

    Strategy: find the last quoted token that looks like a ROM file path (has
    an extension, contains a path separator, and is not a .so/.dll library).

    Args:
        exe: The exe field from a SteamShortcut.

    Returns:
        Path to the ROM file if detected, None otherwise.
    """
    import re as _re
    import shlex as _shlex

    _lib_exts = {'.so', '.dll', '.dylib', ''}

    # Pass 1: last quoted token
    for candidate in reversed(_re.findall(r'"([^"]+)"', exe)):
        p = Path(candidate)
        if p.suffix.lower() not in _lib_exts and '/' in candidate:
            return p

    # Pass 2: last unquoted token that looks like a file path
    try:
        for token in reversed(_shlex.split(exe)):
            p = Path(token)
            if p.suffix.lower() not in _lib_exts and '/' in token:
                return p
    except Exception:
        pass

    return None


def _cmd_rom_art_scrape(args: argparse.Namespace) -> int:
    """Scrape missing (or all) artwork for ROM shortcuts by system or game name.

    This is the go-to command when 'rom import' missed art for some games.
    It re-runs the cascade scraper only for games that are missing images.
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import get_existing_shortcuts, generate_short_app_id
    from systems import get_system
    from art_scraper import (
        CascadeScraper, save_grid_images, ART_TYPES,
        store_art_in_cache, DEFAULT_CACHE_DIR,
    )

    try:
        if config_exists():
            config = get_resolved_config()
            steam_path = Path(config['steam_path'])
            user_id = config.get('steam_user_id', 'auto')
        else:
            steam_path = find_steam_path()
            config = {'steam_path': str(steam_path), 'steam_user_id': 'auto'}
            user_id = 'auto'
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    if not config.get('api_key'):
        print("Error: No SteamGridDB API key configured.")
        print("Run: sgm config set api_key YOUR_KEY")
        return 1

    uid = user_id if user_id != 'auto' else None
    try:
        grid_path = find_grid_path(steam_path, uid)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    system_filter = getattr(args, 'system', None)
    game_filter = (getattr(args, 'game', None) or '').lower()
    force_all = getattr(args, 'all', False)

    # Load all shortcuts, filter by system tag
    all_shortcuts = get_existing_shortcuts(steam_path, uid)

    if system_filter:
        sys_def = get_system(system_filter)
        if not sys_def:
            print(f"Error: Unknown system '{system_filter}'.")
            print("Run 'sgm rom systems' to see supported system names.")
            return 1
        all_tags = sys_def.all_category_tags()
        shortcuts = [
            sc for sc in all_shortcuts
            if any(str(v) in all_tags for v in sc.tags.values())
        ]
        sys_info = {system_filter: sys_def}
    else:
        # All ROM shortcuts (any known system tag)
        from systems import SYSTEMS
        all_rom_tags: set[str] = set()
        sys_info: dict = {}
        for sname, sdef in SYSTEMS.items():
            all_rom_tags.update(sdef.all_category_tags())
            sys_info[sname] = sdef
        shortcuts = [
            sc for sc in all_shortcuts
            if any(str(v) in all_rom_tags for v in sc.tags.values())
        ]

    # Filter by game name if specified
    if game_filter:
        shortcuts = [sc for sc in shortcuts if game_filter in sc.appname.lower()]

    if not shortcuts:
        print(f"\nNo matching ROM shortcuts found.\n")
        return 0

    # Build work list — check which art is missing unless --all
    _art_suffixes = {
        'tall': ('p.png', 'p.jpg'),
        'wide': ('.png', '.jpg'),
        'hero': ('_hero.png', '_hero.jpg'),
        'logo': ('_logo.png', '_logo.jpg'),
        'icon': ('_icon.png', '_icon.jpg'),
    }

    work_list = []  # list of (shortcut, short_id, missing_types, sys_def)
    for sc in shortcuts:
        short_id = str(sc.appid & 0xFFFFFFFF)
        if force_all:
            missing = set(ART_TYPES)
        else:
            missing = set()
            for art_type, suffixes in _art_suffixes.items():
                if not any((grid_path / f"{short_id}{s}").exists() for s in suffixes):
                    missing.add(art_type)
        if missing:
            # Find the sys_def for this shortcut's tag
            sc_tag_val = next((str(v) for v in sc.tags.values()), '')
            matched_sys = None
            for sname, sdef in sys_info.items():
                if sc_tag_val in sdef.all_category_tags():
                    matched_sys = sdef
                    break
            work_list.append((sc, short_id, missing, matched_sys, sc_tag_val))

    if not work_list:
        print(f"\n  All {len(shortcuts)} shortcut(s) already have complete artwork.\n")
        return 0

    print(f"\n  ROM Art Scrape")
    if system_filter:
        print(f"  System:   {get_system(system_filter).fullname}")
    if game_filter:
        print(f"  Game:     {game_filter!r}")
    print(f"  To scrape: {len(work_list)} game(s) with missing art\n")

    if args.dry_run:
        for sc, short_id, missing, _, _tag in work_list[:30]:
            missing_str = ', '.join(sorted(missing))
            rom_path_dry = _extract_rom_path_from_exe(sc.exe)
            hash_hint = "  [hash]" if (rom_path_dry and rom_path_dry.exists()) else ""
            print(f"  {sc.appname[:55]:55s}  missing: {missing_str}{hash_hint}")
        if len(work_list) > 30:
            print(f"  ... and {len(work_list) - 30} more")
        print(f"\n  [hash] = ROM file found, hash-based lookup will be used")
        print(f"  (dry run — no changes made)\n")
        return 0

    scraper = CascadeScraper(config)
    cache_dir = Path(config.get('art_cache_dir', '') or DEFAULT_CACHE_DIR).expanduser()

    GREEN = "\033[32m"; YELLOW = "\033[33m"; RED = "\033[31m"
    CYAN = "\033[36m"; GREY = "\033[90m"; RESET = "\033[0m"; BOLD = "\033[1m"
    BAR_WIDTH = 20

    def _bar(current: int, total_b: int, width: int = BAR_WIDTH) -> str:
        if total_b <= 0:
            return f"[{'─' * width}]"
        filled = int(width * current / total_b)
        return f"[{'█' * filled}{'─' * (width - filled)}]"

    fetched = 0
    failed = 0
    total = len(work_list)

    for idx, (sc, short_id, missing, sdef, sc_tag_val) in enumerate(work_list, 1):
        label = sc.appname[:50].ljust(50)
        counter = f"{GREY}[{idx:>{len(str(total))}}/{total}]{RESET}"

        ss_id = sdef.screenscraper_id if sdef else None
        tgdb_id = sdef.thegamesdb_id if sdef else None

        # Extract ROM file path from shortcut exe for hash-based lookup
        rom_path: Optional[Path] = _extract_rom_path_from_exe(sc.exe)
        if rom_path and not rom_path.exists():
            rom_path = None  # File not accessible (e.g. SD card not mounted)
        rom_filename: Optional[str] = rom_path.name if rom_path else None

        # Hash progress callback — shows hashing bar then clears when done
        hash_label = (rom_filename or sc.appname)[:28].ljust(28)

        def _make_hash_cb(lbl: str, ctr: str):
            def _cb(done: int, total_b: int) -> None:
                bar = _bar(done, total_b)
                pct = int(100 * done / total_b) if total_b else 0
                print(f"\r  {ctr} {GREY}Hashing {lbl} {bar} {pct:3d}%{RESET}",
                      end="", flush=True)
            return _cb

        hash_cb = _make_hash_cb(hash_label, counter) if rom_path else None

        try:
            artwork = scraper.scrape_game(
                title=sc.appname,
                system_name=sc_tag_val if not sdef else sdef.fullname,
                screenscraper_id=ss_id,
                thegamesdb_id=tgdb_id,
                rom_path=rom_path,
                rom_filename=rom_filename,
                hash_progress_cb=hash_cb,
                wanted_types=missing,
            )
            if artwork:
                saved = save_grid_images(short_id, artwork, grid_path)
                if saved:
                    store_art_in_cache(sc.appname, sdef.fullname if sdef else '', saved, cache_dir=cache_dir)
                n = len(saved)
                colour = GREEN if n == len(missing) else YELLOW
                print(f"\r  {counter} {colour}{label}{RESET} {colour}{n}/{len(missing)} images{RESET}  ")
                fetched += n
            else:
                print(f"\r  {counter} {RED}{label}{RESET} no art found           ")
                failed += 1
        except Exception as e:
            print(f"\r  {counter} {RED}{label}{RESET} error: {e}           ")
            failed += 1

    print(f"\n  {BOLD}Results:{RESET} {GREEN}{total - failed} games with art{RESET}, "
          f"{RED}{failed} not found{RESET}, {fetched} images downloaded\n")
    return 0

def _cmd_rom_art_remap(args: argparse.Namespace) -> int:
    """Rename grid art files from old SRM appids to current SGM appids.

    Reads an old shortcuts.vdf (typically a SRM backup) to discover the old
    app-IDs, then maps each game to its current SGM-format app-ID and renames
    the art files in the grid folder accordingly.  No API calls needed.
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import (
        read_shortcuts_vdf,
        generate_short_app_id,
        SteamShortcut,
    )

    backup_file = Path(args.backup)
    if not backup_file.exists():
        print(f"Error: backup file not found: {backup_file}")
        return 1

    # Resolve grid path
    cfg = get_resolved_config() if config_exists() else {}
    steam_path_cfg = cfg.get('steam_path', '')
    user_id = cfg.get('steam_user_id', 'auto')
    try:
        sp = find_steam_path()
        grid_path = find_grid_path(sp, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # Read old shortcuts
    old_shortcuts = read_shortcuts_vdf(backup_file)
    print(f"Read {len(old_shortcuts)} shortcuts from {backup_file.name}")

    # Read current shortcuts to get the correct exe format per game
    vdf_path = grid_path.parent / 'shortcuts.vdf'
    current_shortcuts = read_shortcuts_vdf(vdf_path) if vdf_path.exists() else []
    # Build lookup: appname -> list of current shortcuts
    current_by_name: dict[str, list[SteamShortcut]] = {}
    for sc in current_shortcuts:
        current_by_name.setdefault(sc.appname, []).append(sc)

    art_suffixes = [
        'p.png', 'p.jpg', '.png', '.jpg',
        '_hero.png', '_hero.jpg',
        '_logo.png', '_logo.jpg',
        '_icon.png', '_icon.jpg',
    ]

    renames: list[tuple[Path, Path]] = []
    skipped_no_art = 0
    skipped_same_id = 0
    skipped_no_new = 0
    skipped_conflict = 0

    for old_sc in old_shortcuts:
        old_short = generate_short_app_id(old_sc.exe, old_sc.appname)

        # Find the matching current shortcut for this game
        candidates = current_by_name.get(old_sc.appname, [])
        if not candidates:
            skipped_no_new += 1
            continue

        # Prefer candidate whose tag matches the old one, otherwise take first
        old_tag = list(old_sc.tags.values())[0] if old_sc.tags else ''
        new_sc = candidates[0]
        for c in candidates:
            c_tag = list(c.tags.values())[0] if c.tags else ''
            if c_tag == old_tag:
                new_sc = c
                break

        new_short = generate_short_app_id(new_sc.exe, new_sc.appname)

        if old_short == new_short:
            skipped_same_id += 1
            continue

        # Determine whether this old appid has any art at all
        has_any_art = any(
            (grid_path / f"{old_short}{s}").exists() or
            (grid_path / f"{old_short}{s}").is_symlink()
            for s in art_suffixes
        )
        if not has_any_art:
            skipped_no_art += 1
            continue

        # Collect per-suffix renames
        for suffix in art_suffixes:
            old_file = grid_path / f"{old_short}{suffix}"
            new_file = grid_path / f"{new_short}{suffix}"

            if not old_file.exists() and not old_file.is_symlink():
                continue  # no art for this type

            if new_file.exists() and not getattr(args, 'overwrite', False):
                skipped_conflict += 1
                continue  # new appid already has art, keep it

            renames.append((old_file, new_file))

    if not renames:
        print("Nothing to rename.")
        print(f"  Same appid already:       {skipped_same_id}")
        print(f"  No matching new shortcut: {skipped_no_new}")
        print(f"  No art under old appid:   {skipped_no_art}")
        if skipped_conflict:
            print(f"  New appid already has art (use --overwrite to replace): {skipped_conflict}")
        return 0

    verb = "[DRY RUN] Would rename" if args.dry_run else "Renaming"
    print(f"\n{verb} {len(renames)} art file(s)...")

    renamed = 0
    errors = 0
    for old_file, new_file in sorted(renames):
        if getattr(args, 'verbose', False):
            print(f"  {old_file.name}  ->  {new_file.name}")
        if not args.dry_run:
            try:
                old_file.rename(new_file)
                renamed += 1
            except OSError as e:
                print(f"  Error renaming {old_file.name}: {e}")
                errors += 1
        else:
            renamed += 1

    if args.dry_run:
        print(f"\n(dry run — nothing changed)")
    else:
        print(f"\nDone. Renamed {renamed} file(s){f', {errors} error(s)' if errors else ''}.")

    print(f"\nStats:")
    print(f"  Renamed:              {renamed}")
    print(f"  Already same appid:   {skipped_same_id}")
    print(f"  No matching shortcut: {skipped_no_new}")
    print(f"  No old art found:     {skipped_no_art}")
    if skipped_conflict:
        print(f"  Skipped (conflict):   {skipped_conflict}  (use --overwrite to replace)")
    return 0


def _cmd_rom_art_fix_mount(args: argparse.Namespace) -> int:
    """Rename grid art from old mount-path appids to current mount-path appids.

    When the SD card mount point changes (e.g. /run/media/deck/primary ->
    /run/media/primary), the shortcut app IDs change because they embed the
    ROM path.  This command auto-detects the path change and renames the
    art files without needing an old shortcuts.vdf backup.
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import read_shortcuts_vdf, generate_short_app_id

    cfg = get_resolved_config() if config_exists() else {}
    user_id = cfg.get('steam_user_id', 'auto')
    try:
        sp = find_steam_path()
        grid_path = find_grid_path(sp, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    vdf_path = grid_path.parent / 'shortcuts.vdf'
    if not vdf_path.exists():
        print(f"Error: shortcuts.vdf not found at {vdf_path}")
        return 1

    current_shortcuts = read_shortcuts_vdf(vdf_path)
    print(f"Loaded {len(current_shortcuts)} shortcuts from shortcuts.vdf")

    # Determine which old mount paths to try.
    # Allow user to pass --old-mount; otherwise auto-detect by checking common variants.
    old_mounts_arg = getattr(args, 'old_mount', None) or []
    if isinstance(old_mounts_arg, str):
        old_mounts_arg = [old_mounts_arg]

    # Auto-build candidate old mounts from current exe paths:
    # e.g. /run/media/primary -> /run/media/deck/primary
    #      /run/media/primary -> /media/primary
    current_mounts: set[str] = set()
    for sc in current_shortcuts:
        if '/run/media/' in sc.exe:
            # Extract mount point: everything from /run/media/ up to /Roms/
            import re
            m = re.search(r'(/run/media/[^"]+?)/Roms/', sc.exe)
            if m:
                current_mounts.add(m.group(1))

    if not current_mounts:
        print("No ROM paths found in shortcuts.vdf — nothing to do.")
        return 0

    # Build default candidates: insert or remove 'deck/' component
    auto_old: list[str] = []
    for mount in current_mounts:
        parts = mount.split('/')
        # /run/media/PRIMARY -> /run/media/deck/PRIMARY
        if 'deck' not in parts:
            idx = parts.index('media')
            variant = parts[:idx+1] + ['deck'] + parts[idx+1:]
            auto_old.append('/'.join(variant))
        # /run/media/deck/PRIMARY -> /run/media/PRIMARY
        if 'deck' in parts:
            variant = [p for p in parts if p != 'deck']
            auto_old.append('/'.join(variant))

    old_mounts = old_mounts_arg if old_mounts_arg else auto_old
    print(f"Current mount(s): {sorted(current_mounts)}")
    print(f"Trying old mount(s): {sorted(set(old_mounts))}")

    art_suffixes = [
        'p.png', 'p.jpg', '.png', '.jpg',
        '_hero.png', '_hero.jpg',
        '_logo.png', '_logo.jpg',
        '_icon.png', '_icon.jpg',
    ]

    renames: list[tuple[Path, Path]] = []
    skipped_same = 0
    skipped_no_art = 0
    skipped_conflict = 0

    for sc in current_shortcuts:
        new_short = generate_short_app_id(sc.exe, sc.appname)

        # Try each old mount substitution to find existing art
        for old_mount in set(old_mounts):
            # Replace current mount with old mount in exe
            old_exe = sc.exe
            for cur_mount in current_mounts:
                old_exe = old_exe.replace(cur_mount, old_mount)
            if old_exe == sc.exe:
                continue  # no substitution happened

            old_short = generate_short_app_id(old_exe, sc.appname)
            if old_short == new_short:
                skipped_same += 1
                continue

            has_old_art = any(
                (grid_path / f"{old_short}{s}").exists()
                for s in art_suffixes
            )
            if not has_old_art:
                continue  # try next old mount

            # Found art under old mount — queue renames
            for suffix in art_suffixes:
                old_file = grid_path / f"{old_short}{suffix}"
                new_file = grid_path / f"{new_short}{suffix}"
                if not old_file.exists():
                    continue
                if new_file.exists() and not getattr(args, 'overwrite', False):
                    skipped_conflict += 1
                    continue
                renames.append((old_file, new_file))
            break  # found the right old mount, no need to try others
        else:
            skipped_no_art += 1

    if not renames:
        print("Nothing to rename.")
        print(f"  Already same appid: {skipped_same}")
        print(f"  No old art found:   {skipped_no_art}")
        if skipped_conflict:
            print(f"  Conflicts (use --overwrite): {skipped_conflict}")
        return 0

    verb = "[DRY RUN] Would rename" if args.dry_run else "Renaming"
    print(f"\n{verb} {len(renames)} art file(s)...")

    renamed = 0
    errors = 0
    for old_file, new_file in sorted(renames):
        if getattr(args, 'verbose', False):
            print(f"  {old_file.name}  ->  {new_file.name}")
        if not args.dry_run:
            try:
                old_file.rename(new_file)
                renamed += 1
            except OSError as e:
                print(f"  Error renaming {old_file.name}: {e}")
                errors += 1
        else:
            renamed += 1

    if args.dry_run:
        print("(dry run — nothing changed)")
    else:
        print(f"\nDone. Renamed {renamed} file(s){f', {errors} error(s)' if errors else ''}.")

    print(f"\nStats:")
    print(f"  Renamed:        {renamed}")
    print(f"  No old art:     {skipped_no_art}")
    if skipped_conflict:
        print(f"  Conflicts:      {skipped_conflict}  (use --overwrite to replace)")
    return 0


def _cmd_rom_art_clear(args: argparse.Namespace) -> int:
    """Remove grid art for ROM games."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from rom_scanner import scan_rom_folder, scan_all_systems
    from systems import get_system
    from shortcuts import generate_shortcut_id, generate_short_app_id

    try:
        if config_exists():
            config = get_resolved_config()
            steam_path = Path(config['steam_path'])
            user_id = config.get('steam_user_id', 'auto')
        else:
            steam_path = find_steam_path()
            user_id = 'auto'
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    rom_path = Path(args.path)
    if not rom_path.exists():
        print(f"Error: ROM path not found: {rom_path}")
        return 1

    # Scan ROMs to find short IDs
    if args.system:
        sys_def = get_system(args.system)
        if not sys_def:
            print(f"Error: Unknown system '{args.system}'")
            return 1
        roms = scan_rom_folder(args.system, rom_path / args.system, sys_def)
        all_roms = {args.system: roms} if roms else {}
    else:
        all_roms = scan_all_systems(rom_path)

    if not all_roms:
        print("No ROMs found.")
        return 0

    title_filter = (args.game or "").lower()

    _art_suffixes = (".png", ".jpg", "p.png", "p.jpg",
                     "_hero.png", "_hero.jpg",
                     "_logo.png", "_logo.jpg",
                     "_icon.png", "_icon.jpg")

    to_delete: list[Path] = []

    for system, roms in sorted(all_roms.items()):
        sys_def = get_system(system)
        if not sys_def:
            continue
        for rom in roms:
            if title_filter and title_filter not in rom.steam_title.lower():
                continue

            exe = sys_def.emulator.get_steam_exe(str(rom.path))
            short_id = generate_short_app_id(exe, rom.steam_title)

            for suffix in _art_suffixes:
                img = grid_path / f"{short_id}{suffix}"
                if img.exists() or img.is_symlink():
                    to_delete.append(img)

    if not to_delete:
        print("No art files found to remove.")
        return 0

    print(f"\n{'[DRY RUN] Would remove' if args.dry_run else 'Removing'} "
          f"{len(to_delete)} art file(s):\n")

    removed = 0
    for img in sorted(to_delete):
        print(f"  {img.name}")
        if not args.dry_run:
            try:
                img.unlink()
                removed += 1
            except OSError as e:
                print(f"    Error: {e}")

    if args.dry_run:
        print(f"\n(dry run — nothing deleted)\n")
    else:
        print(f"\nRemoved {removed} file(s).\n")

    return 0



def cmd_rom_remove(args: argparse.Namespace) -> int:
    """Remove all shortcuts and art for a given ROM system.

    Steps:
    1. Look up the system's Steam category tag (e.g. "Atari 2600").
    2. Find all shortcuts in shortcuts.vdf tagged with that category.
    3. Collect their short app IDs so we can delete their art.
    4. Remove matching shortcuts from shortcuts.vdf.
    5. Delete all grid art files for those app IDs.
    6. Mark the Steam collection as deleted.
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import (
        get_existing_shortcuts,
        write_shortcuts_vdf,
        find_shortcuts_vdf,
        generate_short_app_id,
        delete_steam_collections,
    )
    from systems import get_system

    system_name = args.system
    sys_def = get_system(system_name)
    if not sys_def:
        print(f"Error: Unknown system '{system_name}'.")
        print("Run 'sgm rom systems' to see supported system names.")
        return 1

    try:
        if config_exists():
            config = get_resolved_config()
            steam_path = Path(config['steam_path'])
            user_id = config.get('steam_user_id', 'auto')
        else:
            steam_path = find_steam_path()
            user_id = 'auto'
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    uid = user_id if user_id != 'auto' else None

    try:
        grid_path = find_grid_path(steam_path, uid)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # All category tag names for this system (including legacy aliases)
    all_tags = sys_def.all_category_tags()
    primary_tag = sys_def.get_steam_category()

    # Find matching shortcuts
    all_shortcuts = get_existing_shortcuts(steam_path, uid)
    matching = [
        sc for sc in all_shortcuts
        if any(str(v) in all_tags for v in sc.tags.values())
    ]

    if not matching:
        print(f"\nNo shortcuts found for system '{system_name}' "
              f"(category: {primary_tag!r}).\n")
        return 0

    # Collect art files to delete
    _art_suffixes = (
        ".png", ".jpg", "p.png", "p.jpg",
        "_hero.png", "_hero.jpg",
        "_logo.png", "_logo.jpg",
        "_icon.png", "_icon.jpg",
    )
    art_files: list[Path] = []
    for sc in matching:
        short_id = str(sc.appid & 0xFFFFFFFF)
        for suffix in _art_suffixes:
            img = grid_path / f"{short_id}{suffix}"
            if img.exists() or img.is_symlink():
                art_files.append(img)

    print(f"\n  Remove System: {sys_def.fullname}")
    print(f"  Category tag:  {primary_tag}")
    print(f"  Shortcuts:     {len(matching)}")
    print(f"  Art files:     {len(art_files)}\n")

    if not args.yes and not args.dry_run:
        answer = input(
            f"  Remove {len(matching)} shortcuts and {len(art_files)} art files? [y/N] "
        ).strip().lower()
        if answer not in ('y', 'yes'):
            print("  Aborted.\n")
            return 0

    if args.dry_run:
        print("  [DRY RUN] Would remove shortcuts:")
        for sc in sorted(matching, key=lambda s: s.appname)[:20]:
            print(f"    {sc.appname}")
        if len(matching) > 20:
            print(f"    ... and {len(matching) - 20} more")
        print(f"\n  [DRY RUN] Would delete {len(art_files)} art files.")
        print(f"  [DRY RUN] Would mark collection {primary_tag!r} as deleted.\n")
        print("  (dry run — no changes made)\n")
        return 0

    # 1. Remove shortcuts from VDF
    keep = [sc for sc in all_shortcuts if sc not in matching]
    try:
        vdf_path = find_shortcuts_vdf(steam_path, uid)
        write_shortcuts_vdf(vdf_path, keep)
        print(f"  Removed {len(matching)} shortcut(s) from shortcuts.vdf")
    except Exception as e:
        print(f"  Error updating shortcuts.vdf: {e}")
        return 1

    # 2. Delete art files
    removed_art = 0
    for img in art_files:
        try:
            img.unlink()
            removed_art += 1
        except OSError as e:
            print(f"  Warning: Could not delete {img.name}: {e}")
    print(f"  Deleted {removed_art} art file(s)")

    # 3. Mark Steam collection as deleted
    delete_steam_collections(steam_path, all_tags, uid)
    print(f"  Marked collection {primary_tag!r} as deleted in Steam")

    notify_steam_reload()

    print(f"\n  Done. Restart Steam to see changes.\n")
    return 0


def cmd_rom(args: argparse.Namespace) -> int:
    """ROM management commands."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from rom_scanner import scan_all_systems, scan_rom_folder
    from systems import get_system, list_supported_systems
    from shortcuts import (
        generate_short_app_id, generate_shortcut_id,
        SteamShortcut, get_existing_shortcuts, add_shortcuts,
    )
    from shortcuts import update_steam_collections
    from art_scraper import ART_TYPES, CascadeScraper, save_grid_images, store_art_in_cache, DEFAULT_CACHE_DIR

    sub = args.rom_action

    # ── sgm rom scan ─────────────────────────────────────────────
    if sub == 'scan':
        rom_path = Path(args.path)
        if not rom_path.is_dir():
            print(f"Error: ROM path not found: {rom_path}")
            return 1

        if args.system:
            system_def = get_system(args.system)
            if not system_def:
                print(f"Error: Unknown system '{args.system}'")
                print(f"Supported: {', '.join(list_supported_systems())}")
                return 1
            roms = scan_rom_folder(args.system, rom_path / args.system, system_def)
            all_roms = {args.system: roms} if roms else {}
        else:
            all_roms = scan_all_systems(rom_path)

        if not all_roms:
            print("No ROMs found.")
            return 0

        total = 0
        print(f"\n ROM Scan Results ({rom_path})\n")
        for system, roms in sorted(all_roms.items()):
            system_def = get_system(system)
            label = system_def.fullname if system_def else system
            print(f"  {label} ({system}):")
            for rom in roms:
                disc_info = f" [Disc {rom.disc_number}]" if rom.disc_number and rom.disc_number > 1 else ""
                region_info = f" ({rom.region})" if rom.region else ""
                print(f"    {rom.clean_title}{disc_info}{region_info}")
            total += len(roms)
            print()

        print(f"  Total: {total} ROMs across {len(all_roms)} systems\n")
        return 0

    # ── sgm rom import ───────────────────────────────────────────
    elif sub == 'import':
        rom_path = Path(args.path)
        if not rom_path.is_dir():
            print(f"Error: ROM path not found: {rom_path}")
            return 1

        try:
            if config_exists():
                config = get_resolved_config()
            else:
                print("Error: Config required for ROM import. Run 'sgm config init' first.")
                return 1
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1

        steam_path = Path(config['steam_path'])
        user_id = config.get('steam_user_id', 'auto')

        try:
            grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1

        # Scan ROMs
        if args.system:
            system_def = get_system(args.system)
            if not system_def:
                print(f"Error: Unknown system '{args.system}'")
                return 1
            roms = scan_rom_folder(args.system, rom_path / args.system, system_def)
            all_roms = {args.system: roms} if roms else {}
        else:
            all_roms = scan_all_systems(rom_path)

        if not all_roms:
            print("No ROMs found to import.")
            return 0

        total_roms = sum(len(v) for v in all_roms.values())
        print(f"\nFound {total_roms} ROMs across {len(all_roms)} systems")

        if args.dry_run:
            print("[DRY RUN] Would create shortcuts and fetch artwork for:")
            for system, roms in sorted(all_roms.items()):
                sys_def = get_system(system)
                print(f"\n  {sys_def.fullname if sys_def else system}:")
                for rom in roms:
                    print(f"    {rom.steam_title}")
            return 0

        # Build shortcuts
        new_shortcuts = []
        for system, roms in sorted(all_roms.items()):
            sys_def = get_system(system)
            if not sys_def:
                continue

            for rom in roms:
                # Build exe in SRM-compatible format:
                #   '"/usr/bin/flatpak" run <emulator> [core_args] "/rom/path"'
                # launch_options is intentionally empty.
                # This matches SRM's shortcut format so existing grid art works.
                exe = sys_def.emulator.get_steam_exe(str(rom.path))
                launch_opts = ""

                appid = generate_shortcut_id(exe, rom.steam_title)
                short_id = generate_short_app_id(exe, rom.steam_title)

                sc = SteamShortcut(
                    appid=appid,
                    appname=rom.steam_title,
                    exe=exe,
                    start_dir=f'"{str(rom.path.parent)}"',
                    launch_options=launch_opts,
                    tags={"0": sys_def.get_steam_category()},
                )
                new_shortcuts.append((sc, rom, sys_def, short_id))

        if not new_shortcuts:
            print("No shortcuts to create.")
            return 0

        # Add shortcuts to VDF
        print(f"\nAdding {len(new_shortcuts)} shortcuts to Steam...")
        shortcuts_only = [sc for sc, _, _, _ in new_shortcuts]
        # Collect all tag names (current + legacy aliases) for systems being
        # imported so we can purge old SRM-format entries (different app IDs
        # due to exe format) and any entries using obsolete tag strings.
        categories_being_imported: set[str] = set()
        for _, _, sys_def, _ in new_shortcuts:
            categories_being_imported.update(sys_def.all_category_tags())
        added, skipped = add_shortcuts(steam_path, shortcuts_only,
                                      user_id if user_id != 'auto' else None,
                                      replace_existing=True,
                                      remove_by_tags=categories_being_imported)
        print(f"  Added: {added}")

        # Update Steam library collections in localconfig.vdf
        categories_to_ids: dict[str, list[int]] = {}
        for sc, rom, sys_def, short_id in new_shortcuts:
            cat = sys_def.get_steam_category()
            # Use the unsigned short app ID — Steam's collection system expects
            # unsigned 32-bit integers (positive), NOT the signed int32 stored in
            # shortcuts.vdf.  short_id = generate_short_app_id() returns the correct
            # unsigned value (sc.appid & 0xFFFFFFFF).
            categories_to_ids.setdefault(cat, []).append(int(short_id))
        uid = user_id if user_id != 'auto' else None
        update_steam_collections(steam_path, categories_to_ids, uid)

        # Fetch artwork if we have API keys
        if not args.no_art and config.get('api_key'):
            # Filter to only games missing art when --missing-art is set
            art_targets = new_shortcuts
            if getattr(args, 'missing_art', False):
                # Check each game's short_id directly against the grid folder.
                # Checking by name was unreliable when multiple shortcuts share
                # the same title (e.g. two "Druid" entries with different IDs).
                _art_suffixes = (
                    ".png", ".jpg", "p.png", "p.jpg",
                    "_hero.png", "_hero.jpg",
                    "_logo.png", "_logo.jpg",
                    "_icon.png", "_icon.jpg",
                )
                art_targets = [
                    (sc, rom, sys_def, sid)
                    for sc, rom, sys_def, sid in new_shortcuts
                    if not any((grid_path / f"{sid}{suffix}").exists()
                               for suffix in _art_suffixes)
                ]
                skipped_art = len(new_shortcuts) - len(art_targets)
                print(f"\n{skipped_art} games already have art, "
                      f"fetching for {len(art_targets)} missing...")
            else:
                print(f"\nFetching artwork for {len(art_targets)} games...")

            scraper = CascadeScraper(config)
            fetched = 0
            failed = 0
            total = len(art_targets)

            # ANSI colour helpers (no external deps)
            GREEN  = "\033[32m"
            YELLOW = "\033[33m"
            RED    = "\033[31m"
            CYAN   = "\033[36m"
            GREY   = "\033[90m"
            RESET  = "\033[0m"
            BOLD   = "\033[1m"

            BAR_WIDTH = 20   # characters for the progress bar

            def _bar(current: int, total_b: int, width: int = BAR_WIDTH) -> str:
                """Return a [####.....] progress bar string."""
                if total_b <= 0:
                    return f"[{'?' * width}]"
                filled = int(width * current / total_b)
                return f"[{CYAN}{'█' * filled}{GREY}{'░' * (width - filled)}{RESET}]"


            for idx, (sc, rom, sys_def, short_id) in enumerate(art_targets, 1):
                game_label = rom.steam_title[:40].ljust(40)
                counter    = f"{GREY}[{idx:>{len(str(total))}}/{total}]{RESET}"

                # --- Hashing phase (inline progress, updated by scraper) ---
                rom_size = rom.path.stat().st_size if rom.path.exists() else 0
                game_label_inner = rom.filename[:28].ljust(28)

                def _make_hash_cb(label, size, ctr):
                    def _cb(done, total_b):
                        bar = _bar(done, total_b)
                        pct = int(100 * done / total_b) if total_b else 0
                        print(f"\r  {ctr} {GREY}Hashing {label} {bar} {pct:3d}%{RESET}",
                              end="", flush=True)
                    return _cb

                hash_cb = _make_hash_cb(game_label_inner, rom_size, counter)

                try:
                    artwork = scraper.scrape_game(
                        title=rom.clean_title,
                        system_name=rom.system,
                        screenscraper_id=sys_def.screenscraper_id,
                        thegamesdb_id=sys_def.thegamesdb_id,
                        rom_filename=rom.filename,
                        rom_path=rom.path,
                        hash_progress_cb=hash_cb,
                    )

                    if artwork:
                        saved = save_grid_images(short_id, artwork, grid_path)
                        # Store newly downloaded art in the persistent cache
                        if saved:
                            cache_dir = Path(cfg.get('art_cache_dir', '') or DEFAULT_CACHE_DIR).expanduser()
                            store_art_in_cache(rom.clean_title, str(rom.system), saved, cache_dir=cache_dir)
                        n_saved = len(saved)
                        n_total = len(ART_TYPES)
                        art_bar = _bar(n_saved, n_total)
                        colour  = GREEN if n_saved == n_total else YELLOW
                        print(f"\r  {counter} {colour}{game_label}{RESET} "
                              f"{art_bar} {colour}{n_saved}/{n_total} images{RESET}  ")
                        fetched += n_saved
                    else:
                        print(f"\r  {counter} {RED}{game_label}{RESET} "
                              f"{_bar(0, 1)} {RED}no art found{RESET}          ")
                        failed += 1

                except Exception as e:
                    print(f"\r  {counter} {RED}{game_label}{RESET} "
                          f"error: {e}                    ")
                    failed += 1

            total_imgs = fetched
            ok_games   = total - failed
            print(f"\n  {BOLD}Results:{RESET} "
                  f"{GREEN}{ok_games} games with art{RESET}, "
                  f"{RED}{failed} not found{RESET}, "
                  f"{total_imgs} images downloaded\n")
        elif not config.get('api_key'):
            print("\n  Skipping artwork (no API key configured)")
            print("  Run 'sgm config set api_key YOUR_KEY' to enable artwork downloads")

        notify_steam_reload()
        return 0
    elif sub == 'systems':
        print(f"\n Supported Systems\n")
        systems = list_supported_systems()
        for name in systems:
            sys_def = get_system(name)
            print(f"  {name:<16} {sys_def.fullname:<30} [{sys_def.manufacturer}]")
        print(f"\n  Total: {len(systems)} systems\n")
        return 0
    elif sub == 'art':
        return cmd_rom_art(args)
    elif sub == 'collections':
        return _cmd_rom_collections(args)

    return 0


def _cmd_rom_collections(args: argparse.Namespace) -> int:
    """Re-write Steam collections from the current shortcuts.vdf.

    Reads all existing non-Steam shortcuts, groups them by their first tag
    (which is the system/category name), then writes native ``uc-*`` collections
    to cloud-storage-namespace-1.json.  Old ``srm-*`` collections are deleted.

    This is useful after a ``rom import`` to apply collections without redoing
    the full import, or to repair collections that Steam didn't pick up.
    """
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import (
        read_shortcuts_vdf,
        update_steam_collections,
    )

    cfg = get_resolved_config() if config_exists() else {}
    steam_path_cfg = cfg.get('steam_path', '')
    user_id = cfg.get('steam_user_id', 'auto')

    try:
        sp = find_steam_path()
        grid_path = find_grid_path(sp, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    vdf_path = grid_path.parent / 'shortcuts.vdf'
    if not vdf_path.exists():
        print(f"Error: shortcuts.vdf not found at {vdf_path}")
        return 1

    shortcuts = read_shortcuts_vdf(vdf_path)
    print(f"Read {len(shortcuts)} shortcuts from shortcuts.vdf")

    # Group by first tag (= system category)
    by_category: dict[str, list[int]] = {}
    for sc in shortcuts:
        tag = list(sc.tags.values())[0] if sc.tags else None
        if tag:
            by_category.setdefault(tag, []).append(sc.appid)

    print(f"Found {len(by_category)} categories:")
    for cat, ids in sorted(by_category.items()):
        print(f"  {cat:<35} {len(ids):>4} games")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    ok = update_steam_collections(sp, by_category, user_id if user_id != 'auto' else None)
    if ok:
        total = sum(len(v) for v in by_category.values())
        print(f"\n[OK] Wrote {len(by_category)} collections ({total} total memberships) to cloud storage.")
    else:
        print("\nError: failed to update collections.")
        return 1
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    """Handle `sgm cache` subcommands."""
    cache_action = getattr(args, 'cache_action', None)

    if cache_action == 'populate':
        return _cmd_cache_populate(args)

    if cache_action == 'stats':
        return _cmd_cache_stats(args)

    print("Usage: sgm cache <populate|stats>")
    return 1


def _cmd_cache_populate(args: argparse.Namespace) -> int:
    """Scan existing grid art and store it in the persistent art cache."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import read_shortcuts_vdf
    from art_scraper import populate_cache_from_grid, DEFAULT_CACHE_DIR

    cfg = get_resolved_config() if config_exists() else {}
    user_id = cfg.get('steam_user_id', 'auto')
    cache_dir_cfg = cfg.get('art_cache_dir', '')
    cache_dir = Path(cache_dir_cfg).expanduser() if cache_dir_cfg else DEFAULT_CACHE_DIR

    try:
        sp = find_steam_path()
        grid_path = find_grid_path(sp, user_id if user_id != 'auto' else None)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    vdf_path = grid_path.parent / 'shortcuts.vdf'
    if not vdf_path.exists():
        print(f"Error: shortcuts.vdf not found at {vdf_path}")
        return 1

    shortcuts = read_shortcuts_vdf(vdf_path)
    print(f"Scanning {len(shortcuts)} shortcuts for existing art...")
    print(f"Cache directory: {cache_dir}")

    if args.dry_run:
        # Just count without writing
        from shortcuts import generate_short_app_id
        would_cache = 0
        for sc in shortcuts:
            sid = generate_short_app_id(sc.exe, sc.appname)
            has = any((grid_path / f"{sid}{s}").exists()
                      for s in ['p.png','p.jpg','.png','.jpg','_hero.png','_hero.jpg',
                                '_logo.png','_logo.jpg','_icon.png','_icon.jpg'])
            if has:
                would_cache += 1
        print(f"[DRY RUN] Would cache art for {would_cache} games.")
        return 0

    cached = populate_cache_from_grid(shortcuts, grid_path, cache_dir=cache_dir)
    print(f"Cached art for {cached} games into {cache_dir}")
    return 0


def _cmd_cache_stats(args: argparse.Namespace) -> int:
    """Show art cache statistics."""
    from art_scraper import DEFAULT_CACHE_DIR
    from config import config_exists, get_resolved_config

    cfg = get_resolved_config() if config_exists() else {}
    cache_dir_cfg = cfg.get('art_cache_dir', '')
    cache_dir = Path(cache_dir_cfg).expanduser() if cache_dir_cfg else DEFAULT_CACHE_DIR

    if not cache_dir.exists():
        print(f"Art cache is empty (directory does not exist): {cache_dir}")
        return 0

    entries = [d for d in cache_dir.iterdir() if d.is_dir()]
    total_files = sum(len(list(e.iterdir())) for e in entries)
    total_size = sum(f.stat().st_size for e in entries for f in e.iterdir() if f.is_file())

    print(f"Art cache: {cache_dir}")
    print(f"  Games cached:  {len(entries)}")
    print(f"  Total files:   {total_files}")
    print(f"  Total size:    {total_size / 1024 / 1024:0.1f} MB")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export a portable backup bundle."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import get_existing_shortcuts
    from portable import export_bundle, list_bundles

    sub = args.export_action

    if sub == 'create':
        try:
            if config_exists():
                config = get_resolved_config()
            else:
                steam_path = find_steam_path()
                config = {
                    'steam_path': str(steam_path),
                    'steam_user_id': 'auto',
                    'backup_path': str(Path.home() / '.local' / 'share' / 'sgm' / 'backups'),
                }
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1

        steam_path = Path(config['steam_path'])
        user_id = config.get('steam_user_id', 'auto')
        uid = user_id if user_id != 'auto' else None

        try:
            grid_path = find_grid_path(steam_path, uid)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return 1

        shortcuts = get_existing_shortcuts(steam_path, uid)
        output_dir = Path(args.output) if args.output else Path(config.get(
            'backup_path', str(Path.home() / '.local' / 'share' / 'sgm' / 'backups')
        ))

        print(f"\nExporting grid images and shortcuts...")
        bundle_path = export_bundle(
            grid_path=grid_path,
            shortcuts=shortcuts,
            output_dir=output_dir,
            bundle_name=args.name,
            steam_user_id=user_id,
        )
        print(f"  Bundle created: {bundle_path}")
        return 0

    elif sub == 'list':
        try:
            if config_exists():
                config = get_resolved_config()
                backup_path = Path(config.get('backup_path',
                    str(Path.home() / '.local' / 'share' / 'sgm' / 'backups')))
            else:
                backup_path = Path.home() / '.local' / 'share' / 'sgm' / 'backups'
        except Exception:
            backup_path = Path.home() / '.local' / 'share' / 'sgm' / 'backups'

        bundles = list_bundles(backup_path)
        if not bundles:
            print("No export bundles found.")
            return 0

        print(f"\n Export Bundles\n")
        for b in bundles:
            print(f"  {b['name']}")
            print(f"    Created: {b['created']}")
            print(f"    Source:  {b['source_device']}")
            print(f"    Games:   {b['total_games']}  Images: {b['total_images']}  Size: {b['total_size_mb']:0.1f} MB")
            if b['systems']:
                systems_str = ", ".join(f"{k}({v})" for k, v in sorted(b['systems'].items()))
                print(f"    Systems: {systems_str}")
            print()
        return 0

    return 0


def cmd_import_bundle(args: argparse.Namespace) -> int:
    """Import a portable backup bundle."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from portable import import_bundle

    bundle_path = Path(args.bundle)
    if not bundle_path.is_dir():
        print(f"Error: Bundle not found: {bundle_path}")
        return 1

    try:
        if config_exists():
            config = get_resolved_config()
        else:
            steam_path = find_steam_path()
            config = {
                'steam_path': str(steam_path),
                'steam_user_id': 'auto',
            }
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    uid = user_id if user_id != 'auto' else None

    try:
        grid_path = find_grid_path(steam_path, uid)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    mode = "replace" if args.replace else ("missing" if args.missing else "merge")

    print(f"\nImporting bundle: {bundle_path}")
    print(f"Mode: {mode}")
    if getattr(args, 'with_shortcuts', False):
        print(f"Shortcuts: will be restored from bundle")

    imported, skipped, errors = import_bundle(
        bundle_path=bundle_path,
        grid_path=grid_path,
        mode=mode,
        dry_run=args.dry_run,
        with_shortcuts=getattr(args, 'with_shortcuts', False),
    )

    print(f"\n  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    if errors:
        print(f"  Errors:   {errors}")
    print()
    return 0


def cmd_heroic(args: argparse.Namespace) -> int:
    """Handle `sgm heroic` — scan Heroic games and create Steam shortcuts with art."""
    from config import config_exists, get_resolved_config
    from steam import find_steam_path, find_grid_path
    from shortcuts import (
        read_shortcuts_vdf,
        add_shortcuts,
        generate_short_app_id,
        generate_shortcut_id,
        SteamShortcut,
    )
    from heroic import find_heroic_config, get_heroic_games, make_heroic_launch_options, is_heroic_flatpak
    from art_scraper import CascadeScraper

    dry_run = getattr(args, 'dry_run', False)
    no_art = getattr(args, 'no_art', False)
    runner_filter = getattr(args, 'runner', None)  # 'legendary', 'gog', 'nile', or None
    list_only = getattr(args, 'list', False)

    # --- Find Heroic config ---
    heroic_config = find_heroic_config()
    if heroic_config is None:
        print("Error: Heroic Games Launcher not found.")
        print("Looked in:")
        from heroic import HEROIC_CONFIG_PATHS
        for p in HEROIC_CONFIG_PATHS:
            print(f"  {p}")
        return 1

    print(f"  Heroic config: {heroic_config}")

    # --- Get installed games ---
    games = get_heroic_games(heroic_config)
    if runner_filter:
        games = [g for g in games if g['runner'] == runner_filter]

    if not games:
        print(f"No Heroic games found{f' for runner: {runner_filter}' if runner_filter else ''}.")
        return 0

    # --- List mode ---
    if list_only:
        runners = {'legendary': 'Epic', 'gog': 'GOG', 'nile': 'Amazon'}
        print(f"\n  Heroic Games ({len(games)} installed)\n")
        for g in sorted(games, key=lambda x: x['title'].lower()):
            store = runners.get(g['runner'], g['runner'])
            print(f"  [{store:6s}] {g['title']}")
        print()
        return 0

    # --- Resolve Steam paths ---
    try:
        if config_exists():
            config = get_resolved_config()
        else:
            steam_path = find_steam_path()
            config = {'steam_path': str(steam_path), 'steam_user_id': 'auto'}
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    uid = user_id if user_id != 'auto' else None

    try:
        grid_path = find_grid_path(steam_path, uid)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # --- Read existing shortcuts to skip already-imported games ---
    vdf_path = grid_path.parent / 'shortcuts.vdf'
    existing_shortcuts = read_shortcuts_vdf(vdf_path) if vdf_path.exists() else []
    existing_names = {sc.appname.lower() for sc in existing_shortcuts}

    flatpak = is_heroic_flatpak()
    runners_label = {'legendary': 'Epic', 'gog': 'GOG', 'nile': 'Amazon'}

    # --- Summary ---
    print(f"\n  Heroic Import\n")
    print(f"  Games found:  {len(games)}")
    print(f"  Installation: {'Flatpak' if flatpak else 'Native'}")
    print(f"  Grid folder:  {grid_path}")
    print()

    # --- Set up art scraper ---
    scraper = None
    if not no_art:
        api_key = config.get('api_key', '')
        if api_key:
            try:
                scraper = CascadeScraper(config)
            except Exception as e:
                logging.warning(f"Could not initialize art scraper: {e}")
        else:
            print("  [WARN] No API key configured — skipping artwork download.")
            print("         Run: sgm config set api_key YOUR_KEY\n")

    # --- Process games ---
    added = 0
    skipped_existing = 0
    art_downloaded = 0
    art_failed = 0
    new_shortcuts: list[SteamShortcut] = []

    for game in sorted(games, key=lambda x: x['title'].lower()):
        title = game['title']
        app_name = game['app_name']
        runner = game['runner']
        store = runners_label.get(runner, runner)

        # Check if already exists
        if title.lower() in existing_names:
            skipped_existing += 1
            logging.debug(f"Skipping (already exists): {title}")
            continue

        exe, launch_options = make_heroic_launch_options(app_name, runner, flatpak)
        appid = generate_shortcut_id(exe, title)
        short_id = generate_short_app_id(exe, title)

        print(f"  [{store:6s}] {title}")

        if not dry_run:
            sc = SteamShortcut(
                appid=appid,
                appname=title,
                exe=exe,
                start_dir='',
                launch_options=launch_options,
                is_hidden=0,
                allow_desktop_config=1,
                allow_overlay=1,
                openvr=0,
                devkit=0,
                devkit_override_app_id=0,
                tags={0: 'Heroic'},
                icon='',
                last_play_time=0,
            )
            new_shortcuts.append(sc)

            # Download art
            if scraper:
                from art_scraper import save_grid_images
                suffix_map = {'tall': 'p', 'wide': '', 'hero': '_hero', 'logo': '_logo', 'icon': '_icon'}
                missing_types = set()
                for art_type, suffix in suffix_map.items():
                    has = any(
                        (grid_path / f"{short_id}{suffix}{ext}").exists()
                        for ext in ('.png', '.jpg')
                    )
                    if not has:
                        missing_types.add(art_type)

                if missing_types:
                    try:
                        artwork = scraper.scrape_game(title, wanted_types=missing_types)
                        if artwork:
                            saved = save_grid_images(str(short_id), artwork, grid_path)
                            art_downloaded += len(saved)
                            if len(saved) < len(missing_types):
                                art_failed += len(missing_types) - len(saved)
                    except Exception as e:
                        logging.debug(f"Art scrape failed for {title}: {e}")
                        art_failed += len(missing_types)

        added += 1

    # --- Write shortcuts ---
    if not dry_run and new_shortcuts:
        added_count, skipped_count = add_shortcuts(
            steam_path, new_shortcuts,
            uid,
            replace_existing=False,
        )
        print()
        print(f"  [OK] Added {added_count} new shortcut(s) to shortcuts.vdf")

    # --- Summary ---
    print()
    print(f"  Results:")
    print(f"    Added:           {added}")
    print(f"    Already exists:  {skipped_existing}")
    if scraper and not no_art:
        print(f"    Art downloaded:  {art_downloaded}")
        if art_failed:
            print(f"    Art failed:      {art_failed}")
    if dry_run:
        print(f"\n  (dry run — no changes made)")
    else:
        print(f"\n  Restart Steam to see the new entries in your library.")
    print()
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='sgm',
        description='SteamGrid Manager - Protect your custom Steam library artwork',
    )
    parser.add_argument('--version', action='version', version=f'sgm {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # status
    sub_status = subparsers.add_parser('status', help='Show current state')
    sub_status.set_defaults(func=cmd_status)
    
    # backup
    sub_backup = subparsers.add_parser('backup', help='Backup grid images')
    sub_backup.add_argument('--dry-run', action='store_true', help='Show what would be backed up')
    sub_backup.set_defaults(func=cmd_backup)
    
    # restore
    sub_restore = subparsers.add_parser('restore', help='Restore from backup')
    sub_restore.add_argument('--timestamp', '-t', help='Restore from specific backup')
    sub_restore.add_argument('--list', '-l', action='store_true', help='List available backups')
    sub_restore.add_argument('--dry-run', action='store_true', help='Show what would be restored')
    sub_restore.add_argument('--force', '-f', action='store_true', help='Skip confirmation')
    sub_restore.set_defaults(func=cmd_restore)
    
    # refresh
    sub_refresh = subparsers.add_parser(
        'refresh',
        help='Refresh / re-scrape artwork for all games (SRM + ROMs + shortcuts)',
        description=(
            'Re-downloads missing artwork for every game type in one pass.\n'
            'Covers SRM-managed art, ROM shortcuts, and non-ROM shortcuts (Heroic, Wine, etc.).\n\n'
            'Examples:\n'
            '  sgm refresh               # re-scrape all missing art\n'
            '  sgm refresh --all         # force re-download of ALL art\n'
            '  sgm refresh --system c64  # only C64\n'
            '  sgm refresh --game Contra # only games matching "Contra"\n'
            '  sgm refresh --srm-only    # only SRM artworkCache entries\n'
            '  sgm refresh --dry-run     # preview without downloading'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub_refresh.add_argument('--all', action='store_true',
                             help='Re-download all art even if files already exist')
    sub_refresh.add_argument('--system', '-s', metavar='SYSTEM',
                             help='Only refresh ROMs for this system (e.g. c64, atari2600)')
    sub_refresh.add_argument('--game', '-g', metavar='GAME',
                             help='Only refresh games whose name contains this text')
    sub_refresh.add_argument('--srm-only', dest='srm_only', action='store_true',
                             help='Only refresh SRM artworkCache entries (SteamGridDB only)')
    sub_refresh.add_argument('--shortcuts-only', dest='shortcuts_only', action='store_true',
                             help='Only refresh non-ROM shortcuts (Heroic, Wine, flatpaks)')
    sub_refresh.add_argument('--roms-only', dest='roms_only', action='store_true',
                             help='Only refresh ROM shortcuts (skip SRM and non-ROM)')
    sub_refresh.add_argument('--type', choices=['tall', 'wide', 'hero', 'logo', 'icon'],
                             help='Only refresh a specific art type')
    sub_refresh.add_argument('--dry-run', action='store_true',
                             help='Show what would be downloaded without making changes')
    sub_refresh.set_defaults(func=cmd_refresh)
    
    # config
    sub_config = subparsers.add_parser('config', help='Manage configuration')
    config_sub = sub_config.add_subparsers(dest='config_action')
    config_sub.add_parser('init', help='Interactive setup')
    config_sub.add_parser('show', help='Show current config')
    config_set = config_sub.add_parser('set', help='Set a config value')
    config_set.add_argument('key', nargs='?', help='Config key')
    config_set.add_argument('value', nargs='?', help='Config value')
    sub_config.set_defaults(func=cmd_config)
    
    # monitor
    sub_monitor = subparsers.add_parser('monitor', help='Manage auto-detection service')
    monitor_sub = sub_monitor.add_subparsers(dest='monitor_action')
    monitor_sub.add_parser('install', help='Install systemd service')
    monitor_sub.add_parser('uninstall', help='Remove systemd service')
    monitor_sub.add_parser('status', help='Show service status')
    monitor_sub.add_parser('run', help='Run detection check once')
    sub_monitor.set_defaults(func=cmd_monitor)

    # rom
    sub_rom = subparsers.add_parser('rom', help='ROM management (scan, import, systems)')
    rom_sub = sub_rom.add_subparsers(dest='rom_action')

    rom_scan = rom_sub.add_parser('scan', help='Scan ROM folders and show found games')
    rom_scan.add_argument('path', help='Path to ROM root directory')
    rom_scan.add_argument('--system', '-s', help='Scan only this system folder')

    rom_import = rom_sub.add_parser('import', help='Import ROMs as Steam shortcuts with artwork')
    rom_import.add_argument('path', help='Path to ROM root directory')
    rom_import.add_argument('--system', '-s', help='Import only this system')
    rom_import.add_argument('--no-art', action='store_true', help='Skip artwork download')
    rom_import.add_argument('--missing-art', action='store_true',
                            help='Only fetch art for games that have no grid images yet')
    rom_import.add_argument('--dry-run', action='store_true', help='Show what would be imported')

    rom_sub.add_parser('systems', help='List supported systems')

    rom_art = rom_sub.add_parser('art', help='Manage ROM artwork')
    rom_art_sub = rom_art.add_subparsers(dest='rom_art_action')

    rom_art_scrape = rom_art_sub.add_parser(
        'scrape',
        help='Scrape missing artwork for ROM shortcuts (alias for: sgm refresh --roms-only)')
    rom_art_scrape.add_argument(
        '--system', '-s',
        help='Only scrape art for this system (e.g. c64, atari2600)')
    rom_art_scrape.add_argument(
        '--game', '-g',
        help='Only scrape art for games whose name contains this text')
    rom_art_scrape.add_argument(
        '--all', action='store_true',
        help='Re-download all art even if files already exist')
    rom_art_scrape.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be scraped without downloading')

    rom_art_clear = rom_art_sub.add_parser('clear', help='Remove grid art for ROM games')
    rom_art_clear.add_argument('path', help='Path to ROM root directory')
    rom_art_clear.add_argument('--system', '-s', help='Only clear art for this system')
    rom_art_clear.add_argument('--game', '-g', help='Only clear art for games matching this title')
    rom_art_clear.add_argument('--dry-run', action='store_true',
                               help='Show what would be removed without deleting')
    rom_art_remap = rom_art_sub.add_parser(
        'remap', help='Rename art files from old SRM appids to current SGM appids')
    rom_art_remap.add_argument(
        '--backup', required=True,
        help='Path to old shortcuts.vdf (SRM backup) containing original app IDs')
    rom_art_remap.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be renamed without making changes')
    rom_art_remap.add_argument(
        '--overwrite', action='store_true',
        help='Overwrite new-appid art files that already exist')
    rom_art_remap.add_argument(
        '--verbose', '-v', action='store_true',
        help='Print each rename operation')

    rom_art_fix_mount = rom_art_sub.add_parser(
        'fix-mount',
        help='Rename art files after SD card mount path change (e.g. /media/deck/primary -> /media/primary)')
    rom_art_fix_mount.add_argument(
        '--old-mount', dest='old_mount', action='append', default=[],
        metavar='PATH',
        help='Old mount prefix to replace (auto-detected if not specified)')
    rom_art_fix_mount.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be renamed without making changes')
    rom_art_fix_mount.add_argument(
        '--overwrite', action='store_true',
        help='Overwrite destination art files that already exist')
    rom_art_fix_mount.add_argument(
        '--verbose', '-v', action='store_true',
        help='Print each rename operation')

    sub_rom.set_defaults(func=cmd_rom)

    rom_remove = rom_sub.add_parser(
        'remove', help='Remove all shortcuts and art for a system')
    rom_remove.add_argument(
        '--system', '-s', required=True,
        help='System name to remove (e.g. atari2600, c64). Run "sgm rom systems" for names.')
    rom_remove.add_argument(
        '--yes', '-y', action='store_true',
        help='Skip confirmation prompt')
    rom_remove.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be removed without making changes')
    rom_remove.set_defaults(func=cmd_rom_remove)

    rom_collections = rom_sub.add_parser(
        'collections', help='Re-write Steam collections from current shortcuts.vdf')
    rom_collections.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be written without making changes')

    # export
    sub_export = subparsers.add_parser('export', help='Export portable backup bundle')

    # cache
    sub_cache = subparsers.add_parser('cache', help='Manage the persistent art cache')
    cache_sub = sub_cache.add_subparsers(dest='cache_action')
    cache_populate = cache_sub.add_parser(
        'populate', help='Seed art cache from existing grid folder art')
    cache_populate.add_argument(
        '--dry-run', action='store_true',
        help='Show how many games would be cached without writing')
    cache_sub.add_parser('stats', help='Show art cache statistics')
    sub_cache.set_defaults(func=cmd_cache)
    export_sub = sub_export.add_subparsers(dest='export_action')

    export_create = export_sub.add_parser('create', help='Create export bundle')
    export_create.add_argument('--output', '-o', help='Output directory')
    export_create.add_argument('--name', '-n', help='Bundle name')
    export_sub.add_parser('list', help='List available bundles')
    sub_export.set_defaults(func=cmd_export)

    # import (bundle)
    sub_import = subparsers.add_parser('import', help='Import portable backup bundle')
    sub_import.add_argument('bundle', help='Path to bundle directory')
    sub_import.add_argument('--replace', action='store_true', help='Overwrite existing images')
    sub_import.add_argument('--missing', action='store_true', help='Only import missing art types')
    sub_import.add_argument('--dry-run', action='store_true', help='Show what would be imported')
    sub_import.add_argument('--with-shortcuts', action='store_true',
                            help='Also restore shortcuts.vdf from bundle (for cross-device restore)')
    sub_import.set_defaults(func=cmd_import_bundle)

    # heroic (Heroic Games Launcher integration)
    sub_heroic = subparsers.add_parser('heroic', help='Import Heroic Games as Steam shortcuts')
    sub_heroic.add_argument('--list', action='store_true', help='List installed Heroic games without importing')
    sub_heroic.add_argument('--runner', choices=['legendary', 'gog', 'nile'],
                            help='Only process one store (legendary=Epic, gog=GOG, nile=Amazon)')
    sub_heroic.add_argument('--no-art', action='store_true', help='Skip artwork download')
    sub_heroic.add_argument('--dry-run', action='store_true', help='Show what would be added without making changes')
    sub_heroic.set_defaults(func=cmd_heroic)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Setup logging
    log_level = 'debug' if args.verbose else 'info'
    try:
        from config import load_config, config_exists
        if config_exists():
            cfg = load_config()
            if not args.verbose:
                log_level = cfg.get('log_level', 'info')
            setup_logging(log_level, cfg.get('log_file'))
        else:
            setup_logging(log_level)
    except Exception:
        setup_logging(log_level)
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
