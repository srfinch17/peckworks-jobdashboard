import subprocess
import sys
from pathlib import Path

import ledger
import workspace

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "jobkit" / "scripts" / "job_status.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _seed(root, folder, lane="staged", today="2026-01-05"):
    config = workspace.init(root)
    (workspace.lane_dir(root, config, lane) / folder).mkdir(parents=True)
    on_disk = workspace.scan(root, config)
    book = ledger.load(root / "job_ledger.json")
    book, _ = ledger.sync(book, on_disk, today)
    ledger.save(root / "job_ledger.json", book)
    return config


def _add_folder(root, config, folder, lane, today):
    (workspace.lane_dir(root, config, lane) / folder).mkdir(parents=True)
    on_disk = workspace.scan(root, config)
    book = ledger.load(root / "job_ledger.json")
    book, _ = ledger.sync(book, on_disk, today)
    ledger.save(root / "job_ledger.json", book)


def test_ambiguous_fragment_lists_matches_and_exits_nonzero_without_changing_anything(tmp_path):
    root = tmp_path / "JobDashboard"
    config = _seed(root, "7_LumenForge_Portland_Animator")
    _add_folder(root, config, "8_LumenForge_Portland_Modeler", "staged", "2026-01-05")
    before = (root / "job_ledger.json").read_text(encoding="utf-8")

    result = run(str(root), "lumenforge", "awaiting")

    assert result.returncode != 0
    assert "LumenForge_Portland_Animator" in result.stdout
    assert "LumenForge_Portland_Modeler" in result.stdout
    after = (root / "job_ledger.json").read_text(encoding="utf-8")
    assert after == before


def test_no_match_exits_nonzero(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist")

    result = run(str(root), "zzz", "awaiting")

    assert result.returncode != 0
    assert "No job folder matches" in result.stdout


def test_closing_without_a_reason_is_refused_readably(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist", lane="applied")

    result = run(str(root), "acme", "closed")

    assert result.returncode == 1
    assert "closure_reason" in result.stdout
    assert "Traceback" not in result.stdout


def test_invalid_status_is_refused_readably(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist", lane="applied")

    result = run(str(root), "acme", "vibing")

    assert result.returncode == 1
    assert "bad status" in result.stdout.lower()
    assert "Traceback" not in result.stdout


def test_applied_move_sets_applied_date_to_the_observed_move_date(tmp_path):
    root = tmp_path / "JobDashboard"
    config = _seed(root, "7_Acme_Remote_Artist", lane="staged")

    result = run(str(root), "acme", "--applied", "--date", "2026-02-10")

    assert result.returncode == 0
    applied_dir = workspace.lane_dir(root, config, "applied") / "7_Acme_Remote_Artist"
    assert applied_dir.is_dir()
    book = ledger.load(root / "job_ledger.json")
    assert book["7_Acme_Remote_Artist"]["applied_date"] == "2026-02-10"


def test_silence_closure_counts_as_closed_no_response_not_rejected(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist", lane="applied")

    result = run(str(root), "acme", "closed", "--reason", "closed_no_response", "--date", "2026-03-01")

    assert result.returncode == 0
    book = ledger.load(root / "job_ledger.json")
    tally = ledger.counts(book)
    assert tally["closed_no_response"] == 1
    assert tally["rejected"] == 0


# --- Lesson 33: --company, the pre-interview duplicate check ---

def test_company_mode_lists_every_record_for_the_employer(tmp_path):
    root = tmp_path / "JobDashboard"
    config = _seed(root, "7_LumenForge_Portland_Animator", lane="staged")
    _add_folder(root, config, "8_LumenForge_Portland_Modeler", "skipped", "2026-01-05")
    _add_folder(root, config, "9_OtherCo_Remote_Rigger", "staged", "2026-01-05")

    result = run(str(root), "--company", "LumenForge")

    assert result.returncode == 0
    assert "LumenForge_Portland_Animator" in result.stdout
    assert "LumenForge_Portland_Modeler" in result.stdout
    assert "OtherCo_Remote_Rigger" not in result.stdout


def test_company_mode_reports_none_found_without_erroring(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist", lane="staged")

    result = run(str(root), "--company", "NoSuchEmployer")

    assert result.returncode == 0
    assert "No records" in result.stdout


def test_no_reachable_input_produces_a_traceback(tmp_path):
    root = tmp_path / "JobDashboard"
    _seed(root, "7_Acme_Remote_Artist", lane="staged")

    attempts = [
        [str(root), "acme", "awaiting", "--date", "not-a-date"],
        [str(tmp_path / "nope"), "acme", "awaiting"],
        [str(root), "zzz", "awaiting"],
        [str(root), "acme"],
        [str(root)],
        [],
        [str(root), "acme", "applied"],
        [str(root), "acme", "closed", "--reason", "ghosted"],
    ]
    for args in attempts:
        result = run(*args)
        assert "Traceback" not in result.stdout
        assert "Traceback" not in result.stderr
