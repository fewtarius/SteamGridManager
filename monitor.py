#!/usr/bin/env python3
"""Grid folder monitor and auto-restore service.

Detects when Steam has wiped custom grid images and automatically
restores from the latest backup. Integrates with systemd user services.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "sgm-monitor"
SERVICE_DIR = Path.home() / '.config' / 'systemd' / 'user'

# Where to find sgm.py - resolve relative to this module
SGM_DIR = Path(__file__).resolve().parent


def _get_service_content() -> str:
    """Generate systemd service unit content."""
    sgm_py = SGM_DIR / 'sgm.py'
    return f"""[Unit]
Description=SteamGrid Manager - Grid Folder Monitor
Documentation=https://github.com/steamgriddb/sgm

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {sgm_py} monitor run
"""


def _get_timer_content() -> str:
    """Generate systemd timer unit content."""
    return f"""[Unit]
Description=SteamGrid Manager - Periodic Grid Check
Documentation=https://github.com/steamgriddb/sgm

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
"""


def install_monitor() -> int:
    """Install the systemd user service and timer.
    
    Returns:
        Exit code (0 for success).
    """
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    
    service_file = SERVICE_DIR / f"{SERVICE_NAME}.service"
    timer_file = SERVICE_DIR / f"{SERVICE_NAME}.timer"
    
    # Write service unit
    with open(service_file, 'w', encoding='utf-8') as f:
        f.write(_get_service_content())
    print(f"  Created {service_file}")
    
    # Write timer unit
    with open(timer_file, 'w', encoding='utf-8') as f:
        f.write(_get_timer_content())
    print(f"  Created {timer_file}")
    
    # Reload systemd and enable timer
    try:
        subprocess.run(
            ['systemctl', '--user', 'daemon-reload'],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ['systemctl', '--user', 'enable', '--now', f'{SERVICE_NAME}.timer'],
            check=True, capture_output=True, text=True,
        )
        print(f"\n  [OK] Monitor installed and started!")
        print(f"    Checks every 30 minutes after boot")
        print(f"    Run 'sgm monitor status' to check service state")
    except subprocess.CalledProcessError as e:
        print(f"  Warning: Could not enable service: {e.stderr}")
        print(f"  You may need to run: systemctl --user enable --now {SERVICE_NAME}.timer")
        return 1
    except FileNotFoundError:
        print(f"  Warning: systemctl not found. You may need to start the timer manually.")
        return 1
    
    return 0


def uninstall_monitor() -> int:
    """Remove the systemd user service and timer.
    
    Returns:
        Exit code (0 for success).
    """
    # Stop and disable
    try:
        subprocess.run(
            ['systemctl', '--user', 'disable', '--now', f'{SERVICE_NAME}.timer'],
            capture_output=True, text=True,
        )
        subprocess.run(
            ['systemctl', '--user', 'daemon-reload'],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        pass
    
    # Remove files
    service_file = SERVICE_DIR / f"{SERVICE_NAME}.service"
    timer_file = SERVICE_DIR / f"{SERVICE_NAME}.timer"
    
    for f in [service_file, timer_file]:
        if f.exists():
            f.unlink()
            print(f"  Removed {f}")
    
    print(f"\n  [OK] Monitor uninstalled.")
    return 0


def is_monitor_installed() -> bool:
    """Check if the monitor service is installed and enabled."""
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'is-enabled', f'{SERVICE_NAME}.timer'],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def monitor_status() -> int:
    """Show monitor service status.
    
    Returns:
        Exit code (0 for success).
    """
    print(f"\n  Monitor Status\n")
    
    # Check if installed
    service_file = SERVICE_DIR / f"{SERVICE_NAME}.service"
    timer_file = SERVICE_DIR / f"{SERVICE_NAME}.timer"
    
    print(f"  Service file: {'exists' if service_file.exists() else 'NOT FOUND'}")
    print(f"  Timer file:   {'exists' if timer_file.exists() else 'NOT FOUND'}")
    
    # Check systemd status
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'status', f'{SERVICE_NAME}.timer'],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            # Parse key info
            for line in result.stdout.split('\n'):
                line = line.strip()
                if any(x in line for x in ['Active:', 'Trigger:', 'Loaded:']):
                    print(f"  {line}")
        else:
            print(f"  Timer: Not active")
    except FileNotFoundError:
        print(f"  systemctl: Not available")
    
    print()
    return 0


def run_monitor_check() -> int:
    """Run a single monitoring check.
    
    Compares current grid state against the last known state.
    If a significant number of images are missing, auto-restores.
    
    Returns:
        Exit code (0 for success).
    """
    from config import config_exists, get_resolved_config, DATA_DIR
    from steam import find_grid_path
    from backup import get_grid_state, load_state, save_state, list_backups, restore_backup
    
    logger.info("Running monitor check...")
    
    if not config_exists():
        logger.error("No config found. Run 'sgm config init' first.")
        return 1
    
    config = get_resolved_config()
    steam_path = Path(config['steam_path'])
    user_id = config.get('steam_user_id', 'auto')
    backup_path = Path(config.get('backup_path', ''))
    threshold = config.get('auto_restore_threshold', 0.5)
    auto_restore = config.get('auto_restore', True)
    
    try:
        grid_path = find_grid_path(steam_path, user_id if user_id != 'auto' else None)
    except FileNotFoundError:
        logger.error("Grid folder not found")
        return 1
    
    # Get current state
    current = get_grid_state(grid_path)
    state_file = DATA_DIR / 'state.json'
    
    # Load last known state
    last_state = load_state(state_file)
    
    if last_state is None:
        # First run - save current state and exit
        logger.info(f"First run. Saving baseline state: {current['file_count']} files")
        save_state(current, state_file)
        return 0
    
    last_count = last_state.get('file_count', 0)
    current_count = current['file_count']
    
    # Check for wipe
    if last_count == 0:
        logger.info("No previous files recorded. Updating state.")
        save_state(current, state_file)
        return 0
    
    ratio = current_count / last_count if last_count > 0 else 1.0
    
    logger.info(f"Grid check: {current_count}/{last_count} files (ratio: {ratio:0.2f})")
    
    if ratio < threshold:
        logger.warning(
            f"Grid images appear wiped! "
            f"({current_count}/{last_count} files, ratio {ratio:0.2f} < threshold {threshold})"
        )
        
        if not auto_restore:
            logger.info("Auto-restore disabled. Run 'sgm restore' manually.")
            return 0
        
        # Check for available backups
        backups = list_backups(backup_path)
        if not backups:
            logger.error("No backups available for auto-restore!")
            return 1
        
        logger.info(f"Auto-restoring from backup: {backups[0]['timestamp']}")
        result = restore_backup(grid_path, backup_path, dry_run=False, force=True)
        
        if result == 0:
            # Update state after successful restore
            new_state = get_grid_state(grid_path)
            save_state(new_state, state_file)
            logger.info(f"Auto-restore complete. {new_state['file_count']} files restored.")
        
        return result
    else:
        # Update state
        save_state(current, state_file)
        logger.info("Grid images OK. State updated.")
        return 0
