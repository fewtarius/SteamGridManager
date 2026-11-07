#!/usr/bin/env python3
"""Flatpak filesystem permissions for ROM playback.

Flatpak emulators run sandboxed and cannot reach the ROM library unless it is
granted explicitly. A read-only view is not enough: emulators such as PCSX2
keep an ISO cache beside the disc image and refuse to boot when that write
fails. SGM grants read-write access to the ROM roots it imports from, and can
audit every configured emulator for the same problem.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

logger = logging.getLogger(__name__)

FLATPAK_BIN = "flatpak"

# Actions reported by grant/audit calls.
GRANTED = "granted"
ALREADY_OK = "already-covered"
WOULD_GRANT = "would-grant"
FAILED = "failed"
NOT_INSTALLED = "not-installed"
UNAVAILABLE = "flatpak-unavailable"


@dataclass
class PermissionGrant:
    """Outcome of one emulator/path permission decision."""

    app_id: str
    path: str
    action: str
    detail: str = ""

    @property
    def changed(self) -> bool:
        """True when this entry represents an actual or pending change."""
        return self.action in (GRANTED, WOULD_GRANT, FAILED)


def flatpak_available() -> bool:
    """Check whether the flatpak CLI is present."""
    try:
        result = subprocess.run(
            [FLATPAK_BIN, "--version"], capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def installed_apps() -> Set[str]:
    """Return application IDs currently installed for this user.

    Returns:
        Set of flatpak application IDs. Empty when flatpak is unavailable.
    """
    try:
        result = subprocess.run(
            [FLATPAK_BIN, "list", "--app", "--columns=application"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"flatpak list failed: {e}")
        return set()

    if result.returncode != 0:
        logger.debug(f"flatpak list exited {result.returncode}: {result.stderr.strip()}")
        return set()

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _parse_context_filesystems(text: str) -> List[str]:
    """Pull filesystem entries out of a flatpak keyfile context dump.

    Args:
        text: Output of ``flatpak info --show-permissions`` or
            ``flatpak override --show``.

    Returns:
        Filesystem entries in declaration order, negations included.
    """
    entries: List[str] = []
    in_context = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("["):
            in_context = line == "[Context]"
            continue
        if not in_context or not line.startswith("filesystems="):
            continue
        for part in line.split("=", 1)[1].split(";"):
            part = part.strip()
            if part:
                entries.append(part)

    return entries


def effective_filesystems(app_id: str) -> List[str]:
    """Get the filesystem rules an installed app runs with.

    Args:
        app_id: Flatpak application ID.

    Returns:
        Filesystem entries, combining the app manifest and user overrides.
    """
    try:
        result = subprocess.run(
            [FLATPAK_BIN, "info", "--show-permissions", app_id],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"flatpak info failed for {app_id}: {e}")
        return []

    if result.returncode != 0:
        logger.debug(f"flatpak info exited {result.returncode} for {app_id}")
        return []

    return _parse_context_filesystems(result.stdout)


def _split_suffix(entry: str) -> tuple[str, str]:
    """Split a filesystem entry into its path and mode suffix."""
    for suffix in (":ro", ":rw", ":create"):
        if entry.endswith(suffix):
            return entry[: -len(suffix)], suffix[1:]
    return entry, ""


def covers_path_rw(entries: Sequence[str], path: Path,
                   home: Optional[Path] = None) -> bool:
    """Check whether the rules grant read-write access to a path.

    Read-only grants do not count. Emulators need to write sidecar files such
    as PCSX2's ISO cache beside the disc image.

    Args:
        entries: Filesystem entries from :func:`effective_filesystems`.
        path: Path that needs to be writable.
        home: Home directory used to resolve the ``home`` keyword.

    Returns:
        True when a rule grants read-write access covering ``path``.
    """
    home = home or Path.home()
    try:
        target = Path(path).expanduser().resolve()
        home_resolved = home.expanduser().resolve()
    except OSError:
        target = Path(path)
        home_resolved = home

    # A negation removes access that a broader rule granted, so collect the
    # revocations first and never treat them as grants.
    revoked = {e[1:] for e in entries if e.startswith("!")}

    for entry in entries:
        if entry.startswith("!"):
            continue

        base, mode = _split_suffix(entry)
        if mode == "ro" or entry in revoked:
            continue

        if base == "host":
            return True
        if base == "home":
            if target == home_resolved or home_resolved in target.parents:
                return True
            continue

        if base.startswith("xdg-"):
            # XDG aliases resolve to locations we do not control here; the
            # explicit path grant we add covers the requirement regardless.
            continue

        try:
            base_path = Path(base).resolve()
        except OSError:
            continue

        if target == base_path or base_path in target.parents:
            return True

    return False


def grant_path(app_id: str, path: Path, dry_run: bool = False,
               installed: Optional[Set[str]] = None) -> PermissionGrant:
    """Grant an app read-write access to a path.

    Args:
        app_id: Flatpak application ID.
        path: Directory to expose to the sandbox.
        dry_run: Report the change without applying it.
        installed: Pre-computed installed app set, to avoid extra subprocesses.

    Returns:
        PermissionGrant describing what happened.
    """
    target = Path(path).expanduser()
    try:
        target = target.resolve()
    except OSError:
        pass

    if installed is None:
        installed = installed_apps()
    if app_id not in installed:
        return PermissionGrant(app_id, str(target), NOT_INSTALLED,
                               "flatpak app not installed")

    if covers_path_rw(effective_filesystems(app_id), target):
        return PermissionGrant(app_id, str(target), ALREADY_OK)

    if dry_run:
        return PermissionGrant(app_id, str(target), WOULD_GRANT,
                               f"flatpak override --user --filesystem={target}")

    cmd = [FLATPAK_BIN, "override", "--user", f"--filesystem={target}", app_id]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        logger.error(f"flatpak override failed for {app_id}: {e}")
        return PermissionGrant(app_id, str(target), FAILED, str(e))

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        logger.error(f"flatpak override {app_id} exited {result.returncode}: {detail}")
        return PermissionGrant(app_id, str(target), FAILED, detail)

    logger.info(f"Granted {app_id} read-write access to {target}")
    return PermissionGrant(app_id, str(target), GRANTED)


def configured_flatpak_apps(registry) -> Dict[str, str]:
    """Map flatpak application IDs to emulator names from the registry.

    Args:
        registry: An :class:`emulators.EmulatorRegistry`.

    Returns:
        Dict of application ID to display name, deduplicated across emulators.
    """
    apps: Dict[str, str] = {}
    for plugin in registry.list_emulators().values():
        app_id = plugin.flatpak_id
        if app_id:
            apps.setdefault(app_id, plugin.display_name)
    return apps


def ensure_rom_access(app_ids: Sequence[str], rom_roots: Sequence[Path],
                      dry_run: bool = False) -> List[PermissionGrant]:
    """Ensure every listed app can read and write every ROM root.

    Args:
        app_ids: Flatpak application IDs to configure.
        rom_roots: Directories holding ROMs for those emulators.
        dry_run: Report the changes without applying them.

    Returns:
        One PermissionGrant per app/path pair. Empty if flatpak is unavailable.
    """
    if not app_ids or not rom_roots:
        return []

    if not flatpak_available():
        logger.debug("flatpak not available; skipping permission setup")
        return [PermissionGrant(app, str(root), UNAVAILABLE)
                for app in app_ids for root in rom_roots]

    known = installed_apps()
    return [grant_path(app, root, dry_run=dry_run, installed=known)
            for app in sorted(set(app_ids))
            for root in rom_roots]
