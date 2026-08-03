import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "tools" / "no_personal_data.py"

sys.path.insert(0, str(REPO / "tools"))
import no_personal_data as npd


def test_finds_a_forbidden_string(tmp_path):
    (tmp_path / "notes.md").write_text("Contact Jane Doe about the role\n", encoding="utf-8")
    hits = npd.scan(tmp_path, ["Jane Doe"])
    assert len(hits) == 1
    assert hits[0][1] == 1
    assert hits[0][3] == "Jane Doe"


def test_forbidden_match_is_case_insensitive(tmp_path):
    (tmp_path / "notes.md").write_text("contact JANE DOE today\n", encoding="utf-8")
    assert npd.scan(tmp_path, ["Jane Doe"])


def test_finds_a_home_directory_path(tmp_path):
    (tmp_path / "config.json").write_text('{"root": "/Users/someone/Jobs"}\n', encoding="utf-8")
    hits = npd.scan(tmp_path, [])
    assert any(label == "macOS home path" for _, _, label, _ in hits)


def test_placeholder_email_is_allowed(tmp_path):
    (tmp_path / "template.md").write_text("you@example.com\n", encoding="utf-8")
    assert npd.scan(tmp_path, []) == []


def test_real_email_is_blocked(tmp_path):
    (tmp_path / "resume.txt").write_text("someone@gmail.com\n", encoding="utf-8")
    hits = npd.scan(tmp_path, [])
    assert any(label == "email address" for _, _, label, _ in hits)


def test_binary_and_vendor_files_are_skipped(tmp_path):
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "react.min.js").write_text("/Users/whoever/build\n", encoding="utf-8")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff/Users/whoever")
    assert npd.scan(tmp_path, []) == []


def test_clean_repo_passes(tmp_path):
    (tmp_path / "README.md").write_text("A job search workspace.\n", encoding="utf-8")
    assert npd.scan(tmp_path, ["Jane Doe"]) == []


def test_missing_local_list_fails_closed():
    """A fork without the local list must FAIL, never silently pass."""
    import os
    env = os.environ | {"JOBKIT_FORBIDDEN_LIST": str(REPO / "does_not_exist.txt")}
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert "REFUSING TO SCAN" in result.stdout
