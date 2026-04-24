#!/usr/bin/env python3
"""System definitions database for ROM management.

Maps system folder names to file extensions, platform IDs across multiple
scraping services, emulator launch configurations, and display metadata.

Sources:
- JELOS distribution config/emulators/ (maintained by project contributor)
- Skyscraper screenscraper.cpp (ScreenScraper platform IDs)
- EmulationStation-next GamesDBJSONScraper.cpp (TheGamesDB platform IDs)
- SteamGridDB API (uses game name search, no platform IDs needed)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class EmulatorConfig:
    """How to launch ROMs for this system."""
    emulator: str           # "retroarch", "dolphin", "pcsx2", "ppsspp", "cemu", "vita3k"
    core: Optional[str]     # RetroArch core name (without _libretro.so)
    flatpak_id: Optional[str]   # Flatpak app ID if applicable
    launch_args: str        # Template with {rom} or {title_id} placeholder
    launch_mode: str = "rom"  # "rom" (file path) or "title_id" (Vita3K-style)

    def get_executable(self) -> str:
        """Get the full executable path/command."""
        if self.flatpak_id:
            return f"/usr/bin/flatpak run {self.flatpak_id}"
        return self.emulator

    def get_launch_options(self, rom_path: str) -> str:
        """Get launch options for a specific ROM."""
        return self.launch_args.replace("{rom}", rom_path)

    def get_steam_exe(self, rom_path: str) -> str:
        """Build the Steam shortcut ``exe`` field in SRM-compatible format.

        Steam parses the ``exe`` field as::

            "quoted_binary_path" [remaining args including rom]

        Only the first ``"..."`` token is the actual binary.  Everything after
        is treated as command-line arguments.  ``launch_options`` is appended
        last.

        We put the *entire* command including the ROM path in ``exe`` and leave
        ``launch_options`` empty, exactly as Steam ROM Manager does.  This
        means the computed app ID is ROM-path-dependent (same as SRM), so
        existing SRM artwork images continue to display correctly.

        Returns:
            A string like::

                '"/usr/bin/flatpak" run org.libretro.RetroArch -L /core.so "/rom"'

        For Vita3K title-ID mode, the ``{title_id}`` placeholder in
        ``launch_args`` is replaced with the game's title ID (e.g.
        ``PCSE00317``), and ``{rom}`` is replaced with the path to the
        game's eboot.bin.  The ``exe`` field uses the title ID for
        launching, not the ROM file path.
        """
        if self.flatpak_id:
            args = self.launch_args.replace("{rom}", rom_path)
            return f'"/usr/bin/flatpak" run {self.flatpak_id} {args}'
        # Vita3K title-ID mode: replace both {title_id} and {rom}
        if self.launch_mode == "title_id":
            # rom_path for Vita3K is actually the title ID
            args = self.launch_args.replace("{title_id}", rom_path).replace("{rom}", rom_path)
            return f'"{self.emulator}" {args}'
        # Non-flatpak executable
        args = self.launch_args.replace("{rom}", rom_path)
        return f'"{self.emulator}" {args}'


@dataclass
class SystemDef:
    """Complete system definition."""
    name: str               # Folder name (e.g., "c64")
    fullname: str           # Display name (e.g., "Commodore 64")
    manufacturer: str       # e.g., "Commodore"
    extensions: Set[str]    # Valid ROM extensions (e.g., {".d64", ".prg"})
    emulator: EmulatorConfig
    # Platform IDs for scraping services
    screenscraper_id: Optional[int] = None
    thegamesdb_id: Optional[str] = None
    # Category tag for Steam library
    steam_category: Optional[str] = None
    # Legacy SRM/external tag names for this system.  Used when purging old
    # shortcuts so that entries created by Steam ROM Manager or prior SGM
    # versions (which used different tag strings) are also removed.
    legacy_tags: Set[str] = field(default_factory=set)
    # When True, games are installed app directories (not ROM files).
    # The scanner reads subdirectories instead of files.  Used by PS Vita
    # (Vita3K) where games live in ux0/app/<TITLE_ID>/ directories.
    scan_as_dirs: bool = False
    # Extensions to skip (save files, etc.)
    skip_extensions: Set[str] = field(default_factory=lambda: {
        ".srm", ".state", ".state1", ".state2", ".state3", ".state4",
        ".state5", ".sav", ".oops", ".cfg", ".nfo", ".txt", ".xml",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".db", ".ini",
        ".log", ".bak", ".old", ".sync-conflict"
    })

    def is_rom_file(self, filename: str) -> bool:
        """Check if a filename is a valid ROM for this system."""
        lower = filename.lower()
        ext = Path(filename).suffix.lower()

        # Skip hidden files
        if filename.startswith("."):
            return False

        # Skip known non-ROM files
        if ext in self.skip_extensions:
            return False

        # Skip multi-disc bin files (keep .cue/.m3u)
        if ext == ".bin" and "(Track" in filename:
            return False

        # Check if extension matches
        if ext in self.extensions:
            return True

        # For systems with directories as ROMs (some Dreamcast games)
        return False

    def get_steam_category(self) -> str:
        """Get the Steam library category for this system."""
        return self.steam_category or self.fullname

    def all_category_tags(self) -> Set[str]:
        """Return all tag strings to match when purging old shortcuts.

        Includes the current category name plus any legacy aliases.
        """
        return {self.get_steam_category()} | self.legacy_tags


# ═══════════════════════════════════════════════════════════════════════
# Vita3K Path Discovery
# ═══════════════════════════════════════════════════════════════════════

_VITA3K_BINARY: Optional[str] = None  # Cached binary path
_VITA3K_DATA_DIR: Optional[Path] = None  # Cached data directory


def _find_vita3k_binary() -> str:
    """Find the Vita3K executable path.

    Search order:
    1. ``~/.config/Vita3K/Vita3K`` (default install location)
    2. ``/usr/bin/Vita3K`` (system install)
    3. ``/usr/local/bin/Vita3K`` (manual install)
    4. ``Vita3K`` (fall back to PATH lookup)

    Returns:
        Path to Vita3K binary as a string.
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

    # Fall back to bare name (relies on PATH)
    _VITA3K_BINARY = 'Vita3K'
    return _VITA3K_BINARY


