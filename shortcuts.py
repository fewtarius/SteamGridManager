#!/usr/bin/env python3
"""Steam shortcut ID generation and shortcuts.vdf read/write.

Implements the same CRC32-based ID generation algorithm used by
Steam ROM Manager, so our shortcuts are fully compatible.

The shortcuts.vdf format is a binary key-value format used by Steam
to store non-Steam game shortcuts.
"""

import binascii
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# App ID Generation (matches SRM exactly)
# ═══════════════════════════════════════════════════════════════════════

def generate_preliminary_id(exe: str, appname: str) -> int:
    """Generate the preliminary ID used by Steam for non-Steam shortcuts.

    This matches SRM's generatePreliminaryId() exactly.

    Args:
        exe: The executable path string.
        appname: The app/game display name.

    Returns:
        64-bit preliminary ID.
    """
    key = exe + appname
    crc = binascii.crc32(key.encode("utf-8")) & 0xFFFFFFFF
    top = crc | 0x80000000
    return (top << 32) | 0x02000000


def generate_app_id(exe: str, appname: str) -> str:
    """Generate the full app ID (used for Big Picture grids).

    Matches SRM's generateAppId().

    Args:
        exe: The executable path string.
        appname: The app/game display name.

    Returns:
        String representation of the app ID.
    """
    return str(generate_preliminary_id(exe, appname))


def generate_short_app_id(exe: str, appname: str) -> str:
    """Generate the short app ID (used for grid image filenames).

    Matches SRM's generateShortAppId().
    This is the ID used in grid image filenames: {shortAppId}.png, etc.

    Args:
        exe: The executable path string.
        appname: The app/game display name.

    Returns:
        String representation of the short app ID.
    """
    return str(int(generate_app_id(exe, appname)) >> 32)


def generate_shortcut_id(exe: str, appname: str) -> int:
    """Generate the shortcut ID (stored in shortcuts.vdf as appid).

    Matches SRM's generateShortcutId().

    Args:
        exe: The executable path string.
        appname: The app/game display name.

    Returns:
        Signed 32-bit shortcut ID.
    """
    preliminary = generate_preliminary_id(exe, appname)
    unsigned = preliminary >> 32
    # Convert to signed 32-bit
    if unsigned >= 0x80000000:
        return unsigned - 0x100000000
    return unsigned


def shorten_app_id(long_id: str) -> str:
    """Convert a full app ID to short app ID.

    Args:
        long_id: Full app ID string.

    Returns:
        Short app ID string.
    """
    return str(int(long_id) >> 32)


def lengthen_app_id(short_id: str) -> str:
    """Convert a short app ID to full app ID.

    Args:
        short_id: Short app ID string.

    Returns:
        Full app ID string.
    """
    return str((int(short_id) << 32) | 0x02000000)


# ═══════════════════════════════════════════════════════════════════════
# Shortcut Data Structure
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SteamShortcut:
    """Represents a single non-Steam game shortcut."""
    appid: int                          # Signed 32-bit shortcut ID
    appname: str                        # Display name
    exe: str                            # Executable path (quoted)
    start_dir: str                      # Start-in directory (quoted)
    icon: str = ""                      # Icon path
    shortcut_path: str = ""             # Shortcut path
    launch_options: str = ""            # Additional launch arguments
    is_hidden: int = 0                  # Hidden from library
    allow_desktop_config: int = 1       # Allow desktop config
    allow_overlay: int = 1              # Allow Steam overlay
    openvr: int = 0                     # VR game
    devkit: int = 0                     # Dev kit
    devkit_game_id: str = ""            # Dev kit game ID
    devkit_override_app_id: int = 0     # Dev kit override
    last_play_time: int = 0             # Unix timestamp
    flatpak_appid: str = ""             # Flatpak app ID (custom field)
    tags: Dict[str, str] = field(default_factory=dict)  # Tags/categories

    @property
    def short_app_id(self) -> str:
        """Get the short app ID used for grid image filenames."""
        # Convert signed shortcut ID back to unsigned
        unsigned = self.appid if self.appid >= 0 else self.appid + 0x100000000
        return str(unsigned)

    @property
    def full_app_id(self) -> str:
        """Get the full app ID used for Big Picture grids."""
        return lengthen_app_id(self.short_app_id)


