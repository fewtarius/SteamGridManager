# AGENTS.md

**Version:** 1.0  
**Date:** 2026-03-16  
**Purpose:** Technical reference for SGM development (methodology in .clio/instructions.md)

---

## Project Overview

**SGM** (SteamGrid Manager) is a CLI tool that backs up, restores, and refreshes custom Steam library artwork on SteamOS. It also manages game libraries with automatic shortcut creation and multi-provider artwork downloads.

- **Language:** Python 3.10+
- **Architecture:** CLI tool with modular components (backup, refresh, monitor, rom, art, export)
- **Target Platform:** SteamOS 3.x (Arch-based), also works on Desktop Linux
- **Philosophy:** The Unbroken Method (see .clio/instructions.md)

**The Problem:** Steam client updates frequently wipe custom game images from the grid folder. Users lose hundreds of carefully selected capsules, heroes, logos, and icons. Managing game artwork across dozens of systems is complex.

**The Solution:** Backup/restore images instantly, re-download from multiple art providers, auto-detect when images are wiped, and manage game libraries with automatic Steam integration.

---

## Quick Setup

```bash
# Install dependencies
pip install requests

# Run SGM
python3 sgm.py status

# First-time config
python3 sgm.py config init

# Backup images
python3 sgm.py backup

# Restore after Steam wipe
python3 sgm.py restore
```

---

## Architecture

```
User runs `sgm <command>`
    |
    v
sgm.py (CLI entry point / argparse, v1.0.0)
    |
    ├── sgm backup ───────> backup.py
    │                         ├── Snapshot grid folder
    │                         ├── Record metadata + state
    │                         └── Store in ~/.local/share/sgm/backups/
    │
    ├── sgm restore ──────> backup.py
    │                         ├── Find latest (or specified) backup
    │                         ├── Copy files + recreate symlinks
    │                         └── Verify restoration
    │
    ├── sgm refresh ──────> refresh.py
    │                         ├── Parse SRM artworkCache.json
    │                         ├── Query SteamGridDB API v2
    │                         ├── Download images in batches
    │                         └── Save with correct naming
    │
    ├── sgm rom ──────────> rom_scanner.py + systems.py + shortcuts.py + art_scraper.py
    │                                    + permissions.py
    │   ├── scan              ├── Scan ROM folders by system
    │   │                     ├── Clean titles (GoodTools/No-Intro/Redump)
    │   │                     └── Group multi-disc games
    │   ├── import            ├── Generate SRM-compatible shortcut IDs
    │   │                     ├── Write to shortcuts.vdf
    │   │                     └── Cascade scrape artwork
    │   └── systems           └── List 33 supported systems
    │
    ├── sgm export ───────> portable.py
    │                         ├── Bundle grid images + metadata
    │                         └── Create manifest for cross-device
    │
    ├── sgm import ───────> portable.py
    │                         ├── Read bundle manifest
    │                         ├── Copy images with ID remapping
    │                         └── Merge/replace/missing modes
    │
    ├── sgm status ───────> steam.py + backup.py
    │                         └── Report current state
    │
    ├── sgm config ───────> config.py
    │                         └── Interactive setup / show config
    │
    └── sgm monitor ──────> monitor.py
                              ├── Install systemd user service
                              ├── Compare grid state vs expected
                              └── Auto-restore if wiped
```

---

## Directory Structure

| Path | Purpose |
|------|---------|
| `sgm.py` | Main CLI entry point (argparse, subcommand routing) |
| `config.py` | Config management (~/.config/sgm/config.json) |
| `backup.py` | Backup/restore engine |
| `refresh.py` | SteamGridDB API client and refresh engine |
| `steam.py` | Steam path/userdata/grid folder discovery |
| `monitor.py` | Auto-detection and systemd service management |
| `systems.py` | 33 system definitions (platform IDs, emulator configs) |
| `rom_scanner.py` | ROM scanning, title cleaning, multi-disc grouping |
| `shortcuts.py` | SRM-compatible shortcut ID generation, shortcuts.vdf R/W |
| `art_scraper.py` | Multi-provider art scraper (ScreenScraper/GamesDB/SGDB) |
| `portable.py` | Cross-device export/import with manifest bundles |
| `permissions.py` | Flatpak sandbox grants so emulators can reach ROM folders |
| `sgm-monitor.service` | systemd user service unit |
| `sgm-monitor.timer` | systemd user timer unit |
| `install.sh` | Quick installer for SteamOS |
| `requirements.txt` | Python dependencies |
| `README.md` | User-facing documentation |
| `tests/` | Test suite |