def find_vita3k_data_dir() -> Optional[Path]:
    """Find the Vita3K data directory containing installed games.

    Search order:
    1. ``pref-path`` from Vita3K's ``config.yml`` (if set)
    2. ``~/.config/Vita3K/Vita3K/`` (default next to binary)
    3. Common SD card mount points

    When multiple candidates exist, prefers directories where
    ``ux0/app/`` contains at least one valid game (directory with
    ``eboot.bin``).

    Returns:
        Path to Vita3K data directory, or None if not found.
    """
    global _VITA3K_DATA_DIR
    if _VITA3K_DATA_DIR is not None:
        return _VITA3K_DATA_DIR

    candidates: List[Path] = []

    # 1. Check Vita3K config.yml for pref-path
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
                                candidates.append(pref_path)
        except Exception:
            pass

    # 2. ~/.local/share/Vita3K (standard XDG data dir, may be symlink to SD card)
    local_share = Path.home() / '.local' / 'share' / 'Vita3K'
    if local_share.exists() and (local_share / 'ux0').is_dir():
        candidates.append(local_share)

    # 3. Default location next to the binary
    binary_dir = Path(_find_vita3k_binary()).parent
    default_data = binary_dir / 'Vita3K'
    if default_data.exists() and (default_data / 'ux0').is_dir():
        candidates.append(default_data)

    # Also check the binary's parent directory itself
    if binary_dir.exists() and (binary_dir / 'ux0').is_dir():
        candidates.append(binary_dir)

    # 4. Common SD card locations (fallback)
    sd_candidates = [
        Path('/run/media/primary/Vita3K/Vita3K'),
        Path('/run/media/deck/primary/Vita3K/Vita3K'),
        Path('/run/media/primary/Vita3K'),
        Path('/run/media/deck/primary/Vita3K'),
    ]
    for candidate in sd_candidates:
        if candidate.exists() and (candidate / 'ux0').is_dir():
            candidates.append(candidate)

    # Pick the best candidate: prefer directories with actual game data
    def _has_games(data_dir: Path) -> bool:
        """Check if ux0/app/ contains at least one valid game."""
        app_dir = data_dir / 'ux0' / 'app'
        if not app_dir.is_dir():
            return False
        for entry in app_dir.iterdir():
            if entry.is_dir() and (entry / 'eboot.bin').exists():
                return True
        return False

    # Prefer candidates with actual games
    for candidate in candidates:
        if _has_games(candidate):
            _VITA3K_DATA_DIR = candidate
            return _VITA3K_DATA_DIR

    # Fall back to first candidate without games check
    if candidates:
        _VITA3K_DATA_DIR = candidates[0]
        return _VITA3K_DATA_DIR

    return None


