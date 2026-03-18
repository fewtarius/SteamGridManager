#!/usr/bin/env python3
"""SteamGridDB API refresh engine.

Re-downloads custom game images from the SteamGridDB API using
cached artwork mappings from Steam ROM Manager (artworkCache.json).

This module handles SRM-managed games only (those in artworkCache.json).
For ROM/shortcut games without SRM mappings, use 'sgm rom art scrape'.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

STEAMGRIDDB_API = "https://www.steamgriddb.com/api/v2"

# Map from SRM art types to grid filename suffixes
ART_TYPE_MAP = {
    'tall': 'p',          # {appid}p.ext (poster/boxart in library grid)
    'long': '',           # {appid}.ext (horizontal capsule/banner)
    'hero': '_hero',      # {appid}_hero.ext
    'logo': '_logo',      # {appid}_logo.ext
    'icon': '_icon',      # {appid}_icon.ext
}

# Map from art types to SteamGridDB API endpoints
ART_ENDPOINT_MAP = {
    'tall': '/grids/game/{game_id}',
    'long': '/grids/game/{game_id}',
    'hero': '/heroes/game/{game_id}',
    'logo': '/logos/game/{game_id}',
    'icon': '/icons/game/{game_id}',
}


def load_srm_artwork_cache(cache_path: str) -> dict:
    """Load and parse the SRM artwork cache.

    Args:
        cache_path: Path to artworkCache.json.

    Returns:
        Dictionary mapping art_type -> {sgdb_game_id: {artworkId, appId}}.
    """
    path = Path(cache_path)
    if not path.exists():
        logger.warning(f"SRM artwork cache not found: {path}")
        return {}

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data.get('sgdbToArt', {})


def _get_existing_images(grid_path: Path) -> set:
    """Get set of existing image filenames in the grid folder."""
    if not grid_path.exists():
        return set()
    return {
        entry.name for entry in grid_path.iterdir()
        if entry.is_file() or entry.is_symlink()
    }


def _ext_from_url(url: str) -> str:
    """Infer file extension from a URL path."""
    path = url.split('?')[0].lower()
    if '.png' in path:
        return '.png'
    elif '.webp' in path:
        return '.webp'
    elif '.jpg' in path or '.jpeg' in path:
        return '.jpg'
    return '.png'


def refresh_images(
    grid_path: Path,
    api_key: str,
    srm_cache_path: str,
    mode: str = 'missing',
    image_type: Optional[str] = None,
    batch_size: int = 50,
    dry_run: bool = False,
) -> int:
    """Refresh images from SteamGridDB API.

    Uses SRM artworkCache.json to know the exact artwork ID that was originally
    selected for each game and re-downloads it.  Only applies to games managed
    by Steam ROM Manager.  For ROM/shortcut art, use 'sgm rom art scrape'.

    Args:
        grid_path: Path to the grid folder.
        api_key: SteamGridDB API key.
        srm_cache_path: Path to SRM artworkCache.json.
        mode: 'missing' (only missing images) or 'all' (re-download everything).
        image_type: Optional specific type to refresh (tall, wide, hero, logo, icon).
        batch_size: Number of images to download per batch.
        dry_run: If True, only show what would be downloaded.

    Returns:
        Exit code (0 for success).
    """
    from art_scraper import download_image, _http_get_json

    print(f"\n  {'[DRY RUN] ' if dry_run else ''}Refresh Images from SteamGridDB\n")

    # Load SRM cache
    srm_cache = load_srm_artwork_cache(srm_cache_path) if srm_cache_path else {}
    if not srm_cache:
        print("  Warning: No SRM artwork cache found. Cannot determine which images to download.")
        print("  Ensure Steam ROM Manager has been run at least once.")
        return 1

    # Get existing images
    existing = _get_existing_images(grid_path)

    # Determine what types to refresh
    if image_type:
        # Map user-facing names to SRM names
        type_remap = {'tall': 'tall', 'wide': 'long', 'hero': 'hero', 'logo': 'logo', 'icon': 'icon'}
        types_to_refresh = [type_remap.get(image_type, image_type)]
    else:
        types_to_refresh = list(ART_TYPE_MAP.keys())

    # Build download queue
    queue = []

    for art_type in types_to_refresh:
        if art_type not in srm_cache:
            continue

        suffix = ART_TYPE_MAP.get(art_type, '')
        endpoint_template = ART_ENDPOINT_MAP.get(art_type, '')

        for sgdb_game_id, art_info in srm_cache[art_type].items():
            app_id = art_info.get('appId', '')
            artwork_id = art_info.get('artworkId', '')

            if not app_id:
                continue

            # Check if image already exists (any extension)
            if mode == 'missing':
                base_name = f"{app_id}{suffix}"
                has_existing = any(
                    fname.startswith(base_name + '.') for fname in existing
                )
                if has_existing:
                    continue

            queue.append({
                'art_type': art_type,
                'sgdb_game_id': sgdb_game_id,
                'artwork_id': artwork_id,
                'app_id': app_id,
                'suffix': suffix,
                'endpoint': endpoint_template,
            })

    print(f"  Mode:    {'All images' if mode == 'all' else 'Missing only'}")
    if image_type:
        print(f"  Type:    {image_type}")
    print(f"  SRM:     {sum(len(v) for v in srm_cache.values())} cached mappings")
    print(f"  Existing: {len(existing)} images in grid folder")
    print(f"  Queue:   {len(queue)} images to download")

    if not queue:
        print(f"\n  Nothing to download. Grid images are up to date!")
        return 0

    if dry_run:
        print(f"\n  Would download {len(queue)} images")
        for item in queue[:10]:
            base = f"{item['app_id']}{item['suffix']}"
            print(f"    {item['art_type']}: {base}.*")
        if len(queue) > 10:
            print(f"    ... and {len(queue) - 10} more")
        print(f"\n  Dry run complete. No files were downloaded.")
        return 0

    # Download in batches
    print(f"\n  Downloading...")
    downloaded = 0
    failed = 0

    for i, item in enumerate(queue):
        if i > 0 and i % batch_size == 0:
            print(f"    {downloaded}/{len(queue)} downloaded ({failed} failed)")
            time.sleep(1)  # Rate limiting between batches

        try:
            artwork_id = item['artwork_id']

            if not artwork_id:
                failed += 1
                continue

            # Build the SGDB API URL
            endpoint = item['endpoint'].format(game_id=item['sgdb_game_id'])
            params: dict = {}
            if item['art_type'] == 'tall':
                params['dimensions'] = '600x900'
            elif item['art_type'] == 'long':
                params['dimensions'] = '920x430,460x215'

            url = f"{STEAMGRIDDB_API}{endpoint}"
            if params:
                url += '?' + urlencode(params)

            data = _http_get_json(url, headers={"Authorization": f"Bearer {api_key}"})
            if not data:
                failed += 1
                continue

            if not data.get('success') or not data.get('data'):
                failed += 1
                continue

            # Find the exact artwork ID; fall back to first result
            art_url = None
            for art in data['data']:
                if str(art.get('id')) == str(artwork_id):
                    art_url = art.get('url')
                    break
            if not art_url:
                art_url = data['data'][0].get('url')

            if not art_url:
                failed += 1
                continue

            ext = _ext_from_url(art_url)
            filename = f"{item['app_id']}{item['suffix']}{ext}"
            dest = grid_path / filename

            if download_image(art_url, dest):
                downloaded += 1
            else:
                failed += 1

        except Exception as e:
            logger.error(f"Unexpected error for {item.get('sgdb_game_id')}: {e}")
            failed += 1

    print(f"\n  [OK] Refresh complete!")
    print(f"    Downloaded: {downloaded}")
    print(f"    Failed:     {failed}")
    print(f"    Skipped:    {len(queue) - downloaded - failed}")
    print()

    return 0 if failed == 0 else 1