**Key Data Paths:**

| Path | Purpose |
|------|---------|
| `~/.steam/steam/userdata/<id>/config/grid/` | Steam grid images (what we protect) |
| `~/.config/sgm/config.json` | SGM configuration |
| `~/.local/share/sgm/backups/<timestamp>/` | Backup snapshots |
| `~/.local/share/sgm/state.json` | Last known grid folder state |
| `~/.local/share/sgm/sgm.log` | Application log file |
| `~/.var/app/com.steamgriddb.steam-rom-manager/config/steam-rom-manager/userData/artworkCache.json` | SRM artwork mapping |

**Investigate, don't assume:** Use `ls`, `cat`, `find` to verify paths exist before operating on them.

---

## Code Style

**Python Conventions:**

- Python 3.10+ with type hints
- **UTF-8 encoding** for all files
- **4 spaces** indentation (never tabs)
- **Docstrings** for all public functions and classes
- **Minimal dependencies** - only `requests` beyond stdlib
- Follow PEP 8 style guidelines

**Module Template:**

```python
#!/usr/bin/env python3
"""Module description.

Brief explanation of what this module does and its role in the system.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def example_function(param: str, optional: Optional[int] = None) -> bool:
    """Brief description of function.
    
    Args:
        param: Description of parameter.
        optional: Description of optional parameter.
    
    Returns:
        Description of return value.
    
    Raises:
        FileNotFoundError: When the expected file doesn't exist.
    """
    pass
```

**Logging:**

```python
import logging

logger = logging.getLogger(__name__)

# Levels:
logger.debug("Detailed internal state")    # --verbose / dev only
logger.info("Normal operation progress")    # Default user-visible
logger.warning("Recoverable issue")         # Something unexpected but handled
logger.error("Failed operation")            # Something broke
```

**Error Handling:**

```python
# Use specific exceptions, never bare except
try:
    result = api_call()
except requests.RequestException as e:
    logger.error(f"API call failed: {e}")
    return None

# Path operations - always check existence
grid_path = Path(steam_path) / "userdata" / user_id / "config" / "grid"
if not grid_path.exists():
    logger.error(f"Grid folder not found: {grid_path}")
    raise FileNotFoundError(f"Grid folder not found: {grid_path}")
```

---

## Steam Grid Image Naming Convention

**CRITICAL - these naming patterns are how Steam identifies custom images:**

| Image Type | Filename Pattern | Typical Resolution | Description |
|-----------|-----------------|-------------------|-------------|
| Wide Capsule | `{appid}.png` | 920x430 | Horizontal capsule/banner (recent games shelf) |
| Tall Capsule | `{appid}p.png` | 600x900 | Vertical poster/boxart (library grid view) |
| Hero | `{appid}_hero.png` | 1920x620 | Banner at top of game detail page |
| Logo | `{appid}_logo.png` | ~400x230 | Game logo overlay on hero |
| Icon | `{appid}_icon.png` | 256x256 | Small icon (taskbar, friends) |

**File extensions:** Both `.png` and `.jpg` are valid. Preserve original format.

**Symlinks:** ROM/non-Steam game images may be symlinks pointing to other files in the same directory. These represent aliased app IDs (e.g., different shortcut IDs for the same game).

**Important:** Grid folder app IDs are non-Steam shortcut IDs (large numbers >10M). Official Steam games get their art from `appcache/librarycache/` which is NOT wiped by updates. The grid folder exclusively contains ROM/Heroic/non-Steam game custom art.

---

## SteamGridDB API Reference

**Base URL:** `https://www.steamgriddb.com/api/v2`  
**Authentication:** `Authorization: Bearer <api_key>`  
**API Keys:** Free at https://www.steamgriddb.com/profile/preferences/api  
**IMPORTANT:** API keys are user-provided. NEVER embed or hardcode API keys.

