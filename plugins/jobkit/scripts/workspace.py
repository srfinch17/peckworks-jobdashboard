#!/usr/bin/env python3
"""Workspace layout, config, and the never-write-outside-the-root guard.

Knows about directories and configuration. Knows nothing about job status -
that is ledger.py's job.
"""
import json
import os
from pathlib import Path

LANES = ("staged", "applied", "not_applied", "skipped", "expired")

DEFAULT_CONFIG = {
    "version": 1,
    "lanes": {
        "staged": "Jobs to Apply to",
        "applied": "Jobs I Have Applied To",
        "not_applied": "Jobs Not Applied To Because Reasons",
        "skipped": "Skipped",
        "expired": "Expired",
    },
    "vocabulary": {
        "staged": "Ready to apply",
        "applied": "Applied",
        "not_applied": "Passed on",
        "skipped": "Skipped",
        "expired": "Posting closed",
        "in_flight": "Waiting to hear",
        "interviews": "Interviews",
        "rejected": "Not selected",
        "closed_no_response": "No response",
    },
    "score_threshold": 6,
    "stale_after_days": 21,
    "silence_closure_days": 30,
    "features": {"reading_stats": True},
}

EXTRA_DIRS = ("Baseline", "guides")

STARTER_RECIPES = """# Site recipes

One section per site. Updated on both success and failure, with a date.
This file is yours to read and edit.

## Greenhouse (job-boards.greenhouse.io)
- Endpoint: `https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true`
- Returns every open requisition in one call. Pull the whole list, not just the target job.
- Last verified: (not yet used)

## Lever (jobs.lever.co)
- Endpoint: `https://api.lever.co/v0/postings/<company>?mode=json`
- Last verified: (not yet used)

## Ashby (jobs.ashbyhq.com)
- Endpoint: `https://api.ashbyhq.com/posting-api/job-board/<board>`
- Last verified: (not yet used)

## Workday (*.myworkdayjobs.com)
- Endpoint: the CXS JSON behind the posting URL.
- Last verified: (not yet used)

## ADP WorkforceNow
- Endpoint: `https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions?cid=<CID>`
- The rendered page returns a browser-compatibility notice. That is an EXTRACTION
  failure, never a "this job is dead" verdict.
- Last verified: (not yet used)
"""

STARTER_CLAUDE_MD = """# My rules

Anything written here overrides JobKit's defaults. Plain English is fine.

Examples of things you might put here:
- Never show me unpaid or "for exposure" postings.
- Always mention my 3D work before my 2D work.
- I will not relocate outside the Bay Area.

(Delete these examples and write your own.)
"""


def safe_join(root: Path, *parts: str) -> Path:
    """Join under root, refusing anything that escapes it.

    This is the mechanical form of "nothing is ever written outside the workspace."
    """
    root = Path(root).resolve()
    candidate = (root / Path(*parts)).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"{candidate} is outside the workspace {root}")
    return candidate


def load_config(root: Path) -> dict:
    path = Path(root) / "jobkit.json"
    if not path.exists():
        raise FileNotFoundError(f"No jobkit.json in {root}. Run setup first.")
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path} is not a JSON object")
    return config


def lane_dir(root: Path, config: dict, lane: str) -> Path:
    if lane not in config["lanes"]:
        raise ValueError(f"unknown lane {lane!r}; valid: {', '.join(config['lanes'])}")
    return safe_join(root, config["lanes"][lane])


def init(root: Path) -> dict:
    """Create the workspace. Idempotent, and never clobbers a user's file."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    config_path = root / "jobkit.json"
    if config_path.exists():
        config = load_config(root)
    else:
        config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
        _write_atomic(config_path, json.dumps(config, indent=2))

    for lane in LANES:
        lane_dir(root, config, lane).mkdir(parents=True, exist_ok=True)
    for name in EXTRA_DIRS:
        safe_join(root, name).mkdir(parents=True, exist_ok=True)

    _write_if_absent(root / "intake_site_recipes.md", STARTER_RECIPES)
    _write_if_absent(root / "CLAUDE.md", STARTER_CLAUDE_MD)
    return config


def scan(root: Path, config: dict) -> dict[str, str]:
    """Return {folder_name: lane} for every job folder on disk."""
    found: dict[str, str] = {}
    for lane in LANES:
        directory = lane_dir(root, config, lane)
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith((".", "__")):
                continue
            found[child.name] = lane
    return found


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_if_absent(path: Path, text: str) -> None:
    if not path.exists():
        _write_atomic(path, text)
