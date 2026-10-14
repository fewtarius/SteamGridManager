"""Tests for art_scraper HTTP helpers."""

import json
import subprocess

import art_scraper


def _fail_run(*args, **kwargs):
    """Pretend curl is unavailable / returns nothing."""
    return subprocess.CompletedProcess(args=(), returncode=1, stdout="", stderr="")


def _no_sleep(*args, **kwargs):
    pass


def test_http_get_json_retries_on_429_then_succeeds(monkeypatch):
    """A 429 must trigger a retry that eventually returns parsed JSON."""
    calls = {"n": 0}

    def fake(url, headers=None, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            return (b"rate limited", 429, {})
        return (json.dumps({"success": True, "data": []}).encode("utf-8"), 200, {})

    monkeypatch.setattr(art_scraper, "_http_get", fake)
    monkeypatch.setattr("subprocess.run", _fail_run)
    monkeypatch.setattr(art_scraper.time, "sleep", _no_sleep)

    result = art_scraper._http_get_json("http://x.invalid/y", {"X": "y"}, retries=3)
    assert result == {"success": True, "data": []}
    assert calls["n"] == 2


def test_http_get_json_no_retry_on_404(monkeypatch):
    """A 404 is permanent: no retry, no sleep, returns None."""
    calls = {"n": 0}
    sleeps = []

    def fake(url, headers=None, timeout=30):
        calls["n"] += 1
        return (b"Not Found", 404, {})

    monkeypatch.setattr(art_scraper, "_http_get", fake)
    monkeypatch.setattr("subprocess.run", _fail_run)
    monkeypatch.setattr(art_scraper.time, "sleep", lambda *a, **k: sleeps.append(a))

    result = art_scraper._http_get_json("http://x.invalid/y", retries=3)
    assert result is None
    assert calls["n"] == 1
    assert sleeps == []


def test_http_get_json_retries_on_network_error(monkeypatch):
    """A status of 0 (network failure) is transient and must be retried."""
    calls = {"n": 0}

    def fake(url, headers=None, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            return (b"", 0, {})
        return (json.dumps({"ok": True}).encode("utf-8"), 200, {})

    monkeypatch.setattr(art_scraper, "_http_get", fake)
    monkeypatch.setattr("subprocess.run", _fail_run)
    monkeypatch.setattr(art_scraper.time, "sleep", _no_sleep)

    result = art_scraper._http_get_json("http://x.invalid/y", retries=3)
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_http_get_json_aborts_after_exhausting_retries(monkeypatch):
    """Persistent 429 across all attempts returns None."""
    calls = {"n": 0}

    def fake(url, headers=None, timeout=30):
        calls["n"] += 1
        return (b"{}", 429, {})

    monkeypatch.setattr(art_scraper, "_http_get", fake)
    monkeypatch.setattr("subprocess.run", _fail_run)
    monkeypatch.setattr(art_scraper.time, "sleep", _no_sleep)

    result = art_scraper._http_get_json("http://x.invalid/y", retries=3)
    assert result is None
    assert calls["n"] == 3