### Key Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/grids/game/{id}` | Get grid (capsule) images for a game |
| GET | `/heroes/game/{id}` | Get hero images for a game |
| GET | `/logos/game/{id}` | Get logo images for a game |
| GET | `/icons/game/{id}` | Get icon images for a game |
| GET | `/games/steam/{appid}` | Look up SteamGridDB game by Steam app ID |

### SRM Artwork Cache Structure

The `artworkCache.json` from Steam ROM Manager maps SteamGridDB game IDs to artwork:

```json
{
  "version": 0,
  "sgdbToArt": {
    "tall": { "<sgdb_game_id>": { "artworkId": "<artwork_id>", "appId": "<steam_appid>" } },
    "long": { ... },
    "hero": { ... },
    "logo": { ... },
    "icon": { ... }
  }
}
```

**Art type mapping to file names:**
| SRM Art Type | SteamGridDB Endpoint | Grid Filename |
|-------------|---------------------|---------------|
| `tall` | `/grids/game/{id}` | `{appid}p.png` |
| `long` | `/grids/game/{id}` (wide) | `{appid}.png` |
| `hero` | `/heroes/game/{id}` | `{appid}_hero.png` |
| `logo` | `/logos/game/{id}` | `{appid}_logo.png` |
| `icon` | `/icons/game/{id}` | `{appid}_icon.png` |

---

## ROM Management Architecture

### Configuration Layering (`defaults/emulators.json` + `~/.config/sgm/emulators.json`)

System and emulator definitions live in **`defaults/emulators.json`**, shipped
with the app. The user's config holds only their own overrides:

```
defaults/emulators.json          definitions, always current with the release
~/.config/sgm/emulators.json     user customizations, sparse by design
```

`EmulatorRegistry._load_and_merge_configs()` layers the user file over the
defaults in memory. It never writes the merged result back: doing so expanded
the user file into a full copy of the defaults, which pinned every value
against future corrections.

**Code-owned keys.** Some system keys describe upstream services, fixed hardware
facts, or how files are recognised. They come from the defaults and are neither
read from nor written to the user config:

| Key | Why code-owned |
|-----|----------------|
| `screenscraper_id`, `thegamesdb_id` | Upstream API identifiers, not preferences |
| `fullname`, `manufacturer`, `hardware_type`, `release_year` | Fixed facts about the console |
| `extensions`, `aliases` | File recognition; a stale copy silently rejects new formats |

Everything else (`default_emulator`, `steam_category`, `scan_as_dirs`,
`legacy_tags`) is a genuine preference and the user wins. A user who needs
different code-owned values adds their own system entry, which is preserved
whole because it has no default to prune against.

`save_config()` runs `prune_config()` first, so a config identical to the
defaults saves as just `{"version": N}`.

### System Definitions

`systems.py` is a compatibility shim over the registry. Definitions are data,
not code:

| Field | Meaning |
|-------|---------|
| `fullname`, `manufacturer` | Display metadata |
| `hardware_type`, `release_year` | Console facts |
| `extensions` | Accepted ROM file extensions |
| `screenscraper_id` | ScreenScraper `systemeid` ( = unscoped) |
| `thegamesdb_id` | TheGamesDB platform ID |
| `default_emulator` | Emulator ID used to build launch commands |
| `steam_category` | Tag and collection name in Steam |
| `legacy_tags` | Older tag strings still matched when replacing shortcuts |
| `scan_as_dirs` | Folder-per-game systems such as PS Vita |
| `aliases` | Alternate folder names that resolve here |

**Adding a system** means adding an entry to `defaults/emulators.json`:

```json
"newsystem": {
  "fullname": "New System",
  "manufacturer": "Publisher",
  "extensions": [".ext1", ".ext2"],
  "screenscraper_id": 123,
  "thegamesdb_id": "456",
  "default_emulator": "retroarch/newsystem_core",
  "steam_category": "New System"
}
```

Look `screenscraper_id` up in ScreenScraper's `systemesListe.php` and
`thegamesdb_id` at thegamesdb.net/list_platforms.php. Never guess or enumerate:
the original values were filled in sequentially, which produced collisions and
made hash lookups fail with HTTP 404 because the ROM hash was being searched on
the wrong console. `tests/test_screenscraper_ids.py` pins the verified values
and rejects two systems sharing an ID.

