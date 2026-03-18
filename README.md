# SteamGrid Manager (sgm)

Back up, restore, and manage custom Steam library artwork on SteamOS. Scan game libraries, create Steam shortcuts, and download artwork automatically.

## The Problem

On SteamOS (Steam Deck), custom game images (capsules, heroes, logos, icons) live in the Steam userdata grid folder. These get set by tools like Steam ROM Manager, Heroic Launcher, or the Decky SteamGridDB plugin. Steam client updates frequently wipe this folder, destroying all custom artwork.

## The Solution

`sgm` backs up and restores grid images, re-downloads from multiple art providers, auto-detects when images are wiped, and manages game libraries with Steam integration.

```bash
sgm backup                         # snapshot all grid images
sgm restore                        # restore after a Steam wipe
sgm refresh --missing              # re-download missing from SteamGridDB
sgm monitor install                # auto-restore when images are wiped
sgm rom scan /path/to/Roms         # scan game library
sgm rom import /path/to/Roms       # create shortcuts + download artwork
sgm export create                  # portable bundle for another device
```

---

## Quick Start

### 1. Install

On SteamOS (Steam Deck):

```bash
curl -fsSL https://raw.githubusercontent.com/fewtarius/SteamGridManager/main/install.sh | bash
```

Or manually:

```bash
git clone https://github.com/fewtarius/SteamGridManager.git ~/.local/share/sgm
cd ~/.local/share/sgm
pip install requests
```

### 2. Configure

```bash
sgm config init
```

