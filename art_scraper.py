#!/usr/bin/env python3
"""Multi-provider artwork scraper for ROM games.

Cascading search: ScreenScraper -> TheGamesDB -> SteamGridDB.
Downloads box art, screenshots, logos, etc. and converts to Steam
grid image format.

Each provider is a class with a standard interface:
    search_game(title, system) -> game_id
    get_artwork(game_id, art_types) -> dict of art_type -> image_url
"""

import hashlib
import json
import os
import zlib
import shutil
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, NamedTuple


# ═══════════════════════════════════════════════════════════════════════
# ROM Hashing
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# Art Cache
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_CACHE_DIR = Path.home() / ".local" / "share" / "sgm" / "art_cache"


def _cache_key(title: str, system_name: str) -> str:
    """Build a filesystem-safe cache directory name from title + system."""
    raw = f"{system_name}::{title}"
    # Hash to avoid filesystem issues with long/weird titles
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return h


def get_cached_art(title: str, system_name: str,
                   cache_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Return cached art files for a game, keyed by art_type.

    Returns a dict like {'tall': Path(...), 'hero': Path(...), ...}.
    Only returns types that are actually present in the cache.
    """
    base = cache_dir or DEFAULT_CACHE_DIR
    game_cache = base / _cache_key(title, system_name)
    if not game_cache.exists():
        return {}
    result: Dict[str, Path] = {}
    for art_type in ART_TYPES:
        for ext in (".png", ".jpg"):
            p = game_cache / f"{art_type}{ext}"
            if p.exists():
                result[art_type] = p
                break
    return result


def store_art_in_cache(title: str, system_name: str,
                       art_files: Dict[str, Path],
                       cache_dir: Optional[Path] = None) -> None:
    """Copy downloaded/existing art files into the persistent cache.

    Args:
        title: Clean game title.
        system_name: System name (e.g. 'snes').
        art_files: Dict of art_type -> source Path.
        cache_dir: Override default cache directory.
    """
    base = cache_dir or DEFAULT_CACHE_DIR
    game_cache = base / _cache_key(title, system_name)
    game_cache.mkdir(parents=True, exist_ok=True)
    # Store a meta file so humans can grep the cache:
    meta = game_cache / "meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({"title": title, "system": system_name}))
    for art_type, src in art_files.items():
        if not src.exists():
            continue
        dst = game_cache / f"{art_type}{src.suffix}"
        if not dst.exists():
            shutil.copy2(src, dst)
            logger.debug(f"Cached {art_type} for '{title}' ({system_name})")


def populate_cache_from_grid(shortcuts, grid_path: Path,
                              cache_dir: Optional[Path] = None) -> int:
    """Scan existing grid art and populate the cache from matched shortcuts.

    For each shortcut that has art in the grid folder, copies those files
    into the art cache keyed by the shortcut's appname + system tag.
    Returns number of games cached.
    """
    from shortcuts import generate_short_app_id  # local import to avoid circular
    base = cache_dir or DEFAULT_CACHE_DIR
    art_suffixes = {
        "p.png": "tall", "p.jpg": "tall",
        ".png": "wide",  ".jpg": "wide",
        "_hero.png": "hero", "_hero.jpg": "hero",
        "_logo.png": "logo", "_logo.jpg": "logo",
        "_icon.png": "icon", "_icon.jpg": "icon",
    }

    cached_games = 0
    for sc in shortcuts:
        sid = generate_short_app_id(sc.exe, sc.appname)
        # Determine system name from tags (first tag value) or empty string
        system_name = ""
        if sc.tags:
            system_name = list(sc.tags.values())[0] if sc.tags else ""

        art_files: Dict[str, Path] = {}
        for suffix, art_type in art_suffixes.items():
            p = grid_path / f"{sid}{suffix}"
            if p.exists() and art_type not in art_files:
                art_files[art_type] = p

        if art_files:
            store_art_in_cache(sc.appname, system_name, art_files, cache_dir=base)
            cached_games += 1

    return cached_games


class RomHashes(NamedTuple):
    """ROM file hashes and size for ScreenScraper lookup."""
    crc: str       # CRC32 (uppercase hex, no 0x prefix)
    md5: str       # MD5 (uppercase hex)
    sha1: str      # SHA1 (uppercase hex)
    size: int      # File size in bytes


def compute_rom_hashes(rom_path: Path,
                       progress_cb=None) -> Optional["RomHashes"]:
    """Compute CRC32, MD5, and SHA1 hashes of a ROM file.

    Reads the file in chunks to avoid loading large ROMs into memory.
    Calls progress_cb(bytes_read, total_bytes) periodically if provided.

    Args:
        rom_path: Path to the ROM file.
        progress_cb: Optional callback(bytes_read, total_bytes).

    Returns:
        RomHashes with crc, md5, sha1, size — or None on error.
    """
    try:
        size = rom_path.stat().st_size
    except OSError as e:
        logger.warning(f"Cannot stat ROM for hashing: {rom_path}: {e}")
        return None

    crc32_val = 0
    md5_h = hashlib.md5()
    sha1_h = hashlib.sha1()
    chunk_size = 1024 * 1024  # 1 MiB
    read_so_far = 0

    try:
        with open(rom_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                crc32_val = zlib.crc32(chunk, crc32_val)
                md5_h.update(chunk)
                sha1_h.update(chunk)
                read_so_far += len(chunk)
                if progress_cb:
                    progress_cb(read_so_far, size)
    except OSError as e:
        logger.warning(f"Error reading ROM for hashing: {rom_path}: {e}")
        return None

    # CRC32 result is a signed 32-bit int in Python; mask to unsigned
    crc_hex = f"{crc32_val & 0xFFFFFFFF:08X}"
    return RomHashes(
        crc=crc_hex,
        md5=md5_h.hexdigest().upper(),
        sha1=sha1_h.hexdigest().upper(),
        size=size,
    )

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Art Type Definitions
# ═══════════════════════════════════════════════════════════════════════

# Maps to Steam grid naming: {appid}.png, {appid}p.png, {appid}_hero.png, etc.
ART_TYPES = ["tall", "wide", "hero", "logo", "icon"]

@dataclass
class ArtResult:
    """A single artwork image result from a provider."""
    url: str
    art_type: str = ""  # tall, wide, hero, logo, icon
    provider: str = ""  # screenscraper, thegamesdb, steamgriddb, cache
    width: int = 0
    height: int = 0
    mime_type: str = ""
    score: float = 0.0  # Quality/relevance score

    @property
    def extension(self) -> str:
        """Determine file extension from URL or mime type."""
        if self.mime_type:
            ext_map = {
                "image/png": ".png", "image/jpeg": ".jpg",
                "image/webp": ".webp", "image/gif": ".gif",
            }
            ext = ext_map.get(self.mime_type)
            if ext:
                return ext
        # For file:// URLs (cache), derive from path directly
        if self.url.startswith("file://"):
            return Path(self.url[7:]).suffix or ".png"
        # Fall back to URL extension
        parsed = urllib.parse.urlparse(self.url)
        ext = Path(parsed.path).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            return ext
        return ".png"  # Default


@dataclass
class GameMatch:
    """A game match from a scraping provider."""
    game_id: str
    title: str
    provider: str
    platform: str = ""
    year: str = ""
    confidence: float = 0.0


# ═══════════════════════════════════════════════════════════════════════
# HTTP Helpers
# ═══════════════════════════════════════════════════════════════════════

def _http_get(url: str, headers: Optional[Dict[str, str]] = None,
              timeout: int = 30) -> Tuple[bytes, int, Dict[str, str]]:
    """Simple HTTP GET request using urllib (no external deps).

    Args:
        url: URL to fetch.
        headers: Optional request headers.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (response_body, status_code, response_headers).
    """
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "SGM/1.0 (SteamGrid Manager)")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            resp_headers = dict(resp.headers)
            return body, status, resp_headers
    except urllib.error.HTTPError as e:
        return e.read() if e.fp else b"", e.code, {}
    except urllib.error.URLError as e:
        logger.error(f"HTTP request failed: {url} - {e}")
        return b"", 0, {}
    except Exception as e:
        logger.error(f"HTTP request error: {url} - {e}")
        return b"", 0, {}


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None,
                   timeout: int = 30) -> Optional[dict]:
    """HTTP GET returning parsed JSON."""
    body, status, _ = _http_get(url, headers, timeout)
    if status != 200:
        logger.debug(f"HTTP {status} from {url}")
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON decode error from {url}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# Provider: ScreenScraper
# ═══════════════════════════════════════════════════════════════════════

class ScreenScraperProvider:
    """ScreenScraper.fr API v2 provider.

    Uses the jeuInfos.php and jeuRecherche.php endpoints.
    Requires devid/devpassword for API access, plus optional user credentials.

    Rate limit: 1 request per 1.2 seconds.
    """

    API_BASE = "https://www.screenscraper.fr/api2"
    REQUEST_INTERVAL = 1.2  # Seconds between requests

    # Media type mapping: ScreenScraper type -> our art type
    MEDIA_MAP = {
        "box-2D": "tall",           # Box art front
        "box-3D": "tall",           # Box art 3D (fallback)
        "wheel": "logo",            # Wheel/logo art
        "wheel-hd": "logo",         # HD wheel (preferred)
        "ss": "hero",               # Screenshot -> hero
        "sstitle": "hero",          # Title screenshot -> hero (fallback)
        "screenmarquee": "wide",    # Marquee -> wide capsule
        "screenmarqueesmall": "wide",
        "box-texture": "wide",      # Box texture as wide fallback
        "mixrbv1": "tall",          # Mix images (composite) as fallback
    }

    def __init__(self, devid: str, devpassword: str,
                 username: str = "", password: str = ""):
        """Initialize ScreenScraper provider.

        Args:
            devid: Developer ID.
            devpassword: Developer password.
            username: ScreenScraper username (optional, gets more threads).
            password: ScreenScraper password (optional).
        """
        self.devid = devid
        self.devpassword = devpassword
        self.username = username
        self.password = password
        self._last_request_time = 0.0
        self.name = "screenscraper"

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _build_url(self, endpoint: str, params: Dict[str, str]) -> str:
        """Build an API URL with authentication parameters."""
        base_params = {
            "devid": self.devid,
            "devpassword": self.devpassword,
            "softname": "sgm1.0",
            "output": "json",
        }
        if self.username:
            base_params["ssid"] = self.username
        if self.password:
            base_params["sspassword"] = self.password

        base_params.update(params)
        query = urllib.parse.urlencode(base_params)
        return f"{self.API_BASE}/{endpoint}?{query}"

    def search_game(self, title: str, screenscraper_id: Optional[int] = None,
                    rom_filename: Optional[str] = None,
                    rom_path: Optional[Path] = None,
                    hashes: Optional["RomHashes"] = None) -> Optional[GameMatch]:
        """Search for a game on ScreenScraper.

        Lookup priority:
          1. Hash-based lookup (most accurate — works even with bad filenames)
          2. Filename-based lookup via jeuInfos.php
          3. Title search via jeuRecherche.php

        Args:
            title: Game title to search for.
            screenscraper_id: Platform ID for ScreenScraper.
            rom_filename: Original ROM filename for better matching.
            rom_path: Path to ROM file — used to compute hashes if not provided.
            hashes: Pre-computed RomHashes (skips disk read if already done).

        Returns:
            GameMatch if found, None otherwise.
        """
        self._rate_limit()

        params = {}
        if screenscraper_id:
            params["systemeid"] = str(screenscraper_id)

        # --- Hash-based lookup (highest confidence) ---
        if hashes is None and rom_path is not None:
            hashes = compute_rom_hashes(rom_path)

        if hashes:
            params.update({
                "romnom": rom_filename or title,
                "romtaille": str(hashes.size),
                "crc": hashes.crc,
                "md5": hashes.md5,
                "sha1": hashes.sha1,
            })
        else:
            # Fall back to filename-only lookup
            params["romnom"] = rom_filename or title

        url = self._build_url("jeuInfos.php", params)
        data = _http_get_json(url)

        if data and "response" in data and "jeu" in data.get("response", {}):
            jeu = data["response"]["jeu"]
            game_title = self._extract_name(jeu.get("noms", []))
            return GameMatch(
                game_id=str(jeu.get("id", "")),
                title=game_title or title,
                provider=self.name,
                platform=str(screenscraper_id or ""),
                confidence=1.0 if hashes else 0.9,
            )

        # --- Title search fallback ---
        return self._search_by_name(title, screenscraper_id)

    def _search_by_name(self, title: str,
                        screenscraper_id: Optional[int] = None) -> Optional[GameMatch]:
        """Fall back to name-based search using jeuRecherche endpoint."""
        self._rate_limit()

        params = {"recherche": title}
        if screenscraper_id:
            params["systemeid"] = str(screenscraper_id)

        url = self._build_url("jeuRecherche.php", params)
        data = _http_get_json(url)

        if not data or "response" not in data:
            return None

        response = data["response"]
        jeux = response.get("jeux", [])
        if not jeux:
            return None

        # Take best match (first result)
        jeu = jeux[0]
        game_title = self._extract_name(jeu.get("noms", []))

        return GameMatch(
            game_id=str(jeu.get("id", "")),
            title=game_title or title,
            provider=self.name,
            platform=str(screenscraper_id or ""),
            confidence=0.7,
        )

    def get_artwork(self, game_id: str,
                    screenscraper_id: Optional[int] = None) -> Dict[str, ArtResult]:
        """Get artwork for a game by its ScreenScraper game ID.

        Args:
            game_id: ScreenScraper game ID.
            screenscraper_id: Platform ID.

        Returns:
            Dict mapping art_type to ArtResult.
        """
        self._rate_limit()

        params = {"gameid": game_id}
        if screenscraper_id:
            params["systemeid"] = str(screenscraper_id)

        url = self._build_url("jeuInfos.php", params)
        data = _http_get_json(url)

        if not data or "response" not in data or "jeu" not in data.get("response", {}):
            return {}

        jeu = data["response"]["jeu"]
        medias = jeu.get("medias", [])

        results: Dict[str, ArtResult] = {}

        # Prefer US/World region, then EU, then any
        region_prio = ["us", "wor", "eu", "jp", "ss", ""]

        for ss_type, art_type in self.MEDIA_MAP.items():
            if art_type in results:
                continue  # Already have this art type

            for region in region_prio:
                url_found = self._find_media(medias, ss_type, region)
                if url_found:
                    results[art_type] = ArtResult(
                        url=url_found,
                        art_type=art_type,
                        provider=self.name,
                    )
                    break

        return results

    def _find_media(self, medias, media_type: str, region: str) -> Optional[str]:
        """Find a media URL in the medias array."""
        if isinstance(medias, list):
            for media in medias:
                if not isinstance(media, dict):
                    continue
                if media.get("type") == media_type:
                    if not region or media.get("region", "") == region:
                        return media.get("url")
        elif isinstance(medias, dict):
            # Sometimes it's a dict keyed by type
            for media in medias.values():
                if isinstance(media, dict) and media.get("type") == media_type:
                    if not region or media.get("region", "") == region:
                        return media.get("url")
        return None

    def _extract_name(self, noms, prefer_region: str = "us") -> str:
        """Extract game name preferring a specific region."""
        if isinstance(noms, list):
            for nom in noms:
                if isinstance(nom, dict) and nom.get("region") == prefer_region:
                    return nom.get("text", "")
            # Fallback to first name
            for nom in noms:
                if isinstance(nom, dict) and nom.get("text"):
                    return nom["text"]
        return ""


# ═══════════════════════════════════════════════════════════════════════
# Provider: TheGamesDB
# ═══════════════════════════════════════════════════════════════════════

class TheGamesDBProvider:
    """TheGamesDB.net API v1 provider.

    Free API with generous limits.
    """

    API_BASE = "https://api.thegamesdb.net/v1"

    def __init__(self, api_key: str):
        """Initialize TheGamesDB provider.

        Args:
            api_key: API key from thegamesdb.net.
        """
        self.api_key = api_key
        self.name = "thegamesdb"
        self._base_url_cache: Dict[str, str] = {}

    def search_game(self, title: str,
                    thegamesdb_id: Optional[str] = None) -> Optional[GameMatch]:
        """Search for a game on TheGamesDB.

        Args:
            title: Game title to search.
            thegamesdb_id: Platform ID filter.

        Returns:
            GameMatch if found, None otherwise.
        """
        params = {
            "apikey": self.api_key,
            "name": title,
            "fields": "platform",
        }
        if thegamesdb_id:
            params["filter[platform]"] = thegamesdb_id

        query = urllib.parse.urlencode(params)
        url = f"{self.API_BASE}/Games/ByGameName?{query}"
        data = _http_get_json(url)

        if not data or data.get("code") != 200:
            return None

        games = data.get("data", {}).get("games", [])
        if not games:
            return None

        game = games[0]
        return GameMatch(
            game_id=str(game.get("id", "")),
            title=game.get("game_title", title),
            provider=self.name,
            platform=str(game.get("platform", "")),
            year=str(game.get("release_date", ""))[:4],
            confidence=0.8,
        )

    def get_artwork(self, game_id: str) -> Dict[str, ArtResult]:
        """Get artwork for a game by TheGamesDB game ID.

        Args:
            game_id: TheGamesDB game ID.

        Returns:
            Dict mapping art_type to ArtResult.
        """
        params = {
            "apikey": self.api_key,
            "games_id": game_id,
        }
        query = urllib.parse.urlencode(params)
        url = f"{self.API_BASE}/Games/Images?{query}"
        data = _http_get_json(url)

        if not data or data.get("code") != 200:
            return {}

        # Get base URL for images
        base_url = data.get("data", {}).get("base_url", {})
        original_url = base_url.get("original", "")

        images = data.get("data", {}).get("images", {}).get(game_id, [])
        if isinstance(images, dict):
            images = list(images.values())

        results: Dict[str, ArtResult] = {}

        # Type mapping: TheGamesDB type -> our art type
        type_map = {
            "boxart": "tall",       # Front box art
            "fanart": "hero",       # Fan art -> hero
            "banner": "wide",       # Banner -> wide capsule
            "screenshot": "hero",   # Screenshot -> hero fallback
            "clearlogo": "logo",    # Clear logo
        }

        for image in images:
            if not isinstance(image, dict):
                continue

            img_type = image.get("type", "")
            side = image.get("side", "")

            # Only use front boxart
            if img_type == "boxart" and side != "front":
                continue

            art_type = type_map.get(img_type)
            if not art_type or art_type in results:
                continue

            filename = image.get("filename", "")
            if filename and original_url:
                results[art_type] = ArtResult(
                    url=original_url + filename,
                    art_type=art_type,
                    provider=self.name,
                    width=image.get("width", 0),
                    height=image.get("height", 0),
                )

        return results


# ═══════════════════════════════════════════════════════════════════════
# Provider: SteamGridDB
# ═══════════════════════════════════════════════════════════════════════

class SteamGridDBProvider:
    """SteamGridDB.com API v2 provider.

    Best for Steam-specific artwork dimensions.
    """

    API_BASE = "https://www.steamgriddb.com/api/v2"

    def __init__(self, api_key: str):
        """Initialize SteamGridDB provider.

        Args:
            api_key: API key from steamgriddb.com.
        """
        self.api_key = api_key
        self.name = "steamgriddb"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def search_game(self, title: str) -> Optional[GameMatch]:
        """Search for a game on SteamGridDB.

        Args:
            title: Game title to search.

        Returns:
            GameMatch if found, None otherwise.
        """
        encoded = urllib.parse.quote(title)
        url = f"{self.API_BASE}/search/autocomplete/{encoded}"
        data = _http_get_json(url, self._headers)

        if not data or not data.get("success"):
            return None

        games = data.get("data", [])
        if not games:
            return None

        game = games[0]
        return GameMatch(
            game_id=str(game.get("id", "")),
            title=game.get("name", title),
            provider=self.name,
            confidence=0.85,
        )

    def get_artwork(self, game_id: str,
                    art_types: Optional[List[str]] = None) -> Dict[str, ArtResult]:
        """Get artwork for a game by SteamGridDB game ID.

        Args:
            game_id: SteamGridDB game ID.
            art_types: Which art types to fetch (default: all).

        Returns:
            Dict mapping art_type to ArtResult.
        """
        if art_types is None:
            art_types = ART_TYPES

        results: Dict[str, ArtResult] = {}

        # SteamGridDB endpoint mapping
        endpoint_map = {
            "tall": f"/grids/game/{game_id}?dimensions=600x900",
            "wide": f"/grids/game/{game_id}?dimensions=920x430,460x215",
            "hero": f"/heroes/game/{game_id}",
            "logo": f"/logos/game/{game_id}",
            "icon": f"/icons/game/{game_id}",
        }

        for art_type in art_types:
            if art_type not in endpoint_map:
                continue

            url = f"{self.API_BASE}{endpoint_map[art_type]}"
            data = _http_get_json(url, self._headers)

            if not data or not data.get("success"):
                continue

            images = data.get("data", [])
            if not images:
                continue

            # Take highest-scored image
            best = images[0]
            for img in images[1:]:
                if img.get("score", 0) > best.get("score", 0):
                    best = img

            img_url = best.get("url", best.get("thumb", ""))
            if img_url:
                results[art_type] = ArtResult(
                    url=img_url,
                    art_type=art_type,
                    provider=self.name,
                    width=best.get("width", 0),
                    height=best.get("height", 0),
                    score=best.get("score", 0),
                )

        return results


# ═══════════════════════════════════════════════════════════════════════
# Cascade Scraper (combines all providers)
# ═══════════════════════════════════════════════════════════════════════

class CascadeScraper:
    """Multi-provider artwork scraper with cascading fallback.

    Search order: ScreenScraper -> TheGamesDB -> SteamGridDB
    For each provider, search for the game, then fetch all art types.
    Any art types not found cascade to the next provider.
    """

    def __init__(self, config: dict):
        """Initialize with configuration dict.

        Config keys:
            screenscraper_devid, screenscraper_devpassword,
            screenscraper_ssid, screenscraper_sspassword,
            thegamesdb_api_key,
            steamgriddb_api_key (or api_key)
        """
        self.providers: List = []
        self._init_providers(config)
        cache_dir_cfg = config.get("art_cache_dir", "")
        self.cache_dir: Path = (
            Path(cache_dir_cfg).expanduser() if cache_dir_cfg
            else DEFAULT_CACHE_DIR
        )

    def _init_providers(self, config: dict):
        """Initialize providers from config."""
        # ScreenScraper (first priority)
        ss_devid = config.get("screenscraper_devid", "")
        ss_devpass = config.get("screenscraper_devpassword", "")
        if ss_devid and ss_devpass:
            self.providers.append(ScreenScraperProvider(
                devid=ss_devid,
                devpassword=ss_devpass,
                username=config.get("screenscraper_ssid", ""),
                password=config.get("screenscraper_sspassword", ""),
            ))
            logger.info("ScreenScraper provider enabled")

        # TheGamesDB (second priority)
        tgdb_key = config.get("thegamesdb_apikey", config.get("thegamesdb_api_key", ""))
        if tgdb_key:
            self.providers.append(TheGamesDBProvider(api_key=tgdb_key))
            logger.info("TheGamesDB provider enabled")

        # SteamGridDB (third priority / fallback)
        sgdb_key = config.get("steamgriddb_api_key", config.get("api_key", ""))
        if sgdb_key:
            self.providers.append(SteamGridDBProvider(api_key=sgdb_key))
            logger.info("SteamGridDB provider enabled")

        if not self.providers:
            logger.warning("No scraping providers configured")

    def scrape_game(self, title: str, system_name: str = "",
                    screenscraper_id: Optional[int] = None,
                    thegamesdb_id: Optional[str] = None,
                    rom_filename: Optional[str] = None,
                    rom_path: Optional[Path] = None,
                    hash_progress_cb=None,
                    wanted_types: Optional[Set[str]] = None
                    ) -> Dict[str, ArtResult]:
        """Scrape artwork for a game, cascading through providers.

        Args:
            title: Clean game title.
            system_name: System name (for logging).
            screenscraper_id: ScreenScraper platform ID.
            thegamesdb_id: TheGamesDB platform ID.
            rom_filename: Original ROM filename for ScreenScraper matching.
            rom_path: Path to ROM file for hash-based lookup (ScreenScraper).
            hash_progress_cb: Optional callback(bytes_done, total_bytes) for hash progress.
            wanted_types: Art types to fetch (default: all).

        Returns:
            Dict mapping art_type to best ArtResult found.
        """
        if wanted_types is None:
            wanted_types = set(ART_TYPES)

        results: Dict[str, ArtResult] = {}
        remaining = wanted_types.copy()

        # ── Cache check ────────────────────────────────────────────────
        cached = get_cached_art(title, system_name, cache_dir=self.cache_dir)
        for art_type, cached_path in cached.items():
            if art_type in remaining:
                # Return a synthetic ArtResult pointing at the cached file
                # Return a synthetic ArtResult pointing at the cached file
                # using a file:// URL so callers don't need special handling.
                results[art_type] = ArtResult(
                    url=cached_path.as_uri(),
                    art_type=art_type,
                    provider="cache",
                )
                remaining.discard(art_type)
                logger.debug(f"Cache hit: {art_type} for '{title}' ({system_name})")

        if not remaining:
            return results  # Everything served from cache
        # ──────────────────────────────────────────────────────────────

        # Pre-compute hashes once (shared across retry logic)
        hashes: Optional[RomHashes] = None
        if rom_path is not None:
            hashes = compute_rom_hashes(rom_path, progress_cb=hash_progress_cb)

        for provider in self.providers:
            if not remaining:
                break  # Got everything we need

            logger.debug(f"Trying {provider.name} for '{title}' ({system_name})")

            try:
                # Search for the game
                match = self._search_provider(provider, title,
                                              screenscraper_id, thegamesdb_id,
                                              rom_filename, None, hashes)
                if not match:
                    logger.debug(f"  {provider.name}: no match found")
                    continue

                logger.debug(f"  {provider.name}: matched '{match.title}' (id={match.game_id})")

                # Get artwork
                art = self._get_artwork(provider, match.game_id,
                                        screenscraper_id)

                for art_type, art_result in art.items():
                    if art_type in remaining:
                        results[art_type] = art_result
                        remaining.discard(art_type)
                        logger.debug(f"  {provider.name}: got {art_type}")

            except Exception as e:
                logger.warning(f"  {provider.name} error: {e}")
                continue

        if remaining:
            logger.debug(f"  Missing art types for '{title}': {remaining}")

        # ── Store new downloads in cache ───────────────────────────────
        # (only non-cache results, i.e. newly fetched URLs)
        # These will be downloaded by save_grid_images; we can't store them
        # here since we only have URLs. The caller (sgm.py) should call
        # store_art_in_cache after save_grid_images succeeds.
        # ──────────────────────────────────────────────────────────────

        return results

    def _search_provider(self, provider, title: str,
                         ss_id: Optional[int], tgdb_id: Optional[str],
                         rom_filename: Optional[str],
                         rom_path: Optional[Path] = None,
                         hashes: Optional[RomHashes] = None) -> Optional[GameMatch]:
        """Search a specific provider for a game."""
        if isinstance(provider, ScreenScraperProvider):
            return provider.search_game(title, ss_id, rom_filename,
                                        rom_path=rom_path, hashes=hashes)
        elif isinstance(provider, TheGamesDBProvider):
            return provider.search_game(title, tgdb_id)
        elif isinstance(provider, SteamGridDBProvider):
            return provider.search_game(title)
        return None

    def _get_artwork(self, provider, game_id: str,
                     ss_id: Optional[int] = None) -> Dict[str, ArtResult]:
        """Get artwork from a specific provider."""
        if isinstance(provider, ScreenScraperProvider):
            return provider.get_artwork(game_id, ss_id)
        elif isinstance(provider, TheGamesDBProvider):
            return provider.get_artwork(game_id)
        elif isinstance(provider, SteamGridDBProvider):
            return provider.get_artwork(game_id)
        return {}


# ═══════════════════════════════════════════════════════════════════════
# Image Downloader
# ═══════════════════════════════════════════════════════════════════════

def download_image(url: str, output_path: Path, timeout: int = 30) -> bool:
    """Download an image file from a URL.

    Args:
        url: Image URL to download.
        output_path: Where to save the file.
        timeout: Request timeout.

    Returns:
        True if download succeeded.
    """
    try:
        # Handle file:// URLs (cache hits — just copy the file)
        if url.startswith("file://"):
            src = Path(url[7:])
            if not src.exists():
                logger.warning(f"Cached file missing: {src}")
                return False
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, output_path)
            logger.debug(f"Copied from cache: {src} -> {output_path}")
            return True

        body, status, headers = _http_get(url, timeout=timeout)
        if status != 200 or len(body) < 100:
            logger.warning(f"Download failed ({status}): {url}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body)
        logger.debug(f"Downloaded {len(body)} bytes -> {output_path}")
        return True

    except Exception as e:
        logger.error(f"Download error: {url} - {e}")
        return False


def save_grid_images(short_app_id: str, artwork: Dict[str, ArtResult],
                     grid_path: Path, timeout: int = 30) -> Dict[str, Path]:
    """Download artwork and save with Steam grid naming convention.

    Args:
        short_app_id: The short app ID for filename generation.
        artwork: Dict of art_type -> ArtResult.
        grid_path: Steam grid folder path.
        timeout: Download timeout per image.

    Returns:
        Dict mapping art_type to saved file path.
    """
    # Steam grid filename patterns
    # Wide capsule = {id}.png (920x430, horizontal)
    # Tall capsule = {id}p.png (600x900, vertical/portrait)
    name_map = {
        "wide": f"{short_app_id}",           # {id}.png  — horizontal banner
        "tall": f"{short_app_id}p",          # {id}p.png — vertical boxart
        "hero": f"{short_app_id}_hero",      # {id}_hero.png
        "logo": f"{short_app_id}_logo",      # {id}_logo.png
        "icon": f"{short_app_id}_icon",      # {id}_icon.png
    }

    saved: Dict[str, Path] = {}

    for art_type, art_result in artwork.items():
        if art_type not in name_map:
            continue

        ext = art_result.extension
        filename = name_map[art_type] + ext
        output_path = grid_path / filename

        if download_image(art_result.url, output_path, timeout):
            saved[art_type] = output_path

    return saved
