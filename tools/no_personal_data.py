#!/usr/bin/env python3
"""Refuse to commit if personal data appears anywhere in the repo.

Fails CLOSED. If the local forbidden-strings file is missing this exits 1, so a
clone without that file gets a loud failure rather than a silent pass.

The forbidden list itself is personal data, so it lives in a gitignored file.
Only patterns that reveal nothing on their own are hardcoded here.
"""
import os
import re
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

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "vendor", ".venv", ".pytest_cache",
    # ponytail: SDD planning docs (docs/superpowers/, .superpowers/) quote this
    # guard's own test fixtures verbatim as illustrative markdown examples.
    # They're meta/tooling scaffolding, not shipped app content, so they're
    # excluded the same way .git/vendor are. Revisit if real user data ever
    # ends up in a plan doc instead of an example.
    "superpowers", ".superpowers",
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip"}
SKIP_NAMES = {
    "no_personal_data.py",
    "forbidden_strings.local.txt",
    # ponytail: this test file's own fixtures contain example emails/paths
    # used to exercise the ALWAYS patterns; same self-reference rationale as
    # skipping no_personal_data.py above.
    "test_no_personal_data.py",
}


def iter_files(repo: Path):
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name in SKIP_NAMES:
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
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, label in ALWAYS:
                for match in re.finditer(pattern, line):
                    found = match.group()
                    if label == "email address" and found.lower().endswith(PLACEHOLDER_DOMAINS):
                        continue
                    hits.append((rel, lineno, label, found))
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
