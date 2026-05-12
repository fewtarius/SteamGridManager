#!/usr/bin/env python3
"""System definitions for SGM.

All system and emulator definitions are loaded from emulators.json.
This module provides backward-compatible interfaces to the emulator plugin system.

System definitions can be queried directly or through the emulator registry.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from emulators import (
    get_registry,
    get_system,
    get_system_emulator,
    SystemPlugin,
    EmulatorPlugin,
    list_all_systems,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Backward Compatibility Layer
# ═══════════════════════════════════════════════════════════════════════

def get_system_def(system_id: str) -> Optional[SystemPlugin]:
    """Get a system definition by ID (backward compatible API).

    Args:
        system_id: The system identifier (e.g., 'n64', 'psx').

    Returns:
        The SystemPlugin for the system, or None.
    """
    return get_system(system_id)


def get_system_ids() -> List[str]:
    """Get all known system IDs."""
    registry = get_registry()
    return list(registry.list_systems().keys())


# Alias for compatibility
list_supported_systems = get_system_ids


def get_system_info(system_id: str) -> Optional[Dict]:
    """Get system information as a dictionary.

    Args:
        system_id: The system identifier.

    Returns:
        Dictionary with system info, or None if not found.
    """
    system = get_system(system_id)
    if system:
        return system.get_info()
    return None


def get_extensions(system_id: str) -> Set[str]:
    """Get supported file extensions for a system."""
    system = get_system(system_id)
    if system:
        return system.extensions
    return set()


def is_rom_file(system_id: str, filename: str) -> bool:
    """Check if a filename is a valid ROM for a system."""
    system = get_system(system_id)
    if system:
        return system.is_rom_file(filename)
    return False


def get_default_emulator_id(system_id: str) -> str:
    """Get the default emulator ID for a system."""
    system = get_system(system_id)
    if system:
        return system.default_emulator_id
    return ""


def get_emulator_plugin(system_id: str, emulator_id: Optional[str] = None) -> Optional[EmulatorPlugin]:
    """Get the emulator plugin for a system.

    Args:
        system_id: The system name.
        emulator_id: Optional specific emulator ID (overrides default).

    Returns:
        The EmulatorPlugin, or None.
    """
    return get_system_emulator(system_id, emulator_id)


def list_systems() -> Dict[str, SystemPlugin]:
    """List all available systems."""
    return get_registry().list_systems()


class _SYSTEMS:
    """Backward-compatible SYSTEMS dict wrapper.

    Allows SYSTEMS.keys(), SYSTEMS.items(), SYSTEMS[...], etc.
    """

    def __iter__(self):
        return get_registry().list_systems().keys().__iter__()

    def __getitem__(self, key):
        return get_registry().list_systems()[key]

    def __contains__(self, key):
        return key in get_registry().list_systems()

    def keys(self):
        return get_registry().list_systems().keys()

    def values(self):
        return get_registry().list_systems().values()

    def items(self):
        return get_registry().list_systems().items()

    def get(self, key, default=None):
        return get_registry().list_systems().get(key, default)


# Backward-compatible SYSTEMS constant
SYSTEMS = _SYSTEMS()


def get_steam_category(system_id: str) -> str:
    """Get the Steam library category for a system."""
    system = get_system(system_id)
    if system:
        return system.steam_category
    return system_id.upper()


def list_supported_systems() -> List[str]:
    """Get list of supported system names."""
    return get_system_ids()


def all_category_tags(system_id: str) -> Set[str]:
    """Return all tag strings to match when purging old shortcuts.

    Includes the current category name plus any legacy aliases.
    """
    system = get_system(system_id)
    if system:
        return {system.steam_category}
    return {system_id.upper()}


# ═══════════════════════════════════════════════════════════════════════
# Legacy SystemDef wrapper (for code compatibility)
# ═══════════════════════════════════════════════════════════════════════

class SystemDef:
    """Backward-compatible SystemDef wrapper around SystemPlugin.

    This class provides the same interface as the old SystemDef dataclass
    for code that depends on the old structure.
    """

    def __init__(self, system_id: str):
        """Create a SystemDef wrapper for a system.

        Args:
            system_id: The system identifier.
        """
        self._system_id = system_id
        self._plugin = get_system(system_id)

    @property
    def name(self) -> str:
        """Folder name."""
        return self._system_id

    @property
    def fullname(self) -> str:
        """Display name."""
        if self._plugin:
            return self._plugin.fullname
        return self._system_id

    @property
    def manufacturer(self) -> str:
        """System manufacturer."""
        if self._plugin:
            return self._plugin.manufacturer
        return ""

    @property
    def extensions(self) -> Set[str]:
        """Valid ROM extensions."""
        if self._plugin:
            return self._plugin.extensions
        return set()

    @property
    def screenscraper_id(self) -> Optional[int]:
        """ScreenScraper platform ID."""
        if self._plugin:
            return self._plugin.screenscraper_id
        return None

    @property
    def thegamesdb_id(self) -> Optional[str]:
        """TheGamesDB platform ID."""
        if self._plugin:
            return self._plugin.thegamesdb_id
        return None

    @property
    def steam_category(self) -> Optional[str]:
        """Steam category tag."""
        if self._plugin:
            return self._plugin.steam_category
        return None

    @property
    def legacy_tags(self) -> Set[str]:
        """Legacy SRM/external tag names."""
        # Legacy tags not stored in new config, return empty set
        return set()

    @property
    def scan_as_dirs(self) -> bool:
        """Games installed as app directories (Vita3K style)."""
        if self._plugin:
            return self._plugin.scan_as_dirs
        return False

    @property
    def default_emulator(self) -> Optional[str]:
        """Default emulator plugin ID."""
        if self._plugin:
            return self._plugin.default_emulator_id
        return None

    @property
    def release_year(self) -> Optional[int]:
        """Release year."""
        if self._plugin:
            return self._plugin.release_year
        return None

    @property
    def hardware_type(self) -> str:
        """Hardware type."""
        if self._plugin:
            return self._plugin.hardware_type
        return "console"

    @property
    def skip_extensions(self) -> Set[str]:
        """Extensions to skip (save files, etc.)."""
        return {
            ".srm", ".state", ".state1", ".state2", ".state3", ".state4",
            ".state5", ".sav", ".oops", ".cfg", ".nfo", ".txt", ".xml",
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".db", ".ini",
            ".log", ".bak", ".old", ".sync-conflict"
        }

    @property
    def emulator(self):
        """Get EmulatorConfig-like object for backward compatibility."""
        from systems import get_emulator_plugin
        plugin = get_emulator_plugin(self._system_id)
        if plugin:
            return EmulatorConfigWrapper(plugin)
        return None

    def is_rom_file(self, filename: str) -> bool:
        """Check if a filename is a valid ROM for this system."""
        if self._plugin:
            return self._plugin.is_rom_file(filename)

        lower = filename.lower()
        ext = Path(filename).suffix.lower()

        if filename.startswith("."):
            return False

        if ext in self.skip_extensions:
            return False

        if ext == ".bin" and "(Track" in filename:
            return False

        return ext in self.extensions

    def get_steam_category(self) -> str:
        """Get the Steam library category for this system."""
        return self.steam_category or self.fullname

    def all_category_tags(self) -> Set[str]:
        """Return all tag strings to match when purging old shortcuts."""
        return {self.get_steam_category()} | self.legacy_tags

    def get_default_emulator_id(self) -> str:
        """Get the default emulator plugin ID for this system."""
        if self.default_emulator:
            return self.default_emulator
        if self._plugin and self._plugin.emulator:
            emulator = self._plugin.emulator
            if hasattr(emulator, 'core'):
                return f"retroarch/{emulator.core}"
            if emulator.flatpak_id:
                return emulator.flatpak_id
        return "retroarch"

    def get_retroarch_core(self) -> Optional[str]:
        """Get the RetroArch core if this system uses RetroArch."""
        if self._plugin and self._plugin.emulator:
            if hasattr(self._plugin.emulator, 'core'):
                return self._plugin.emulator.core
        return None


class EmulatorConfigWrapper:
    """Backward-compatible wrapper around EmulatorPlugin.

    Provides the same interface as the old EmulatorConfig dataclass.
    """

    def __init__(self, plugin: EmulatorPlugin):
        self._plugin = plugin

    @property
    def emulator(self) -> str:
        """Executable name or path."""
        if self._plugin.flatpak_id:
            return f"/usr/bin/flatpak run {self._plugin.flatpak_id}"
        if self._plugin.executable:
            return self._plugin.executable
        return self._plugin.id

    @property
    def core(self) -> Optional[str]:
        """RetroArch core name (if applicable)."""
        if hasattr(self._plugin, 'core'):
            return self._plugin.core
        return None

    @property
    def flatpak_id(self) -> Optional[str]:
        """Flatpak app ID."""
        return self._plugin.flatpak_id

    @property
    def launch_args(self) -> str:
        """Template for launch arguments."""
        return self._plugin.launch_args

    @property
    def launch_mode(self) -> str:
        """Launch mode: 'rom' or 'title_id'."""
        return self._plugin.launch_mode

    def get_executable(self) -> str:
        """Get the full executable path/command."""
        return self.emulator

    def get_launch_options(self, rom_path: str) -> str:
        """Get launch options for a specific ROM."""
        return self._plugin.launch_args.replace("{rom}", rom_path)

    def get_steam_exe(self, rom_path: str) -> str:
        """Build the Steam shortcut 'exe' field in SRM-compatible format."""
        return self._plugin.get_steam_exe(rom_path)


# ═══════════════════════════════════════════════════════════════════════
# Vita3K Helpers (kept for backward compatibility)
# ═══════════════════════════════════════════════════════════════════════

_VITA3K_BINARY: Optional[str] = None


def _find_vita3k_binary() -> str:
    """Find the Vita3K executable path.

    Search order:
    1. ``~/.config/Vita3K/Vita3K``
    2. ``/usr/bin/Vita3K``
    3. ``/usr/local/bin/Vita3K``
    4. ``Vita3K`` (PATH fallback)
    """
    global _VITA3K_BINARY
    if _VITA3K_BINARY is not None:
        return _VITA3K_BINARY

    candidates = [
        Path.home() / '.config' / 'Vita3K' / 'Vita3K',
        Path('/usr/bin/Vita3K'),
        Path('/usr/local/bin/Vita3K'),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            _VITA3K_BINARY = str(candidate)
            return _VITA3K_BINARY

    _VITA3K_BINARY = 'Vita3K'
    return _VITA3K_BINARY


def find_vita3k_data_dir() -> Optional[Path]:
    """Find the Vita3K data directory containing installed games."""
    from emulators import get_emulator

    # Use the emulator plugin's data_dir property
    vita3k = get_emulator("vita3k")
    if vita3k and hasattr(vita3k, 'data_dir'):
        return vita3k.data_dir

    # Fallback: check common locations
    candidates = [
        Path.home() / '.local' / 'share' / 'Vita3K',
        Path.home() / '.config' / 'Vita3K' / 'Vita3K',
    ]

    config_path = Path.home() / '.config' / 'Vita3K' / 'config.yml'
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    key, _, value = line.partition(':')
                    if key.strip() == 'pref-path':
                        pref = value.strip()
                        if pref:
                            pref_path = Path(pref).expanduser()
                            if pref_path.exists():
                                return pref_path
        except Exception:
            pass

    for candidate in candidates:
        if candidate.exists() and (candidate / 'ux0').is_dir():
            return candidate

    return None