# ═══════════════════════════════════════════════════════════════════════
# shortcuts.vdf Binary Parser
# ═══════════════════════════════════════════════════════════════════════

# VDF binary type markers
VDF_TYPE_OBJECT = 0x00
VDF_TYPE_STRING = 0x01
VDF_TYPE_INT32 = 0x02
VDF_TYPE_END = 0x08

# Known integer fields in shortcuts.vdf
INT32_FIELDS = {
    "appid", "ishidden", "allowdesktopconfig", "allowoverlay",
    "openvr", "devkit", "devkitoverrideappid", "lastplaytime",
}


def read_shortcuts_vdf(path: Path) -> List[SteamShortcut]:
    """Read and parse a shortcuts.vdf file.

    Args:
        path: Path to shortcuts.vdf file.

    Returns:
        List of SteamShortcut objects.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file format is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"shortcuts.vdf not found: {path}")

    data = path.read_bytes()
    shortcuts = []
    pos = 0

    # Skip top-level object marker and "shortcuts" key
    if data[pos:pos + 1] == b'\x00':
        pos += 1
        # Read "shortcuts" key
        end = data.index(b'\x00', pos)
        pos = end + 1

    while pos < len(data):
        # Each shortcut starts with 0x00 + index string
        if data[pos:pos + 1] == b'\x08':
            break  # End of shortcuts object
        if data[pos:pos + 1] == b'\x00':
            pos += 1
            # Read index
            end = data.index(b'\x00', pos)
            pos = end + 1

            # Parse shortcut fields
            shortcut_data, pos = _parse_vdf_object(data, pos)
            shortcut = _dict_to_shortcut(shortcut_data)
            if shortcut:
                shortcuts.append(shortcut)
        else:
            pos += 1

    logger.info(f"Read {len(shortcuts)} shortcuts from {path}")
    return shortcuts


def _parse_vdf_object(data: bytes, pos: int) -> Tuple[dict, int]:
    """Parse a VDF binary object starting at pos.

    Returns:
        Tuple of (parsed dict, new position).
    """
    result = {}

    while pos < len(data):
        type_byte = data[pos]
        pos += 1

        if type_byte == VDF_TYPE_END:
            break

        # Read key name
        end = data.index(b'\x00', pos)
        key = data[pos:end].decode('utf-8', errors='replace').lower()
        pos = end + 1

        if type_byte == VDF_TYPE_STRING:
            # String value
            end = data.index(b'\x00', pos)
            value = data[pos:end].decode('utf-8', errors='replace')
            pos = end + 1
            result[key] = value

        elif type_byte == VDF_TYPE_INT32:
            # 32-bit integer
            value = struct.unpack('<i', data[pos:pos + 4])[0]
            pos += 4
            result[key] = value

        elif type_byte == VDF_TYPE_OBJECT:
            # Nested object (e.g., tags)
            sub_obj, pos = _parse_vdf_object(data, pos)
            result[key] = sub_obj

    return result, pos


def _dict_to_shortcut(data: dict) -> Optional[SteamShortcut]:
    """Convert a parsed VDF dict to a SteamShortcut object."""
    try:
        return SteamShortcut(
            appid=data.get("appid", 0),
            appname=data.get("appname", data.get("AppName", "")),
            exe=data.get("exe", data.get("Exe", "")),
            start_dir=data.get("startdir", data.get("StartDir", "")),
            icon=data.get("icon", data.get("icon", "")),
            shortcut_path=data.get("shortcutpath", ""),
            launch_options=data.get("launchoptions", data.get("LaunchOptions", "")),
            is_hidden=data.get("ishidden", data.get("IsHidden", 0)),
            allow_desktop_config=data.get("allowdesktopconfig", data.get("AllowDesktopConfig", 1)),
            allow_overlay=data.get("allowoverlay", data.get("AllowOverlay", 1)),
            openvr=data.get("openvr", data.get("OpenVR", 0)),
            devkit=data.get("devkit", data.get("Devkit", 0)),
            devkit_game_id=data.get("devkitgameid", data.get("DevkitGameID", "")),
            devkit_override_app_id=data.get("devkitoverrideappid", data.get("DevkitOverrideAppID", 0)),
            last_play_time=data.get("lastplaytime", data.get("LastPlayTime", 0)),
            flatpak_appid=data.get("flatpakappid", data.get("FlatpakAppID", "")),
            tags=data.get("tags", {}),
        )
    except Exception as e:
        logger.warning(f"Failed to parse shortcut: {e}")
        return None


def write_shortcuts_vdf(path: Path, shortcuts: List[SteamShortcut]) -> None:
    """Write shortcuts to a shortcuts.vdf file.

    Args:
        path: Output path for shortcuts.vdf.
        shortcuts: List of SteamShortcut objects to write.
    """
    buf = bytearray()

    # Top-level object: \x00 "shortcuts" \x00
    buf.append(VDF_TYPE_OBJECT)
    buf.extend(b'shortcuts\x00')

    for i, sc in enumerate(shortcuts):
        # Object start: \x00 "index" \x00
        buf.append(VDF_TYPE_OBJECT)
        buf.extend(str(i).encode('utf-8'))
        buf.append(0x00)

        # Write fields
        _write_int32(buf, "appid", sc.appid)
        _write_string(buf, "AppName", sc.appname)
        _write_string(buf, "Exe", sc.exe)
        _write_string(buf, "StartDir", sc.start_dir)
        _write_string(buf, "icon", sc.icon)
        _write_string(buf, "ShortcutPath", sc.shortcut_path)
        _write_string(buf, "LaunchOptions", sc.launch_options)
        _write_int32(buf, "IsHidden", sc.is_hidden)
        _write_int32(buf, "AllowDesktopConfig", sc.allow_desktop_config)
        _write_int32(buf, "AllowOverlay", sc.allow_overlay)
        _write_int32(buf, "OpenVR", sc.openvr)
        _write_int32(buf, "Devkit", sc.devkit)
        _write_string(buf, "DevkitGameID", sc.devkit_game_id)
        _write_int32(buf, "DevkitOverrideAppID", sc.devkit_override_app_id)
        _write_int32(buf, "LastPlayTime", sc.last_play_time)
        _write_string(buf, "FlatpakAppID", sc.flatpak_appid)

        # Tags sub-object
        buf.append(VDF_TYPE_OBJECT)
        buf.extend(b'tags\x00')
        for tag_idx, tag_val in sc.tags.items():
            _write_string(buf, str(tag_idx), str(tag_val))
        buf.append(VDF_TYPE_END)

        # End of shortcut object
        buf.append(VDF_TYPE_END)

    # End of shortcuts object
    buf.append(VDF_TYPE_END)

    # End of root object (top-level container wrapping "shortcuts")
    buf.append(VDF_TYPE_END)

    # Backup existing file
    if path.exists():
        backup = path.with_suffix('.vdf.bak')
        import shutil
        shutil.copy2(path, backup)
        logger.info(f"Backed up existing shortcuts.vdf to {backup}")

    path.write_bytes(bytes(buf))
    logger.info(f"Wrote {len(shortcuts)} shortcuts to {path}")


def _write_string(buf: bytearray, key: str, value: str) -> None:
    """Write a string field to the VDF buffer."""
    buf.append(VDF_TYPE_STRING)
    buf.extend(key.encode('utf-8'))
    buf.append(0x00)
    buf.extend(value.encode('utf-8'))
    buf.append(0x00)


def _write_int32(buf: bytearray, key: str, value: int) -> None:
    """Write a 32-bit integer field to the VDF buffer."""
    buf.append(VDF_TYPE_INT32)
    buf.extend(key.encode('utf-8'))
    buf.append(0x00)
    buf.extend(struct.pack('<i', value))


# ═══════════════════════════════════════════════════════════════════════
# High-Level Operations
# ═══════════════════════════════════════════════════════════════════════

def find_shortcuts_vdf(steam_path: Path, user_id: Optional[str] = None) -> Path:
    """Find the shortcuts.vdf file for a Steam user.

    Args:
        steam_path: Steam installation path.
        user_id: Specific user ID, or None to auto-detect.

    Returns:
        Path to shortcuts.vdf.

    Raises:
        FileNotFoundError: If shortcuts.vdf cannot be found.
    """
    userdata = steam_path / "userdata"

    if user_id:
        vdf = userdata / user_id / "config" / "shortcuts.vdf"
        if vdf.exists():
            return vdf
        raise FileNotFoundError(f"shortcuts.vdf not found for user {user_id}")

    # Auto-detect: find first user with a shortcuts.vdf
    for user_dir in sorted(userdata.iterdir()):
        if not user_dir.is_dir():
            continue
        vdf = user_dir / "config" / "shortcuts.vdf"
        if vdf.exists():
            logger.info(f"Found shortcuts.vdf for user {user_dir.name}")
            return vdf

    raise FileNotFoundError("No shortcuts.vdf found in any user profile")


def get_existing_shortcuts(steam_path: Path,
                           user_id: Optional[str] = None) -> List[SteamShortcut]:
    """Get all existing non-Steam shortcuts.

    Args:
        steam_path: Steam installation path.
        user_id: Specific user ID, or None to auto-detect.

    Returns:
        List of existing shortcuts, or empty list if none found.
    """
    try:
        vdf_path = find_shortcuts_vdf(steam_path, user_id)
        return read_shortcuts_vdf(vdf_path)
    except FileNotFoundError:
        return []


def add_shortcuts(steam_path: Path, new_shortcuts: List[SteamShortcut],
                  user_id: Optional[str] = None,
                  replace_existing: bool = False) -> Tuple[int, int]:
    """Add new shortcuts to shortcuts.vdf, preserving existing ones.

    Args:
        steam_path: Steam installation path.
        new_shortcuts: Shortcuts to add.
        user_id: Specific user ID, or None to auto-detect.
        replace_existing: If True, replace shortcuts with matching appid.

    Returns:
        Tuple of (added_count, skipped_count).
    """
    existing = get_existing_shortcuts(steam_path, user_id)
    existing_ids = {sc.appid for sc in existing}

    added = 0
    skipped = 0

    for new_sc in new_shortcuts:
        if new_sc.appid in existing_ids:
            if replace_existing:
                # Remove old entry
                existing = [sc for sc in existing if sc.appid != new_sc.appid]
                existing.append(new_sc)
                added += 1
            else:
                skipped += 1
        else:
            existing.append(new_sc)
            added += 1

    # Find or create the VDF path
    try:
        vdf_path = find_shortcuts_vdf(steam_path, user_id)
    except FileNotFoundError:
        # Create the config directory if needed
        userdata = steam_path / "userdata"
        if user_id:
            config_dir = userdata / user_id / "config"
        else:
            # Use first user directory
            for user_dir in sorted(userdata.iterdir()):
                if user_dir.is_dir():
                    config_dir = user_dir / "config"
                    break
            else:
                raise FileNotFoundError("No user profile found in Steam userdata")
        config_dir.mkdir(parents=True, exist_ok=True)
        vdf_path = config_dir / "shortcuts.vdf"

    # Skip writing if nothing changed — avoids truncation if killed mid-write
    if added == 0:
        logger.info(f"No new shortcuts to add, skipping VDF write")
        return added, skipped

    write_shortcuts_vdf(vdf_path, existing)
    logger.info(f"Added {added} shortcuts, skipped {skipped} existing")
    return added, skipped


def find_localconfig_vdf(steam_path: Path, user_id: Optional[str] = None) -> Path:
    """Find the localconfig.vdf for a Steam user.

    Args:
        steam_path: Steam installation path.
        user_id: Specific Steam user ID, or None to auto-detect.

    Returns:
        Path to localconfig.vdf.

    Raises:
        FileNotFoundError: If not found.
    """
    userdata = steam_path / "userdata"
    if user_id:
        candidates = [userdata / user_id]
    else:
        candidates = sorted(userdata.iterdir()) if userdata.exists() else []

    for user_dir in candidates:
        vdf = user_dir / "config" / "localconfig.vdf"
        if vdf.exists():
            return vdf

    raise FileNotFoundError("localconfig.vdf not found in Steam userdata")


def update_steam_collections(steam_path: Path,
                              shortcuts_by_category: Dict[str, List[int]],
                              user_id: Optional[str] = None) -> bool:
    """Add shortcuts to Steam library collections in localconfig.vdf.

    Steam ROM Manager uses collection IDs of the form ``srm-<base64(name)>``.
    Steam uses cloud storage (``cloud-storage-namespace-1.json``) as the
    authoritative collection source — ``localconfig.vdf`` is a secondary cache.
    Both files must be updated for collections to appear after Steam starts.

    Each collection entry in ``user-collections`` has the shape::

        {
            "id": "srm-<base64>",
            "added": [<appid>, ...],
            "removed": []
        }

    The collection name IS the base64-decoded ID suffix — Steam derives the
    display name from it at runtime.

    Args:
        steam_path: Steam installation path.
        shortcuts_by_category: Mapping of category name -> list of short app IDs
            (the 32-bit IDs, not the full 64-bit ones).
        user_id: Specific Steam user ID, or None to auto-detect.

    Returns:
        True on success, False on failure.
    """
    import base64
    import json
    import re

    try:
        vdf_path = find_localconfig_vdf(steam_path, user_id)
    except FileNotFoundError as e:
        logger.warning(f"Could not find localconfig.vdf: {e}")
        return False

    # --- Cloud storage update (authoritative source) ---
    cloud_path = vdf_path.parent / "cloudstorage" / "cloud-storage-namespace-1.json"
    cloud_modified_path = vdf_path.parent / "cloudstorage" / "cloud-storage-namespace-1.modified.json"
    if cloud_path.exists():
        try:
            import time as _time
            cloud_data: list = json.load(cloud_path.open(encoding="utf-8"))

            # Build a lookup: key -> index in cloud_data list
            cloud_index: dict[str, int] = {}
            for i, item in enumerate(cloud_data):
                if isinstance(item, list) and len(item) >= 2 and isinstance(item[1], dict):
                    cloud_index[item[1].get("key", "")] = i

            # Get the highest version number currently in the file
            max_version = 1
            for item in cloud_data:
                if isinstance(item, list) and len(item) >= 2:
                    v = item[1].get("version", "0")
                    try:
                        max_version = max(max_version, int(str(v)))
                    except (ValueError, TypeError):
                        pass
            next_version = max_version + 1

            timestamp_ms = int(_time.time() * 1000)

            for category, app_ids in shortcuts_by_category.items():
                if not app_ids:
                    continue

                b64 = base64.b64encode(category.encode("utf-8")).decode().rstrip("=")
                coll_id = f"srm-{b64}"
                cloud_key = f"user-collections.{coll_id}"

                value_obj = {
                    "id": coll_id,
                    "added": list(app_ids),
                    "removed": [],
                }
                new_entry = {
                    "key": cloud_key,
                    "timestamp": timestamp_ms,
                    "value": json.dumps(value_obj, separators=(",", ":")),
                    "version": str(next_version),
                    "conflictResolutionMethod": "custom",
                    "strMethodId": "union-collections",
                }
                if cloud_key in cloud_index:
                    # Replace existing entry (may be is_deleted=True)
                    cloud_data[cloud_index[cloud_key]] = [cloud_key, new_entry]
                else:
                    cloud_data.append([cloud_key, new_entry])
                    cloud_index[cloud_key] = len(cloud_data) - 1

                next_version += 1

            # Write back cloud storage files
            import tempfile as _tempfile, os as _os
            tmp_cloud = cloud_path.with_suffix(".json.sgm_tmp")
            with tmp_cloud.open("w", encoding="utf-8") as f:
                json.dump(cloud_data, f, separators=(",", ":"))
            _os.replace(tmp_cloud, cloud_path)

            # Clear the modified file (pending changes) — we've written the full state
            cloud_modified_path.write_text("[]", encoding="utf-8")

            logger.info(f"Updated cloud-storage-namespace-1.json with Steam collections")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to update cloud storage collections: {e}")
    else:
        logger.debug(f"Cloud storage not found at {cloud_path}, skipping")

    try:
        content = vdf_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to read localconfig.vdf: {e}")
        return False

    # Extract the user-collections JSON value (it's a JSON string escaped inside VDF)
    pattern = re.compile(r'("user-collections"\t+)"(.*?)"(\s*\n)', re.DOTALL)
    match = pattern.search(content)

    if match:
        raw_json = match.group(2).replace('\\"', '"')
        try:
            collections: dict = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse user-collections JSON: {e}")
            return False
    else:
        # No user-collections key yet — we'll create it
        collections = {}

    changed = False
    for category, app_ids in shortcuts_by_category.items():
        if not app_ids:
            continue

        b64 = base64.b64encode(category.encode("utf-8")).decode().rstrip("=")
        coll_id = f"srm-{b64}"

        if coll_id not in collections:
            collections[coll_id] = {"id": coll_id, "added": [], "removed": []}
            logger.info(f"Creating Steam collection: {category!r} ({coll_id})")
            changed = True

        existing_added: list = collections[coll_id]["added"]
        new_ids = [aid for aid in app_ids if aid not in existing_added]
        if new_ids:
            existing_added.extend(new_ids)
            logger.info(f"Added {len(new_ids)} app IDs to collection {category!r}")
            changed = True

    if not changed:
        logger.debug("No collection changes needed")
        return True

    # Serialise back — escape quotes for VDF embedding
    new_json = json.dumps(collections, separators=(",", ":")).replace('"', '\\"')

    if match:
        new_content = (
            content[: match.start()]
            + match.group(1)
            + f'"{new_json}"'
            + match.group(3)
            + content[match.end():]
        )
    else:
        # Append before the closing braces of the appropriate section.
        # Simplest safe approach: insert before the last occurrence of closing
        # section markers (two closing braces at the end of the Software block).
        insert_line = f'\t\t"user-collections"\t\t"{new_json}"\n'
        # Find a sensible insertion point — after "user-roaming-config-store"
        insert_match = re.search(r'("user-roaming-config-store".*?\n)', content, re.DOTALL)
        if insert_match:
            pos = insert_match.end()
            new_content = content[:pos] + insert_line + content[pos:]
        else:
            # Fallback: append before the last closing brace block
            new_content = content.rstrip() + "\n" + insert_line

    try:
        # Write atomically via temp file
        import tempfile, os
        tmp = vdf_path.with_suffix(".vdf.sgm_tmp")
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, vdf_path)
        logger.info(f"Updated localconfig.vdf with Steam collections")
        return True
    except OSError as e:
        logger.error(f"Failed to write localconfig.vdf: {e}")
        return False
