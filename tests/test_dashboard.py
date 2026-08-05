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


def test_generated_page_loads_nothing_from_the_network_except_google_fonts(tmp_path):
    """Links to postings are fine. The ONE allowed CDN load is the Google
    Fonts stylesheet - nothing load-bearing depends on it, every font stack
    ends in a system fallback, so the page still looks deliberate blocked.
    This forbids: any <script src=, any @import, any remote <img src="http,
    and any <link rel="stylesheet"> whose href is not on fonts.googleapis.com."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<script src=" not in html
    assert "@import" not in html
    assert '<img src="http' not in html
    for tag in re.findall(r"<link\b[^>]*>", html):
        if 'rel="stylesheet"' not in tag:
            continue
        href = re.search(r'href="([^"]+)"', tag)
        assert href and href.group(1).startswith("https://fonts.googleapis.com/"), tag


def test_font_identity_link_is_present(tmp_path):
    """Guards against silently dropping the Space Grotesk / IBM Plex identity."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "fonts.googleapis.com/css2?family=Space+Grotesk" in html
    assert 'rel="preconnect" href="https://fonts.gstatic.com"' in html


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


# --- library section (guides/*.html) ---

def test_library_section_appears_in_output(tmp_path):
    workspace.init(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert 'id="library"' in html


def test_a_guide_with_title_and_description_renders(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "negotiating.html").write_text(
        '<html><head><title>Negotiating Offers</title>'
        '<meta name="description" content="A short field guide to comp talks."></head>'
        '<body></body></html>',
        encoding="utf-8",
    )
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "Negotiating Offers" in html
    assert "A short field guide to comp talks." in html
    assert 'href="guides/negotiating.html"' in html


def test_a_guide_with_a_hostile_title_is_escaped(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "hostile.html").write_text(
        '<html><head><title>R&D <script>alert(1)</script> Notes</title></head><body></body></html>',
        encoding="utf-8",
    )
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<script>alert(1)</script>" not in html
    assert "R&amp;D" in html


def test_empty_guides_dir_renders_an_honest_empty_state(tmp_path):
    workspace.init(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "No guides yet" in html


# --- interviews panel ---

def _section_html(html_doc: str, section_id: str) -> str:
    match = re.search(rf'<section[^>]*id="{section_id}".*?</section>', html_doc, re.DOTALL)
    return match.group(0) if match else ""


def test_interview_scheduled_job_appears_in_interviews_not_waiting(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "8_Riot_LA_ConceptArtist", "interview_scheduled", "2026-01-15")
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-20")
    interviews_section = _section_html(html_doc, "interviews")
    waiting_section = _section_html(html_doc, "active")
    assert "Riot" in interviews_section
    assert "Riot" not in waiting_section


def test_interviews_panel_appears_above_ready_to_apply(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "8_Riot_LA_ConceptArtist", "interview_scheduled", "2026-01-15")
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-20")
    assert html_doc.index('id="interviews"') < html_doc.index('id="staged"')


def test_no_interviews_section_is_absent(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert 'id="interviews"' not in html_doc


def test_applied_job_with_no_applied_date_renders_unknown_and_sorts_last(tmp_path):
    config = workspace.init(tmp_path)
    staged = workspace.lane_dir(tmp_path, config, "staged") / "9_Known_LA_Job"
    staged.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    staged.rename(workspace.lane_dir(tmp_path, config, "applied") / "9_Known_LA_Job")
    dashboard.build(tmp_path, "2026-01-10")
    (workspace.lane_dir(tmp_path, config, "applied") / "5_Unknown_LA_Job").mkdir()
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    waiting_section = _section_html(html_doc, "active")
    assert "applied date unknown" in waiting_section
    assert waiting_section.index("Known") < waiting_section.index("Unknown")


def test_posting_url_refuses_a_javascript_scheme(tmp_path):
    """Injection guard: only http(s) links are ever emitted as the posting link."""
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler"
    folder.mkdir()
    (folder / "original_job_posting.md").write_text("javascript:alert(1)\n", encoding="utf-8")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "javascript:" not in html
    assert ">posting<" not in html


# --- library: categories, icons, filter toolbar, read tracking ---

def test_guide_with_declared_meta_uses_them(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "craft.html").write_text(
        '<html><head><title>Color Theory</title>'
        '<meta name="jobkit-category" content="Craft">'
        '<meta name="jobkit-icon" content="palette"></head><body></body></html>',
        encoding="utf-8",
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert 'data-category="Craft"' in html_doc


def test_guide_without_meta_infers_category_from_title(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "portfolio.html").write_text(
        '<html><head><title>Building Your Portfolio Reel</title></head><body></body></html>',
        encoding="utf-8",
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert 'data-category="Career"' in html_doc


def test_guide_with_unmatched_title_falls_back_to_guides_category(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "misc.html").write_text(
        '<html><head><title>Zzyzx Notes</title></head><body></body></html>',
        encoding="utf-8",
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert 'data-category="Guides"' in html_doc


def test_hostile_title_is_escaped_in_card_and_filter_data(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "hostile.html").write_text(
        '<html><head><title>R&D <script>alert(1)</script> Craft</title></head><body></body></html>',
        encoding="utf-8",
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert "<script>alert(1)</script>" not in html_doc
    assert "R&amp;D" in html_doc


def test_library_toolbar_has_search_input_and_category_chips(tmp_path):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "craft.html").write_text(
        '<html><head><title>Color Theory</title>'
        '<meta name="jobkit-category" content="Craft"></head><body></body></html>',
        encoding="utf-8",
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    lib_section = _section_html(html_doc, "library")
    assert 'id="libq"' in lib_section
    assert 'data-chip="Craft"' in lib_section
    assert 'data-chip="All"' in lib_section


def test_reading_stats_off_skips_harvest_and_no_read_state(tmp_path, monkeypatch):
    config = workspace.init(tmp_path)
    import json
    cfg = json.loads((tmp_path / "jobkit.json").read_text(encoding="utf-8"))
    cfg["features"]["reading_stats"] = False
    (tmp_path / "jobkit.json").write_text(json.dumps(cfg), encoding="utf-8")
    guides = tmp_path / "guides"
    (guides / "craft.html").write_text(
        '<html><head><title>Color Theory</title></head><body></body></html>', encoding="utf-8"
    )

    called = []
    monkeypatch.setattr("reading_stats.harvest", lambda root: called.append(root) or {"pages": {}})
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    assert called == []
    assert "unread" not in html_doc.lower() or 'data-read="0"' not in html_doc


def test_reading_stats_on_shows_read_state_from_json(tmp_path, monkeypatch):
    workspace.init(tmp_path)
    guides = tmp_path / "guides"
    (guides / "craft.html").write_text(
        '<html><head><title>Color Theory</title></head><body></body></html>', encoding="utf-8"
    )
    monkeypatch.setattr(
        "reading_stats.harvest",
        lambda root: {"watermark": 1, "daily": {},
                       "pages": {"craft.html": {"opens": 3, "first": "2026-01-01", "last": "2026-01-20"}}},
    )
    html_doc = dashboard.build(tmp_path, "2026-02-01")
    lib_section = _section_html(html_doc, "library")
    assert "2026-01-20" in lib_section


def test_humanize_keeps_runs_of_capitals_and_digits_together():
    """A naive lower-or-digit -> upper split turns 3DGeneralist into "3 DGeneralist"."""
    assert dashboard._humanize("3DGeneralist") == "3D Generalist"
    assert dashboard._humanize("SeniorVFXArtist") == "Senior VFX Artist"
    assert dashboard._humanize("AIEngineer") == "AI Engineer"
    assert dashboard._humanize("LookDevArtist") == "Look Dev Artist"


# --- main() error handling: no raw tracebacks for a first-time user ---

def test_main_on_a_path_that_does_not_exist_names_the_path(tmp_path, capsys):
    missing = tmp_path / "does_not_exist_here"
    code = dashboard.main([str(missing), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert str(missing) in out


def test_main_on_a_directory_with_no_jobkit_json_mentions_setup(tmp_path, capsys):
    code = dashboard.main([str(tmp_path), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert "setup" in out.lower()


def test_main_on_a_malformed_jobkit_json_says_config_unreadable(tmp_path, capsys):
    (tmp_path / "jobkit.json").write_text("{not valid json", encoding="utf-8")
    code = dashboard.main([str(tmp_path), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert "config" in out.lower()


def test_main_on_an_initialized_workspace_still_writes_the_dashboard(tmp_path, capsys):
    workspace.init(tmp_path)
    code = dashboard.main([str(tmp_path), "--no-open"])
    assert code == 0
    assert (tmp_path / "CareerDashboard.html").exists()


# --- FIX 5: reachable bad states must degrade gracefully, never a raw traceback ---

def test_a_malformed_applied_date_does_not_crash_the_build(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    book["8_Riot_LA_ConceptArtist"]["applied_date"] = "2026-13-45"
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-15")
    assert "Riot" in html_doc


def test_main_on_a_corrupt_job_ledger_gives_a_friendly_message(tmp_path, capsys):
    workspace.init(tmp_path)
    (tmp_path / "job_ledger.json").write_text("{not valid json", encoding="utf-8")
    code = dashboard.main([str(tmp_path), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert "traceback" not in out.lower()
    assert "job_ledger.json" in out


def test_build_survives_a_ledger_entry_missing_its_history_key(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    applied_dir = workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist"
    applied_dir.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    del book["8_Riot_LA_ConceptArtist"]["history"]
    ledger.save(tmp_path / "job_ledger.json", book)
    # Move it to a still-rendered lane so the "moved" event actually
    # exercises the history.append() codepath that used to KeyError.
    applied_dir.rename(workspace.lane_dir(tmp_path, config, "staged") / "8_Riot_LA_ConceptArtist")
    html_doc = dashboard.build(tmp_path, "2026-01-11")
    assert "Riot" in html_doc


def test_build_survives_a_ledger_entry_that_is_a_string_not_an_object(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    book["9_Ghost_Remote_Job"] = "this is not a real ledger entry"
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-11")
    assert "Pixar" in html_doc


def test_main_with_lanes_removed_from_config_gives_a_friendly_message(tmp_path, capsys):
    import json
    workspace.init(tmp_path)
    cfg_path = tmp_path / "jobkit.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    del cfg["lanes"]
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    code = dashboard.main([str(tmp_path), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert "traceback" not in out.lower()
    assert "jobkit.json" in out


def test_main_on_a_permission_error_while_saving_the_ledger_gives_a_friendly_message(
    tmp_path, capsys, monkeypatch
):
    """Stands in for a read-only job_ledger.json (common under Dropbox/OneDrive):
    monkeypatching the failure keeps the test deterministic across platforms
    where making a file genuinely read-only behaves differently."""
    import ledger
    workspace.init(tmp_path)

    def boom(*args, **kwargs):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(ledger, "save", boom)
    code = dashboard.main([str(tmp_path), "--no-open"])
    out = capsys.readouterr().out
    assert code == 2
    assert "traceback" not in out.lower()


# --- FIX 6: a future applied_date must not render as a negative day count ---

# --- FIX 3: offer/phone_screen/missing must each render somewhere, and the
# in_flight tile must agree with the "Waiting to hear" panel it labels ---

def test_offer_status_gets_its_own_panel_and_tile(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "9_Riot_LA_ConceptArtist").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "9_Riot_LA_ConceptArtist", "offer", "2026-01-20")
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-21")
    offers_section = _section_html(html_doc, "offers")
    waiting_section = _section_html(html_doc, "active")
    assert "Riot" in offers_section
    assert "Riot" not in waiting_section
    assert 'data-count="offers">1<' in html_doc


def test_phone_screen_status_appears_in_interviews_not_waiting(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "9_Riot_LA_ConceptArtist").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "9_Riot_LA_ConceptArtist", "phone_screen", "2026-01-15")
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-20")
    interviews_section = _section_html(html_doc, "interviews")
    waiting_section = _section_html(html_doc, "active")
    assert "Riot" in interviews_section
    assert "Phone screen" in interviews_section
    assert "Riot" not in waiting_section


def test_in_flight_tile_matches_the_waiting_panel_when_an_interview_is_open(tmp_path):
    """FIX 3 reproduction: the tile used to count every open application
    (including interview-stage ones) while the "Waiting to hear" panel it
    labels only ever showed the non-interview subset."""
    import ledger
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "9_Pixar_LA_Modeler").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "8_Riot_LA_ConceptArtist", "interview_scheduled", "2026-01-15")
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-20")
    waiting_section = _section_html(html_doc, "active")
    assert waiting_section.count("jcard") == 1  # only Pixar; Riot moved to interviews
    assert 'data-count="in_flight">1<' in html_doc


def test_a_missing_folder_renders_in_the_missing_panel(tmp_path):
    config = workspace.init(tmp_path)
    staged = workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler"
    staged.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    import shutil
    shutil.rmtree(staged)
    html_doc = dashboard.build(tmp_path, "2026-01-15")
    missing_section = _section_html(html_doc, "missing")
    assert "Pixar" in missing_section


def test_duplicate_folder_in_two_lanes_produces_a_warning(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "7_Pixar_LA_Modeler").mkdir()
    html_doc = dashboard.build(tmp_path, "2026-01-10")
    assert "warnbox" in html_doc
    assert "7_Pixar_LA_Modeler" in html_doc
    assert "both the" in html_doc


def test_a_renamed_lane_orphan_produces_a_warning(tmp_path):
    import json
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler").mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    cfg_path = tmp_path / "jobkit.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["lanes"]["staged"] = "Jobs To Chase"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    workspace.lane_dir(tmp_path, cfg, "staged").mkdir(parents=True, exist_ok=True)
    html_doc = dashboard.build(tmp_path, "2026-01-15")
    assert "warnbox" in html_doc
    assert "lane was renamed" in html_doc


def test_a_long_silent_waiting_job_gets_a_silence_chip(tmp_path):
    config = workspace.init(tmp_path)
    staged = workspace.lane_dir(tmp_path, config, "staged") / "8_Riot_LA_ConceptArtist"
    staged.mkdir()
    dashboard.build(tmp_path, "2026-01-01")
    staged.rename(workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist")
    dashboard.build(tmp_path, "2026-01-01")
    html_doc = dashboard.build(tmp_path, "2026-02-15")
    waiting_section = _section_html(html_doc, "active")
    assert "likely closed silently" in waiting_section


# --- Lesson 34: the per-employer response clock ---

def _apply_and_close(tmp_path, config, folder, apply_day, close_day, reason="rejected"):
    import ledger
    (workspace.lane_dir(tmp_path, config, "staged") / folder).mkdir()
    dashboard.build(tmp_path, apply_day)
    (workspace.lane_dir(tmp_path, config, "staged") / folder).rename(
        workspace.lane_dir(tmp_path, config, "applied") / folder)
    dashboard.build(tmp_path, apply_day)
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, folder, "closed", close_day, closure_reason=reason)
    ledger.save(tmp_path / "job_ledger.json", book)


def _apply_only(tmp_path, config, folder, apply_day):
    (workspace.lane_dir(tmp_path, config, "staged") / folder).mkdir()
    dashboard.build(tmp_path, apply_day)
    (workspace.lane_dir(tmp_path, config, "staged") / folder).rename(
        workspace.lane_dir(tmp_path, config, "applied") / folder)
    dashboard.build(tmp_path, apply_day)


def test_waiting_card_inside_employer_normal_window_says_silence_is_uninformative(tmp_path):
    config = workspace.init(tmp_path)
    _apply_and_close(tmp_path, config, "8_LumenForge_Portland_Modeler", "2026-01-01", "2026-01-15")
    _apply_and_close(tmp_path, config, "7_LumenForge_Austin_Rigger", "2026-02-01", "2026-02-22")
    _apply_only(tmp_path, config, "9_LumenForge_Remote_Animator", "2026-03-01")

    # 10 days waiting, well inside the measured 14-21 day window.
    html_doc = dashboard.build(tmp_path, "2026-03-11")
    waiting_section = _section_html(html_doc, "active")
    assert "LumenForge" in waiting_section
    assert "isn't good news or bad news yet" in waiting_section
    assert "likely closed silently" not in waiting_section


def test_waiting_card_with_no_employer_history_uses_the_global_baseline(tmp_path):
    config = workspace.init(tmp_path)
    _apply_and_close(tmp_path, config, "8_LumenForge_Portland_Modeler", "2026-01-01", "2026-01-15")
    _apply_only(tmp_path, config, "9_OtherCo_Remote_Rigger", "2026-02-01")

    html_doc = dashboard.build(tmp_path, "2026-02-06")
    waiting_section = _section_html(html_doc, "active")
    assert "no history yet for OtherCo" in waiting_section
    assert "search-wide baseline" in waiting_section


def test_silent_chip_and_uninformative_chip_never_both_appear(tmp_path):
    config = workspace.init(tmp_path)
    _apply_and_close(tmp_path, config, "8_LumenForge_Portland_Modeler", "2026-01-01", "2026-01-15")
    _apply_only(tmp_path, config, "9_LumenForge_Remote_Animator", "2026-01-01")

    # 45 days later - past the default silence_closure_days (30).
    html_doc = dashboard.build(tmp_path, "2026-02-15")
    waiting_section = _section_html(html_doc, "active")
    assert "likely closed silently" in waiting_section
    assert "good news or bad news" not in waiting_section


def test_waiting_card_with_no_applied_date_renders_neither_signal_chip():
    """No applied_date must mean no chip, never a guessed 0."""
    text = dashboard._card(
        {
            "company": "LumenForge", "role": "", "location": "", "score": None,
            "status": "awaiting", "closure_reason": "", "applied_date": "",
            "first_seen": "", "closed_date": "", "status_date": "",
            "days_waiting": None, "stale": False, "days_since_signal": None,
            "silent": False, "response_source": None, "response_window": None,
            "posting_url": "", "folder_uri": "",
        },
        "active",
    )
    assert "days since last signal" not in text
    assert "good news or bad news" not in text
    assert "applied date unknown" in text


def test_a_future_applied_date_does_not_render_as_negative_days(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    folder = workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist"
    folder.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    book["8_Riot_LA_ConceptArtist"]["applied_date"] = "2026-06-01"
    ledger.save(tmp_path / "job_ledger.json", book)
    html_doc = dashboard.build(tmp_path, "2026-01-15")
    waiting_section = _section_html(html_doc, "active")
    assert "future" in waiting_section
    assert re.search(r"-\d+ days", waiting_section) is None