Use `` only when ScreenScraper genuinely has no matching platform. `arcade` is
the one case: releases are catalogued per board (CPS1/2/3, Cave, Atomiswave)
rather than under a single Arcade entry, so lookups run unscoped.

### ROM Scanner (`rom_scanner.py`)

**Container selection.** One game often exists as several files that clean to
the same title. The scanner keeps one entry per title and prefers the most
complete container: `.chd` > `.cue`/`.gdi` > `.m3u` > `.iso` > `.bin`. A
`.bin`/`.cue` pair resolves to the cue sheet, which carries the track layout the
bare bin lacks. Later discs set `is_multi_disc` on the first entry instead of
adding a shortcut.

**Title cleaning pipeline:**
1. Strip file extension (without using `Path.stem` which breaks on dots in parentheses)
2. Handle GoodTools format: `Game v1.001 (2000)(Publisher)(NTSC)(US)[!]`
3. Strip trailing version numbers: `Game v1.01`
4. Extract disc number: `(Disc 1)`, `(CD 2)`
5. Strip metadata tags: `(USA)`, `(Europe)`, `[!]`, `(Rev A)`, `(En,Fr,De)`
6. Strip remaining all-caps parenthesized metadata
7. Collapse whitespace and dashes

**Multi-disc handling:** Games with `(Disc N)` are grouped by clean title. Only the first disc gets a shortcut.

**Save file filtering:** `.srm`, `.sav`, `.state` files are excluded.

### Shortcut ID Generation (`shortcuts.py`)

Steam uses CRC32-based IDs for non-Steam shortcuts:

```python
def generate_app_id(exe: str, app_name: str) -> int:
    """Generate Steam's non-Steam app ID using CRC32.
    
    Algorithm (matches Steam ROM Manager):
    1. Concatenate exe + app_name as UTF-8
    2. CRC32 hash
    3. Bitwise OR with 0x80000000
    4. Shift left 32 bits
    5. OR with 0x02000000
    
    Returns the full 64-bit app ID.
    """
```

**Short app ID** (used in grid filenames): `(full_app_id >> 32) | 0x02000000`

**shortcuts.vdf format:** Binary format with byte markers:
- `\x00` = start of key-value pair (string)
- `\x01` = string value
- `\x02` = int32 value
- `\x08` / `\x0b` = end markers

### Art Scraper (`art_scraper.py`)

**Provider cascade:**

```
CascadeScraper
├── ScreenScraperProvider (if configured)
│   ├── Uses system-specific platform IDs
│   ├── Searches by ROM filename or game title
│   ├── Returns: box-2D (tall), screenshot (wide), fanart (hero), wheel (logo)
│   └── Rate limited: 1 req/sec
│
├── TheGamesDBProvider (if configured)
│   ├── Uses platform-specific IDs
│   ├── Searches by game title
│   ├── Returns: boxart (tall), fanart (hero), banner (wide)
│   └── Rate limited: 1 req/2sec
│
└── SteamGridDBProvider (if api_key configured)
    ├── Searches by game title (with optional platform filter)
    ├── Returns: grid (tall/wide), hero, logo, icon
    └── Rate limited: 1 req/sec
```

For each game, each art type is tried across providers until found. Missing types from one provider are filled by the next.

**ScreenScraper lookup rules.** A `systemeid` mismatch is the difference between
a hash hit and an HTTP 404: the hash is correct but searched on the wrong
console. Two upstream behaviours need explicit handling:

- A name search with no hits returns HTTP 2 with `"jeux": [{}]`, an empty object
  rather than an empty list. Only an entry carrying a real `id` counts as a
  match.
- `get_artwork` with an empty id produces `jeuInfos.php?gameid=`, which can only
  ever be a 400. Guarded in `ScreenScraper.get_artwork` and again in
  `CascadeScraper._get_artwork`.

**Never log credentials.** ScreenScraper authenticates with `devid`,
`devpassword`, `ssid` and `sspassword` in the query string, and those values end
up in `~/.local/share/sgm/sgm.log`. Pass every URL through `_redact_url()`
before logging it; it masks the parameters named in `SECRET_PARAMS` while
leaving `systemeid`, hashes and filenames visible for debugging.

**Retry policy.** Only `_RETRYABLE_STATUSES` (429, 5xx, network failure) are
retried with backoff. The curl fallback runs only for `_CURL_FALLBACK_STATUSES`
(, 403), where urllib itself is the problem. Retrying a 44 against a rate-limited
API just burns quota.

