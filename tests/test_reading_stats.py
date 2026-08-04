import json
import sqlite3
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
