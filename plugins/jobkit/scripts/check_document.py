#!/usr/bin/env python3
"""Refuse a generated document that breaks the user's own rules.

Usage:
  python3 check_document.py <document.txt> <profile.json>

Exit 0 = clean. Exit 1 = problems listed on stdout.
"""
import json
import sys
from pathlib import Path

import checks


def main(argv: list) -> int:
    if len(argv) < 2:
        print("Usage: python3 check_document.py <document.txt> <profile.json>")
        return 2

    document = Path(argv[0]).expanduser()
    profile_path = Path(argv[1]).expanduser()

    if not document.exists():
        print(f"No such document: {document}")
        return 2

    # A missing or unreadable profile is a usage error, never an empty
    # profile: running the check without the user's own rules would print
    # "clean" while checking nothing.
    if not profile_path.exists():
        print(f"Cannot find the profile: {profile_path}")
        print("The check needs it for your banned phrases and length limits, so nothing was checked.")
        return 2
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read the profile at {profile_path}: {exc}")
        print("Fix that file first; nothing was checked.")
        return 2

    problems = checks.run_all(document.read_text(encoding="utf-8-sig"), profile)

    if problems:
        print(f"REFUSED: {document.name} has {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"{document.name}: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