### Portable Bundle (`portable.py`)

**Bundle structure:**

```
sgm_export_20260316_154500/
├── manifest.json           # Metadata: games, systems, image counts
├── images/                 # All grid images organized by app ID
│   ├── 12345678.png        # Tall capsule
│   ├── 12345678p.png       # Wide capsule
│   ├── 12345678_hero.png   # Hero banner
│   ├── 12345678_logo.png   # Logo
│   └── 12345678_icon.png   # Icon
└── shortcuts.json          # Shortcut definitions for re-creation
```

**Import modes:**
- `merge`: Add missing images, keep existing (default)
- `missing`: Only add art types that don't exist for an app ID
- `replace`: Overwrite everything

### Flatpak Permissions (`permissions.py`)

Flatpak emulators are sandboxed and cannot reach ROM folders unless granted.
Read-only is not sufficient: PCSX2 writes an ISO cache beside the disc image and
will not boot when that write fails, which surfaces as a broken shortcut rather
than a sandbox problem.

| Function | Purpose |
|----------|---------|
| `installed_apps()` | App IDs installed for this user |
| `effective_filesystems(app_id)` | Rules from `flatpak info --show-permissions` |
| `covers_path_rw(entries, path)` | Whether the app can already read **and write** `path` |
| `grant_path(app_id, path)` | Apply `flatpak override --user --filesystem=...` |
| `configured_flatpak_apps(registry)` | App IDs backing the configured emulators |
| `ensure_rom_access(apps, roots)` | Bulk entry point used by import and audit |

`covers_path_rw` treats `home:ro` and `host:ro` as insufficient, resolves the
target so a grant on a parent directory counts, and honours `!entry` negations.
Grants are user-level, scoped to the exact folders named, and idempotent.

`sgm rom import` calls this for the emulators it just used. `sgm rom
permissions <folder> [--fix]` audits every configured emulator.

---

## Configuration Reference

**Config location:** `~/.config/sgm/config.json`

```json
{
  "version": 1,
  "api_key": "",
  "steam_path": "~/.steam/steam",
  "steam_user_id": "auto",
  "backup_path": "~/.local/share/sgm/backups",
  "srm_artwork_cache": "~/.var/app/com.steamgriddb.steam-rom-manager/config/steam-rom-manager/userData/artworkCache.json",
  "auto_restore": true,
  "auto_restore_threshold": 0.5,
  "batch_size": 50,
  "log_level": "info",
  "log_file": "~/.local/share/sgm/sgm.log"
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `api_key` | string | "" | SteamGridDB API key (user-provided) |
| `steam_path` | string | auto | Path to Steam installation |
| `steam_user_id` | string | auto | Steam32 user ID |
| `backup_path` | string | ~/.local/share/sgm/backups | Backup storage location |
| `srm_artwork_cache` | string | (SRM flatpak path) | Path to SRM artworkCache.json |
| `auto_restore` | bool | true | Enable auto-restore on detection |
| `auto_restore_threshold` | float | 0.5 | Trigger restore if file count drops below this ratio |
| `batch_size` | int | 50 | API downloads per batch |
| `log_level` | string | info | Logging verbosity |

**New v2 config keys (optional):**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `screenscraper_devid` | string | "" | ScreenScraper developer ID |
| `screenscraper_devpassword` | string | "" | ScreenScraper developer password |
| `screenscraper_ssid` | string | "" | ScreenScraper username (ssid) |
| `screenscraper_sspassword` | string | "" | ScreenScraper password |
| `thegamesdb_apikey` | string | "" | TheGamesDB API key |

---

## Testing

**Before Committing:**

```bash
# 1. Syntax check
python3 -m py_compile sgm.py
python3 -m py_compile config.py
python3 -m py_compile backup.py
python3 -m py_compile refresh.py
python3 -m py_compile steam.py
python3 -m py_compile monitor.py
python3 -m py_compile systems.py
python3 -m py_compile rom_scanner.py
python3 -m py_compile shortcuts.py
python3 -m py_compile art_scraper.py
python3 -m py_compile permissions.py
python3 -m py_compile portable.py

# 2. Run unit tests
python3 -m pytest tests/ -v

