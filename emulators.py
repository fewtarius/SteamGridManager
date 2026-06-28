#!/usr/bin/env python3
"""Emulator plugin system for SGM.

All emulator definitions and system mappings are loaded from emulators.json.
Default definitions are packaged in defaults/emulators.json and copied to
~/.config/sgm/emulators.json on first run.

Config location: ~/.config/sgm/emulators.json

Structure:
- emulators: Base emulator definitions (retroarch, dolphin, pcsx2, etc.)
- retroarch_cores: RetroArch core definitions
- systems: System configurations with default emulator and extensions
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / '.config' / 'sgm'
EMULATORS_CONFIG = CONFIG_DIR / 'emulators.json'


def _find_default_config() -> Path:
    """Locate the default emulators.json, checking multiple locations."""
    candidates = [
        Path(__file__).parent / 'defaults' / 'emulators.json',  # installed copy
        Path(__file__).parent.parent / 'defaults' / 'emulators.json',  # repo root
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]  # fallback to standard location


DEFAULT_CONFIG = _find_default_config()

# Flatpak IDs for known emulators
FLATPAK_IDS = {
    "retroarch": "org.libretro.RetroArch",
    "dolphin": "org.DolphinEmu.dolphin-emu",
    "pcsx2": "net.pcsx2.PCSX2",
    "ppsspp": "org.ppsspp.PPSSPP",
    "cemu": "info.cemu.Cemu",
    "xemu": "app.xemu.xemu",
    "primehack": "io.github.DolphinEmu.Primehack",
    "melonds": "org.desmume.Desmume",
    "rpcs3": "net.rpcs3.RPCS3",
    "yuzu": "org.yuzu_emu.yuzu",
    "citra": "org.citra_emu.citra",
}


# ═══════════════════════════════════════════════════════════════════════
# Plugin Base Class
# ═══════════════════════════════════════════════════════════════════════

class EmulatorPlugin:
    """Base class for emulator plugins.

    All emulator types inherit from this class. Plugins are created from
    config data loaded from emulators.json.
    """

    def __init__(self, emulator_id: str, config: Dict):
        """
        Args:
            emulator_id: Unique identifier (e.g., 'retroarch/fceumm', 'dolphin').
            config: Configuration dictionary from emulators.json.
        """
        self._id = emulator_id
        self._config = config

    @property
    def id(self) -> str:
        """Unique identifier for this emulator."""
        return self._id

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._config.get("display_name", self._id)

    @property
    def description(self) -> str:
        """Brief description."""
        return self._config.get("description", "")

    @property
    def emulator_type(self) -> str:
        """Type: 'retroarch', 'standalone', 'native'."""
        return self._config.get("type", "standalone")

    @property
    def flatpak_id(self) -> Optional[str]:
        """Flatpak app ID if applicable."""
        return self._config.get("flatpak_id")

    @property
    def is_flatpak(self) -> bool:
        """True if this emulator runs as a flatpak."""
        return self.flatpak_id is not None

    @property
    def executable(self) -> Optional[str]:
        """Path to executable (for native emulators)."""
        return self._config.get("executable")

    @property
    def launch_args(self) -> str:
        """Template for launch arguments."""
        return self._config.get("launch_args", '"{rom}"')

    @property
    def launch_mode(self) -> str:
        """Launch mode: 'rom', 'title_id', 'rom_stem'."""
        return self._config.get("launch_mode", "rom")

    @property
    def supported_extensions(self) -> Set[str]:
        """File extensions typically associated with this emulator."""
        return set(self._config.get("supported_extensions", [".zip", ".7z"]))

    @property
    def is_available(self) -> bool:
        """True if the emulator is installed and can be used."""
        available, _ = self.validate()
        return available

    def find_executable(self) -> str:
        """Find the emulator executable path.

        Returns:
            Path to executable as a string.
        Raises:
            FileNotFoundError: If the emulator is not installed.
        """
        if self.is_flatpak:
            return "/usr/bin/flatpak"

        exe = self.executable
        if exe:
            exe_path = Path(exe).expanduser()
            if exe_path.exists():
                return str(exe_path)

        raise FileNotFoundError(f"Executable not found for {self._id}")

    def get_launch_command(self, rom_path: str, title_id: Optional[str] = None) -> str:
        """Build the launch command for a ROM.

        Args:
            rom_path: Path to the ROM file or title ID.
            title_id: Optional PS Vita title ID.

        Returns:
            The full command string to launch the emulator.
        """
        args = self.launch_args

        # Replace placeholders
        if self.launch_mode == "rom_stem":
            rom_name = Path(rom_path).stem
            args = args.replace("{rom_stem}", rom_name).replace("{rom}", rom_path)
        elif self.launch_mode == "title_id":
            tid = title_id or rom_path
            args = args.replace("{title_id}", tid).replace("{rom}", rom_path)
        else:
            args = args.replace("{rom}", rom_path)
            if title_id:
                args = args.replace("{title_id}", title_id)

        return args

    def get_steam_exe(self, rom_path: str, title_id: Optional[str] = None) -> str:
        """Build the Steam shortcut 'exe' field in SRM-compatible format.

        Args:
            rom_path: Path to the ROM file or title ID.
            title_id: Optional PS Vita title ID.

        Returns:
            A string like: '"/usr/bin/flatpak" run org.libretro.RetroArch -L ...'
        """
        if self.is_flatpak and self.flatpak_id:
            launch_cmd = self.get_launch_command(rom_path, title_id)
            return f'"/usr/bin/flatpak" run {self.flatpak_id} {launch_cmd}'
        else:
            exe = self.find_executable()
            launch_cmd = self.get_launch_command(rom_path, title_id)
            return f'"{exe}" {launch_cmd}'

    def validate(self) -> Tuple[bool, str]:
        """Validate that the emulator is installed and usable.

        Returns:
            Tuple of (is_available, status_message).
        """
        try:
            if self.is_flatpak:
                result = os.system(f"flatpak info {self.flatpak_id} >/dev/null 2>&1")
                if result == 0:
                    return True, "Installed"
                return False, f"{self.flatpak_id} flatpak not installed"

            exe = self.find_executable()
            if Path(exe).exists():
                return True, f"Installed at {exe}"
            return False, f"Executable not found: {exe}"
        except FileNotFoundError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error: {e}"

    def get_info(self) -> Dict:
        """Get emulator info as a dictionary for display."""
        available, status = self.validate()
        return {
            "id": self._id,
            "name": self.display_name,
            "type": self.emulator_type,
            "flatpak": self.flatpak_id,
            "available": available,
            "status": status,
            "description": self.description,
            "extensions": sorted(self.supported_extensions),
        }


# ═══════════════════════════════════════════════════════════════════════
# Vita3K Plugin
# ═══════════════════════════════════════════════════════════════════════

class Vita3KPlugin(EmulatorPlugin):
    """Vita3K emulator plugin with multi-path binary discovery.

    Vita3K is commonly installed in several locations on SteamOS:
    - ``~/.config/Vita3K/Vita3K`` (local build)
    - ``/opt/vita3k/Vita3K`` (manual install)
    - ``/usr/bin/Vita3K`` (system package)
    - ``/usr/local/bin/Vita3K`` (manual system install)

    This plugin searches all known locations and falls back to PATH.
    Custom search paths can be specified in emulators.json via the
    ``search_paths`` key.
    """

    # Default search paths for the Vita3K binary, in priority order.
    DEFAULT_BINARY_SEARCH_PATHS = [
        Path.home() / '.config' / 'Vita3K' / 'Vita3K',
        Path('/opt/vita3k/Vita3K'),
        Path('/usr/bin/Vita3K'),
        Path('/usr/local/bin/Vita3K'),
    ]

    # Default search paths for the Vita3K data directory.
    DEFAULT_DATA_SEARCH_PATHS = [
        Path('/opt/vita3k/data'),
        Path.home() / '.local' / 'share' / 'Vita3K' / 'Vita3K',
        Path.home() / '.config' / 'Vita3K' / 'Vita3K',
    ]

    @property
    def binary_search_paths(self) -> List[Path]:
        """Search paths for the Vita3K binary, from config or defaults."""
        paths = self._config.get("search_paths", [])
        if paths:
            return [Path(p).expanduser() for p in paths]
        return self.DEFAULT_BINARY_SEARCH_PATHS

    @property
    def data_search_paths(self) -> List[Path]:
        """Search paths for the Vita3K data directory."""
        return self.DEFAULT_DATA_SEARCH_PATHS

    def find_executable(self) -> str:
        """Find the Vita3K binary by searching known locations.

        Returns:
            Path to Vita3K executable as a string.
        Raises:
            FileNotFoundError: If Vita3K is not found anywhere.
        """
        # Check configured executable first (if it's an absolute path)
        exe = self.executable
        if exe:
            exe_path = Path(exe).expanduser()
            if exe_path.is_absolute() and exe_path.exists():
                return str(exe_path)

        # Search known locations (from config or defaults)
        for candidate in self.binary_search_paths:
            if candidate.exists() and candidate.is_file():
                return str(candidate)

        # PATH fallback
        result = shutil.which('Vita3K')
        if result:
            return result

        raise FileNotFoundError(
            "Vita3K not found. Searched: "
            + ", ".join(str(p) for p in self.binary_search_paths)
            + ", and PATH"
        )

    @property
    def data_dir(self) -> Optional[Path]:
        """Find the Vita3K data directory containing installed games.

        Checks config.yml pref-path first, then known locations.
        """
        # Check config.yml for pref-path
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

        # Check known data directory locations
        for candidate in self.data_search_paths:
            if candidate.exists() and (candidate / 'ux0').is_dir():
                return candidate

        return None

    def validate(self) -> Tuple[bool, str]:
        """Check if Vita3K is installed and usable."""
        try:
            exe = self.find_executable()
            return True, f"Installed at {exe}"
        except FileNotFoundError:
            return False, "Vita3K not found in known locations or PATH"


# ═══════════════════════════════════════════════════════════════════════
# RetroArch Core Plugin
# ═══════════════════════════════════════════════════════════════════════

class RetroArchCorePlugin(EmulatorPlugin):
    """RetroArch core plugin.

    RetroArch is a multi-platform emulator frontend that uses cores
    for different systems. Each core is registered as 'retroarch/{core_name}'.
    """

    def __init__(self, core_name: str, config: Dict):
        """
        Args:
            core_name: RetroArch core name (e.g., 'snes9x', 'mupen64plus_next').
            config: Configuration dictionary for the core.
        """
        self._core_name = core_name
        super().__init__(f"retroarch/{core_name}", config)

    @property
    def core(self) -> str:
        """The RetroArch core name."""
        return self._core_name

    @property
    def flatpak_id(self) -> Optional[str]:
        """Get flatpak_id from config, default to RetroArch."""
        return self._config.get("flatpak_id", FLATPAK_IDS.get("retroarch"))

    def find_executable(self) -> str:
        """Return flatpak path or retroarch binary."""
        if self.is_flatpak:
            return "/usr/bin/flatpak"
        return "retroarch"

    def get_launch_command(self, rom_path: str, title_id: Optional[str] = None) -> str:
        """Build launch command with -L flag for core."""
        return f'-L /{self._core_name}_libretro.so "{rom_path}"'

    def get_steam_exe(self, rom_path: str, title_id: Optional[str] = None) -> str:
        """Build Steam exe field for RetroArch core."""
        if self.is_flatpak:
            launch_cmd = self.get_launch_command(rom_path, title_id)
            return f'"/usr/bin/flatpak" run {self.flatpak_id} {launch_cmd}'
        else:
            exe = self.find_executable()
            launch_cmd = self.get_launch_command(rom_path, title_id)
            return f'"{exe}" {launch_cmd}'

    def validate(self) -> Tuple[bool, str]:
        """Check if RetroArch flatpak is installed."""
        if self.is_flatpak:
            result = os.system(f"flatpak info {self.flatpak_id} >/dev/null 2>&1")
            if result == 0:
                return True, "Installed (Flatpak)"
            return False, "RetroArch flatpak not installed"
        else:
            exe = shutil.which("retroarch")
            if exe:
                return True, f"Installed at {exe}"
            return False, "retroarch not found in PATH"


# ═══════════════════════════════════════════════════════════════════════
# System Plugin (System with default emulator)
# ═══════════════════════════════════════════════════════════════════════

class SystemPlugin:
    """System configuration with default emulator.

    Represents a gaming system (e.g., 'n64', 'psx') with its default emulator
    and supported file extensions.
    """

    def __init__(self, system_id: str, config: Dict, emulator_plugin: Optional[EmulatorPlugin] = None):
        """
        Args:
            system_id: System identifier (e.g., 'n64', 'psx').
            config: System configuration from emulators.json.
            emulator_plugin: The default emulator plugin for this system.
        """
        self._id = system_id
        self._config = config
        self._emulator = emulator_plugin

    @property
    def id(self) -> str:
        return self._id

    @property
    def fullname(self) -> str:
        """Full system name."""
        return self._config.get("fullname", self._id)

    @property
    def manufacturer(self) -> str:
        """System manufacturer."""
        return self._config.get("manufacturer", "")

    @property
    def hardware_type(self) -> str:
        """Hardware type: console, portable, computer, arcade, handheld."""
        return self._config.get("hardware_type", "console")

    @property
    def release_year(self) -> Optional[int]:
        """Release year."""
        return self._config.get("release_year")

    @property
    def extensions(self) -> Set[str]:
        """Supported ROM file extensions."""
        return set(self._config.get("extensions", [".zip", ".7z"]))

    @property
    def screenscraper_id(self) -> int:
        """ScreenScraper platform ID."""
        return self._config.get("screenscraper_id", 0)

    @property
    def thegamesdb_id(self) -> str:
        """TheGamesDB platform ID."""
        return str(self._config.get("thegamesdb_id", "0"))

    @property
    def steam_category(self) -> str:
        """Steam category name."""
        return self._config.get("steam_category", self._id.upper())

    @property
    def scan_as_dirs(self) -> bool:
        """Scan subdirectories as games (for Vita3K)."""
        return self._config.get("scan_as_dirs", False)

    @property
    def emulator(self) -> Optional[EmulatorPlugin]:
        """Default emulator plugin."""
        return self._emulator

    @property
    def launch_mode(self) -> str:
        """Launch mode: 'rom' or 'title_id'."""
        if self._emulator:
            return self._emulator.launch_mode
        return "rom"

    @property
    def default_emulator_id(self) -> str:
        """Default emulator ID string."""
        return self._config.get("default_emulator", "")

    @property
    def legacy_tags(self) -> Set[str]:
        """Legacy category tag aliases for this system."""
        return set(self._config.get("legacy_tags", []))

    def is_rom_file(self, filename: str) -> bool:
        """Check if a filename has a valid extension for this system."""
        ext = Path(filename).suffix.lower()
        return ext in self.extensions

    def get_steam_category(self) -> str:
        """Get the Steam library category for this system."""
        return self.steam_category

    def all_category_tags(self) -> Set[str]:
        """Return all tag strings to match when purging old shortcuts."""
        return {self.get_steam_category()} | self.legacy_tags

    def get_info(self) -> Dict:
        """Get system info as a dictionary."""
        info = {
            "id": self._id,
            "fullname": self.fullname,
            "manufacturer": self.manufacturer,
            "hardware_type": self.hardware_type,
            "release_year": self.release_year,
            "default_emulator": self.default_emulator_id,
            "extensions": sorted(self.extensions),
            "screenscraper_id": self.screenscraper_id,
            "thegamesdb_id": self.thegamesdb_id,
            "steam_category": self.steam_category,
        }
        if self._emulator:
            available, status = self._emulator.validate()
            info["emulator_available"] = available
            info["emulator_status"] = status
        return info


# ═══════════════════════════════════════════════════════════════════════
# EmulatorRegistry
# ═══════════════════════════════════════════════════════════════════════

class EmulatorRegistry:
    """Registry of emulators and systems loaded from emulators.json.

    All configurations are loaded from the config file. Built-in defaults
    are provided via defaults/emulators.json in the package directory.
    """

    def __init__(self):
        self._config: Dict = {}
        self._emulators: Dict[str, EmulatorPlugin] = {}
        self._retroarch_cores: Dict[str, RetroArchCorePlugin] = {}
        self._systems: Dict[str, SystemPlugin] = {}
        self._system_aliases: Dict[str, str] = {}
        self._load_config()

    def _load_and_merge_configs(self) -> Dict:
        """Load defaults and user config, deep-merging them together.

        Defaults provide the base. User config overrides on top.
        Sections merged: emulators, retroarch_cores, systems.
        If the merge added anything new, writes merged config back.

        Returns:
            The merged configuration dictionary.
        """
        # Load defaults
        if not DEFAULT_CONFIG.exists():
            logger.warning(f"Default emulators config not found: {DEFAULT_CONFIG}")
            return {}

        try:
            with open(DEFAULT_CONFIG, 'r', encoding='utf-8') as f:
                defaults = json.load(f)
            logger.debug(f"Loaded defaults with {len(defaults.get('systems', {}))} systems")
        except Exception as e:
            logger.error(f"Failed to load default config: {e}")
            return {}

        # If no user config exists, write defaults as-is and return
        if not EMULATORS_CONFIG.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            try:
                with open(EMULATORS_CONFIG, 'w', encoding='utf-8') as f:
                    json.dump(defaults, f, indent=2)
                logger.info(f"Wrote default emulators.json to {EMULATORS_CONFIG}")
            except Exception as e:
                logger.error(f"Failed to write config: {e}")
            return defaults

        # Load user config
        try:
            with open(EMULATORS_CONFIG, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            logger.debug(f"Loaded user config with {len(user_config.get('systems', {}))} systems")
        except json.JSONDecodeError as e:
            logger.warning(f"User config corrupt, falling back to defaults: {e}")
            return defaults
        except Exception as e:
            logger.error(f"Failed to load user config: {e}")
            return defaults

        # Deep merge: defaults -> base, user -> overlay
        merged = dict(defaults)
        changed = False

        for section in ("emulators", "retroarch_cores", "systems"):
            default_section = defaults.get(section, {})
            user_section = user_config.get(section, {})

            if not user_section:
                continue

            # Start with all default entries
            merged_section = dict(default_section)
            # Overlay user entries (user wins for same key)
            for key, value in user_section.items():
                if key in default_section:
                    # User has customization - use theirs
                    merged_section[key] = value
                else:
                    # User-only entry - preserve it (maybe they added custom system)
                    merged_section[key] = value

            merged[section] = merged_section

            # Detect if defaults added new entries the user didn't have
            new_keys = set(default_section.keys()) - set(user_section.keys())
            if new_keys:
                logger.info(f"Added {len(new_keys)} new {section} from defaults: "
                           f"{', '.join(sorted(new_keys))}")
                changed = True

        # Write back merged config so next load is fast
        if changed:
            try:
                # Preserve user's version if they have one, else use defaults version
                merged["version"] = user_config.get("version", defaults.get("version", 1))
                # Preserve user comments
                if "_comment" in user_config:
                    merged["_comment"] = user_config["_comment"]
                with open(EMULATORS_CONFIG, 'w', encoding='utf-8') as f:
                    json.dump(merged, f, indent=2)
                logger.info(f"Wrote merged emulators.json to {EMULATORS_CONFIG}")
            except Exception as e:
                logger.warning(f"Failed to write merged config: {e} (continuing anyway)")

        return merged

    def _load_config(self) -> None:
        """Load emulator configurations, merging defaults with user config.

        Always loads the default emulators.json, then deep-merges the user's
        config on top. This ensures users always get new systems and emulators
        from updated defaults without losing their customizations.
        """
        try:
            self._config = self._load_and_merge_configs()

            self._load_emulators()
            self._load_retroarch_cores()
            self._load_systems()

            logger.info(f"Loaded {len(self._emulators)} emulators, "
                       f"{len(self._retroarch_cores)} RetroArch cores, "
                       f"{len(self._systems)} systems")

        except Exception as e:
            logger.error(f"Failed to load emulators config: {e}")

    # Emulator IDs that use specialized plugin classes.
    SPECIALIZED_PLUGINS = {
        "vita3k": Vita3KPlugin,
    }

    def _load_emulators(self) -> None:
        """Load base emulator definitions."""
        emulators = self._config.get("emulators", {})
        for emulator_id, config in emulators.items():
            if config.get("type") == "retroarch":
                # RetroArch cores are loaded separately
                continue
            plugin_class = self.SPECIALIZED_PLUGINS.get(emulator_id, EmulatorPlugin)
            plugin = plugin_class(emulator_id, config)
            self._emulators[emulator_id] = plugin

    def _load_retroarch_cores(self) -> None:
        """Load RetroArch core definitions."""
        cores = self._config.get("retroarch_cores", {})
        for core_name, config in cores.items():
            plugin = RetroArchCorePlugin(core_name, config)
            self._retroarch_cores[core_name] = plugin
            # Register with retroarch/ prefix
            self._emulators[f"retroarch/{core_name}"] = plugin

    def _load_systems(self) -> None:
        """Load system definitions and register aliases."""
        systems = self._config.get("systems", {})
        for system_id, config in systems.items():
            default_emulator_id = config.get("default_emulator", "")
            emulator_plugin = None

            if default_emulator_id:
                emulator_plugin = self.get(default_emulator_id)

            plugin = SystemPlugin(system_id, config, emulator_plugin)
            self._systems[system_id] = plugin

            # Register aliases so folder names like "zmachine" resolve
            # to the canonical system (e.g. "infocom").
            for alias in config.get("aliases", []):
                self._system_aliases[alias] = system_id

    def get(self, emulator_id: str) -> Optional[EmulatorPlugin]:
        """Get an emulator plugin by ID.

        Args:
            emulator_id: The emulator identifier (e.g., 'retroarch/snes9x', 'dolphin').

        Returns:
            The EmulatorPlugin if found, else None.
        """
        return self._emulators.get(emulator_id)

    def get_system(self, system_id: str) -> Optional[SystemPlugin]:
        """Get a system configuration by ID or alias.

        Args:
            system_id: The system identifier or alias (e.g., 'n64', 'psx', 'zmachine').

        Returns:
            The SystemPlugin if found, else None.
        """
        # Direct lookup first
        system = self._systems.get(system_id)
        if system:
            return system
        # Resolve alias to canonical system ID
        canonical_id = self._system_aliases.get(system_id)
        if canonical_id:
            return self._systems.get(canonical_id)
        return None

    def get_for_system(self, system_id: str, emulator_id: Optional[str] = None) -> Optional[EmulatorPlugin]:
        """Get the emulator plugin for a system.

        Args:
            system_id: The system name (e.g., 'n64', 'psx').
            emulator_id: Optional specific emulator ID (overrides default).

        Returns:
            The EmulatorPlugin for the system, or None if not configured.
        """
        if emulator_id:
            return self.get(emulator_id)

        system = self._systems.get(system_id)
        if system:
            return system.emulator

        return None

    def list_emulators(self) -> Dict[str, EmulatorPlugin]:
        """List all emulator plugins."""
        return self._emulators.copy()

    def list_systems(self) -> Dict[str, SystemPlugin]:
        """List all system plugins."""
        return self._systems.copy()

    def list_retroarch_cores(self) -> Dict[str, RetroArchCorePlugin]:
        """List all RetroArch core plugins."""
        return self._retroarch_cores.copy()

    def save_config(self) -> None:
        """Save current configuration to emulators.json."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        with open(EMULATORS_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2)

        logger.info(f"Saved emulators config to {EMULATORS_CONFIG}")


