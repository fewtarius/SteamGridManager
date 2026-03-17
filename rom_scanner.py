#!/usr/bin/env python3
"""ROM scanner and title extraction engine.

Scans ROM folders, extracts clean game titles from filenames,
and manages ROM metadata for import into Steam.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from systems import SystemDef, get_system, SYSTEMS

logger = logging.getLogger(__name__)


@dataclass
class RomEntry:
    """A single ROM file with extracted metadata."""
    path: Path                          # Full path to ROM file
    filename: str                       # Original filename
    system: str                         # System folder name
    raw_title: str                      # Title before cleaning
    clean_title: str                    # Cleaned display title
    extension: str                      # File extension
    is_multi_disc: bool = False         # Part of a multi-disc set
    disc_number: Optional[int] = None   # Disc number if multi-disc
    region: Optional[str] = None        # Detected region (USA, EUR, JPN)
    tags: Set[str] = field(default_factory=set)  # Extracted tags [!], (Rev A), etc.

    @property
    def steam_title(self) -> str:
        """Title formatted for Steam shortcut display."""
        if self.disc_number and self.disc_number > 1:
            return f"{self.clean_title} (Disc {self.disc_number})"
        return self.clean_title


# ═══════════════════════════════════════════════════════════════════════
# Title Cleaning Engine
# ═══════════════════════════════════════════════════════════════════════

# Patterns to extract and remove from ROM filenames
# Order matters: process tags before stripping parentheticals

# Region codes found in ROM names
REGION_MAP = {
    "USA": "USA", "US": "USA", "U": "USA",
    "EUR": "EUR", "Europe": "EUR", "E": "EUR",
    "Japan": "JPN", "JPN": "JPN", "JP": "JPN", "J": "JPN",
    "World": "WLD", "W": "WLD",
    "NTSC": "USA", "PAL": "EUR",
}

# Tags we want to detect but remove from display title
STRIP_TAGS = re.compile(
    r'\s*[\[\(]('
    r'[!\?]|'                           # [!] verified dump
    r'Rev\s*[A-Z0-9.]+|'               # (Rev A), (Rev 1.1)
    r'[Vv]\s*[\d.]+|'                   # (V1.1), (v1.01)
    r'Beta|Proto|Sample|Demo|Promo|'
    r'Unl|Pirate|PD|Hack|'
    r'NTSC|PAL|'
    r'USA|Europe|Japan|World|Korea|'    # Full region names
    r'USA,\s*Europe|'                   # Multi-region
    r'En(?:,\w{2})*|'                   # (En,Fr,De,Es,It) language lists
    r'[A-Z]{2,3}(?:,\s*[A-Z]{2,3})*'   # Region codes (US, EU, JP)
    r')[\]\)]',
    re.IGNORECASE
)

# Disc number patterns
DISC_PATTERN = re.compile(
    r'[\(\[]\s*(?:Disc|Disk|CD)\s*(\d+)\s*[\)\]]',
    re.IGNORECASE
)

# GoodTools dump info patterns  e.g., (2000)(GOD)(NTSC)(US)[!]
GOODTOOLS_TAG = re.compile(
    r'[\(\[]\d{4}\)[\(\[]'   # (2000)(
    r'|[\(\[]\w+\)\s*[\(\[]' # followed by more tags
)

# Common patterns in Dreamcast/Saturn folder-based ROMs
FOLDER_ROM_PATTERN = re.compile(
    r'\s+v[\d.]+\s*\(\d{4}\)\([^)]+\)\([^)]+\)\([^)]+\)',
    re.IGNORECASE
)

# No-Intro naming convention: "Game Title (Region) (Rev X) [flags]"
NOINTRO_SUFFIX = re.compile(
    r'\s*\([^)]*\)\s*(?:\[[^\]]*\]\s*)*$'
)


def extract_region(filename: str) -> Optional[str]:
    """Extract region code from a ROM filename.

    Args:
        filename: ROM filename (with or without extension).

    Returns:
        Normalized region code (USA, EUR, JPN, WLD) or None.
    """
    # Check parenthetical region codes
    regions = re.findall(r'[\(\[]([\w,\s]+)[\)\]]', filename)
    for region_str in regions:
        for part in region_str.split(","):
            part = part.strip()
            if part in REGION_MAP:
                return REGION_MAP[part]

    return None


def extract_disc_number(filename: str) -> Optional[int]:
    """Extract disc number from filename.

    Args:
        filename: ROM filename.

    Returns:
        Disc number (1-based) or None.
    """
    match = DISC_PATTERN.search(filename)
    if match:
        return int(match.group(1))

    # Also check for "Disc 1" in title without parens
    match = re.search(r'Disc\s*(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def clean_title(filename: str) -> str:
    """Extract a clean game title from a ROM filename.

    Handles No-Intro, GoodTools, TOSEC, and custom naming conventions.

    Args:
        filename: ROM filename (without extension).

    Returns:
        Clean display-ready game title.
    """
    title = filename

    # Remove file extension if still present
    # Use a targeted approach to avoid Path.stem mishandling dots in parentheses
    for ext in (".zip", ".7z", ".nes", ".smc", ".sfc", ".z64", ".n64", ".v64",
                ".gb", ".gbc", ".gba", ".nds", ".iso", ".gcz", ".ciso", ".wbfs",
                ".rvz", ".dol", ".wad", ".wud", ".wux", ".wua", ".rpx",
                ".bin", ".gen", ".md", ".smd", ".sms", ".gg", ".cdi", ".gdi",
                ".chd", ".m3u", ".cue", ".img", ".mdf", ".pbp", ".ccd",
                ".cso", ".gz", ".nrg", ".dump", ".a26", ".rom", ".xfd",
                ".atr", ".atx", ".cdm", ".cas", ".car", ".a52", ".xex",
                ".a78", ".lnx", ".lyx", ".d64", ".d71", ".d80", ".d81",
                ".d82", ".g64", ".g41", ".x64", ".t64", ".tap", ".prg",
                ".p00", ".crt", ".int", ".col", ".adf", ".uae", ".ipf",
                ".dms", ".adz", ".lha", ".hdf", ".hdz", ".dat",
                ".z1", ".z2", ".z3", ".z4", ".z5", ".z6",
                ".com", ".bat", ".exe", ".dosz",
                ".png", ".jpg", ".jpeg"):
        if title.lower().endswith(ext):
            title = title[:-len(ext)]
            break

    # Handle GoodTools-style dumps: "Game v1.001 (2000)(Publisher)(NTSC)(US)[!]"
    # Remove everything from the version/year pattern onwards
    match = re.search(r'\s+v[\d.]+\s*\(\d{4}\)', title)
    if match:
        title = title[:match.start()]

    # Also handle "Game v1.001 (2000)(stuff)" where version is at end
    # Strip trailing "v1" or "v1.001" from GoodTools remnants
    title = re.sub(r'\s+v\d+(\.\d+)*\s*$', '', title)

    # Remove disc number but remember it
    title = DISC_PATTERN.sub('', title)

    # Remove all parenthetical/bracket tags
    # Process from right to left to handle nested patterns
    title = STRIP_TAGS.sub('', title)

    # Remove remaining parenthetical groups that look like metadata
    # Keep ones that look like subtitles (contain lowercase words)
    def is_metadata(match_obj):
        content = match_obj.group(1)
        # If it's all uppercase/numbers/punctuation, it's metadata
        if re.match(r'^[A-Z0-9\s,.\-!]+$', content):
            return True
        # Known metadata patterns
        if re.match(r'^(Rev|v\d|Proto|Beta|Demo|Sample|\d{4})', content, re.IGNORECASE):
            return True
        return False

    # Remove outer parenthetical metadata but keep subtitle-like content
    remaining = re.findall(r'\(([^)]+)\)', title)
    for content in remaining:
        if is_metadata(re.match(r'(.*)', content)):
            title = title.replace(f'({content})', '')

    # Remove remaining brackets
    title = re.sub(r'\[[^\]]*\]', '', title)

    # Clean up artifacts
    title = re.sub(r'\s*-\s*$', '', title)      # Trailing dash
    title = re.sub(r'\s{2}', ' ', title)        # Multiple spaces
    title = title.strip(' -,')                    # Leading/trailing junk

    # Fix common character issues
    title = title.replace('_', ' ')               # Underscores to spaces
    title = re.sub(r'\s{2}', ' ', title)        # Clean up again

    return title.strip()


# ═══════════════════════════════════════════════════════════════════════
# ROM Scanner
# ═══════════════════════════════════════════════════════════════════════

def scan_rom_folder(system_name: str, folder_path: Path,
                    system_def: Optional[SystemDef] = None) -> List[RomEntry]:
    """Scan a single system ROM folder for valid ROM files.

    Args:
        system_name: System identifier (folder name).
        folder_path: Path to the ROM folder.
        system_def: Optional SystemDef to use (auto-detected if None).

    Returns:
        List of RomEntry objects for valid ROMs found.
    """
    if system_def is None:
        system_def = get_system(system_name)

    if system_def is None:
        logger.warning(f"Unknown system: {system_name}")
        return []

    if not folder_path.is_dir():
        logger.warning(f"ROM folder not found: {folder_path}")
        return []

    roms: List[RomEntry] = []
    seen_titles: Dict[str, RomEntry] = {}

    # Scan files in folder (non-recursive for most systems)
    for item in sorted(folder_path.iterdir()):
        # Skip subdirectories (except for some systems like Dreamcast)
        if item.is_dir():
            # Check if it's a folder-based ROM (Dreamcast, etc.)
            if system_name in ("dreamcast",) and _is_folder_rom(item, system_def):
                rom = _create_rom_entry(item, system_name, is_dir=True)
                if rom:
                    roms.append(rom)
            continue

        # Skip non-ROM files
        if not system_def.is_rom_file(item.name):
            continue

        rom = _create_rom_entry(item, system_name)
        if rom is None:
            continue

        # Dedup multi-disc: keep only Disc 1 entry
        base_title = rom.clean_title
        if base_title in seen_titles:
            existing = seen_titles[base_title]
            if rom.disc_number and rom.disc_number > 1:
                existing.is_multi_disc = True
                continue  # Skip subsequent discs
        else:
            seen_titles[base_title] = rom

        roms.append(rom)

    logger.info(f"Found {len(roms)} ROMs in {system_name} ({folder_path})")
    return roms


def _create_rom_entry(path: Path, system_name: str,
                      is_dir: bool = False) -> Optional[RomEntry]:
    """Create a RomEntry from a file or directory path.

    Args:
        path: Path to the ROM file or directory.
        system_name: System identifier.
        is_dir: Whether this is a directory-based ROM.

    Returns:
        RomEntry or None if the file should be skipped.
    """
    filename = path.name
    stem = path.stem if not is_dir else path.name
    ext = path.suffix.lower() if not is_dir else ""

    # Extract metadata
    region = extract_region(stem)
    disc_num = extract_disc_number(stem)
    title = clean_title(stem)

    if not title:
        logger.debug(f"Empty title after cleaning: {filename}")
        return None

    return RomEntry(
        path=path,
        filename=filename,
        system=system_name,
        raw_title=stem,
        clean_title=title,
        extension=ext,
        is_multi_disc=disc_num is not None and disc_num > 1,
        disc_number=disc_num,
        region=region,
    )


def _is_folder_rom(folder: Path, system_def: SystemDef) -> bool:
    """Check if a directory is a folder-based ROM (e.g., Dreamcast GDI).

    Args:
        folder: Directory to check.
        system_def: System definition for extension matching.

    Returns:
        True if the directory contains ROM data files.
    """
    # Skip known non-ROM folders
    if folder.name.lower() in ("images", "manuals", "media", ".stfolder"):
        return False

    # Check for data files inside
    for f in folder.iterdir():
        if f.suffix.lower() in (".gdi", ".cue", ".cdi"):
            return True
    return False


def scan_all_systems(rom_root: Path) -> Dict[str, List[RomEntry]]:
    """Scan all system folders under a ROM root directory.

    Args:
        rom_root: Root directory containing system folders.

    Returns:
        Dict mapping system names to lists of RomEntry objects.
    """
    if not rom_root.is_dir():
        logger.error(f"ROM root not found: {rom_root}")
        return {}

    results: Dict[str, List[RomEntry]] = {}

    for folder in sorted(rom_root.iterdir()):
        if not folder.is_dir():
            continue

        system_name = folder.name.lower()
        system_def = get_system(system_name)

        if system_def is None:
            logger.info(f"Skipping unknown system folder: {system_name}")
            continue

        roms = scan_rom_folder(system_name, folder, system_def)
        if roms:
            results[system_name] = roms

    total = sum(len(v) for v in results.values())
    logger.info(f"Scanned {len(results)} systems, found {total} total ROMs")
    return results