# ═══════════════════════════════════════════════════════════════════════
# RetroArch core definitions (Flatpak)
# ═══════════════════════════════════════════════════════════════════════

def _ra(core: str) -> EmulatorConfig:
    """Shorthand for RetroArch Flatpak with a given core."""
    return EmulatorConfig(
        emulator="retroarch",
        core=core,
        flatpak_id="org.libretro.RetroArch",
        launch_args=f'-L /{core}_libretro.so "{{rom}}"'
    )


def _standalone(flatpak_id: str, args: str) -> EmulatorConfig:
    """Shorthand for standalone emulator via Flatpak."""
    return EmulatorConfig(
        emulator=flatpak_id.split(".")[-1].lower(),
        core=None,
        flatpak_id=flatpak_id,
        launch_args=args,
    )

def _vita3k() -> EmulatorConfig:
    """Shorthand for Vita3K PlayStation Vita emulator.

    Vita3K launches games by title ID (e.g. PCSE00317), not by ROM file path.
    The ``{title_id}`` placeholder in launch_args is replaced at runtime.
    The emulator path is auto-discovered at import time.
    """
    return EmulatorConfig(
        emulator=_find_vita3k_binary(),
        core=None,
        flatpak_id=None,
        launch_args='-F -r "{title_id}"',
        launch_mode="title_id",
    )


# ═══════════════════════════════════════════════════════════════════════
# System Definitions Database
# ═══════════════════════════════════════════════════════════════════════