# ═══════════════════════════════════════════════════════════════════════
# Global Registry
# ═══════════════════════════════════════════════════════════════════════

_registry: Optional[EmulatorRegistry] = None


def get_registry() -> EmulatorRegistry:
    """Get the global emulator registry singleton."""
    global _registry
    if _registry is None:
        _registry = EmulatorRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _registry
    _registry = None


# ═══════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════

def get_emulator(emulator_id: str) -> Optional[EmulatorPlugin]:
    """Get an emulator plugin by ID.

    Args:
        emulator_id: The emulator identifier.

    Returns:
        The EmulatorPlugin, or None if not found.
    """
    return get_registry().get(emulator_id)


def get_system(system_id: str) -> Optional[SystemPlugin]:
    """Get a system configuration by ID.

    Args:
        system_id: The system identifier.

    Returns:
        The SystemPlugin, or None if not found.
    """
    return get_registry().get_system(system_id)


def get_system_emulator(system_id: str, emulator_id: Optional[str] = None) -> Optional[EmulatorPlugin]:
    """Get the emulator plugin for a system.

    Args:
        system_id: The system name.
        emulator_id: Optional specific emulator ID.

    Returns:
        The EmulatorPlugin, or None.
    """
    return get_registry().get_for_system(system_id, emulator_id)


