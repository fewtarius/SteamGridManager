#!/usr/bin/env python3
"""SteamGridDB API refresh engine.

Re-downloads custom game images from the SteamGridDB API using
cached artwork mappings from Steam ROM Manager (artworkCache.json).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

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


def _api_request(endpoint: str, api_key: str, params: Optional[dict] = None) -> dict:
    """Make an authenticated request to SteamGridDB API using curl.
    
    Args:
        endpoint: API endpoint path.
        api_key: SteamGridDB API key.
        params: Optional query parameters.
    
    Returns:
        API response as dictionary.
    """
    import subprocess
    from urllib.parse import urlencode
    
    url = f"{STEAMGRIDDB_API}{endpoint}"
    if params:
        url += '?' + urlencode(params)
    
    result = subprocess.run(
        ['curl', '-s', '-H', f'Authorization: Bearer {api_key}', url],
        capture_output=True, text=True, timeout=30,
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    
    return json.loads(result.stdout)


def _download_image(url: str, dest: Path) -> bool:
    """Download an image from URL to destination using curl.
    
    Args:
        url: Image URL.
        dest: Destination file path.
    
    Returns:
        True on success, False on failure.
    """
    import subprocess
    
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ['curl', '-s', '-L', '-o', str(dest), url],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


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


def _get_existing_images(grid_path: Path) -> set[str]:
    """Get set of existing image filenames in the grid folder."""
    if not grid_path.exists():
        return set()
    return {
        entry.name for entry in grid_path.iterdir()
        if entry.is_file() or entry.is_symlink()
    }


def _get_ext_from_url(url: str) -> str:
    """Extract file extension from URL."""
    # Parse URL path to get extension
    path = url.split('?')[0]  # Remove query params
    if '.png' in path.lower():
        return '.png'
    elif '.webp' in path.lower():
        return '.webp'
    elif '.jpg' in path.lower() or '.jpeg' in path.lower():
        return '.jpg'
    return '.png'  # Default


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
    print(f"  SRM:     {sum(len(v) for v in srm_cache.values()):} cached mappings")
    print(f"  Existing: {len(existing):} images in grid folder")
    print(f"  Queue:   {len(queue):} images to download")
    
    if not queue:
        print(f"\n  Nothing to download. Grid images are up to date!")
        return 0
    
    if dry_run:
        print(f"\n  Would download {len(queue):} images")
        # Show sample of what would be downloaded
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
            print(f"    {downloaded:}/{len(queue):} downloaded ({failed} failed)")
            time.sleep(1)  # Rate limiting between batches
        
        try:
            # Get the specific artwork URL
            artwork_id = item['artwork_id']
            
            # If we have an artwork ID, use the direct art endpoint
            if artwork_id:
                try:
                    # For grids, we need to pass dimensions filter for tall vs wide
                    endpoint = item['endpoint'].format(game_id=item['sgdb_game_id'])
                    params = {}
                    if item['art_type'] == 'tall':
                        params['dimensions'] = '600x900'
                    elif item['art_type'] == 'long':
                        params['dimensions'] = '920x430,460x215'
                    
                    data = _api_request(endpoint, api_key, params)
                    
                    if data.get('success') and data.get('data'):
                        # Find the matching artwork, or use first available
                        art_url = None
                        for art in data['data']:
                            if str(art.get('id')) == str(artwork_id):
                                art_url = art.get('url')
                                break
                        if not art_url:
                            art_url = data['data'][0].get('url')
                        
                        if art_url:
                            ext = _get_ext_from_url(art_url)
                            filename = f"{item['app_id']}{item['suffix']}{ext}"
                            dest = grid_path / filename
                            
                            if _download_image(art_url, dest):
                                downloaded += 1
                            else:
                                failed += 1
                        else:
                            failed += 1
                    else:
                        failed += 1
                        
                except Exception as e:
                    logger.debug(f"API error for {item['sgdb_game_id']}: {e}")
                    failed += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            failed += 1
    
    print(f"\n  [OK] Refresh complete!")
    print(f"    Downloaded: {downloaded:}")
    print(f"    Failed:     {failed:}")
    print(f"    Skipped:    {len(queue) - downloaded - failed:}")
    print()
    
    return 0 if failed == 0 else 1
