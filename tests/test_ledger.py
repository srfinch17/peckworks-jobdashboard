import json
import pytest

import ledger


def _staged(folder="7_Pixar_Emeryville_Modeler"):
    book, _ = ledger.sync({}, {folder: "staged"}, "2026-01-05")
    return book, folder


# --- the regression guard for the source workspace's applied_date flaw ---

def test_applied_date_survives_a_later_status_change():
    """The flaw in the source tracker: closing a job overwrote its apply date."""
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    assert book[folder]["applied_date"] == "2026-01-10"

    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="rejected")
    assert book[folder]["applied_date"] == "2026-01-10", "apply date must not follow the rejection"


def test_set_status_never_invents_an_applied_date():
    book, folder = _staged()
    ledger.set_status(book, folder, "awaiting", "2026-01-20")
    assert "applied_date" not in book[folder]


def test_a_job_first_seen_already_applied_has_no_applied_date():
    """The move was never observed, so the date is unknown. Unknown stays unset."""
    book, _ = ledger.sync({}, {"8_Riot_LA_ConceptArtist": "applied"}, "2026-01-10")
    assert "applied_date" not in book["8_Riot_LA_ConceptArtist"]
    assert book["8_Riot_LA_ConceptArtist"]["status"] == "awaiting"


def test_applied_date_is_not_reset_by_a_later_sync():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-03-01")
    assert book[folder]["applied_date"] == "2026-01-10"


# --- closure reason is a separate field ---

def test_closing_requires_a_reason():
    book, folder = _staged()
    with pytest.raises(ValueError, match="closure_reason"):
        ledger.set_status(book, folder, "closed", "2026-02-01")


def test_closure_reason_must_be_valid():
    book, folder = _staged()
    with pytest.raises(ValueError, match="closure_reason"):
        ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="ghosted")


def test_closure_reason_is_rejected_only_for_a_real_rejection():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "closed", "2026-03-20", closure_reason="closed_no_response")
    tally = ledger.counts(book)
    assert tally["rejected"] == 0
    assert tally["closed_no_response"] == 1


def test_rejected_count_survives_the_folder_vanishing():
    """A rejection is a historical fact; tidying the folder must not erase it."""
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="rejected")
    book, _ = ledger.sync(book, {}, "2026-03-01")
    assert book[folder]["lane"] == "missing"
    tally = ledger.counts(book)
    assert tally["rejected"] == 1
    assert tally["missing"] == 1


def test_closed_no_response_count_survives_the_folder_vanishing():
    """Same guard, other reason - the two must stay distinguishable after cleanup."""
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="closed_no_response")
    book, _ = ledger.sync(book, {}, "2026-03-01")
    tally = ledger.counts(book)
    assert tally["closed_no_response"] == 1
    assert tally["rejected"] == 0
    assert tally["missing"] == 1


def test_in_flight_survives_the_folder_vanishing():
    """Nothing resolved just because the folder went missing - it's still open."""
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    book, _ = ledger.sync(book, {}, "2026-02-01")
    tally = ledger.counts(book)
    assert tally["in_flight"] == 1


def test_interviews_survives_the_folder_vanishing():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "interview_scheduled", "2026-01-15")
    book, _ = ledger.sync(book, {}, "2026-02-01")
    tally = ledger.counts(book)
    assert tally["interviews"] == 1


def test_a_never_applied_staged_job_is_not_in_flight():
    book, folder = _staged()
    tally = ledger.counts(book)
    assert tally["in_flight"] == 0


def test_a_job_first_seen_already_applied_counts_as_in_flight():
    """No applied_date (the move was never observed), but it is genuinely
    being waited on - the first scan of any workspace that already has
    applied jobs in it must not make them invisible to in_flight."""
    book, _ = ledger.sync({}, {"8_Studio_Remote_Artist": "applied"}, "2026-01-10")
    assert "applied_date" not in book["8_Studio_Remote_Artist"]
    tally = ledger.counts(book)
    assert tally["in_flight"] == 1


def test_offers_are_unaffected_by_the_in_flight_fix():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "offer", "2026-01-20")
    tally = ledger.counts(book)
    assert tally["offers"] == 1

    book2, folder2 = _staged("9_Other_Studio_Job")
    book2, _ = ledger.sync(book2, {folder2: "applied"}, "2026-01-10")
    ledger.set_status(book2, folder2, "offer", "2026-01-20")
    book2, _ = ledger.sync(book2, {}, "2026-02-01")
    tally2 = ledger.counts(book2)
    assert tally2["offers"] == 0


# --- the full in_flight acceptance table ---

def _applied(folder="7_Pixar_Emeryville_Modeler"):
    book, folder = _staged(folder)
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    return book, folder


def test_an_observed_staged_to_applied_move_is_in_flight():
    book, _ = _applied()
    assert ledger.counts(book)["in_flight"] == 1


def test_an_interview_on_a_vanished_folder_is_still_in_flight():
    book, folder = _applied()
    ledger.set_status(book, folder, "interview_scheduled", "2026-01-15")
    book, _ = ledger.sync(book, {}, "2026-02-01")
    tally = ledger.counts(book)
    assert tally["in_flight"] == 1
    assert tally["interviews"] == 1


