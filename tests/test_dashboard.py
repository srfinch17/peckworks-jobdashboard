import re

import dashboard
import workspace


def _workspace_with_two_jobs(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    return config


def test_build_emits_html_containing_both_jobs(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "Pixar" in html
    assert "Riot" in html


def test_generated_page_never_fetches(tmp_path):
    """A file:// page cannot fetch a sibling JSON file. It fails silently and
    looks like an empty dashboard. All data must be baked into the markup."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html


def test_generated_page_loads_nothing_from_the_network(tmp_path):
    """Links to postings are fine. Loading assets over the network is not -
    the page must render identically with the wifi off."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<script src=" not in html
    assert 'rel="stylesheet"' not in html
    assert "@import" not in html
    assert '<img src="http' not in html


def test_build_writes_the_ledger(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    dashboard.build(tmp_path, "2026-02-01")
    assert (tmp_path / "job_ledger.json").exists()


def test_job_titles_are_html_escaped(tmp_path):
    """Uses & rather than angle brackets: Windows forbids < > in filenames,
    so an angle-bracket folder name cannot even be created to test with."""
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Acme&Sons_LA_Artist").mkdir()
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "&amp;Sons" in html
    assert "Acme&Sons" not in html


def test_counts_appear_in_the_page(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert 'data-count="staged">1<' in html
    assert 'data-count="applied">1<' in html


def test_folder_name_is_parsed_into_score_company_location_role(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "Emeryville" in html
    assert "Modeler" in html


def test_a_nonconforming_folder_name_still_renders(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "SomeOldJob").mkdir()
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "SomeOldJob" in html


def test_days_waiting_is_shown_for_an_applied_job(tmp_path):
    """applied_date is set on the build that OBSERVES the move into applied
    (ledger.sync's rule - never backfilled), so the move must be observed on
    2026-01-10 for a later build on 2026-02-01 to report 22 days waiting."""
    config = workspace.init(tmp_path)
    staged = workspace.lane_dir(tmp_path, config, "staged") / "8_Riot_LA_ConceptArtist"
    staged.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    staged.rename(workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist")
    dashboard.build(tmp_path, "2026-01-10")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "22 days" in html


def test_rejections_and_no_response_are_reported_separately(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    for name in ("8_Riot_LA_ConceptArtist", "7_Pixar_Emeryville_Modeler"):
        (workspace.lane_dir(tmp_path, config, "applied") / name).mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "8_Riot_LA_ConceptArtist", "closed", "2026-02-01", closure_reason="rejected")
    ledger.set_status(book, "7_Pixar_Emeryville_Modeler", "closed", "2026-02-01", closure_reason="closed_no_response")
    ledger.save(tmp_path / "job_ledger.json", book)
    html = dashboard.build(tmp_path, "2026-02-02")
    assert 'data-count="rejected">1<' in html
    assert 'data-count="closed_no_response">1<' in html


def test_empty_workspace_renders_without_crashing(tmp_path):
    workspace.init(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<html" in html or "<!doctype" in html.lower()
    assert 'data-count="staged">0<' in html


# --- file:// URI must be openable on Windows (WHATWG drive-letter detection
# keys off the RAW "C:" - a percent-encoded "C%3A" is not recognized) ---

def test_folder_uri_keeps_the_drive_letter_colon_unescaped(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert re.search(r'href="file:///[A-Za-z]:/', html), html
    assert "%3A" not in html


# --- a BOM or CRLF in original_job_posting.md must not silently drop the
# posting link ---

def test_posting_url_survives_a_byte_order_mark(tmp_path):
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_bytes(
        "https://example.com/job/123\n".encode("utf-8-sig")
    )
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "https://example.com/job/123" in html


def test_posting_url_survives_crlf_line_endings(tmp_path):
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_bytes(
        b"https://example.com/job/456\r\nmore notes\r\n"
    )
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "https://example.com/job/456" in html


def test_posting_url_is_empty_for_an_empty_file(tmp_path):
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_text("", encoding="utf-8")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert ">posting<" not in html


def test_posting_url_is_empty_when_first_line_is_not_a_url(tmp_path):
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_text("Notes about the role\n", encoding="utf-8")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert ">posting<" not in html


def test_posting_url_refuses_a_javascript_scheme(tmp_path):
    """Injection guard: only http(s) links are ever emitted as the posting link."""
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_text("javascript:alert(1)\n", encoding="utf-8")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "javascript:" not in html
    assert ">posting<" not in html