# 3. Quick smoke test
python3 sgm.py status

# 4. Backup dry run
python3 sgm.py backup --dry-run

# 5. Restore dry run
python3 sgm.py restore --dry-run

# 6. ROM scan test
python3 sgm.py rom systems
python3 sgm.py rom scan /run/media/primary/Roms --system c64

# 7. ROM import dry run
python3 sgm.py rom import /run/media/primary/Roms --system c64 --dry-run
```

**Test Locations:**

- `tests/test_backup.py` - Backup/restore tests
- `tests/test_refresh.py` - API refresh tests
- `tests/test_steam.py` - Steam path discovery tests
- `tests/test_monitor.py` - Monitor detection tests
- `tests/test_config.py` - Config management tests
- `tests/test_rom_scanner.py` - ROM scanning and title cleaning tests
- `tests/test_shortcuts.py` - Shortcut ID generation and VDF tests
- `tests/test_art_scraper.py` - Art scraper cascade tests
- `tests/test_portable.py` - Export/import bundle tests
- `tests/test_systems.py` - System definitions validation tests
- `tests/test_emulators_config.py` - Defaults/user-config merge, code-owned keys, sparse save
- `tests/test_screenscraper_ids.py` - Platform ID correctness and uniqueness
- `tests/test_art_scraper_requests.py` - URL redaction, retry policy, empty-match handling
- `tests/test_rom_scanner_containers.py` - Container preference, bin/cue dedup, CHD discovery
- `tests/test_permissions.py` - Flatpak coverage rules and grant behaviour

**Test Requirements:**

1. **Syntax must pass** - All .py files must pass `python3 -m py_compile`
2. **Unit tests must exist** - New features require new tests
3. **Tests must pass** - Exit code 0 required
4. **Dry-run testing** - Use `--dry-run` flags to verify logic without side effects
5. **Never test with real API calls in CI** - Mock the SteamGridDB API

**New Feature Checklist:**

1. Create test file in `tests/`
2. Run: `python3 -m pytest tests/test_feature.py -v`
3. Verify all tests pass
4. Include test in commit

---

## Commit Format

```
type(scope): brief description

Problem: What was broken/incomplete
Solution: How you fixed it
Testing: How you verified the fix
```

**Types:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

**Scopes:** `backup`, `restore`, `refresh`, `monitor`, `config`, `steam`, `cli`

**Example:**

```bash
git add -A
git commit -m "feat(backup): implement full grid folder backup

Problem: No way to save grid images before Steam wipes them
Solution: Added backup engine with timestamped snapshots, metadata, and symlink handling
Testing: Dry-run tested with 4612 files, backup/restore verified"
```

**Pre-Commit Checklist:**

- [ ] `python3 -m py_compile` passes on all changed .py files
- [ ] Docstrings updated if API changed
- [ ] Commit message explains WHAT and WHY
- [ ] No `TODO`/`FIXME` comments (finish the work)
- [ ] Test coverage for new code
- [ ] No handoff files in `ai-assisted/` staged

---

## Development Tools

**Useful Commands:**

```bash
# Check current grid folder state
ls -la ~/.steam/steam/userdata/*/config/grid/ | head -20
ls ~/.steam/steam/userdata/*/config/grid/ | wc -l

# Count image types
cd ~/.steam/steam/userdata/*/config/grid/
ls -1 | grep -oP '(_[a-z]+)?\.(png|jpg)$' | sort | uniq -c | sort -rn

# Check SRM artwork cache
python3 -c "import json; d=json.load(open('$HOME/.var/app/com.steamgriddb.steam-rom-manager/config/steam-rom-manager/userData/artworkCache.json')); print({k:len(v) for k,v in d['sgdbToArt'].items()})"

# Test SteamGridDB API
curl -s -H "Authorization: Bearer YOUR_KEY" https://www.steamgriddb.com/api/v2/games/steam/228980 | python3 -m json.tool

# Check symlinks
find ~/.steam/steam/userdata/*/config/grid/ -maxdepth 1 -type l | wc -l

# Git operations
git status
git log --oneline -10
git diff
```

---

## Common Patterns

**Path Discovery:**

```python
from pathlib import Path

