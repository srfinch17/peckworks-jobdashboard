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
    # FIX 5: "not_applied", "skipped", "expired" were dropped from here - no
    # panel or tile ever looked them up, so they were dead config, same
    # complaint as the "threshold" decoy in profile.example.json. Every key
    # below is one the dashboard actually renders.
    "vocabulary": {
        "staged": "Ready to apply",
        "applied": "Applied",
        "in_flight": "Waiting to hear",
        "interviews": "Interviews",
        "offers": "Offers",
        "rejected": "Not selected",
        "closed_no_response": "No response",
    },
    "score_threshold": 6,
    "stale_after_days": 21,
    # FIX 5: wired into a chip on waiting cards (dashboard.py's "silent"
    # field) rather than deleted - matches the owner's stated lesson that a
    # stale application quietly inflates the in-flight count until someone
    # actually looks.
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

# Entertainment and media industry sites

Verified by direct probe on 2026-08-05. Re-mark stale with a date if one breaks.

## NBCUniversal (nbcunicareers.com)
- Fully public JSON API via SmartRecruiters, no auth needed:
  `https://api.smartrecruiters.com/v1/companies/NBCUniversal3/postings?limit=100&offset=0`
- One posting: append `/<id>`; the numeric id appears in the posting URL.
- Returns the employer's whole open-req list in one call. Use it.
- Last verified: 2026-08-05 (436 open postings at time of check)

## Warner Bros. Discovery (careers.wbd.com)
- Phenom front end over Workday. Search returns JSON via POST to
  `https://careers.wbd.com/widgets` with `Content-Type: application/json` and a body:
  `{"lang":"en_global","deviceType":"desktop","country":"global",
    "pageName":"search-results","ddoKey":"refineSearch","from":0,"size":10,
    "jobs":true,"counts":true,"all_fields":["category","country","state","city","type"],
    "jdsource":"facets","siteType":"external","keywords":"<terms>","global":true,
    "selected_fields":{},"locationData":{}}`
- Read `refineSearch.data.jobs[]`: title, jobId, applyUrl, description teaser.
- The applyUrl exposes the underlying Workday tenant
  (`warnerbros.wd5.myworkdayjobs.com/global`), so the generic Workday recipe
  above also applies.
- Last verified: 2026-08-05

## Paramount (careers.paramount.com)
- SuccessFactors career site, server rendered: a plain GET works for search
  and for job pages, no JS needed.
- Search: `https://careers.paramount.com/search/?q=<terms>`; job links match `/job/`.
- Last verified: 2026-08-05

## Disney (jobs.disneycareers.com)
- Radancy site, server rendered: a plain GET works.
- Search: `https://jobs.disneycareers.com/search-jobs/<terms>`; job links match `/job/`.
- Last verified: 2026-08-05

## Fox (foxcareers.com)
- Custom site, server rendered: a plain GET works.
- Search: `https://www.foxcareers.com/Search?searchText=<terms>`;
  job pages at `/Search/JobDetail/<ReqId>` (req ids look like R50032802).
- Last verified: 2026-08-05

## Upwork (upwork.com)
- Hard wall: a plain fetch gets a Cloudflare challenge (HTTP 403, verified),
  and job details require login. No public unauthenticated API exists.
- Tier 1 (paste the posting text) is the reliable path. Tier 3 works only
  through the user's own logged-in browser session.
- Upwork is a freelance marketplace, not an employer: treat the posting CLIENT
  as an intermediary of unknown identity and say so at intake, exactly like an
  agency flag. Watch for rights-grab terms in the brief.
- Last verified: 2026-08-05
"""

STARTER_CLAUDE_MD = """# My rules

Anything written here overrides JobKit's defaults. Plain English is fine.

Examples of things you might put here:
- Never show me unpaid or "for exposure" postings.
- Always mention my 3D work before my 2D work.
- I will not relocate outside the Bay Area.

(Delete these examples and write your own.)

