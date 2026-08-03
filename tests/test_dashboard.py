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
