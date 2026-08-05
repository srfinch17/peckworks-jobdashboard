#!/usr/bin/env python3
"""Refuse to commit if personal data appears anywhere in the repo.

Fails CLOSED. If the local forbidden-strings file is missing this exits 1, so a
clone without that file gets a loud failure rather than a silent pass.

The forbidden list itself is personal data, so it lives in a gitignored file.
Only patterns that reveal nothing on their own are hardcoded here.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LIST = REPO / "tools" / "forbidden_strings.local.txt"

ALWAYS = [
    (r"C:\\Users\\[A-Za-z0-9._-]+", "Windows home path"),
    (r"/Users/[A-Za-z0-9._-]+", "macOS home path"),
    (r"/home/[A-Za-z0-9._-]+", "Linux home path"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
]

PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "example.test")

# Fixture placeholders that legitimately appear in tracked planning docs
# because those docs quote this guard's own test code verbatim (illustrative
# examples, not real user data). Keyed by (relative path, exact matched text)
# so it never masks the same string appearing anywhere else - test fixtures
# under tmp_path are a different relative path and stay caught.
PLACEHOLDER_ALLOWLIST: set[tuple[str, str]] = {
    ("docs/superpowers/plans/2026-08-03-jobkit-core-loop.md", "/Users/someone"),
    ("docs/superpowers/plans/2026-08-03-jobkit-core-loop.md", "/Users/whoever"),
    ("docs/superpowers/plans/2026-08-03-jobkit-core-loop.md", "someone@gmail.com"),
}

# Same idea as PLACEHOLDER_ALLOWLIST, but for hits from the local forbidden-
# strings file rather than the ALWAYS patterns, and keyed with a line number:
# a forbidden identity fragment is a false positive here only because it is a
# substring of the GitHub owner/repo name, which forbidden_strings.local.txt
# itself documents as deliberately public (it is already in the repo URL and
# the git remote) and asks reviewers not to block on. Line-scoped so the same
# fragment appearing anywhere else in the file - a real, non-public mention -
# still stops the commit.
FORBIDDEN_LINE_ALLOWLIST: set[tuple[str, int]] = {
    ("README.md", 11),  # the /plugin marketplace add ... install command
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", "vendor", ".venv", ".pytest_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip"}
# Relative-path (posix, repo-root-relative) exact matches, not bare basenames -
# a file named test_no_personal_data.py dropped elsewhere must still be scanned.
SKIP_NAMES = {
    "tools/no_personal_data.py",
    "tools/forbidden_strings.local.txt",
    "tests/test_no_personal_data.py",
}


def _tracked_files(repo: Path) -> list[Path] | None:
    """Files git actually tracks in repo - i.e. what can reach GitHub.

    Returns None (triggering the plain-directory rglob fallback) when repo
    isn't a git work tree at all, or is a subdirectory of one (e.g. a pytest
    tmp_path fixture) rather than the tracked repo root itself.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None  # git not installed
    if result.returncode != 0:
        return None
    if Path(result.stdout.strip()).resolve() != repo.resolve():
        return None
    ls = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True,
    )
    return [repo / line for line in ls.stdout.splitlines() if line]


def iter_files(repo: Path):
    tracked = _tracked_files(repo)
    paths = tracked if tracked is not None else sorted(repo.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.relative_to(repo).as_posix() in SKIP_NAMES:
            continue
        yield path


def scan(repo: Path, forbidden: list[str]) -> list[tuple[Path, int, str, str]]:
    hits: list[tuple[Path, int, str, str]] = []
    terms = [t.lower() for t in forbidden if t]
    for path in iter_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable; nothing to scan
        rel = path.relative_to(repo)
        rel_posix = rel.as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, label in ALWAYS:
                for match in re.finditer(pattern, line):
                    found = match.group()
                    if label == "email address" and found.lower().endswith(PLACEHOLDER_DOMAINS):
                        continue
                    if (rel_posix, found) in PLACEHOLDER_ALLOWLIST:
                        continue
                    hits.append((rel, lineno, label, found))
            if (rel_posix, lineno) in FORBIDDEN_LINE_ALLOWLIST:
                continue
            low = line.lower()
            for original, term in zip(forbidden, terms):
                if term and term in low:
                    hits.append((rel, lineno, "forbidden string", original))
    return hits


def main() -> int:
    list_path = Path(os.environ.get("JOBKIT_FORBIDDEN_LIST", DEFAULT_LIST))
    if not list_path.exists():
        print(f"REFUSING TO SCAN: {list_path} is missing.")
        print("Create it with one forbidden string per line: your name, employer names,")
        print("usernames, anything that must never reach a public repo.")
        print("It is gitignored on purpose - the list itself is personal data.")
        return 1

    forbidden = [
        line.strip()
        for line in list_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    hits = scan(REPO, forbidden)
    if hits:
        print(f"BLOCKED: {len(hits)} personal-data hit(s)\n")
        for rel, lineno, label, found in hits:
            print(f"  {rel}:{lineno}  [{label}]  {found}")
        print("\nNothing was committed. Remove these or add a deliberate exception.")
        return 1
    print("no_personal_data: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
