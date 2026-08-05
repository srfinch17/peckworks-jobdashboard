import json
import sqlite3
import tempfile
from pathlib import Path

import reading_stats


def _chrome_epoch(iso_day: str) -> int:
    """Convert an ISO date to a Chrome visit_time (microseconds since 1601-01-01 UTC)."""
    import datetime
    dt = datetime.datetime.fromisoformat(iso_day).replace(tzinfo=datetime.timezone.utc)
    return int((dt.timestamp() + reading_stats.CHROME_EPOCH_OFFSET) * 1e6)


def _make_history_db(path: Path, visits: list) -> None:
    """visits: list of (url, iso_day) tuples, shaped like Chrome's urls/visits tables."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT)")
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
    for i, (url, day) in enumerate(visits, start=1):
        con.execute("INSERT INTO urls (id, url) VALUES (?, ?)", (i, url))
        con.execute("INSERT INTO visits (url, visit_time) VALUES (?, ?)", (i, _chrome_epoch(day)))
    con.commit()
    con.close()


def test_harvest_returns_existing_stats_unchanged_when_no_browser_history_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [tmp_path / "nope" / "History"])
    (tmp_path / "reading_stats.json").write_text(
        json.dumps({"watermark": 42, "pages": {"a.html": {"opens": 1, "first": "2026-01-01", "last": "2026-01-01"}}, "daily": {}}),
        encoding="utf-8",
    )
    stats = reading_stats.harvest(tmp_path)
    assert stats["watermark"] == 42
    assert stats["pages"]["a.html"]["opens"] == 1


def test_harvest_records_a_visit_to_a_workspace_guide(tmp_path, monkeypatch):
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "negotiating.html").write_text("<html></html>", encoding="utf-8")
    history_dir = tmp_path / "browser"
    history_dir.mkdir()
    history = history_dir / "History"
    url = (guides / "negotiating.html").resolve().as_uri()
    _make_history_db(history, [(url, "2026-01-05")])
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [history])

    stats = reading_stats.harvest(tmp_path)
    assert stats["pages"]["negotiating.html"]["opens"] == 1
    assert stats["pages"]["negotiating.html"]["last"] == "2026-01-05"
    assert stats["watermark"] > 0


def test_harvest_does_not_record_a_visit_outside_the_workspace(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside_workspace_guide.html"
    outside.write_text("<html></html>", encoding="utf-8")
    history_dir = tmp_path / "browser"
    history_dir.mkdir()
    history = history_dir / "History"
    _make_history_db(history, [(outside.resolve().as_uri(), "2026-01-05")])
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [history])

    stats = reading_stats.harvest(tmp_path)
    assert stats["pages"] == {}
    outside.unlink()


def test_harvest_skips_the_dashboard_itself(tmp_path, monkeypatch):
    dash = tmp_path / "CareerDashboard.html"
    dash.write_text("<html></html>", encoding="utf-8")
    history_dir = tmp_path / "browser"
    history_dir.mkdir()
    history = history_dir / "History"
    _make_history_db(history, [(dash.resolve().as_uri(), "2026-01-05")])
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [history])

    stats = reading_stats.harvest(tmp_path)
    assert stats["pages"] == {}


def test_watermark_is_monotonic_and_second_harvest_does_not_double_count(tmp_path, monkeypatch):
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "negotiating.html").write_text("<html></html>", encoding="utf-8")
    history_dir = tmp_path / "browser"
    history_dir.mkdir()
    history = history_dir / "History"
    url = (guides / "negotiating.html").resolve().as_uri()
    _make_history_db(history, [(url, "2026-01-05")])
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [history])

    stats1 = reading_stats.harvest(tmp_path)
    wm1 = stats1["watermark"]
    stats2 = reading_stats.harvest(tmp_path)
    assert stats2["watermark"] == wm1
    assert stats2["pages"]["negotiating.html"]["opens"] == 1


# --- FIX 1: file:// URL parsing must not depend on the host platform ---

def test_file_url_to_path_handles_a_posix_url_literal():
    """"file:///" is 8 characters; a naive [8:] slice eats the leading slash
    of a POSIX path, so every macOS visit was silently discarded. Fed as a
    literal string, not built with as_uri() on the machine running the test,
    which would only ever produce the host's own URL shape."""
    assert reading_stats._file_url_to_path(
        "file:///Users/<name>/ws/guides/negotiating.html"
    ) == "/Users/<name>/ws/guides/negotiating.html"


def test_file_url_to_path_handles_a_windows_drive_letter_url_literal():
    assert reading_stats._file_url_to_path(
        "file:///C:/Users/<name>/ws/guides/negotiating.html"
    ) == "C:/Users/<name>/ws/guides/negotiating.html"


def test_file_url_to_path_strips_query_and_fragment():
    assert reading_stats._file_url_to_path(
        "file:///Users/<name>/ws/g.html?x=1#top"
    ) == "/Users/<name>/ws/g.html"


def test_is_under_requires_a_path_separator_boundary():
    """A plain startswith() lets "JobSearchPrivate" match root "JobSearch"."""
    assert reading_stats._is_under("/users/benny/jobsearch/g.html", "/users/benny/jobsearch")
    assert reading_stats._is_under("/users/benny/jobsearch", "/users/benny/jobsearch")
    assert not reading_stats._is_under(
        "/users/benny/jobsearchprivate/g.html", "/users/benny/jobsearch"
    )


# --- FIX 2: the Chrome History DB copy must not outlive the harvest ---

def test_harvest_does_not_leave_a_copy_of_the_history_db_behind(tmp_path, monkeypatch):
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "negotiating.html").write_text("<html></html>", encoding="utf-8")
    history_dir = tmp_path / "browser"
    history_dir.mkdir()
    history = history_dir / "History"
    url = (guides / "negotiating.html").resolve().as_uri()
    _make_history_db(history, [(url, "2026-01-05")])
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [history])

    captured = {}
    real_tempdir = tempfile.TemporaryDirectory

    def spy(*args, **kwargs):
        d = real_tempdir(*args, **kwargs)
        captured["path"] = Path(d.name)
        return d

    monkeypatch.setattr(reading_stats.tempfile, "TemporaryDirectory", spy)

    reading_stats.harvest(tmp_path)

    assert "path" in captured, "harvest never copied the history DB"
    assert not captured["path"].exists(), "the copy of the browser history DB was left behind"


# --- FIX 3: a corrupt reading_stats.json must degrade to empty stats, not crash ---

def test_harvest_degrades_to_empty_stats_when_reading_stats_json_is_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [tmp_path / "nope" / "History"])
    (tmp_path / "reading_stats.json").write_text("{not valid json", encoding="utf-8")

    stats = reading_stats.harvest(tmp_path)

    assert stats == {"watermark": 0, "pages": {}, "daily": {}}