def list_all_emulators() -> List[Dict]:
    """List all available emulators with status.

    Returns:
        List of dictionaries with emulator info.
    """
    registry = get_registry()
    emulators = []

    for emulator_id, plugin in registry.list_emulators().items():
        info = plugin.get_info()
        info["emulator_id"] = emulator_id
        emulators.append(info)

    return emulators


def list_all_systems() -> List[Dict]:
    """List all available systems with status.

    Returns:
        List of dictionaries with system info.
    """
    registry = get_registry()
    systems = []

    for system_id, plugin in registry.list_systems().items():
        info = plugin.get_info()
        systems.append(info)

    return systems


def get_emulators_for_system(system_id: str) -> List[Dict]:
    """Get all configured emulators for a system.

    Args:
        system_id: The system name.

    Returns:
        List of emulator info dictionaries.
    """
    registry = get_registry()
    system = registry.get_system(system_id)

    if not system:
        return []

    emulators = []

    # Get the configured emulator
    if system.emulator:
        info = system.emulator.get_info()
        info["emulator_id"] = system.default_emulator_id
        emulators.append(info)

    return emulators


def create_emulator_from_id(emulator_id: str) -> Optional[EmulatorPlugin]:
    """Format emulator status for CLI display.

    Args:
        plugin: The emulator plugin.

    Returns:
        A formatted string showing emulator status.
    """
    available, status = plugin.validate()
    symbol = "[OK]" if available else "[--]"
    return f"{symbol} {plugin.display_name}: {status}"