SYSTEMS: Dict[str, SystemDef] = {
    # ─── Nintendo ───────────────────────────────────────────────────
    "nes": SystemDef(
        name="nes",
        fullname="Nintendo Entertainment System",
        manufacturer="Nintendo",
        extensions={".nes", ".unif", ".unf", ".zip", ".7z"},
        emulator=_ra("fceumm"),
        screenscraper_id=3,
        thegamesdb_id="7",
        legacy_tags={"NES"},
    ),
    "snes": SystemDef(
        name="snes",
        fullname="Super Nintendo",
        manufacturer="Nintendo",
        extensions={".smc", ".fig", ".sfc", ".swc", ".zip", ".7z"},
        emulator=_ra("snes9x"),
        screenscraper_id=4,
        thegamesdb_id="6",
        legacy_tags={"SNES"},
    ),
    "n64": SystemDef(
        name="n64",
        fullname="Nintendo 64",
        manufacturer="Nintendo",
        extensions={".z64", ".n64", ".v64", ".zip", ".7z"},
        emulator=_ra("mupen64plus_next"),
        screenscraper_id=14,
        thegamesdb_id="3",
    ),
    "gb": SystemDef(
        name="gb",
        fullname="Game Boy",
        manufacturer="Nintendo",
        extensions={".gb", ".gbc", ".zip", ".7z"},
        emulator=_ra("mgba"),
        screenscraper_id=9,
        thegamesdb_id="4",
        legacy_tags={"GameBoy"},
    ),
    "gbc": SystemDef(
        name="gbc",
        fullname="Game Boy Color",
        manufacturer="Nintendo",
        extensions={".gb", ".gbc", ".zip", ".7z"},
        emulator=_ra("mgba"),
        screenscraper_id=10,
        thegamesdb_id="41",
        legacy_tags={"GBC", "GameBoy Color"},
    ),
    "gba": SystemDef(
        name="gba",
        fullname="Game Boy Advance",
        manufacturer="Nintendo",
        extensions={".gba", ".zip", ".7z"},
        emulator=_ra("mgba"),
        screenscraper_id=12,
        thegamesdb_id="5",
        legacy_tags={"GBA", "GameBoy Advance"},
    ),
    "nds": SystemDef(
        name="nds",
        fullname="Nintendo DS",
        manufacturer="Nintendo",
        extensions={".nds", ".zip", ".7z"},
        emulator=_ra("melondsds"),
        screenscraper_id=15,
        thegamesdb_id="8",
        legacy_tags={"DS", "Nintendo DS"},
    ),
    "gamecube": SystemDef(
        name="gamecube",
        fullname="GameCube",
        manufacturer="Nintendo",
        extensions={".gcm", ".iso", ".gcz", ".ciso", ".wbfs", ".rvz", ".dol"},
        emulator=_standalone(
            "org.DolphinEmu.dolphin-emu",
            '-b -e "{rom}"'
        ),
        screenscraper_id=13,
        thegamesdb_id="2",
        legacy_tags={"Gamecube"},
    ),
    "wii": SystemDef(
        name="wii",
        fullname="Wii",
        manufacturer="Nintendo",
        extensions={".gcm", ".iso", ".gcz", ".ciso", ".wbfs", ".rvz", ".dol", ".wad"},
        emulator=_standalone(
            "org.DolphinEmu.dolphin-emu",
            '-b -e "{rom}"'
        ),
        screenscraper_id=16,
        thegamesdb_id="9",
    ),
    "wiiu": SystemDef(
        name="wiiu",
        fullname="Wii U",
        manufacturer="Nintendo",
        extensions={".wud", ".wux", ".wua", ".rpx"},
        emulator=_standalone(
            "info.cemu.Cemu",
            '-f -g "{rom}"'
        ),
        screenscraper_id=18,
        thegamesdb_id="38",
    ),

    # ─── Sega ───────────────────────────────────────────────────────
    "genesis": SystemDef(
        name="genesis",
        fullname="Genesis",
        manufacturer="Sega",
        extensions={".bin", ".gen", ".md", ".sg", ".smd", ".zip", ".7z"},
        emulator=_ra("genesis_plus_gx"),
        screenscraper_id=1,
        thegamesdb_id="18",
        legacy_tags={"Genesis/Mega Drive", "Mega Drive"},
    ),
    "mastersystem": SystemDef(
        name="mastersystem",
        fullname="Master System",
        manufacturer="Sega",
        extensions={".bin", ".sms", ".zip", ".7z"},
        emulator=_ra("genesis_plus_gx"),
        screenscraper_id=2,
        thegamesdb_id="35",
    ),
    "gamegear": SystemDef(
        name="gamegear",
        fullname="Game Gear",
        manufacturer="Sega",
        extensions={".bin", ".gg", ".zip", ".7z"},
        emulator=_ra("genesis_plus_gx"),
        screenscraper_id=21,
        thegamesdb_id="20",
    ),
    "dreamcast": SystemDef(
        name="dreamcast",
        fullname="Dreamcast",
        manufacturer="Sega",
        extensions={".cdi", ".gdi", ".chd", ".m3u", ".cue"},
        emulator=_ra("flycast"),
        screenscraper_id=23,
        thegamesdb_id="16",
    ),
    "saturn": SystemDef(
        name="saturn",
        fullname="Saturn",
        manufacturer="Sega",
        extensions={".cue", ".chd", ".iso"},
        emulator=_ra("mednafen_saturn"),
        screenscraper_id=22,
        thegamesdb_id="17",
    ),

    # ─── Sony ───────────────────────────────────────────────────────
    "psx": SystemDef(
        name="psx",
        fullname="PlayStation",
        manufacturer="Sony",
        extensions={".bin", ".cue", ".img", ".mdf", ".pbp", ".toc", ".cbn",
                    ".m3u", ".ccd", ".chd", ".iso"},
        emulator=_ra("mednafen_psx_hw"),
        screenscraper_id=57,
        thegamesdb_id="10",
        legacy_tags={"PS1", "PlayStation 1"},
    ),
    "ps2": SystemDef(
        name="ps2",
        fullname="PlayStation 2",
        manufacturer="Sony",
        extensions={".iso", ".mdf", ".nrg", ".bin", ".img", ".dump", ".gz",
                    ".cso", ".chd", ".cue"},
        emulator=_standalone(
            "net.pcsx2.PCSX2",
            '"{rom}" -batch -fullscreen'
        ),
        screenscraper_id=58,
        thegamesdb_id="11",
        legacy_tags={"PS2"},
    ),
    "psp": SystemDef(
        name="psp",
        fullname="PlayStation Portable",
        manufacturer="Sony",
        extensions={".iso", ".cso", ".pbp", ".chd"},
        emulator=_standalone(
            "org.ppsspp.PPSSPP",
            '"{rom}" --fullscreen'
        ),
        screenscraper_id=61,
        thegamesdb_id="13",
        legacy_tags={"PSP"},
    ),
    "psvita": SystemDef(
        name="psvita",
        fullname="PlayStation Vita",
        manufacturer="Sony",
        extensions={".vpk"},  # VPK packages (for manual install); installed apps scanned by title ID
        emulator=_vita3k(),
        screenscraper_id=62,
        thegamesdb_id="39",
        steam_category="PlayStation Vita",
        legacy_tags={"PS Vita", "Vita", "PSVita"},
        scan_as_dirs=True,  # Games are installed app directories in ux0/app/<TITLE_ID>/
    ),

    # ─── Atari ──────────────────────────────────────────────────────
    "atari2600": SystemDef(
        name="atari2600",
        fullname="Atari 2600",
        manufacturer="Atari",
        extensions={".a26", ".bin", ".zip", ".7z"},
        emulator=_ra("stella"),
        screenscraper_id=26,
        thegamesdb_id="22",
    ),
    "atari5200": SystemDef(
        name="atari5200",
        fullname="Atari 5200",
        manufacturer="Atari",
        extensions={".rom", ".xfd", ".atr", ".atx", ".cdm", ".cas", ".car",
                    ".bin", ".a52", ".xex", ".zip", ".7z"},
        emulator=_ra("atari800"),
        screenscraper_id=40,
        thegamesdb_id="26",
    ),
    "atari7800": SystemDef(
        name="atari7800",
        fullname="Atari 7800",
        manufacturer="Atari",
        extensions={".a78", ".bin", ".zip", ".7z"},
        emulator=_ra("prosystem"),
        screenscraper_id=41,
        thegamesdb_id="27",
        legacy_tags={"7800"},
    ),
    "atarilynx": SystemDef(
        name="atarilynx",
        fullname="Atari Lynx",
        manufacturer="Atari",
        extensions={".lnx", ".lyx", ".o", ".zip", ".7z"},
        emulator=_ra("mednafen_lynx"),
        screenscraper_id=28,
        thegamesdb_id="4924",
    ),

    # ─── Commodore ──────────────────────────────────────────────────
    "c64": SystemDef(
        name="c64",
        fullname="Commodore 64",
        manufacturer="Commodore",
        extensions={".d64", ".d71", ".d80", ".d81", ".d82", ".g64", ".g41",
                    ".x64", ".t64", ".tap", ".prg", ".p00", ".crt", ".bin",
                    ".d6z", ".d7z", ".d8z", ".g6z", ".g4z", ".x6z", ".cmd",
                    ".m3u", ".vsf", ".nib", ".nbz", ".zip"},
        emulator=_ra("vice_x64sc"),
        screenscraper_id=66,
        thegamesdb_id="40",
        legacy_tags={"C64"},
    ),
    "vic20": SystemDef(
        name="vic20",
        fullname="VIC-20",
        manufacturer="Commodore",
        extensions={".20", ".a0", ".b0", ".d64", ".d71", ".d80", ".d81",
                    ".d82", ".g64", ".g41", ".x64", ".t64", ".tap", ".prg",
                    ".p00", ".crt", ".bin", ".gz", ".d6z", ".d7z", ".d8z",
                    ".g6z", ".g4z", ".x6z", ".cmd", ".m3u", ".vsf", ".nib",
                    ".nbz", ".zip"},
        emulator=_ra("vice_xvic"),
        screenscraper_id=73,
        thegamesdb_id="4945",
    ),
    "amiga": SystemDef(
        name="amiga",
        fullname="Amiga",
        manufacturer="Commodore",
        extensions={".zip", ".adf", ".uae", ".ipf", ".dms", ".adz", ".lha",
                    ".m3u", ".hdf", ".hdz"},
        emulator=_ra("puae"),
        screenscraper_id=64,
        thegamesdb_id="4911",
    ),

    # ─── Other ──────────────────────────────────────────────────────
    "coleco": SystemDef(
        name="coleco",
        fullname="ColecoVision",
        manufacturer="Coleco",
        extensions={".bin", ".col", ".rom", ".zip", ".7z"},
        emulator=_ra("gearcoleco"),
        screenscraper_id=48,
        thegamesdb_id="31",
    ),
    "intellivision": SystemDef(
        name="intellivision",
        fullname="Intellivision",
        manufacturer="Mattel",
        extensions={".int", ".bin", ".rom", ".zip", ".7z"},
        emulator=_ra("freeintv"),
        screenscraper_id=115,
        thegamesdb_id="32",
    ),
    "neogeo": SystemDef(
        name="neogeo",
        fullname="Neo Geo",
        manufacturer="SNK",
        extensions={".7z", ".zip"},
        emulator=_ra("fbneo"),
        screenscraper_id=142,
        thegamesdb_id="24",
        legacy_tags={"Neo Geo CD"},
    ),
    "arcade": SystemDef(
        name="arcade",
        fullname="Arcade",
        manufacturer="Arcade",
        extensions={".zip", ".7z"},
        emulator=_ra("mame2003_plus"),
        screenscraper_id=75,
        thegamesdb_id="23",
    ),

    # ─── PC / Interactive Fiction ───────────────────────────────────
    "pc": SystemDef(
        name="pc",
        fullname="DOS",
        manufacturer="Microsoft",
        extensions={".com", ".bat", ".exe", ".dosz"},
        emulator=_ra("dosbox_pure"),
        screenscraper_id=135,
        thegamesdb_id="1",
    ),
    "infocom": SystemDef(
        name="infocom",
        fullname="Infocom / Z-Machine",
        manufacturer="Infocom",
        extensions={".dat", ".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".zip"},
        emulator=_ra("81"),  # No standard core; placeholder
        screenscraper_id=None,
        thegamesdb_id=None,
        legacy_tags={"Interactive Fiction", "Infocom"},
    ),
    "zmachine": SystemDef(
        name="zmachine",
        fullname="Z-Machine",
        manufacturer="Infocom",
        extensions={".dat", ".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".zip"},
        emulator=_ra("81"),  # Placeholder
        screenscraper_id=None,
        thegamesdb_id=None,
    ),

    # ─── Microsoft ──────────────────────────────────────────────────
    "xbox": SystemDef(
        name="xbox",
        fullname="Xbox",
        manufacturer="Microsoft",
        extensions={".iso"},
        emulator=_standalone(
            "app.xemu.xemu",
            '-full-screen -dvd_path "{rom}"',
        ),
        screenscraper_id=32,
        thegamesdb_id="14",
    ),
}

# Aliases for folder name variations
SYSTEM_ALIASES: Dict[str, str] = {
    "megadrive": "genesis",
    "megadrive-japan": "genesis",
    "sfc": "snes",
    "famicom": "nes",
    "segacd": "dreamcast",
    "megacd": "dreamcast",
    "vic20_old": "vic20",
    "colecovision": "coleco",
    "sg-1000": "mastersystem",
}


def get_system(folder_name: str) -> Optional[SystemDef]:
    """Look up a system definition by folder name.

    Args:
        folder_name: The ROM folder name (e.g., "c64", "amiga").

    Returns:
        SystemDef if found, None otherwise.
    """
    name = folder_name.lower().strip()
    if name in SYSTEMS:
        return SYSTEMS[name]
    if name in SYSTEM_ALIASES:
        return SYSTEMS[SYSTEM_ALIASES[name]]
    return None


def get_all_systems() -> Dict[str, SystemDef]:
    """Get all defined systems."""
    return SYSTEMS.copy()


def list_supported_systems() -> List[str]:
    """Get sorted list of supported system folder names."""
    return sorted(SYSTEMS.keys())
