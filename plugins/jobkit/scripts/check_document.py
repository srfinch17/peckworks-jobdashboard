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

    document = Path(argv[0])
    profile_path = Path(argv[1])

    if not document.exists():
        print(f"No such document: {document}")
        return 2

    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    problems = checks.run_all(document.read_text(encoding="utf-8"), profile)

    if problems:
        print(f"REFUSED: {document.name} has {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"{document.name}: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