def format_system_status(plugin: SystemPlugin) -> str:
    """Format system status for CLI display.

    Args:
        plugin: The system plugin.

    Returns:
        A formatted string showing system and its default emulator.
    """
    default = plugin.default_emulator_id or "none"
    if plugin.emulator:
        available, _ = plugin.emulator.validate()
        symbol = "[OK]" if available else "[--]"
    else:
        symbol = "[--]"

    return f"{symbol} {plugin.id}: {plugin.fullname} -> {default}"


# ═══════════════════════════════════════════════════════════════════════
# Config File Management
# ═══════════════════════════════════════════════════════════════════════

def get_config_path() -> Path:
    """Get the path to the emulators config file."""
    return EMULATORS_CONFIG


def get_default_config_path() -> Path:
    """Get the path to the default emulators config file."""
    return DEFAULT_CONFIG


def emulators_config_exists() -> bool:
    """Check if user emulators.json exists (not just defaults)."""
    return EMULATORS_CONFIG.exists()


def init_config() -> bool:
    """Initialize emulators.json from defaults.

    Returns:
        True if config was created, False if already exists.
    """
    if EMULATORS_CONFIG.exists():
        return False

    if not DEFAULT_CONFIG.exists():
        logger.error(f"Default config not found: {DEFAULT_CONFIG}")
        return False

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(DEFAULT_CONFIG, EMULATORS_CONFIG)
        logger.info(f"Created emulators.json from defaults at {EMULATORS_CONFIG}")
        reset_registry()
        return True
    except Exception as e:
        logger.error(f"Failed to create config: {e}")
        return False


def load_config() -> Dict:
    """Load and return the current config.

    Returns:
        Configuration dictionary.
    """
    return get_registry()._config


def save_config(config: Dict) -> None:
    """Save configuration to emulators.json.

    Args:
        config: Configuration dictionary to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(EMULATORS_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

    logger.info(f"Saved emulators config to {EMULATORS_CONFIG}")
    reset_registry()