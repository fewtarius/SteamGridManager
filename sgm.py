#!/usr/bin/env python3
"""SteamGrid Manager (sgm) - Protect your custom Steam library artwork.

CLI tool that backs up, restores, and refreshes custom game images
on SteamOS/Linux. Prevents loss of artwork after Steam client updates.
"""

import argparse
import logging
import sys
from pathlib import Path

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


def cmd_refresh(args: argparse.Namespace) -> int:
    """Refresh images from SteamGridDB API."""
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
    
    mode = 'all' if args.all else 'missing'
    image_type = getattr(args, 'type', None)
    
    return refresh_images(
        grid_path=grid_path,
        api_key=config['api_key'],
        srm_cache_path=config.get('srm_artwork_cache', ''),
        mode=mode,
        image_type=image_type,
        batch_size=config.get('batch_size', 50),
        dry_run=args.dry_run,
    )


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

    if art_action == 'clear':
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

                exe = sys_def.emulator.get_executable()
                launch_opts = sys_def.emulator.get_launch_options(str(rom.path))
                if not exe.startswith('"'):
                    exe = f'"{exe}"'

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

    print("Usage: sgm rom art <clear> [options]")
    return 1


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
    from art_scraper import ART_TYPES, CascadeScraper, save_grid_images

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
                exe = sys_def.emulator.get_executable()
                launch_opts = sys_def.emulator.get_launch_options(str(rom.path))

                # Wrap exe in quotes for Steam
                if not exe.startswith('"'):
                    exe = f'"{exe}"'

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
        added, skipped = add_shortcuts(steam_path, shortcuts_only,
                                       user_id if user_id != 'auto' else None)
        print(f"  Added: {added}, Already existed: {skipped}")

        # Update Steam library collections in localconfig.vdf
        categories_to_ids: dict[str, list[int]] = {}
        for sc, rom, sys_def, short_id in new_shortcuts:
            cat = sys_def.get_steam_category()
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

    imported, skipped, errors = import_bundle(
        bundle_path=bundle_path,
        grid_path=grid_path,
        mode=mode,
        dry_run=args.dry_run,
    )

    print(f"\n  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    if errors:
        print(f"  Errors:   {errors}")
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
    sub_refresh = subparsers.add_parser('refresh', help='Refresh images from SteamGridDB')
    sub_refresh.add_argument('--all', action='store_true', help='Re-download everything')
    sub_refresh.add_argument('--missing', action='store_true', help='Only download missing (default)')
    sub_refresh.add_argument('--type', choices=['tall', 'wide', 'hero', 'logo', 'icon'], 
                            help='Only refresh specific type')
    sub_refresh.add_argument('--dry-run', action='store_true', help='Show what would be downloaded')
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
    rom_art_clear = rom_art_sub.add_parser('clear', help='Remove grid art for ROM games')
    rom_art_clear.add_argument('path', help='Path to ROM root directory')
    rom_art_clear.add_argument('--system', '-s', help='Only clear art for this system')
    rom_art_clear.add_argument('--game', '-g', help='Only clear art for games matching this title')
    rom_art_clear.add_argument('--dry-run', action='store_true',
                               help='Show what would be removed without deleting')

    sub_rom.set_defaults(func=cmd_rom)

    # export
    sub_export = subparsers.add_parser('export', help='Export portable backup bundle')
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
    sub_import.set_defaults(func=cmd_import_bundle)
    
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
