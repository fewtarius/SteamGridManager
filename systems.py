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
    emulator: str           # "retroarch", "dolphin", "pcsx2", "ppsspp", "cemu"
    core: Optional[str]     # RetroArch core name (without _libretro.so)
    flatpak_id: Optional[str]   # Flatpak app ID if applicable
    launch_args: str        # Template with {rom} placeholder

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
        """
        if self.flatpak_id:
            args = self.launch_args.replace("{rom}", rom_path)
            return f'"/usr/bin/flatpak" run {self.flatpak_id} {args}'
        # Non-flatpak executable
        args = self.launch_args.replace("{rom}", rom_path)
        return f'"{self.emulator}" {args}'


@dataclass
class SystemDef:
    """Complete system definition."""
    name: str               # Folder name (e.g., "snes")
    fullname: str           # Display name (e.g., "Super Nintendo")
    manufacturer: str       # e.g., "Nintendo"
    extensions: Set[str]    # Valid ROM extensions (e.g., {".sfc", ".smc"})
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
        thegamesdb_id=None,  # No VIC-20 on TheGamesDB
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
        thegamesdb_id=None,  # Arcade doesn't map cleanly
    ),

    # ─── PC / Interactive Fiction ───────────────────────────────────
    "pc": SystemDef(
        name="pc",
        fullname="DOS",
        manufacturer="Microsoft",
        extensions={".com", ".bat", ".exe", ".dosz"},
        emulator=_ra("dosbox_pure"),
        screenscraper_id=135,
        thegamesdb_id=None,
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
        folder_name: The ROM folder name (e.g., "snes", "genesis").

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
