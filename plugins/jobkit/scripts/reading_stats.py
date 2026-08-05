#!/usr/bin/env python3
"""Harvest reads of workspace guide pages from Chrome's history DB into reading_stats.json.

Chrome (and Chromium-family browsers) log every file:// visit in a SQLite DB. This
module copies that DB (it is locked while the browser runs), pulls visits to *.html
files newer than a stored watermark, and merges them into reading_stats.json in the
workspace (the durable record; Chrome expires its own history after ~90 days).
Keyed by lowercase basename.

PRIVACY: only visits to file:// URLs UNDER THE WORKSPACE ROOT are ever recorded.
Anything else read out of the history DB is discarded in memory and never written
to reading_stats.json or printed anywhere. Opening the dashboard itself is
navigation, not reading, so that one file is always skipped too.

Fail-soft on purpose, same reasoning as the original this was ported from: a stats
problem (locked DB, missing browser, unreadable file) must never break a dashboard
build. The whole harvest is wrapped in one try/except that prints a one-line notice
and returns whatever stats already existed.
"""
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01
DASHBOARD_BASENAME = "careerdashboard.html"


def candidate_history_paths() -> list:
    """Return every plausible Chromium-family History DB path for this OS.

    A list, not a single winner, so a future profile (another Chrome channel,
    another browser) is a one-line addition here.
    """
    home = Path.home()
    candidates = []
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roots = {
            "Chrome": base / "Google" / "Chrome" / "User Data",
            "Chrome Beta": base / "Google" / "Chrome Beta" / "User Data",
            "Chromium": base / "Chromium" / "User Data",
            "Brave": base / "BraveSoftware" / "Brave-Browser" / "User Data",
            "Edge": base / "Microsoft" / "Edge" / "User Data",
        }
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
        roots = {
            "Chrome": base / "Google" / "Chrome",
            "Chrome Beta": base / "Google" / "Chrome Beta",
            "Chromium": base / "Chromium",
            "Brave": base / "BraveSoftware" / "Brave-Browser",
            "Edge": base / "Microsoft Edge",
        }
    else:  # Linux
        base = home / ".config"
        roots = {
            "Chrome": base / "google-chrome",
            "Chrome Beta": base / "google-chrome-beta",
            "Chromium": base / "chromium",
            "Brave": base / "BraveSoftware" / "Brave-Browser",
            "Edge": base / "microsoft-edge",
        }
    for root in roots.values():
        candidates.append(root / "Default" / "History")
    return candidates


def _stats_path(root: Path) -> Path:
    return Path(root) / "reading_stats.json"


def _load(root: Path) -> dict:
    path = _stats_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"watermark": 0, "pages": {}, "daily": {}}


def _file_url_to_path(url: str) -> str:
    """file:// URL -> filesystem path, POSIX or Windows drive-letter form.

    Deliberately not the platform's own url2pathname: this converts a URL a
    macOS Chrome wrote while the code happens to run on Windows (or vice
    versa), so it cannot depend on the host platform's own path rules.
    urlparse().path already strips the query/fragment and leaves percent
    escapes for unquote() to resolve.
    """
    raw = unquote(urlparse(url).path)
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
        raw = raw[1:]  # "/C:/Users/<name>" -> "C:/Users/<name>"
    return raw


def _is_under(path: str, root_url: str) -> bool:
    """True if `path` is root_url itself or something inside it.

    A plain startswith() would let "/Users/<name>/JobSearchPrivate" match
    root "/Users/<name>/JobSearch" - require a path-separator boundary.
    """
    return path == root_url or path.startswith(root_url + "/")


def harvest(root: Path) -> dict:
    """Merge new browser visits under `root` into reading_stats.json; return stats.

    `root` is the workspace root, passed explicitly (this module lives under the
    plugin directory, not the workspace, so it cannot be inferred from __file__).
    """
    root = Path(root)
    stats = {"watermark": 0, "pages": {}, "daily": {}}
    try:
        stats = _load(root)
        history = next((p for p in candidate_history_paths() if p.exists()), None)
        if history is None:
            return stats  # no supported browser installed; not an error

        root_url = root.resolve().as_posix().lower()
        wm = stats["watermark"]
        # The live DB is locked while the browser runs, so it is copied first.
        # A TemporaryDirectory (not a fixed path) so the copy - a snapshot of
        # every URL the user has ever visited - never outlives this call.
        with tempfile.TemporaryDirectory(prefix="jobkit_chrome_history_") as tmp_dir:
            tmp = Path(tmp_dir) / "History"
            shutil.copy2(history, tmp)
            con = sqlite3.connect(tmp)
            try:
                rows = con.execute(
                    "SELECT u.url, v.visit_time FROM visits v JOIN urls u ON u.id = v.url "
                    "WHERE u.url LIKE 'file:///%' AND v.visit_time > ?", (stats["watermark"],)
                ).fetchall()
            finally:
                con.close()

        for url, vt in rows:
            path = _file_url_to_path(url).lower()
            if not _is_under(path, root_url) or not path.endswith(".html"):
                continue  # outside the workspace, or not an html page: discard, never stored
            base = os.path.basename(path)
            if base == DASHBOARD_BASENAME:
                continue  # opening the dashboard is navigation, not reading
            day = datetime.datetime.fromtimestamp(
                vt / 1e6 - CHROME_EPOCH_OFFSET, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d")
            page = stats["pages"].setdefault(base, {"opens": 0, "first": day, "last": day})
            page["opens"] += 1
            page["first"] = min(page["first"], day)
            page["last"] = max(page["last"], day)
            stats["daily"][day] = stats["daily"].get(day, 0) + 1
            wm = max(wm, vt)
        stats["watermark"] = wm
        _stats_path(root).write_text(json.dumps(stats, indent=0, sort_keys=True), encoding="utf-8")
    except Exception as e:
        print(f"reading_stats: harvest skipped ({e})")
    return stats


if __name__ == "__main__":
    import sys
    s = harvest(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
    pages = sorted(s["pages"].items(), key=lambda kv: -kv[1]["opens"])
    total = sum(p["opens"] for _, p in pages)
    print(f"{total} reads across {len(pages)} pages; top 5:")
    for base, p in pages[:5]:
        print(f"  {p['opens']:>3}x  {base}  (last {p['last']})")
    # ponytail: self-check - watermark must be monotonic and json must round-trip
    assert _load(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())["watermark"] == s["watermark"]