# Lessons learned

JobKit appends what it learns from this search here, one dated bullet at a
time, and reads this section back on every task. Corrections you make land
here too, so the same mistake is not repeated next week. Edit or delete
freely; this file is yours.

Format: `- 2026-01-15: <the lesson, one or two sentences, and why it holds>`

Lessons about a SITE (how a job board behaves, what broke, what worked)
belong in `intake_site_recipes.md` instead, next to that site's recipe.
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
    path = Path(root).expanduser() / "jobkit.json"
    if not path.exists():
        raise FileNotFoundError(f"No jobkit.json in {root}. Run setup first.")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError(f"{path} is not a JSON object")
    return config


def lane_dir(root: Path, config: dict, lane: str) -> Path:
    if lane not in config["lanes"]:
        raise ValueError(f"unknown lane {lane!r}; valid: {', '.join(config['lanes'])}")
    return safe_join(root, config["lanes"][lane])


def init(root: Path) -> dict:
    """Create the workspace. Idempotent, and never clobbers a user's file."""
    # expanduser: the canonical setup phrase is "~/JobDashboard", and an
    # unexpanded ~ silently creates a literal "~" folder in the current dir.
    root = Path(root).expanduser()
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

    # First-day guide: shipped as a real HTML file next to this script so it can
    # be previewed in a browser during development, copied (never clobbered) into
    # the user's library where the dashboard picks it up like any other guide.
    template = Path(__file__).resolve().parent.parent / "templates" / "Getting_Started.html"
    if template.exists():
        _write_if_absent(safe_join(root, "guides", "Getting_Started.html"),
                         template.read_text(encoding="utf-8"))
    return config


def scan(root: Path, config: dict) -> dict[str, str]:
    """Return {folder_name: lane} for every job folder on disk."""
    found, _ = scan_with_warnings(root, config)
    return found


def scan_with_warnings(root: Path, config: dict) -> "tuple[dict[str, str], list[str]]":
    """Same as scan(), plus a plain-English warning for every collision.

    FIX 4: the same folder name can exist under two lanes at once (a Dropbox
    restore, or a user copying a folder). The old scan() silently kept
    whichever lane it visited last and discarded the fact that a collision
    happened at all. Lanes are still visited in the same fixed order and the
    last one visited still wins - unchanged behavior - but now a warning
    names both lanes so the loser is not just silently gone.
    """
    found: dict[str, str] = {}
    warnings: list[str] = []
    for lane in LANES:
        directory = lane_dir(root, config, lane)
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith((".", "__")):
                continue
            if child.name in found:
                warnings.append(
                    f"{child.name!r} exists in both the {found[child.name]!r} and {lane!r} "
                    f"lanes; showing it as {lane!r} - move or rename one copy to fix this."
                )
            found[child.name] = lane
    return found, warnings


def find_unmapped_job_dirs(root: Path, config: dict, missing_names: set) -> dict:
    """Top-level workspace folders that are not a configured lane or extra
    dir, but contain a subfolder matching a ledger entry now marked
    'missing'.

    FIX 4: this is the fingerprint of a lane renamed in jobkit.json after
    jobs already existed in its old physical folder - scan() looks for jobs
    under the NEW name, finds nothing, and every job that used to live there
    quietly flips to "missing" with no clue why. Returns
    {directory_name: [matching job folder names]}.
    """
    root = Path(root)
    if not missing_names:
        return {}
    known = set(config.get("lanes", {}).values()) | set(EXTRA_DIRS)
    found = {}
    if not root.is_dir():
        return found
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in known or child.name.startswith((".", "__")):
            continue
        try:
            matches = sorted(j.name for j in child.iterdir() if j.is_dir() and j.name in missing_names)
        except OSError:
            continue
        if matches:
            found[child.name] = matches
    return found


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_if_absent(path: Path, text: str) -> None:
    if not path.exists():
        _write_atomic(path, text)
