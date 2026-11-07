#!/usr/bin/env python3
"""Tests for ScreenScraper request handling in art_scraper.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import art_scraper as A


def response(payload, status=200):
    """Build an (_http_get) return tuple."""
    return (json.dumps(payload).encode(), status, {})


@pytest.fixture
def provider():
    """A ScreenScraper provider with rate limiting disabled."""
    prov = A.ScreenScraperProvider(devid="dev", devpassword="dp",
                                   username="user", password="pw")
    with patch.object(prov, "_rate_limit"):
        yield prov


class TestUrlRedaction:
    """Logged URLs must not carry credentials."""

    def test_masks_every_secret_param(self):
        url = ("https://example/api?devid=SECRET1&devpassword=SECRET2"
               "&ssid=SECRET3&sspassword=SECRET4&apikey=SECRET5")
        redacted = A._redact_url(url)
        for marker in ("SECRET1", "SECRET2", "SECRET3", "SECRET4", "SECRET5"):
            assert marker not in redacted

    def test_keeps_debugging_context(self):
        url = "https://example/api?devid=SECRET1&systemeid=58&crc=FE4ADB7"
        redacted = A._redact_url(url)
        assert "systemeid=58" in redacted
        assert "crc=FE4ADB7" in redacted

    def test_leaves_query_free_urls_alone(self):
        url = "https://example/api/jeux"
        assert A._redact_url(url) == url

    def test_empty_values_stay_empty(self):
        """A blank credential is not worth masking, and must not error."""
        assert "gameid=" in A._redact_url("https://example/api?gameid=&devid=X")


class TestRetryPolicy:
    """Permanent errors must not be retried or re-requested through curl."""

    def test_404_is_not_retried(self, provider):
        calls = []

        def fake(url, headers=None, timeout=3):
            calls.append(url)
            return (b'{"error": "Rom non trouvee"}', 404, {})

        with patch.object(A, "_http_get", fake), \
             patch.object(A, "_curl_get_json") as curl, \
             patch.object(A.time, "sleep"):
            assert A._http_get_json("https://example/api") is None

        assert len(calls) == 1
        curl.assert_not_called()

    def test_400_is_not_retried(self, provider):
        calls = []

        def fake(url, headers=None, timeout=3):
            calls.append(url)
            return (b"", 400, {})

        with patch.object(A, "_http_get", fake), \
             patch.object(A, "_curl_get_json") as curl, \
             patch.object(A.time, "sleep"):
            assert A._http_get_json("https://example/api") is None

        assert len(calls) == 1
        curl.assert_not_called()

    def test_503_is_retried(self):
        calls = []

        def fake(url, headers=None, timeout=3):
            calls.append(url)
            return (b"", 503, {}) if len(calls) < 3 else response({"ok": True})

        with patch.object(A, "_http_get", fake), patch.object(A.time, "sleep"):
            assert A._http_get_json("https://example/api") == {"ok": True}

        assert len(calls) == 3

    def test_403_falls_back_to_curl(self):
        """A blocked user agent is worth a curl retry."""
        with patch.object(A, "_http_get", lambda *a, **k: (b"", 403, {})), \
             patch.object(A, "_curl_get_json", return_value={"ok": True}), \
             patch.object(A.time, "sleep"):
            assert A._http_get_json("https://example/api") == {"ok": True}

    def test_unparseable_200_is_not_retried(self):
        calls = []

        def fake(url, headers=None, timeout=3):
            calls.append(url)
            return (b"<html>not json</html>", 200, {})

        with patch.object(A, "_http_get", fake), patch.object(A.time, "sleep"):
            assert A._http_get_json("https://example/api") is None

        assert len(calls) == 1


class TestNameSearchResults:
    """ScreenScraper signals 'no match' with an empty jeu object."""

    def test_empty_jeu_object_is_no_match(self, provider):
        payload = {"response": {"jeux": [{}]}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            assert provider._search_by_name("Dark Cloud", 58) is None

    def test_empty_list_is_no_match(self, provider):
        payload = {"response": {"jeux": []}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            assert provider._search_by_name("Dark Cloud", 58) is None

    def test_jeu_without_id_is_no_match(self, provider):
        payload = {"response": {"jeux": [{"noms": [{"text": "Dark Cloud"}]}]}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            assert provider._search_by_name("Dark Cloud", 58) is None

    def test_first_usable_entry_wins(self, provider):
        payload = {"response": {"jeux": [
            {},
            {"id": "21972", "noms": [{"text": "Dark Cloud"}],
             "systeme": {"id": "58"}},
        ]}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            match = provider._search_by_name("Dark Cloud", 58)

        assert match is not None
        assert match.game_id == "21972"

    def test_result_from_other_platform_is_rejected(self, provider):
        """A same-titled game on another system must not supply box art."""
        payload = {"response": {"jeux": [
            {"id": "99", "noms": [{"text": "Dark Cloud"}],
             "systeme": {"id": "17"}},
        ]}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            assert provider._search_by_name("Dark Cloud", 58) is None

    def test_unscoped_search_accepts_any_platform(self, provider):
        """Arcade has no ScreenScraper system id, so results are unscoped."""
        payload = {"response": {"jeux": [
            {"id": "99", "noms": [{"text": "Galaga"}], "systeme": {"id": "142"}},
        ]}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            match = provider._search_by_name("Galaga", None)

        assert match is not None
        assert match.game_id == "99"


class TestHashLookupResults:
    """The jeuInfos hash path has the same empty-id hazard."""

    def test_jeu_without_id_is_not_a_match(self, provider):
        payload = {"response": {"jeu": {"noms": [{"text": "Dark Cloud"}]}}}
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)), \
             patch.object(provider, "_search_by_name", return_value=None) as name:
            assert provider.search_game("Dark Cloud", 58) is None

        name.assert_called_once()

    def test_hash_match_returns_id(self, provider):
        payload = {"response": {"jeu": {"id": "21972",
                                        "noms": [{"text": "Dark Cloud"}]}}}
        hashes = A.RomHashes(crc="FE4ADB7", md5="B5E456C",
                             sha1="FF3D665", size=17979816)
        with patch.object(A, "_http_get", lambda *a, **k: response(payload)):
            match = provider.search_game("Dark Cloud", 58,
                                         rom_filename="dc.iso", hashes=hashes)

        assert match.game_id == "21972"
        assert match.confidence == 1.0


class TestEmptyGameId:
    """An empty id can only ever produce a 400, so never request one."""

    def test_provider_issues_no_request(self):
        with patch.object(A, "_http_get") as http, \
             patch.object(A, "_curl_get_json") as curl:
            prov = A.ScreenScraperProvider(devid="d", devpassword="p")
            assert prov.get_artwork("", 58) == {}

        http.assert_not_called()
        curl.assert_not_called()

    def test_whitespace_id_is_rejected(self):
        with patch.object(A, "_http_get") as http:
            prov = A.ScreenScraperProvider(devid="d", devpassword="p")
            assert prov.get_artwork("   ", 58) == {}
        http.assert_not_called()

    def test_cascade_guard_skips_provider(self):
        scraper = A.CascadeScraper({})
        prov = A.ScreenScraperProvider(devid="d", devpassword="p")
        with patch.object(A, "_http_get") as http:
            assert scraper._get_artwork(prov, "", 58) == {}
        http.assert_not_called()