This walks you through:
- Finding your Steam installation (auto-detected on SteamOS)
- Setting your SteamGridDB API key (free, see [Getting API Keys](#getting-api-keys))
- Choosing a backup location

### 3. First Backup

```bash
sgm backup
```

### 4. Check Status

```bash
sgm status
```

---

## Getting API Keys

sgm can download artwork from up to three providers. Each requires a free API key.

### SteamGridDB (recommended)

SteamGridDB is the primary artwork source. Required for `sgm refresh`, recommended for `sgm rom import`.

1. Go to [steamgriddb.com](https://www.steamgriddb.com/)
2. Create a free account or sign in
3. Go to Profile > Preferences > API
   (direct link: https://www.steamgriddb.com/profile/preferences/api)
4. Generate an API key
5. Set it: `sgm config set api_key YOUR_KEY_HERE`

### ScreenScraper (optional)

Good coverage for retro games. First provider checked in the cascade.

1. Go to [screenscraper.fr](https://www.screenscraper.fr/)
2. Create a free account
3. The ScreenScraper API requires developer credentials (devid/devpassword) tied to scraping apps. Most users won't need this - SteamGridDB alone has excellent coverage.
4. If you have dev credentials:
   ```bash
   sgm config set screenscraper_devid YOUR_DEVID
   sgm config set screenscraper_devpassword YOUR_DEVPASS
   sgm config set screenscraper_ssid YOUR_USERNAME
   sgm config set screenscraper_sspassword YOUR_PASSWORD
   ```

### TheGamesDB (optional)

Community-driven database with good metadata.

1. Go to [thegamesdb.net](https://thegamesdb.net/)
2. Request a free API key
3. Set it: `sgm config set thegamesdb_apikey YOUR_KEY_HERE`

### Cascade Order

When downloading artwork, sgm checks providers in this order:

```
ScreenScraper -> TheGamesDB -> SteamGridDB
```

If a provider doesn't have a particular art type, the next one is tried. This maximizes coverage for obscure titles.

For most users, just SteamGridDB is enough. It has the best coverage for Steam-friendly artwork sizes.

---

## Commands

### `sgm status`

Show current state: image counts by type, backup info, config status, monitor service.

```bash
sgm status
```

### `sgm backup [--dry-run]`

Create a timestamped backup of all grid images including symlinks.

```bash
sgm backup              # create backup
sgm backup --dry-run    # preview without backing up
```

### `sgm restore [--list] [--timestamp TS] [--dry-run] [--force]`

Restore grid images from a backup snapshot.

```bash
sgm restore              # restore latest backup
sgm restore --list       # list available backups
sgm restore -t 20260316  # restore specific backup
sgm restore --dry-run    # preview without restoring
sgm restore --force      # skip confirmation prompt
```

### `sgm refresh [--all|--missing|--shortcuts] [--type TYPE] [--dry-run]`

Re-download images from SteamGridDB using SRM artwork cache mappings.

```bash
sgm refresh --missing        # only download missing images (default)
sgm refresh --all            # re-download everything
sgm refresh --shortcuts      # scrape art for non-ROM shortcuts (Heroic, flatpaks, other games)
sgm refresh --type hero      # only refresh hero banners
sgm refresh --dry-run        # preview without downloading
```

Requires a SteamGridDB API key.

### `sgm heroic [--no-art] [--dry-run]`

Import games from Heroic Games Launcher as Steam non-Steam shortcuts and download artwork.

```bash
sgm heroic               # import new Heroic games and download art
sgm heroic --no-art      # import shortcuts only, skip art download
sgm heroic --dry-run     # preview what would be imported
```

Reads Heroic's game library config (GOG/Epic/Amazon) and adds any games not already in
Steam's shortcuts.vdf. Existing shortcuts are never overwritten.

### `sgm config {init|show|set}`

Manage configuration.

```bash
sgm config init              # interactive setup wizard
sgm config show              # display current config
sgm config set api_key KEY   # set a value
```

### `sgm monitor {install|uninstall|status|run}`

Manage the systemd service that auto-restores when Steam wipes grid images.

```bash
sgm monitor install     # install and start the service
sgm monitor status      # check service status
sgm monitor uninstall   # remove the service
sgm monitor run         # run a one-time check
```

---

## Game Library Management

sgm can scan a game library, create Steam shortcuts, and download artwork. This gives your game collection a native Steam library experience.

### Scan

```bash
sgm rom scan /path/to/Roms
sgm rom scan /path/to/Roms --system snes    # scan one system only
```

### Import

```bash
sgm rom import /path/to/Roms               # all systems
sgm rom import /path/to/Roms --system nes   # one system
sgm rom import /path/to/Roms --dry-run      # preview only
sgm rom import /path/to/Roms --no-art       # skip artwork download
```

Import does the following:

1. Scans ROMs and cleans filenames into human-readable titles
2. Creates Steam shortcuts (won't duplicate existing entries)
3. Downloads artwork from configured providers
4. Saves images with correct Steam grid naming

Restart Steam after importing to see the new entries.

### List Supported Systems

```bash
sgm rom systems
```

### ROM Folder Layout

sgm expects ROMs organized by system folder name:

```
Roms/
+-- nes/
|   +-- Game Title (USA).nes
|   +-- Another Game (USA).nes
+-- snes/
|   +-- Game Title (USA).sfc
+-- genesis/
|   +-- Game Title (USA).md
+-- psx/
|   +-- Game Title (Disc 1).bin
|   +-- Game Title (Disc 1).cue
|   +-- Game Title (Disc 2).bin
+-- ...
```

### Supported Systems

| Folder | System | Manufacturer |
|--------|--------|--------------|
| `amiga` | Amiga | Commodore |
| `arcade` | Arcade | Various |
| `atari2600` | Atari 2600 | Atari |
| `atari5200` | Atari 5200 | Atari |
| `atari7800` | Atari 7800 | Atari |
| `atarilynx` | Atari Lynx | Atari |
| `c64` | Commodore 64 | Commodore |
| `coleco` | ColecoVision | Coleco |
| `dreamcast` | Dreamcast | Sega |
| `gamecube` | GameCube | Nintendo |
| `gamegear` | Game Gear | Sega |
| `gb` | Game Boy | Nintendo |
| `gba` | Game Boy Advance | Nintendo |
| `gbc` | Game Boy Color | Nintendo |
| `genesis` | Genesis / Mega Drive | Sega |
| `infocom` | Infocom / Z-Machine | Infocom |
| `intellivision` | Intellivision | Mattel |
| `mastersystem` | Master System | Sega |
| `n64` | Nintendo 64 | Nintendo |
| `nds` | Nintendo DS | Nintendo |
| `neogeo` | Neo Geo | SNK |
| `nes` | NES | Nintendo |
| `pc` | DOS | Microsoft |
| `ps2` | PlayStation 2 | Sony |
| `psp` | PlayStation Portable | Sony |
| `psx` | PlayStation | Sony |
| `saturn` | Saturn | Sega |
| `snes` | Super Nintendo | Nintendo |
| `vic20` | VIC-20 | Commodore |
| `wii` | Wii | Nintendo |
| `wiiu` | Wii U | Nintendo |
| `xbox` | Xbox | Microsoft |
| `zmachine` | Z-Machine | Infocom |

### Title Cleaning

sgm cleans ROM filenames automatically:

| Input | Output |
|-------|--------|
| `Game Title (USA).sfc` | Game Title |
| `Game Title (USA) (v1.01).iso` | Game Title |
| `Game v1.001 (2000)(Publisher)(NTSC)(US)[!]` | Game |
| `Game Title (Disc 1).iso` | Game Title |
| `Game Title (Europe) (En,Fr,De).iso` | Game Title |

Handles GoodTools, No-Intro, and Redump naming conventions. Multi-disc games are grouped automatically.

---

## Portable Backup

Transfer your entire game library (images + shortcuts) between devices.

### Export

```bash
sgm export create                  # create bundle in default backup location
sgm export create -o /mnt/usb/     # export to USB drive
sgm export create -n my_backup     # custom bundle name
sgm export list                    # list available bundles
```

### Import on Another Device

```bash
sgm import /path/to/bundle         # merge with existing (default)
sgm import /path/to/bundle --missing  # only fill in missing art types
sgm import /path/to/bundle --replace  # overwrite all existing
sgm import /path/to/bundle --dry-run  # preview only
```

---

## Configuration

Config file: `~/.config/sgm/config.json`

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | *(empty)* | SteamGridDB API key |
| `steam_path` | auto-detected | Steam installation path |
| `steam_user_id` | auto-detected | Steam user ID |
| `backup_path` | `~/.local/share/sgm/backups` | Backup storage |
| `srm_artwork_cache` | auto-detected | SRM artworkCache.json path |
| `auto_restore` | `true` | Auto-restore when wiped |
| `auto_restore_threshold` | `0.5` | Trigger when file count drops below 50% |
| `batch_size` | `50` | Downloads per batch |
| `log_level` | `info` | Log verbosity (debug, info, warning, error) |
| `screenscraper_devid` | *(empty)* | ScreenScraper developer ID |
| `screenscraper_devpassword` | *(empty)* | ScreenScraper developer password |
| `screenscraper_ssid` | *(empty)* | ScreenScraper username (ssid) |
| `screenscraper_sspassword` | *(empty)* | ScreenScraper password |
| `thegamesdb_apikey` | *(empty)* | TheGamesDB API key |

Don't share your config file - it contains your API keys.

---

## How It Works

### Artwork Protection

1. **Backup** copies all grid images (including symlinks) to a timestamped snapshot
2. **Restore** copies files back and recreates symlinks from the saved map
3. **Refresh** uses SRM's artworkCache.json to map app IDs to SteamGridDB game IDs, then downloads matching artwork
4. **Monitor** checks the grid folder periodically via systemd and auto-restores if file count drops significantly

### ROM Import

1. Scans ROM folder tree, matching subfolder names to known systems
2. Strips metadata (region, version, dump info) from filenames
3. Generates Steam shortcut IDs using the same CRC32 algorithm as Steam ROM Manager
4. Writes entries to Steam's shortcuts.vdf (non-destructive)
5. Cascades through art providers to find artwork for each game

### Grid Image Types

| Type | Filename | Size | Location in Steam |
|------|----------|------|-------------------|
| Tall capsule | `{id}p.png` | 600x900 | Library grid |
| Wide capsule | `{id}.png` | 920x430 | Shelf/carousel |
| Hero | `{id}_hero.png` | 1920x620 | Game detail banner |
| Logo | `{id}_logo.png` | ~400x230 | Overlay on hero |
| Icon | `{id}_icon.png` | 256x256 | Taskbar, friends |

---

## Requirements

- Python 3.10+
- `requests` (`pip install requests`)
- SteamOS or Linux with Steam installed
- SteamGridDB API key (free) for artwork features
- (optional) Steam ROM Manager for refresh mappings
- (optional) ScreenScraper / TheGamesDB keys for more ROM art coverage

## Security

- API keys are stored locally in `~/.config/sgm/config.json`
- Keys are only sent to their respective API endpoints
- No keys are hardcoded in the source
- Don't commit or share your config file
- Use `--dry-run` on any command to preview before making changes

## License

GPLv3. See [LICENSE](LICENSE) for details.
