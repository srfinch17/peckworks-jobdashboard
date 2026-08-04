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


def test_missing_profile_treated_as_empty(tmp_path):
    doc = tmp_path / "resume.txt"
    doc.write_text("Familiar with Houdini.\n", encoding="utf-8")

    result = run(str(doc), str(tmp_path / "no_profile.json"))

    assert result.returncode == 0
    assert "clean" in result.stdout