def find_steam_path() -> Path:
    """Find the Steam installation directory."""
    candidates = [
        Path.home() / '.steam' / 'steam',
        Path.home() / '.local' / 'share' / 'Steam',
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Steam installation not found")

def find_grid_path(steam_path: Path) -> Path:
    """Find the grid folder for the first user."""
    userdata = steam_path / 'userdata'
    for user_dir in userdata.iterdir():
        grid = user_dir / 'config' / 'grid'
        if grid.exists():
            return grid
    raise FileNotFoundError("No grid folder found")
```

**Backup Metadata:**

```python
{
    "timestamp": "2026-03-16T14:18:00",
    "source_path": "/home/user/.steam/steam/userdata/12345/config/grid",
    "file_count": 4612,
    "real_files": 3890,
    "symlinks": 722,
    "total_size_bytes": 2362232832,
    "symlink_map": {
        "1234567890.png": "9876543210.png"
    }
}
```

**API Request Pattern:**

```python
import requests

def api_request(endpoint: str, api_key: str) -> dict:
    """Make an authenticated request to SteamGridDB API."""
    url = f"https://www.steamgriddb.com/api/v2{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()
```

---

## Documentation

### What Needs Documentation

| Change Type | Required Documentation |
|-------------|------------------------|
| New feature | Docstring + update README.md |
| CLI change | Update README.md usage section |
| Config change | Update AGENTS.md config reference |
| API integration | Update AGENTS.md API reference |
| Design decision | Add to commit message |

### Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| `README.md` | Installation, usage, configuration | Users |
| `AGENTS.md` | Technical reference | AI agents / developers |
| `.clio/instructions.md` | Project methodology | AI agents |
| `.clio/PRD.md` | Product requirements | Stakeholders |

---

## Anti-Patterns (What NOT To Do)

| Anti-Pattern | Why It's Wrong | What To Do |
|--------------|----------------|------------|
| Hardcode API keys | Security risk, won't work for other users | Use config file, prompt user for key |
| Hardcode Steam paths | Different systems have different paths | Use discovery functions in steam.py |
| Skip `--dry-run` support | Users can't verify before destructive ops | Always implement dry-run flags |
| Bare `except:` clauses | Hides real errors, makes debugging impossible | Catch specific exceptions |
| Ignore symlinks | Breaks ROM/non-Steam game images | Handle symlinks explicitly in backup/restore |
| Download without rate limiting | Gets API key banned | Respect batch sizes, add delays |
| Assume single image format | Some are PNG, some JPG | Preserve original format, don't convert |
| Skip syntax check before commit | Catches errors early | Run `python3 -m py_compile` on all files |
| Use `os.path` instead of `pathlib` | Inconsistent, less readable | Use `pathlib.Path` everywhere |
| Print to stdout for logging | Mixes output with log messages | Use `logging` module, print only user-facing output |
| Guess a platform ID | Sequential values collide and hash lookups 404 | Look it up upstream; tests reject duplicate IDs |
| Log a URL without redacting | Writes API keys and passwords into the log file | Pass it through `_redact_url()` first |
| Merge defaults into the user config | Freezes every value against future corrections | Keep the user file sparse; defaults own the definitions |
| Assume a sandboxed emulator can write to a ROM folder | Game silently fails to launch | Grant read-write access on import; audit with `sgm rom permissions` |

---

## Quick Reference

**Syntax Check:**
```bash
python3 -m py_compile sgm.py
```

**Run Tests:**
```bash
python3 -m pytest tests/ -v
```

**Smoke Test:**
```bash
python3 sgm.py status
```

**Backup:**
```bash
python3 sgm.py backup
python3 sgm.py backup --dry-run
```

**Restore:**
```bash
python3 sgm.py restore
python3 sgm.py restore --list
python3 sgm.py restore --dry-run
```

**Refresh:**
```bash
python3 sgm.py refresh --missing
python3 sgm.py refresh --all
python3 sgm.py refresh --dry-run
```

**Config:**
```bash
python3 sgm.py config init
python3 sgm.py config show
python3 sgm.py config set api_key YOUR_KEY
```

**Monitor:**
```bash
python3 sgm.py monitor install
python3 sgm.py monitor status
python3 sgm.py monitor uninstall
```

---

*For project methodology and workflow, see .clio/instructions.md*  
*For product requirements, see .clio/PRD.md*  
*For universal agent behavior, see system prompt*
