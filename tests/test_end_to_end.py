"""The full path a first-time user takes, against a directory that did not exist.

Every workspace here lives under pytest's tmp_path, never under the repo.
"""
import json
import re

import ledger
import workspace
import dashboard
import reading_stats


def _section(html_text: str, section_id: str) -> str:
    """Slice out one <section id="..."> ... </section> block for a scoped assertion."""
    match = re.search(
        rf'<section class="panel[^"]*" id="{section_id}">(.*?)</section>',
        html_text,
        re.DOTALL,
    )
    assert match, f"no <section id={section_id!r}> in the page"
    return match.group(1)


def test_empty_directory_to_dashboard(tmp_path):
    root = tmp_path / "JobDashboard"
    assert not root.exists()

    config = workspace.init(root)

    staged = workspace.lane_dir(root, config, "staged")
    (staged / "9_Pixar_Emeryville_EnvironmentArtist").mkdir()
    (staged / "7_Riot_LosAngeles_ConceptArtist").mkdir()
    (staged / "9_Pixar_Emeryville_EnvironmentArtist" / "original_job_posting.md").write_text(
        "https://boards.greenhouse.io/example/jobs/1\n\nWe need an environment artist.\n",
        encoding="utf-8",
    )

    html = dashboard.build(root, "2026-02-01")
    assert 'data-count="staged">2<' in html
    assert "https://boards.greenhouse.io/example/jobs/1" in html


def test_apply_then_reject_does_not_move_the_apply_date(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)

    staged = workspace.lane_dir(root, config, "staged")
    (staged / "7_Riot_LosAngeles_ConceptArtist").mkdir()
    dashboard.build(root, "2026-02-01")

    # Day 10: applied to it.
    (staged / "7_Riot_LosAngeles_ConceptArtist").rename(
        workspace.lane_dir(root, config, "applied") / "7_Riot_LosAngeles_ConceptArtist"
    )
    dashboard.build(root, "2026-02-10")

    book = ledger.load(root / "job_ledger.json")
    assert book["7_Riot_LosAngeles_ConceptArtist"]["applied_date"] == "2026-02-10"

    # Day 40: rejected, weeks later. The apply date must not move.
    ledger.set_status(book, "7_Riot_LosAngeles_ConceptArtist", "closed",
                       "2026-03-12", closure_reason="rejected")
    ledger.save(root / "job_ledger.json", book)

    html = dashboard.build(root, "2026-03-12")
    book = ledger.load(root / "job_ledger.json")
    assert book["7_Riot_LosAngeles_ConceptArtist"]["applied_date"] == "2026-02-10"
    assert 'data-count="rejected">1<' in html


def test_a_silence_closure_is_not_counted_as_a_rejection(tmp_path):
    root = tmp_path / "JobDashboard"
    workspace.init(root)
    config = workspace.load_config(root)
    (workspace.lane_dir(root, config, "applied") / "8_Acme_Remote_Illustrator").mkdir()
    dashboard.build(root, "2026-01-01")

    book = ledger.load(root / "job_ledger.json")
    ledger.set_status(book, "8_Acme_Remote_Illustrator", "closed",
                       "2026-04-01", closure_reason="closed_no_response")
    ledger.save(root / "job_ledger.json", book)

    html = dashboard.build(root, "2026-04-01")
    assert 'data-count="rejected">0<' in html
    assert 'data-count="closed_no_response">1<' in html


def test_nothing_written_outside_the_workspace(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)
    (workspace.lane_dir(root, config, "staged") / "6_Acme_Remote_Artist").mkdir()

    dashboard.build(root, "2026-01-01")
    dashboard.build(root, "2026-01-02")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["JobDashboard"]


def test_first_seen_survives_lane_moves_and_status_changes(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)
    staged = workspace.lane_dir(root, config, "staged")
    (staged / "5_Acme_Remote_Artist").mkdir()

    dashboard.build(root, "2026-01-01")
    book = ledger.load(root / "job_ledger.json")
    assert book["5_Acme_Remote_Artist"]["first_seen"] == "2026-01-01"

    (staged / "5_Acme_Remote_Artist").rename(
        workspace.lane_dir(root, config, "applied") / "5_Acme_Remote_Artist"
    )
    dashboard.build(root, "2026-01-15")
    book = ledger.load(root / "job_ledger.json")
    assert book["5_Acme_Remote_Artist"]["first_seen"] == "2026-01-01"

    ledger.set_status(book, "5_Acme_Remote_Artist", "interview_scheduled", "2026-01-20")
    ledger.save(root / "job_ledger.json", book)
    dashboard.build(root, "2026-01-20")
    book = ledger.load(root / "job_ledger.json")
    assert book["5_Acme_Remote_Artist"]["first_seen"] == "2026-01-01"


def test_an_interview_moves_out_of_waiting_into_interviews(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)
    (workspace.lane_dir(root, config, "applied") / "6_Acme_Remote_Artist").mkdir()
    dashboard.build(root, "2026-01-01")

    book = ledger.load(root / "job_ledger.json")
    ledger.set_status(book, "6_Acme_Remote_Artist", "interview_scheduled", "2026-01-10")
    ledger.save(root / "job_ledger.json", book)

    html = dashboard.build(root, "2026-01-10")
    assert 'data-count="interviews">1<' in html

    interviews_html = _section(html, "interviews")
    active_html = _section(html, "active")
    assert "Acme" in interviews_html
    assert "Acme" not in active_html


def test_library_renders_from_guides_and_escapes_a_hostile_title(tmp_path):
    root = tmp_path / "JobDashboard"
    workspace.init(root)
    guides = root / "guides"
    (guides / "hostile.html").write_text(
        "<html><head><title>Color & <Light></title>"
        '<meta name="description" content="Notes on tone &amp; contrast."></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    html = dashboard.build(root, "2026-01-01")
    library_html = _section(html, "library")
    assert "Color &amp; &lt;Light&gt;" in library_html
    # The raw hostile fragment must never appear unescaped in the page.
    assert "<Light>" not in library_html


def test_reading_stats_safe_with_no_browser(tmp_path, monkeypatch):
    root = tmp_path / "JobDashboard"
    workspace.init(root)

    # ponytail: simulate "no browser installed" the same way harvest() itself
    # detects it, rather than reaching into its internals.
    monkeypatch.setattr(reading_stats, "candidate_history_paths", lambda: [])

    html = dashboard.build(root, "2026-01-01")
    assert "<html" in html

    stats_path = root / "reading_stats.json"
    if stats_path.exists():
        data = json.loads(stats_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "pages" in data


def test_second_build_is_idempotent(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)
    (workspace.lane_dir(root, config, "staged") / "8_Acme_Remote_Artist").mkdir()
    (workspace.lane_dir(root, config, "applied") / "6_Beta_Remote_Artist").mkdir()

    dashboard.build(root, "2026-01-01")
    book_first = ledger.load(root / "job_ledger.json")

    html_second = dashboard.build(root, "2026-01-01")
    book_second = ledger.load(root / "job_ledger.json")

    assert set(book_first) == set(book_second)
    assert book_first["8_Acme_Remote_Artist"]["first_seen"] == book_second["8_Acme_Remote_Artist"]["first_seen"]
    assert book_first["6_Beta_Remote_Artist"].get("applied_date") == book_second["6_Beta_Remote_Artist"].get("applied_date")
    assert ledger.counts(book_first) == ledger.counts(book_second)
    assert 'data-count="staged">1<' in html_second
    assert 'data-count="applied">1<' in html_second
