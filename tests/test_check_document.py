import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "jobkit" / "scripts" / "check_document.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_clean_document_exits_zero(tmp_path):
    doc = tmp_path / "resume.txt"
    doc.write_text("Familiar with Houdini and Maya.\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"banned_phrases": [], "envelope": {"max_words": 500, "max_sections": 8}}), encoding="utf-8")

    result = run(str(doc), str(profile))

    assert result.returncode == 0
    assert "clean" in result.stdout


def test_inflated_document_exits_one_and_names_problem(tmp_path):
    doc = tmp_path / "resume.txt"
    doc.write_text("Expert in everything.\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"banned_phrases": [], "envelope": {"max_words": 500, "max_sections": 8}}), encoding="utf-8")

    result = run(str(doc), str(profile))

    assert result.returncode == 1
    assert "REFUSED" in result.stdout
    assert "expert in" in result.stdout.lower()


def test_missing_document_exits_two(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")

    result = run(str(tmp_path / "nope.txt"), str(profile))

    assert result.returncode == 2
    assert "No such document" in result.stdout


def test_missing_profile_refuses_loudly(tmp_path):
    # A guard that silently runs without the user's rules prints "clean"
    # while checking nothing. That is the product's own definition of a
    # failure, so a missing profile is a usage error, not an empty profile.
    doc = tmp_path / "resume.txt"
    doc.write_text("Familiar with Houdini.\n", encoding="utf-8")

    result = run(str(doc), str(tmp_path / "no_profile.json"))

    assert result.returncode == 2
    assert "no_profile.json" in result.stdout
    assert "clean" not in result.stdout


def test_profile_with_utf8_bom_is_read(tmp_path):
    # profile.json may be authored on Windows and synced via Dropbox; a
    # BOM must not produce a traceback or lose the user's rules.
    doc = tmp_path / "resume.txt"
    doc.write_text("The forbidden word.\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_bytes(b'\xef\xbb\xbf{"banned_phrases": ["forbidden"]}')

    result = run(str(doc), str(profile))

    assert result.returncode == 1
    assert "forbidden" in result.stdout


def test_invalid_profile_json_is_a_plain_error(tmp_path):
    doc = tmp_path / "resume.txt"
    doc.write_text("Fine.\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text("{not json", encoding="utf-8")

    result = run(str(doc), str(profile))

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "profile.json" in result.stdout


def test_tilde_paths_are_expanded(tmp_path):
    # zsh does not expand ~ inside quotes, and the build skill quotes both
    # arguments, so a literal tilde reaching argv is a realistic input.
    import os
    home = tmp_path / "home"
    home.mkdir()
    (home / "resume.txt").write_text("Familiar with Houdini.\n", encoding="utf-8")
    (home / "profile.json").write_text('{"banned_phrases": []}', encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "~/resume.txt", "~/profile.json"],
        capture_output=True, text=True, env=env,
    )

    assert result.returncode == 0
    assert "clean" in result.stdout
