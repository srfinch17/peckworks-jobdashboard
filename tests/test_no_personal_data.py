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


def test_tracked_files_in_any_dir_name_are_still_scanned(tmp_path):
    """Regression: SKIP_DIRS must never grow to exclude a directory git tracks.

    Round 1 added "superpowers" to SKIP_DIRS so the guard would stop scanning
    docs/superpowers/ - a real, tracked, will-be-pushed directory - which made
    it print "clean" over an actual leak. This plants a forbidden pattern
    inside a *tracked* file under a directory literally named "superpowers"
    (and, for good measure, "vendor" - already skipped on purpose) in a
    throwaway git repo, and asserts the tracked one is always caught.
    """
    import os
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    docs_dir = tmp_path / "docs" / "superpowers"
    docs_dir.mkdir(parents=True)
    (docs_dir / "plan.md").write_text("home is /Users/realleak here\n", encoding="utf-8")
    sp.run(["git", "add", "."], cwd=tmp_path, check=True, env=env)
    sp.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True, env=env)

    hits = npd.scan(tmp_path, [])
    assert any(
        found == "/Users/realleak" and "docs" in rel.parts and "superpowers" in rel.parts
        for rel, _, _, found in hits
    ), "a tracked file under docs/superpowers/ must still be scanned, not silently skipped"


# --- FIX 9: the README's install command deliberately names the real,
# already-public GitHub owner/repo, which can collide with identity
# fragments in forbidden_strings.local.txt (e.g. "Finch" inside
# "srfinch17"). That one line is allowlisted; every other line is not. ---

def test_forbidden_line_allowlist_permits_only_its_own_line(tmp_path):
    lines = ["filler line\n"] * 11
    lines[10] = "   /plugin marketplace add srfinch17/peckworks-jobdashboard\n"  # line 11
    lines.append("Finch shows up again here, unrelated to the install line\n")  # line 12
    (tmp_path / "README.md").write_text("".join(lines), encoding="utf-8")
    hits = npd.scan(tmp_path, ["Finch"])
    assert hits == [(Path("README.md"), 12, "forbidden string", "Finch")]


def test_missing_local_list_fails_closed():
    """A fork without the local list must FAIL, never silently pass."""
    import os
    env = os.environ | {"JOBKIT_FORBIDDEN_LIST": str(REPO / "does_not_exist.txt")}
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert "REFUSING TO SCAN" in result.stdout