def test_an_offer_is_still_in_flight():
    book, folder = _applied()
    ledger.set_status(book, folder, "offer", "2026-01-20")
    tally = ledger.counts(book)
    assert tally["in_flight"] == 1
    assert tally["offers"] == 1


def test_a_closed_job_is_not_in_flight():
    book, folder = _applied()
    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="rejected")
    tally = ledger.counts(book)
    assert tally["in_flight"] == 0
    assert tally["rejected"] == 1


def test_a_closed_job_whose_folder_vanished_is_not_in_flight():
    book, folder = _applied()
    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="rejected")
    book, _ = ledger.sync(book, {}, "2026-03-01")
    tally = ledger.counts(book)
    assert tally["in_flight"] == 0
    assert tally["rejected"] == 1


@pytest.mark.parametrize("lane", ["expired", "skipped", "not_applied", "staged"])
def test_a_job_moved_out_of_the_applied_lane_is_not_in_flight(lane):
    """The posting expired, or the user filed it away. Nothing is being waited on."""
    book, folder = _applied()
    book, _ = ledger.sync(book, {folder: lane}, "2026-02-01")
    assert book[folder]["status"] == "awaiting"
    assert ledger.counts(book)["in_flight"] == 0


def test_a_job_that_went_missing_then_came_back_staged_is_not_in_flight():
    book, folder = _applied()
    book, _ = ledger.sync(book, {}, "2026-02-01")
    book, _ = ledger.sync(book, {folder: "staged"}, "2026-02-02")
    assert ledger.counts(book)["in_flight"] == 0


def test_set_status_on_a_staged_job_does_not_make_it_in_flight():
    book, folder = _staged()
    ledger.set_status(book, folder, "awaiting", "2026-01-20")
    assert ledger.counts(book)["in_flight"] == 0


def test_reason_is_refused_when_not_closing():
    book, folder = _staged()
    with pytest.raises(ValueError, match="only applies"):
        ledger.set_status(book, folder, "awaiting", "2026-01-20", closure_reason="rejected")


# --- lanes, history, missing folders ---

def test_sync_records_a_lane_move_in_history():
    book, folder = _staged()
    book, events = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    assert ("moved", folder, "applied") in events
    assert any("staged -> applied" in line for line in book[folder]["history"])


def test_a_vanished_folder_is_marked_missing_not_silently_kept():
    """The source tracker kept ghosts at their last known status forever."""
    book, folder = _staged()
    book, events = ledger.sync(book, {}, "2026-02-01")
    assert book[folder]["lane"] == "missing"
    assert ("missing", folder, "missing") in events


def test_a_returning_folder_leaves_missing():
    book, folder = _staged()
    book, _ = ledger.sync(book, {}, "2026-02-01")
    book, _ = ledger.sync(book, {folder: "staged"}, "2026-02-02")
    assert book[folder]["lane"] == "staged"


def test_counts_exclude_missing_from_the_staged_tally():
    book, _ = ledger.sync({}, {"a": "staged", "b": "staged"}, "2026-01-05")
    book, _ = ledger.sync(book, {"a": "staged"}, "2026-01-06")
    assert ledger.counts(book)["staged"] == 1


def test_unknown_status_is_refused():
    book, folder = _staged()
    with pytest.raises(ValueError, match="bad status"):
        ledger.set_status(book, folder, "vibing", "2026-01-20")


def test_set_status_on_a_missing_job_raises():
    with pytest.raises(KeyError):
        ledger.set_status({}, "nope", "awaiting", "2026-01-20")


# --- disambiguation, replacing the substring workaround ---

def test_resolve_returns_every_match_for_the_caller_to_disambiguate():
    book, _ = ledger.sync(
        {}, {"7_LumenForge_Portland_Animator": "staged", "8_LumenForge_Portland_Modeler": "staged"},
        "2026-01-05",
    )
    assert ledger.resolve(book, "lumenforge") == [
        "7_LumenForge_Portland_Animator",
        "8_LumenForge_Portland_Modeler",
    ]


def test_resolve_returns_empty_when_nothing_matches():
    book, _ = _staged()
    assert ledger.resolve(book, "zzz") == []


# --- persistence ---

def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    book, _ = _staged()
    path = tmp_path / "job_ledger.json"
    ledger.save(path, book)
    assert json.loads(path.read_text(encoding="utf-8")) == book
    assert list(tmp_path.iterdir()) == [path]


def test_load_of_a_missing_file_returns_empty(tmp_path):
    assert ledger.load(tmp_path / "job_ledger.json") == {}


def test_load_rejects_a_non_object(tmp_path):
    path = tmp_path / "job_ledger.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        ledger.load(path)


def test_days_since():
    assert ledger.days_since("2026-01-10", "2026-02-01") == 22
    assert ledger.days_since("", "2026-02-01") is None
    assert ledger.days_since(None, "2026-02-01") is None
