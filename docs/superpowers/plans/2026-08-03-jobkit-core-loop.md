# JobKit Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code plugin that turns an empty folder into a job-search workspace, ingests a pasted job link into a tracked folder with a tailored resume, and regenerates a self-contained dashboard that opens by double-click.

**Architecture:** One plugin directory containing skills (markdown procedures loaded on demand) plus four small Python modules. The plugin is read-only and updated by `git pull`; the user's workspace holds all data and all customization. The ledger is keyed on folder name. The dashboard is a single HTML file with every value baked into the markup at generation time, because a `file://` page cannot `fetch()` a sibling JSON file.

**Tech Stack:** Python 3.11+ (standard library only for this plan — no pip installs), Markdown skills, vanilla HTML/CSS/JS. pytest for tests (dev-only, never a runtime requirement).

**Source spec:** `docs/superpowers/specs/2026-08-02-jobkit-design.md`

## Global Constraints

- **Python 3.11 or newer.** Standard library only in this plan. `python-docx` and `reportlab` arrive in the Session 3 plan, not here.
- **Nothing is ever written outside the workspace root.** Every script takes the workspace path as an explicit argument. Never infer it from the current working directory.
- **The ledger is keyed on folder name.** Never on a content hash of a file that gets edited.
- **`applied_date` is set only from an observed real signal** — a folder moving into the applied lane. Never backfilled from a later status event, never defaulted to today, never guessed. If unknown it stays unset.
- **`status` and `closure_reason` are separate fields.** Only `closure_reason == "rejected"` counts as a rejection anywhere.
- **The dashboard is one self-contained HTML file.** Inline CSS, inline SVG, vanilla JS. No server, no build step, no npm, no CDN for anything load-bearing. All data baked in at generation time. **The string `fetch(` must never appear in generated output.**
- **All user-supplied text is HTML-escaped** before it reaches the page.
- **No personal data in this repo.** No real names beyond "Benny", no employer names, no home directory paths, no real email addresses. `tools/no_personal_data.py` must pass before any push.
- **The tool never makes the art.** No image generation, no touching portfolio files, no writing anything that claims to be the user's creative work.
- **Every state-changing skill regenerates the dashboard** at the end of its turn.
- **Every skill checks the workspace `CLAUDE.md` last**; if it contradicts plugin instructions, the workspace file wins.

---

## File Structure

**Created by this plan:**

| Path | Responsibility |
|---|---|
| `tools/no_personal_data.py` | Pre-commit guard. Scans repo for personal data, exits nonzero on a hit. |
| `.claude-plugin/marketplace.json` | Makes this repo installable as a plugin marketplace. |
| `plugins/jobkit/.claude-plugin/plugin.json` | Plugin manifest — name, version, description. |
| `plugins/jobkit/scripts/workspace.py` | Workspace creation, config load, lane→folder mapping, path containment. |
| `plugins/jobkit/scripts/ledger.py` | Ledger load/save/sync/status. Folder-keyed, atomic writes. |
| `plugins/jobkit/scripts/checks.py` | Envelope check, banned-phrase check, competence-inflation check. |
| `plugins/jobkit/scripts/dashboard.py` | Reads workspace + ledger, emits one self-contained HTML file. |
| `plugins/jobkit/skills/*/SKILL.md` | The procedures: setup, intake, build, help. |
| `plugins/jobkit/commands/*.md` | Thin slash-command wrappers. |
| `tests/` | pytest suite. `conftest.py` puts `scripts/` on the path. |

**Module boundaries:** `workspace.py` knows about directories and config and nothing about job status. `ledger.py` knows about job records and nothing about the filesystem layout (it is handed a `{folder: lane}` dict). `checks.py` is pure text-in, problems-out. `dashboard.py` is the only module that emits HTML. Nothing imports upward.

---

### Task 1: Repo init and the personal-data guard

The guard ships before the first push, because the push is the irreversible step.

**Files:**
- Create: `.gitignore`
- Create: `tools/no_personal_data.py`
- Create: `tools/forbidden_strings.local.txt` (gitignored)
- Create: `tests/test_no_personal_data.py`
- Create: `.git/hooks/pre-commit`

**Interfaces:**
- Consumes: nothing
- Produces: `scan(repo: Path, forbidden: list[str]) -> list[tuple[Path, int, str, str]]` returning `(relative_path, line_number, label, matched_text)`; `main() -> int` returning a shell exit code.

- [ ] **Step 1: Initialize the repository**

```bash
# run from the repo root
git init
git branch -M main
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
tools/forbidden_strings.local.txt
```

The forbidden-strings list is itself personal data. It never gets committed.

- [ ] **Step 3: Write the failing test**

Create `tests/test_no_personal_data.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `python -m pytest tests/test_no_personal_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'no_personal_data'`

- [ ] **Step 5: Write the guard**

Create `tools/no_personal_data.py`:

```python
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

SKIP_DIRS = {".git", "__pycache__", "node_modules", "vendor", ".venv", ".pytest_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip"}
SKIP_NAMES = {"no_personal_data.py", "forbidden_strings.local.txt"}


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
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_no_personal_data.py -v`
Expected: PASS, 8 passed

- [ ] **Step 7: Create the local forbidden list**

Create `tools/forbidden_strings.local.txt`. One string per line. At minimum: your full name, your username, every employer named in your source workspace, your real email domain.

```
# One forbidden string per line. Case-insensitive substring match.
# This file is gitignored. It is personal data.
```

Fill it in with real values. Do not commit it — `.gitignore` already covers it.

- [ ] **Step 8: Wire the pre-commit hook**

Create `.git/hooks/pre-commit`:

```sh
#!/bin/sh
python tools/no_personal_data.py || exit 1
```

Then: `chmod +x .git/hooks/pre-commit`

Note: `.git/hooks/` is not versioned. Task 2 adds a README line telling a future clone to re-create it.

- [ ] **Step 9: Verify the hook actually blocks**

```bash
echo "my name is <put a string from your local list here>" > /tmp/leak_test.md
cp /tmp/leak_test.md ./leak_test.md
git add leak_test.md
git commit -m "test: this must be refused"
```
Expected: commit REFUSED, output shows `BLOCKED: 1 personal-data hit(s)`.

Then clean up: `git reset && rm leak_test.md`

- [ ] **Step 10: Commit**

```bash
git add .gitignore tools/no_personal_data.py tests/test_no_personal_data.py
git commit -m "feat: add personal-data guard that fails closed"
```

---

### Task 2: The Phase 0 gate — plugin scaffold, push, install

The only task that can invalidate the architecture. Ten minutes. Do it before writing anything else.

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/jobkit/.claude-plugin/plugin.json`
- Create: `plugins/jobkit/skills/jobkit-help/SKILL.md`
- Create: `plugins/jobkit/commands/jobkit-help.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1's guard (must pass before the push)
- Produces: an installable plugin named `jobkit`; a working `/jobkit-help` command

- [ ] **Step 1: Create the marketplace manifest**

Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "peckworks-jobdashboard",
  "owner": {
    "name": "peckworks"
  },
  "plugins": [
    {
      "name": "jobkit",
      "source": "./plugins/jobkit",
      "description": "A job-search workspace you drive by talking to Claude. Paste job links, get tracked folders with tailored materials, and a dashboard that opens by double-click."
    }
  ]
}
```

- [ ] **Step 2: Create the plugin manifest**

Create `plugins/jobkit/.claude-plugin/plugin.json`:

```json
{
  "name": "jobkit",
  "version": "0.1.0",
  "description": "Job-search workspace: paste job links, get tracked folders with tailored materials and an offline dashboard.",
  "author": {
    "name": "peckworks"
  }
}
```

- [ ] **Step 3: Create the stub skill**

Create `plugins/jobkit/skills/jobkit-help/SKILL.md`:

```markdown
---
name: jobkit-help
description: Use when the user asks what JobKit can do, how to use it, what to say, or types /jobkit-help. Also use the first time a user interacts with JobKit in a session where no workspace has been set up yet.
---

# What you can say to JobKit

Answer in plain English. This user may not be technical. Describe things to
**say**, not commands to run.

If no workspace exists yet, lead with setup and stop there — do not list the
rest, it will not work yet.

## Getting started

- **"Set up my job search in ~/JobDashboard"** — creates the workspace and walks
  through a short interview. Do this first.

## Every day

- **Paste a job link** — JobKit reads the posting, scores the fit, and files it.
- **"Build the application for the Pixar one"** — tailors a resume from the baseline.
- **"I applied to the Pixar one"** — moves it to the applied lane.
- **"Here's a rejection email"** *(paste it)* — records it and files the email.
- **"They want to schedule an interview"** — creates an interview card.
- **"Open my dashboard"** — regenerates and opens the HTML dashboard.

## Anytime

- **"Make me a guide about colour theory"** — builds a study page in your library.
- **"What's going on with my search?"** — a briefing of where everything stands.

## Ground rules worth stating if asked

- JobKit never makes art and never touches portfolio files. It handles the admin
  around the work, not the work.
- Nothing is written outside the workspace folder.
- Nothing is invented. If a date or a fact is unknown, it stays unknown.
```

- [ ] **Step 4: Create the command wrapper**

Create `plugins/jobkit/commands/jobkit-help.md`:

```markdown
---
description: What you can say to JobKit
---

Invoke the `jobkit-help` skill and show the user what they can say.
```

- [ ] **Step 5: Update the README status line**

In `README.md`, replace the line reading `**Status: planning. Nothing is built yet.** Start with `docs/ASSESSMENT.md`.` with:

```markdown
**Status: in development.** Design: `docs/superpowers/specs/2026-08-02-jobkit-design.md`.
Plan: `docs/superpowers/plans/2026-08-03-jobkit-core-loop.md`.

## Contributing

After cloning, re-create the pre-commit guard (git does not version hooks):

```sh
printf '#!/bin/sh\npython tools/no_personal_data.py || exit 1\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Then create `tools/forbidden_strings.local.txt` with one forbidden string per line.
The guard refuses to run without it.
```

- [ ] **Step 6: Run the guard manually before pushing**

Run: `python tools/no_personal_data.py`
Expected: `no_personal_data: clean`

**If this reports any hit, stop. Do not push.** Fix the hit first.

- [ ] **Step 7: Commit and push**

```bash
git add .claude-plugin plugins README.md
git commit -m "feat: add plugin scaffold with jobkit-help skill"
gh repo create peckworks-jobdashboard --public --source=. --remote=origin --push
```

If the repo already exists on GitHub: `git remote add origin <url> && git push -u origin main`

- [ ] **Step 8: Install the plugin in Claude Code CLI**

```
/plugin marketplace add <owner>/peckworks-jobdashboard
/plugin install jobkit
```

Then type `/jobkit-help`.
Expected: the help text from Step 3 appears.

- [ ] **Step 9: Install the plugin in Claude Desktop's Code tab — THE GATE**

Repeat Step 8 inside Claude Desktop's Code tab. Type `/jobkit-help`.

**Record the result in `docs/BUILD_PLAN.md` under Phase 0 either way.**

- **If it works:** continue to Task 3 unchanged.
- **If it does not:** the plugin artifact is unchanged. Benny installs Claude Code CLI with `npm install -g @anthropic-ai/claude-code` and runs it there. Note this in the README install instructions and continue to Task 3 unchanged.

- [ ] **Step 10: Commit the gate result**

```bash
git add docs/BUILD_PLAN.md README.md
git commit -m "docs: record Phase 0 install gate result"
```

---

### Task 3: Workspace module — creation, config, path containment

**Files:**
- Create: `plugins/jobkit/scripts/workspace.py`
- Create: `tests/conftest.py`
- Create: `tests/test_workspace.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `LANES: tuple[str, ...]` = `("staged", "applied", "not_applied", "skipped", "expired")`
  - `DEFAULT_CONFIG: dict`
  - `init(root: Path) -> dict` — creates directories and `jobkit.json`, returns the config
  - `load_config(root: Path) -> dict`
  - `lane_dir(root: Path, config: dict, lane: str) -> Path`
  - `scan(root: Path, config: dict) -> dict[str, str]` — `{folder_name: lane}`
  - `safe_join(root: Path, *parts: str) -> Path` — raises `ValueError` if the result escapes `root`

- [ ] **Step 1: Create the pytest path shim**

Create `tests/conftest.py`:

```python
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "jobkit" / "scripts"
sys.path.insert(0, str(SCRIPTS))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_workspace.py`:

```python
import json
import pytest

import workspace


def test_init_creates_every_lane_directory(tmp_path):
    config = workspace.init(tmp_path)
    for lane in workspace.LANES:
        assert workspace.lane_dir(tmp_path, config, lane).is_dir()
    assert (tmp_path / "Baseline").is_dir()
    assert (tmp_path / "guides").is_dir()


def test_init_writes_config_and_is_reloadable(tmp_path):
    written = workspace.init(tmp_path)
    assert (tmp_path / "jobkit.json").exists()
    assert workspace.load_config(tmp_path) == written


def test_init_is_idempotent_and_preserves_edits(tmp_path):
    config = workspace.init(tmp_path)
    config["score_threshold"] = 8
    (tmp_path / "jobkit.json").write_text(json.dumps(config), encoding="utf-8")
    again = workspace.init(tmp_path)
    assert again["score_threshold"] == 8


def test_init_creates_starter_files(tmp_path):
    workspace.init(tmp_path)
    assert (tmp_path / "intake_site_recipes.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_init_never_overwrites_user_claude_md(tmp_path):
    workspace.init(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# My rules\nNever show me unpaid gigs.\n", encoding="utf-8")
    workspace.init(tmp_path)
    assert "Never show me unpaid gigs" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_scan_maps_folders_to_lanes(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    found = workspace.scan(tmp_path, config)
    assert found == {
        "7_Pixar_Emeryville_Modeler": "staged",
        "8_Riot_LA_ConceptArtist": "applied",
    }


def test_scan_ignores_dot_and_dunder_folders(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "__pycache__").mkdir()
    (workspace.lane_dir(tmp_path, config, "staged") / ".DS_Store_dir").mkdir()
    assert workspace.scan(tmp_path, config) == {}


def test_scan_ignores_loose_files(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "stray.md").write_text("x", encoding="utf-8")
    assert workspace.scan(tmp_path, config) == {}


def test_safe_join_allows_paths_inside_the_workspace(tmp_path):
    result = workspace.safe_join(tmp_path, "Jobs to Apply to", "7_Pixar_Emeryville_Modeler")
    assert str(result).startswith(str(tmp_path.resolve()))


def test_safe_join_refuses_to_escape_the_workspace(tmp_path):
    with pytest.raises(ValueError, match="outside the workspace"):
        workspace.safe_join(tmp_path, "..", "..", "Desktop", "secrets.txt")


def test_safe_join_refuses_an_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="outside the workspace"):
        workspace.safe_join(tmp_path, "/etc/passwd")


def test_lane_dir_rejects_an_unknown_lane(tmp_path):
    config = workspace.init(tmp_path)
    with pytest.raises(ValueError, match="unknown lane"):
        workspace.lane_dir(tmp_path, config, "nonsense")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'workspace'`

- [ ] **Step 4: Write the module**

Create `plugins/jobkit/scripts/workspace.py`:

```python
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
    _write_if_absent(root / "CLAUDE.md", STARTER_CLAUD_MD_FIX)
    return config


# Named separately so the constant above stays readable.
STARTER_CLAUD_MD_FIX = STARTER_CLAUDE_MD


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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS, 12 passed

- [ ] **Step 6: Simplify the awkward constant**

The `STARTER_CLAUD_MD_FIX` indirection above is noise. Replace the `_write_if_absent(root / "CLAUDE.md", STARTER_CLAUD_MD_FIX)` line with `_write_if_absent(root / "CLAUDE.md", STARTER_CLAUDE_MD)` and delete the `STARTER_CLAUD_MD_FIX` line entirely.

Run: `python -m pytest tests/test_workspace.py -v`
Expected: PASS, 12 passed

- [ ] **Step 7: Commit**

```bash
git add plugins/jobkit/scripts/workspace.py tests/conftest.py tests/test_workspace.py
git commit -m "feat: add workspace module with path-containment guard"
```

---

### Task 4: Ledger module — folder-keyed, atomic, honest dates

This task carries the regression guards for the two flaws found in the source workspace.

**Files:**
- Create: `plugins/jobkit/scripts/ledger.py`
- Create: `tests/test_ledger.py`

**Interfaces:**
- Consumes: `workspace.LANES`
- Produces:
  - `STATUSES: tuple[str, ...]` = `("none", "awaiting", "phone_screen", "interview_scheduled", "interviewed", "offer", "closed")`
  - `CLOSURE_REASONS: tuple[str, ...]` = `("rejected", "closed_no_response", "withdrawn")`
  - `load(path: Path) -> dict`
  - `save(path: Path, ledger: dict) -> None` — atomic
  - `sync(ledger: dict, on_disk: dict[str, str], today: str) -> tuple[dict, list[tuple[str, str, str]]]` — events are `(kind, folder, lane)` where kind is `"new" | "moved" | "missing"`
  - `set_status(ledger: dict, folder: str, status: str, today: str, closure_reason: str | None = None) -> dict`
  - `resolve(ledger: dict, fragment: str) -> list[str]`
  - `counts(ledger: dict) -> dict[str, int]`
  - `days_since(date_str: str, today: str) -> int | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger.py`:

```python
import json
import pytest

import ledger


def _staged(folder="7_Pixar_Emeryville_Modeler"):
    book, _ = ledger.sync({}, {folder: "staged"}, "2026-01-05")
    return book, folder


# --- the regression guard for the source workspace's applied_date flaw ---

def test_applied_date_survives_a_later_status_change():
    """The flaw in the source tracker: closing a job overwrote its apply date."""
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    assert book[folder]["applied_date"] == "2026-01-10"

    ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="rejected")
    assert book[folder]["applied_date"] == "2026-01-10", "apply date must not follow the rejection"


def test_set_status_never_invents_an_applied_date():
    book, folder = _staged()
    ledger.set_status(book, folder, "awaiting", "2026-01-20")
    assert "applied_date" not in book[folder]


def test_a_job_first_seen_already_applied_has_no_applied_date():
    """The move was never observed, so the date is unknown. Unknown stays unset."""
    book, _ = ledger.sync({}, {"8_Riot_LA_ConceptArtist": "applied"}, "2026-01-10")
    assert "applied_date" not in book["8_Riot_LA_ConceptArtist"]
    assert book["8_Riot_LA_ConceptArtist"]["status"] == "awaiting"


def test_applied_date_is_not_reset_by_a_later_sync():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-03-01")
    assert book[folder]["applied_date"] == "2026-01-10"


# --- closure reason is a separate field ---

def test_closing_requires_a_reason():
    book, folder = _staged()
    with pytest.raises(ValueError, match="closure_reason"):
        ledger.set_status(book, folder, "closed", "2026-02-01")


def test_closure_reason_must_be_valid():
    book, folder = _staged()
    with pytest.raises(ValueError, match="closure_reason"):
        ledger.set_status(book, folder, "closed", "2026-02-01", closure_reason="ghosted")


def test_closure_reason_is_rejected_only_for_a_real_rejection():
    book, folder = _staged()
    book, _ = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    ledger.set_status(book, folder, "closed", "2026-03-20", closure_reason="closed_no_response")
    tally = ledger.counts(book)
    assert tally["rejected"] == 0
    assert tally["closed_no_response"] == 1


def test_reason_is_refused_when_not_closing():
    book, folder = _staged()
    with pytest.raises(ValueError, match="only applies"):
        ledger.set_status(book, folder, "awaiting", "2026-01-20", closure_reason="rejected")


# --- lanes, history, missing folders ---

def test_sync_records_a_lane_move_in_history():
    book, folder = _staged()
    book, events = ledger.sync(book, {folder: "applied"}, "2026-01-10")
    assert ("moved", folder, "applied") in events
    assert any("staged -> applied" in line for line in book[folder]["history"])


def test_a_vanished_folder_is_marked_missing_not_silently_kept():
    """The source tracker kept ghosts at their last known status forever."""
    book, folder = _staged()
    book, events = ledger.sync(book, {}, "2026-02-01")
    assert book[folder]["lane"] == "missing"
    assert ("missing", folder, "missing") in events


def test_a_returning_folder_leaves_missing():
    book, folder = _staged()
    book, _ = ledger.sync(book, {}, "2026-02-01")
    book, _ = ledger.sync(book, {folder: "staged"}, "2026-02-02")
    assert book[folder]["lane"] == "staged"


def test_counts_exclude_missing_from_the_staged_tally():
    book, _ = ledger.sync({}, {"a": "staged", "b": "staged"}, "2026-01-05")
    book, _ = ledger.sync(book, {"a": "staged"}, "2026-01-06")
    assert ledger.counts(book)["staged"] == 1


def test_unknown_status_is_refused():
    book, folder = _staged()
    with pytest.raises(ValueError, match="bad status"):
        ledger.set_status(book, folder, "vibing", "2026-01-20")


def test_set_status_on_a_missing_job_raises():
    with pytest.raises(KeyError):
        ledger.set_status({}, "nope", "awaiting", "2026-01-20")


# --- disambiguation, replacing the substring workaround ---

def test_resolve_returns_every_match_for_the_caller_to_disambiguate():
    book, _ = ledger.sync(
        {}, {"7_Anduril_CostaMesa_Artist": "staged", "8_Anduril_CostaMesa_Modeler": "staged"},
        "2026-01-05",
    )
    assert ledger.resolve(book, "anduril") == [
        "7_Anduril_CostaMesa_Artist",
        "8_Anduril_CostaMesa_Modeler",
    ]


def test_resolve_returns_empty_when_nothing_matches():
    book, _ = _staged()
    assert ledger.resolve(book, "zzz") == []


# --- persistence ---

def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    book, _ = _staged()
    path = tmp_path / "job_ledger.json"
    ledger.save(path, book)
    assert json.loads(path.read_text(encoding="utf-8")) == book
    assert list(tmp_path.iterdir()) == [path]


def test_load_of_a_missing_file_returns_empty(tmp_path):
    assert ledger.load(tmp_path / "job_ledger.json") == {}


def test_load_rejects_a_non_object(tmp_path):
    path = tmp_path / "job_ledger.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        ledger.load(path)


def test_days_since():
    assert ledger.days_since("2026-01-10", "2026-02-01") == 22
    assert ledger.days_since("", "2026-02-01") is None
    assert ledger.days_since(None, "2026-02-01") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ledger'`

- [ ] **Step 3: Write the module**

Create `plugins/jobkit/scripts/ledger.py`:

```python
#!/usr/bin/env python3
"""The job ledger.

Keyed on FOLDER NAME. Never on a hash of a file that gets edited - that pattern
orphans a job's history the moment someone adds a note to it.

Two rules this module enforces mechanically:
  1. applied_date is set ONLY when a folder is observed moving into the applied
     lane. It is never backfilled from a later status event and never defaulted
     to today. Unknown stays unset.
  2. A closed job carries a closure_reason. "They rejected me" and "I gave up
     after 82 days" are different facts and one field cannot hold both.
"""
import json
import os
from datetime import date
from pathlib import Path

STATUSES = (
    "none",
    "awaiting",
    "phone_screen",
    "interview_scheduled",
    "interviewed",
    "offer",
    "closed",
)

CLOSURE_REASONS = ("rejected", "closed_no_response", "withdrawn")


def load(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def save(path, book: dict) -> None:
    """Write atomically. A truncated ledger is unrecoverable for a non-technical user."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(book, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def sync(book: dict, on_disk: dict, today: str) -> tuple[dict, list]:
    """Reconcile the ledger against what is actually on disk.

    on_disk maps folder name -> lane. Returns (book, events).
    """
    events = []

    for folder, lane in on_disk.items():
        entry = book.get(folder)
        if entry is None:
            entry = {
                "lane": lane,
                "status": "none",
                "history": [f"{today}: first seen in {lane}"],
            }
            if lane == "applied":
                # We never observed the move, so the apply date is unknown.
                # Leave it unset - it must never be guessed.
                entry["status"] = "awaiting"
            book[folder] = entry
            events.append(("new", folder, lane))
            continue

        previous = entry.get("lane")
        if previous == lane:
            continue

        entry["lane"] = lane
        entry["history"].append(f"{today}: {previous} -> {lane}")
        events.append(("moved", folder, lane))

        if lane == "applied" and "applied_date" not in entry:
            # An OBSERVED move into applied is a real signal. This is the only
            # place applied_date is ever set automatically.
            entry["applied_date"] = today
            if entry.get("status") in ("none", None):
                entry["status"] = "awaiting"

    for folder, entry in book.items():
        if folder in on_disk:
            continue
        if entry.get("lane") == "missing":
            continue
        entry["history"].append(f"{today}: folder not found -> missing")
        entry["lane"] = "missing"
        events.append(("missing", folder, "missing"))

    return book, events


def set_status(book: dict, folder: str, status: str, today: str, closure_reason=None) -> dict:
    if folder not in book:
        raise KeyError(folder)
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}; valid: {', '.join(STATUSES)}")
    if status == "closed":
        if closure_reason not in CLOSURE_REASONS:
            raise ValueError(
                "closing a job needs a closure_reason: " + ", ".join(CLOSURE_REASONS)
            )
    elif closure_reason is not None:
        raise ValueError("closure_reason only applies when status is 'closed'")

    entry = book[folder]
    previous = entry.get("status", "none")
    entry["status"] = status
    if closure_reason is not None:
        entry["closure_reason"] = closure_reason

    label = f"{status} ({closure_reason})" if closure_reason else status
    entry.setdefault("history", []).append(f"{today}: {previous} -> {label}")
    return entry


def resolve(book: dict, fragment: str) -> list:
    """Every folder matching fragment. The caller disambiguates - never guess."""
    needle = fragment.lower()
    return sorted(name for name in book if needle in name.lower())


def counts(book: dict) -> dict:
    tally = {
        "staged": 0,
        "applied": 0,
        "not_applied": 0,
        "skipped": 0,
        "expired": 0,
        "missing": 0,
        "in_flight": 0,
        "interviews": 0,
        "offers": 0,
        "rejected": 0,
        "closed_no_response": 0,
        "withdrawn": 0,
    }
    for entry in book.values():
        lane = entry.get("lane", "missing")
        if lane in tally:
            tally[lane] += 1
        if lane != "applied":
            continue
        status = entry.get("status", "none")
        if status == "closed":
            reason = entry.get("closure_reason")
            if reason in tally:
                tally[reason] += 1
        else:
            tally["in_flight"] += 1
            if status in ("interview_scheduled", "interviewed"):
                tally["interviews"] += 1
            elif status == "offer":
                tally["offers"] += 1
    return tally


def days_since(date_str, today: str):
    if not date_str:
        return None
    return (date.fromisoformat(today) - date.fromisoformat(date_str)).days
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_ledger.py -v`
Expected: PASS, 19 passed

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: PASS, all green

- [ ] **Step 6: Commit**

```bash
git add plugins/jobkit/scripts/ledger.py tests/test_ledger.py
git commit -m "feat: add folder-keyed ledger with applied_date and closure-reason guards"
```

---

### Task 5: Checks module — envelope, banned phrases, competence inflation

**Files:**
- Create: `plugins/jobkit/scripts/checks.py`
- Create: `tests/test_checks.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `INFLATION_PATTERNS: list[tuple[str, str]]`
  - `envelope(text: str, max_words: int, max_sections: int) -> list[str]`
  - `banned_phrases(text: str, banned: list[str]) -> list[str]`
  - `inflation(text: str) -> list[str]`
  - `run_all(text: str, profile: dict) -> list[str]` — every problem found, empty list means clean

- [ ] **Step 1: Write the failing test**

Create `tests/test_checks.py`:

```python
import checks


RESUME = """# Jane Q
## Summary
Modeler and texture artist.
## Experience
Made things.
## Education
Art school.
"""


def test_envelope_passes_a_document_inside_bounds():
    assert checks.envelope(RESUME, max_words=500, max_sections=6) == []


def test_envelope_flags_a_document_that_is_too_long():
    long_text = "word " * 900
    problems = checks.envelope(long_text, max_words=500, max_sections=6)
    assert any("too long" in p for p in problems)


def test_envelope_flags_too_many_sections():
    text = "\n".join(f"## Section {i}\nbody\n" for i in range(12))
    problems = checks.envelope(text, max_words=5000, max_sections=6)
    assert any("sections" in p for p in problems)


def test_envelope_counts_only_h2_headings():
    text = "# Title\n## One\n### Sub\n## Two\n"
    assert checks.envelope(text, max_words=500, max_sections=2) == []


def test_banned_phrases_finds_a_hit_case_insensitively():
    hits = checks.banned_phrases("I am a proven self-starter", ["self-starter"])
    assert hits == ["self-starter"]


def test_banned_phrases_returns_empty_when_clean():
    assert checks.banned_phrases("Modeler and texture artist.", ["self-starter"]) == []


def test_inflation_flags_years_of_your_life():
    hits = checks.inflation("which builds on your years of environment art")
    assert hits


def test_inflation_flags_extensive_experience():
    assert checks.inflation("Extensive experience in Houdini")


def test_inflation_flags_expert_claims():
    assert checks.inflation("Expert in Substance Painter")


def test_inflation_allows_a_plain_comparison():
    """Comparisons are fine. It is the comparison-becomes-a-claim shape that lies."""
    assert checks.inflation("Similar to the environment work in my Pixar piece") == []


def test_inflation_allows_hedged_framing():
    assert checks.inflation("Familiar with Houdini") == []


def test_run_all_collects_every_category():
    profile = {
        "banned_phrases": ["self-starter"],
        "envelope": {"max_words": 20, "max_sections": 2},
    }
    text = "## A\n## B\n## C\n" + "Expert in everything, a real self-starter. " * 10
    problems = checks.run_all(text, profile)
    assert any("too long" in p for p in problems)
    assert any("sections" in p for p in problems)
    assert any("self-starter" in p for p in problems)
    assert any("inflation" in p for p in problems)


def test_run_all_is_empty_for_a_clean_document():
    profile = {"banned_phrases": ["self-starter"], "envelope": {"max_words": 500, "max_sections": 6}}
    assert checks.run_all(RESUME, profile) == []


def test_run_all_uses_defaults_when_profile_is_bare():
    assert checks.run_all(RESUME, {}) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_checks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'checks'`

- [ ] **Step 3: Write the module**

Create `plugins/jobkit/scripts/checks.py`:

```python
#!/usr/bin/env python3
"""Build-time guards for generated documents.

Text in, list of problems out. An empty list means clean.

The inflation check exists because the dangerous sentence is usually surrounded
by honest ones. "Similar to the piece you made for X" is fine. "Which builds on
your years of X" invents a credential when the baseline records one project.
"""
import re

DEFAULT_MAX_WORDS = 700
DEFAULT_MAX_SECTIONS = 8

INFLATION_PATTERNS = [
    (r"\byears of (?:your|his|her|their|my)\b", "a comparison turned into a claim about time"),
    (r"\bextensive experience\b", "unearned scale"),
    (r"\bdeep (?:expertise|experience|knowledge)\b", "unearned depth"),
    (r"\bexpert (?:in|at|with)\b", "unearned mastery"),
    (r"\bmastery of\b", "unearned mastery"),
    (r"\bseasoned\b", "unearned tenure"),
    (r"\bveteran\b", "unearned tenure"),
    (r"\bbuilds on your years\b", "a comparison turned into a claim about time"),
]


def envelope(text: str, max_words: int = DEFAULT_MAX_WORDS,
             max_sections: int = DEFAULT_MAX_SECTIONS) -> list:
    problems = []
    words = len(text.split())
    if words > max_words:
        problems.append(f"too long: {words} words, limit is {max_words}")
    sections = len(re.findall(r"^## (?!#)", text, flags=re.MULTILINE))
    if sections > max_sections:
        problems.append(f"too many sections: {sections}, limit is {max_sections}")
    return problems


def banned_phrases(text: str, banned: list) -> list:
    low = text.lower()
    return [phrase for phrase in banned if phrase and phrase.lower() in low]


def inflation(text: str) -> list:
    hits = []
    for pattern, why in INFLATION_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            hits.append(f"{match.group()} ({why})")
    return hits


def run_all(text: str, profile: dict) -> list:
    limits = profile.get("envelope", {})
    problems = envelope(
        text,
        max_words=limits.get("max_words", DEFAULT_MAX_WORDS),
        max_sections=limits.get("max_sections", DEFAULT_MAX_SECTIONS),
    )
    problems += [f"banned phrase: {p}" for p in banned_phrases(text, profile.get("banned_phrases", []))]
    problems += [f"inflation: {h}" for h in inflation(text)]
    return problems
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_checks.py -v`
Expected: PASS, 14 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/jobkit/scripts/checks.py tests/test_checks.py
git commit -m "feat: add envelope, banned-phrase and inflation checks"
```

---

### Task 6: Dashboard generator

**Files:**
- Create: `plugins/jobkit/scripts/dashboard.py`
- Create: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `workspace.load_config`, `workspace.scan`, `workspace.lane_dir`, `ledger.load`, `ledger.sync`, `ledger.save`, `ledger.counts`, `ledger.days_since`
- Produces:
  - `build(root: Path, today: str) -> str` — syncs the ledger, returns the HTML
  - `render(context: dict) -> str` — pure; context has keys `today`, `counts`, `vocabulary`, `staged`, `active`, `closed`, `root_uri`
  - `main(argv: list[str]) -> int` — CLI entry point, writes `CareerDashboard.html` and opens it

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard.py`:

```python
import dashboard
import workspace


def _workspace_with_two_jobs(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    return config


def test_build_emits_html_containing_both_jobs(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "Pixar" in html
    assert "Riot" in html


def test_generated_page_never_fetches(tmp_path):
    """A file:// page cannot fetch a sibling JSON file. It fails silently and
    looks like an empty dashboard. All data must be baked into the markup."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html


def test_generated_page_loads_nothing_from_the_network(tmp_path):
    """Links to postings are fine. Loading assets over the network is not -
    the page must render identically with the wifi off."""
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<script src=" not in html
    assert 'rel="stylesheet"' not in html
    assert "@import" not in html
    assert '<img src="http' not in html


def test_build_writes_the_ledger(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    dashboard.build(tmp_path, "2026-02-01")
    assert (tmp_path / "job_ledger.json").exists()


def test_job_titles_are_html_escaped(tmp_path):
    """Uses & rather than angle brackets: Windows forbids < > in filenames,
    so an angle-bracket folder name cannot even be created to test with."""
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Acme&Sons_LA_Artist").mkdir()
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "&amp;Sons" in html
    assert "Acme&Sons" not in html


def test_counts_appear_in_the_page(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert 'data-count="staged">1<' in html
    assert 'data-count="applied">1<' in html


def test_folder_name_is_parsed_into_score_company_location_role(tmp_path):
    _workspace_with_two_jobs(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "Emeryville" in html
    assert "Modeler" in html


def test_a_nonconforming_folder_name_still_renders(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "SomeOldJob").mkdir()
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "SomeOldJob" in html


def test_days_waiting_is_shown_for_an_applied_job(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    staged = workspace.lane_dir(tmp_path, config, "staged") / "8_Riot_LA_ConceptArtist"
    staged.mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    staged.rename(workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist")
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "22 days" in html


def test_rejections_and_no_response_are_reported_separately(tmp_path):
    import ledger
    config = workspace.init(tmp_path)
    for name in ("8_Riot_LA_ConceptArtist", "7_Pixar_Emeryville_Modeler"):
        (workspace.lane_dir(tmp_path, config, "applied") / name).mkdir()
    dashboard.build(tmp_path, "2026-01-10")
    book = ledger.load(tmp_path / "job_ledger.json")
    ledger.set_status(book, "8_Riot_LA_ConceptArtist", "closed", "2026-02-01", closure_reason="rejected")
    ledger.set_status(book, "7_Pixar_Emeryville_Modeler", "closed", "2026-02-01", closure_reason="closed_no_response")
    ledger.save(tmp_path / "job_ledger.json", book)
    html = dashboard.build(tmp_path, "2026-02-02")
    assert 'data-count="rejected">1<' in html
    assert 'data-count="closed_no_response">1<' in html


def test_empty_workspace_renders_without_crashing(tmp_path):
    workspace.init(tmp_path)
    html = dashboard.build(tmp_path, "2026-02-01")
    assert "<html" in html or "<!doctype" in html.lower()
    assert 'data-count="staged">0<' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: Write the module**

Create `plugins/jobkit/scripts/dashboard.py`:

```python
#!/usr/bin/env python3
"""Generate CareerDashboard.html - one self-contained file, no server.

THE CONSTRAINT THAT SHAPES THIS FILE: a page opened from file:// cannot fetch()
a sibling JSON file. Browsers treat each local file as its own origin and CORS
blocks it, and it fails SILENTLY - you get a blank page, not an error. So every
value is written into the markup here, at generation time. The JavaScript in the
page only filters and expands data that is already present.

Usage:
  python dashboard.py <workspace-path> [--no-open]
"""
import html
import re
import sys
import webbrowser
from datetime import date
from pathlib import Path
from urllib.parse import quote

import ledger
import workspace

FOLDER_RE = re.compile(r"^(\d+)_([^_]+)_([^_]+)_(.+)$")


def parse_folder(name: str) -> dict:
    """Split <score>_<Company>_<Location>_<Role>. Degrade gracefully."""
    match = FOLDER_RE.match(name)
    if not match:
        return {"score": None, "company": name, "location": "", "role": ""}
    score, company, location, role = match.groups()
    return {
        "score": int(score),
        "company": company,
        "location": _humanize(location),
        "role": _humanize(role),
    }


def _humanize(token: str) -> str:
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", token)
    return spaced.replace("-", " ").strip()


def _posting_url(root: Path, config: dict, lane: str, folder: str) -> str:
    """Line 1 of original_job_posting.md is the source URL, by convention."""
    path = workspace.lane_dir(root, config, lane) / folder / "original_job_posting.md"
    if not path.exists():
        return ""
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError, UnicodeDecodeError):
        return ""
    return first if first.startswith(("http://", "https://")) else ""


def _folder_uri(root: Path, config: dict, lane: str, folder: str) -> str:
    path = workspace.lane_dir(root, config, lane) / folder
    return "file:///" + quote(str(path).replace("\\", "/").lstrip("/"))


def build(root, today: str = None) -> str:
    root = Path(root)
    today = today or date.today().isoformat()
    config = workspace.load_config(root)

    on_disk = workspace.scan(root, config)
    book = ledger.load(root / "job_ledger.json")
    book, _ = ledger.sync(book, on_disk, today)

    # Fill in facts the folder name carries, without ever overwriting the ledger.
    for folder, lane in on_disk.items():
        entry = book[folder]
        parsed = parse_folder(folder)
        for key in ("score", "company", "location", "role"):
            entry.setdefault(key, parsed[key])
        if not entry.get("posting_url"):
            found = _posting_url(root, config, lane, folder)
            if found:
                entry["posting_url"] = found

    ledger.save(root / "job_ledger.json", book)

    def card(folder: str, entry: dict) -> dict:
        lane = entry.get("lane", "missing")
        waited = ledger.days_since(entry.get("applied_date"), today)
        return {
            "folder": folder,
            "company": entry.get("company") or folder,
            "role": entry.get("role") or "",
            "location": entry.get("location") or "",
            "score": entry.get("score"),
            "status": entry.get("status", "none"),
            "closure_reason": entry.get("closure_reason", ""),
            "applied_date": entry.get("applied_date", ""),
            "days_waiting": waited,
            "stale": waited is not None and waited >= config.get("stale_after_days", 21),
            "posting_url": entry.get("posting_url", ""),
            "folder_uri": _folder_uri(root, config, lane, folder) if lane in config["lanes"] else "",
        }

    cards = {folder: card(folder, entry) for folder, entry in book.items()}

    staged = [cards[f] for f, e in book.items() if e.get("lane") == "staged"]
    applied = [(f, e) for f, e in book.items() if e.get("lane") == "applied"]
    active = [cards[f] for f, e in applied if e.get("status") != "closed"]
    closed = [cards[f] for f, e in applied if e.get("status") == "closed"]

    staged.sort(key=lambda c: (-(c["score"] or 0), c["company"]))
    active.sort(key=lambda c: (c["days_waiting"] is None, -(c["days_waiting"] or 0)))
    closed.sort(key=lambda c: c["company"])

    return render({
        "today": today,
        "counts": ledger.counts(book),
        "vocabulary": config.get("vocabulary", {}),
        "staged": staged,
        "active": active,
        "closed": closed,
    })


def render(context: dict) -> str:
    vocab = context["vocabulary"]
    counts = context["counts"]

    def label(key: str, fallback: str) -> str:
        return html.escape(vocab.get(key, fallback))

    tiles = [
        ("staged", label("staged", "Ready to apply")),
        ("applied", label("applied", "Applied")),
        ("in_flight", label("in_flight", "Waiting to hear")),
        ("interviews", label("interviews", "Interviews")),
        ("rejected", label("rejected", "Not selected")),
        ("closed_no_response", label("closed_no_response", "No response")),
    ]
    tile_html = "\n".join(
        f'<div class="tile"><span class="n" data-count="{key}">{counts.get(key, 0)}</span>'
        f'<span class="l">{text}</span></div>'
        for key, text in tiles
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Dashboard</title>
<style>
:root {{ --bg:#0e1116; --card:#171b22; --line:#252b35; --ink:#e6e9ef;
        --dim:#8b95a5; --accent:#6ea8fe; --warn:#e0b341; --bad:#e06c75; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
header {{ padding:28px 32px 8px; }}
h1 {{ margin:0; font-size:22px; letter-spacing:-.01em; }}
.sub {{ color:var(--dim); font-size:13px; margin-top:4px; }}
.tiles {{ display:flex; flex-wrap:wrap; gap:12px; padding:20px 32px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
         padding:14px 18px; min-width:118px; }}
.tile .n {{ display:block; font-size:26px; font-weight:600; }}
.tile .l {{ display:block; color:var(--dim); font-size:12px; margin-top:2px; }}
section {{ padding:8px 32px 28px; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
      color:var(--dim); border-bottom:1px solid var(--line); padding-bottom:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; }}
.job {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.job h3 {{ margin:0 0 2px; font-size:15px; }}
.job .role {{ color:var(--dim); font-size:13px; }}
.job .meta {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.chip {{ font-size:11px; border:1px solid var(--line); border-radius:999px;
         padding:2px 8px; color:var(--dim); text-decoration:none; }}
.chip:hover {{ color:var(--ink); border-color:var(--accent); }}
.score {{ border-color:var(--accent); color:var(--accent); }}
.stale {{ border-color:var(--warn); color:var(--warn); }}
.rejected {{ border-color:var(--bad); color:var(--bad); }}
.empty {{ color:var(--dim); font-size:13px; padding:8px 0; }}
#q {{ background:var(--card); border:1px solid var(--line); color:var(--ink);
      border-radius:8px; padding:8px 12px; width:260px; margin:0 32px; }}
</style></head><body>
<header>
  <h1>Job Dashboard</h1>
  <div class="sub">Updated {html.escape(context['today'])}</div>
</header>
<div class="tiles">{tile_html}</div>
<input id="q" type="search" placeholder="Filter by company or role" aria-label="Filter jobs">
{_section(label('staged', 'Ready to apply'), context['staged'], 'staged')}
{_section(label('in_flight', 'Waiting to hear'), context['active'], 'active')}
{_section('Closed', context['closed'], 'closed')}
<!-- Library section reserved. Adding it later must not be a redesign. -->
<script>
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const needle = q.value.toLowerCase();
  document.querySelectorAll('.job').forEach(el => {{
    el.style.display = el.dataset.search.includes(needle) ? '' : 'none';
  }});
}});
</script>
</body></html>
"""


def _section(title: str, cards: list, key: str) -> str:
    if not cards:
        body = '<div class="empty">Nothing here yet.</div>'
    else:
        body = '<div class="grid">' + "".join(_card(c) for c in cards) + "</div>"
    return f'<section data-lane="{key}"><h2>{title} ({len(cards)})</h2>{body}</section>'


def _card(c: dict) -> str:
    company = html.escape(str(c["company"]))
    role = html.escape(str(c["role"]))
    location = html.escape(str(c["location"]))
    search = html.escape(f"{c['company']} {c['role']} {c['location']}".lower(), quote=True)

    chips = []
    if c["score"] is not None:
        chips.append(f'<span class="chip score">fit {c["score"]}</span>')
    if location:
        chips.append(f'<span class="chip">{location}</span>')
    if c["days_waiting"] is not None:
        cls = "chip stale" if c["stale"] else "chip"
        chips.append(f'<span class="{cls}">{c["days_waiting"]} days</span>')
    if c["closure_reason"]:
        cls = "chip rejected" if c["closure_reason"] == "rejected" else "chip"
        chips.append(f'<span class="{cls}">{html.escape(c["closure_reason"].replace("_", " "))}</span>')
    if c["folder_uri"]:
        chips.append(f'<a class="chip" href="{html.escape(c["folder_uri"], quote=True)}">open folder</a>')
    if c["posting_url"]:
        chips.append(f'<a class="chip" href="{html.escape(c["posting_url"], quote=True)}">posting</a>')

    return (
        f'<article class="job" data-search="{search}">'
        f"<h3>{company}</h3><div class=\"role\">{role}</div>"
        f'<div class="meta">{"".join(chips)}</div></article>'
    )


def main(argv: list) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python dashboard.py <workspace-path> [--no-open]")
        return 1
    root = Path(args[0]).expanduser().resolve()
    out = root / "CareerDashboard.html"
    out.write_text(build(root), encoding="utf-8")
    print(f"Dashboard -> {out}")
    if "--no-open" not in argv:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Look at it with your own eyes**

```bash
python -c "import sys; sys.path.insert(0,'plugins/jobkit/scripts'); import workspace; workspace.init('/tmp/jk')"
mkdir -p "/tmp/jk/Jobs to Apply to/9_Pixar_Emeryville_EnvironmentArtist"
mkdir -p "/tmp/jk/Jobs I Have Applied To/7_Riot_LosAngeles_ConceptArtist"
python plugins/jobkit/scripts/dashboard.py /tmp/jk
```

Expected: the page opens in a browser and looks deliberate. If it looks like an unstyled document, the CSS did not survive — fix before continuing. This is the artifact Benny shows people.

- [ ] **Step 6: Commit**

```bash
git add plugins/jobkit/scripts/dashboard.py tests/test_dashboard.py
git commit -m "feat: add self-contained dashboard generator"
```

---

### Task 7: The setup skill

**Files:**
- Create: `plugins/jobkit/skills/jobkit-setup/SKILL.md`
- Create: `plugins/jobkit/commands/jobkit-setup.md`
- Create: `plugins/jobkit/templates/profile.example.json`

**Interfaces:**
- Consumes: `workspace.init`, `dashboard.main`
- Produces: a workspace containing `jobkit.json`, `profile.json`, `Baseline/`, and a first `CareerDashboard.html`

- [ ] **Step 1: Create the profile template**

Create `plugins/jobkit/templates/profile.example.json`:

```json
{
  "name": "",
  "email": "you@example.com",
  "phone": "",
  "portfolio_urls": [],
  "home_location": "",
  "relocation": "",
  "remote_preference": "",
  "target_roles": [],
  "must_haves": [],
  "deal_breakers": [],
  "banned_phrases": [],
  "envelope": {
    "max_words": 700,
    "max_sections": 8
  },
  "scoring": {
    "threshold": 6,
    "rubric": []
  }
}
```

- [ ] **Step 2: Write the setup skill**

Create `plugins/jobkit/skills/jobkit-setup/SKILL.md`:

```markdown
---
name: jobkit-setup
description: Use when the user wants to set up, install, initialize, or start a JobKit job-search workspace, says "set up my job search", names a folder to use for job hunting, or when any other JobKit skill finds that no jobkit.json exists yet.
---

# Setting up a JobKit workspace

This is the most important skill in the product. It produces the data every other
skill runs on. Take it slowly and get it right.

Assume the user is not technical. No jargon. One question at a time.

## Rules for the whole interview

- **One question per message.** A wall of questions makes people bail.
- **Never invent an answer.** "I don't know" is a valid answer and it stays blank.
  A blank field is honest; a plausible-looking guess is a lie you will repeat on
  every resume from here on.
- **Resumable.** Save after each answer. If the session ends mid-interview, the
  next one picks up from the first empty field.
- **You are not judging them.** No feedback on their answers, no encouragement,
  no "great!". A colleague taking notes.

## Step 1 — the workspace path

Ask where they want it. Suggest `~/JobDashboard`. Confirm the full path back to
them before creating anything.

Then run:

```bash
python -c "import sys; sys.path.insert(0, r'${CLAUDE_PLUGIN_ROOT}/scripts'); import workspace; workspace.init(r'<path>')"
```

Tell them what you created, in plain words: a folder for jobs they're going to
apply to, one for jobs they've applied to, one for the ones that didn't work out,
and a place for their resume.

**Store the path.** Every later command needs it. Nothing is ever written outside it.

## Step 2 — the environment check

Check and REPORT. Never hard-fail; a tool that refuses to start gets uninstalled.

```bash
python3 --version
```

Report what is present and what is missing, with the exact command to fix each.
`python-docx` and `reportlab` are only needed for Word and PDF output — say that
plainly and say text files work without them.

Check whether a browser automation tool is available. If not, say what still works
without it: pasted text and structured job-board data, which is most of the value.

## Step 3 — the interview

Write answers into `profile.json` in the workspace, using
`${CLAUDE_PLUGIN_ROOT}/templates/profile.example.json` as the shape. Save after
each answer.

Ask in this order, one at a time:

1. Name, email, phone. (Email and phone go on the resume — confirm they want them there.)
2. Where they live, and whether they will relocate. Ask about remote separately.
3. What kind of work they want. Let them answer in their own words, then read
   back the job titles you would search for and let them correct you.
4. Links to their portfolio or work samples. **Links only. JobKit never touches
   the files themselves.**
5. What has to be true for a job to be worth applying to. Then what makes one an
   instant no. These become the scoring rubric.
6. Anything they never want written on their behalf — words, phrases, claims.
   These become `banned_phrases`.

## Step 4 — the baseline

`Baseline/` is the source of truth. **Every claim in every generated document must
trace back to something in here.** Nothing else is ever invented.

Two paths:

- **They have a resume.** Ask them to save it into `Baseline/` and tell you the
  filename. Read it. Read back what you found, and ask what is missing or wrong.
- **They do not.** Build one together. Walk through their history one role at a
  time. For each: what they did, what was actually theirs, what tools, what
  changed because of them. Write it to `Baseline/baseline_resume.txt`.

⚠️ **The single most dangerous field is "what part was yours."** If they worked on
backgrounds, the baseline says backgrounds. No document JobKit ever writes may
imply they did the whole piece. Ask about it explicitly for every collaborative
project, and write the answer down verbatim.

## Step 5 — first dashboard

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>"
```

It will open in their browser. Tell them to bookmark it, and tell them it is a
plain file on their computer — no internet, no login, no server. It updates itself
every time they add or change a job.

## Step 6 — tell them what to do next

Exactly one instruction: **paste a job link.** Nothing else. They will discover
the rest by asking, and `/jobkit-help` lists it.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
```

- [ ] **Step 3: Create the command wrapper**

Create `plugins/jobkit/commands/jobkit-setup.md`:

```markdown
---
description: Set up a new JobKit job-search workspace
---

Invoke the `jobkit-setup` skill and walk the user through creating their workspace.
```

- [ ] **Step 4: Test on a genuinely empty directory**

In Claude Code with the plugin installed, run `/jobkit-setup` and point it at a brand new empty folder. Complete the interview with throwaway answers.

Verify by hand:
- `jobkit.json` exists with all five lanes
- `profile.json` exists and contains your throwaway answers
- All five lane directories plus `Baseline/` and `guides/` exist
- `CLAUDE.md` and `intake_site_recipes.md` exist
- `CareerDashboard.html` opens by double-click and shows zeros
- **Nothing was written outside the folder you named**

- [ ] **Step 5: Commit**

```bash
git add plugins/jobkit/skills/jobkit-setup plugins/jobkit/commands/jobkit-setup.md plugins/jobkit/templates/profile.example.json
git commit -m "feat: add jobkit-setup onboarding skill"
```

---

### Task 8: The intake skill

**Files:**
- Create: `plugins/jobkit/skills/job-intake/SKILL.md`
- Create: `plugins/jobkit/commands/intake.md`

**Interfaces:**
- Consumes: `workspace.load_config`, `workspace.lane_dir`, `dashboard.main`, `profile.json` scoring rubric
- Produces: a job folder named `<score>_<Company>_<Location>_<Role>` containing `original_job_posting.md` (source URL on line 1) and `note.md`

- [ ] **Step 1: Write the intake skill**

Create `plugins/jobkit/skills/job-intake/SKILL.md`:

```markdown
---
name: job-intake
description: Use when the user pastes a job posting URL or the text of a job posting, asks to add/ingest/track a job, says "here's a job", or shares a link to a careers page or job board listing. Also use when they ask to score or rate a job for fit.
---

# Taking in a job

Runs fifty times over a search. Make it fast and make it honest.

If there is no `jobkit.json` in the workspace, run `jobkit-setup` first.

## 1. Get the posting

Three tiers. Try in order. **Say out loud which one you used** — the user needs to
know how much to trust the result.

**Tier 1 — pasted text.** Always works, zero dependencies. If they pasted the body,
use it and skip to step 2.

**Tier 2 — public ATS JSON.** Check `intake_site_recipes.md` first. The documented
endpoints are in there for Greenhouse, Lever, Ashby, Workday and ADP.

🔑 **Pull the employer's WHOLE requisition list, not just the target job.** Most of
these endpoints return every open req in one call, and the sibling reqs routinely
state what the target omits. A blank location field is ambiguous on its own; a blank
field sitting next to five populated ones is a decision. Costs one extra request.

⚠️ **A page that renders as a JavaScript shell is an EXTRACTION failure, never a
"this job is dead" verdict.** ADP returns a browser-compatibility notice while its
JSON API returns every open req. Report "could not read the page," and never let
this move a job to the expired lane.

**Tier 3 — browser.** Only if a browser automation tool is available. Follow the
recipe for that site if one exists.

**Source tiering when sources disagree:** the employer's own ATS is truth. A board
listing is a copy that may be stale, re-titled, or mis-attributed. The ATS wins.
When the board is silent, ask the ATS before asking the user.

**On a login or captcha wall: stop and say so in plain words.** Which site, what it
needs from them, and that you will wait. **Never return a wall or a partial page as
if it were the posting.** Silent partial success is the failure mode that poisons
the whole record.

## 2. Flag an intermediary IN THE SAME BREATH

If the poster is not the employer, say so immediately — never below the fold, never
after the good news. An agency, staffing firm, aggregator or reposter distorts
everything: salary in both directions, mis-attributed employer, dead reqs left up,
unnamed end client.

For creative work the same tell wears different clothes: content mills, "for
exposure" postings, contests dressed as jobs, agencies that will not name the studio,
and rights-grab terms in the posting. Say which one you think it is and why.

## 3. Score it

Score 1–10 against the rubric in `profile.json`. Show your reasoning in one or two
lines — not a table, not an essay.

- **At or above the threshold** (default 6): build the folder, step 4.
- **Below it:** create `Skipped/0_<Company>_<Role>_SKIPPED/skipped.md` recording the
  posting URL, the score, and **the specific disqualifying reason.** Never drop a job
  silently. The skip log is how a search gets smarter about what to stop chasing.

## 4. Create the folder

In the staged lane, named `<score>_<Company>_<Location>_<Role>`. No spaces, no
punctuation beyond the underscores. Location is a city or `Remote`.

Two files:

**`original_job_posting.md`** — the source URL on **line 1, by itself**, then the
verbatim posting body. Line 1 is what every downstream link depends on. If there is
genuinely no URL, line 1 reads `Applied via <source> - URL not captured` and you say
so out loud.

**`note.md`** — your read: fit, gaps against the baseline, what to lead with, and
anything the posting leaves unclear.

## 5. Record what you learned

Append to `intake_site_recipes.md`: the site, what worked, the endpoint or selector,
any wall you hit, and today's date. If a recipe was already there and failed, **mark
it stale with the date and what broke** — do not delete it — then record what you
fell back to.

## 6. Refresh the dashboard

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>" --no-open
```

Always. A dashboard that lags behind the folders is worse than no dashboard, because
it gets trusted.

## 7. Report

Short. Tier used, score with a one-line reason, intermediary if any, folder created.
No enthusiasm — a posting is not a callback.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
```

- [ ] **Step 2: Create the command wrapper**

Create `plugins/jobkit/commands/intake.md`:

```markdown
---
description: Take in a job posting from a link or pasted text
---

Invoke the `job-intake` skill with whatever the user provided.
```

- [ ] **Step 3: Test with a real posting**

Find a live Greenhouse or Lever posting for a graphics or design role. Paste the URL into a Claude session with the plugin installed.

Verify:
- The tier used was announced
- A folder appeared in the staged lane with the right name shape
- `original_job_posting.md` line 1 is the URL
- `intake_site_recipes.md` gained an entry with today's date
- `CareerDashboard.html` shows the new card
- The card's "open folder" link opens the folder

Then test the failure path: paste a LinkedIn URL, which will hit a wall.
Expected: it says which site, what it needs, and waits. **It must not fabricate a posting or file an empty folder.**

- [ ] **Step 4: Commit**

```bash
git add plugins/jobkit/skills/job-intake plugins/jobkit/commands/intake.md
git commit -m "feat: add job-intake skill with tiered extraction"
```

---

### Task 9: The build skill

**Files:**
- Create: `plugins/jobkit/skills/build-application/SKILL.md`
- Create: `plugins/jobkit/commands/build.md`
- Create: `plugins/jobkit/scripts/check_document.py`

**Interfaces:**
- Consumes: `checks.run_all`, `profile.json`, `Baseline/`
- Produces: `check_document.py <path-to-txt> <path-to-profile.json>` exiting 0 when clean and 1 with a problem list otherwise; a tailored `.txt` resume in the job folder

- [ ] **Step 1: Write the CLI wrapper for the checks**

Create `plugins/jobkit/scripts/check_document.py`:

```python
#!/usr/bin/env python3
"""Refuse a generated document that breaks the user's own rules.

Usage:
  python check_document.py <document.txt> <profile.json>

Exit 0 = clean. Exit 1 = problems listed on stdout.
"""
import json
import sys
from pathlib import Path

import checks


def main(argv: list) -> int:
    if len(argv) < 2:
        print("Usage: python check_document.py <document.txt> <profile.json>")
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
```

- [ ] **Step 2: Test the wrapper end to end**

```bash
mkdir -p /tmp/jkdoc
printf 'Expert in everything.\n' > /tmp/jkdoc/resume.txt
printf '{"banned_phrases":[],"envelope":{"max_words":500,"max_sections":8}}' > /tmp/jkdoc/profile.json
python plugins/jobkit/scripts/check_document.py /tmp/jkdoc/resume.txt /tmp/jkdoc/profile.json
echo "exit=$?"
```

Expected: `REFUSED`, one inflation problem listed, `exit=1`.

```bash
printf 'Familiar with Houdini and Maya.\n' > /tmp/jkdoc/resume.txt
python plugins/jobkit/scripts/check_document.py /tmp/jkdoc/resume.txt /tmp/jkdoc/profile.json
echo "exit=$?"
```

Expected: `resume.txt: clean`, `exit=0`.

- [ ] **Step 3: Write the build skill**

Create `plugins/jobkit/skills/build-application/SKILL.md`:

```markdown
---
name: build-application
description: Use when the user asks to build, write, tailor, draft, or prepare an application, resume, or cover letter for a specific job already in the workspace. Also use when they say "build the X one" or ask what to send to a company they have taken in.
---

# Building an application

## Read first, in this order

1. `profile.json` — who they are, their rules, their banned phrases
2. `Baseline/` — **the only source of truth for any claim**
3. The job folder's `original_job_posting.md` and `note.md`
4. The workspace `CLAUDE.md`

## The one rule everything else serves

**Every claim traces to the baseline.** No invented metrics, no invented tools, no
rounding a number up because it reads better, no skill they did not list. If the
posting wants something the baseline does not have, the resume does not claim it —
you say so to the user instead, as a gap.

A fabricated line survives right up until someone asks about it in a room.

## Write the resume

Tailored `.txt` in the job folder, named
`Resume_<Company>_<Role>.txt`. Text is the source of truth; Word and PDF are
generated from it later.

Select and order what the baseline already contains to match what the posting asks
for. That is the entire job: selection and ordering, never invention.

## Framing defaults DOWN

The dangerous sentence is always surrounded by honest ones, which is exactly why it
gets through.

- Thin in the baseline → "familiar with". **Never** "extensive experience in".
- One project → "built a", never "years of".
- A comparison is fine. A comparison that becomes a claim is a fabrication.
  - Fine: "Similar to the environment work in my Redwood piece."
  - Fabrication: "Which builds on your years of environment art."

⚠️ **For creative work this binds hardest to role attribution.** If the baseline says
they did backgrounds, no sentence may imply they did the whole piece. If it says they
were one of six, no sentence may read as though they led it. When the baseline is
vague about what part was theirs, **ask them** — do not choose the flattering reading.

## Cover letter

**Off by default.** Write one only when the application requires it. Most are never
read, and skipping it keeps the build fast.

## Run the checks before you show them anything

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/check_document.py" "<job-folder>/Resume_<Company>_<Role>.txt" "<workspace>/profile.json"
```

If it exits nonzero, **fix the document and run it again.** Do not show the user a
draft that failed its own checks, and do not talk them out of a check. If a check
seems wrong, say so and let them decide.

## Refresh the dashboard

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>" --no-open
```

## Then say the quiet part

The draft is theirs to defend. Tell them plainly: read it before it goes anywhere,
and if there is a line they could not talk about for two minutes in a room, cut it.
Something you helped write is not something they can defend live, and that gap is
where interviews are lost.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
```

- [ ] **Step 4: Create the command wrapper**

Create `plugins/jobkit/commands/build.md`:

```markdown
---
description: Build a tailored application for a job in the workspace
---

Invoke the `build-application` skill for the job the user names.
```

- [ ] **Step 5: Test against the real job from Task 8**

Ask Claude to build the application for the job you took in. Verify:
- The resume is `.txt` in the job folder
- Every claim in it appears in your `Baseline/` file
- `check_document.py` was actually run and passed
- The dashboard refreshed

Then deliberately break it: add `"self-starter"` to `banned_phrases` in `profile.json`, ask for a rebuild, and confirm the check catches it if it appears.

- [ ] **Step 6: Commit**

```bash
git add plugins/jobkit/skills/build-application plugins/jobkit/commands/build.md plugins/jobkit/scripts/check_document.py
git commit -m "feat: add build-application skill with document checks"
```

---

### Task 10: End-to-end verification on an empty directory

The most likely bug in a tool like this is assuming a file that only exists because an earlier run made it.

**Files:**
- Create: `tests/test_end_to_end.py`
- Modify: `docs/BUILD_PLAN.md`

**Interfaces:**
- Consumes: every module built above
- Produces: a passing full-suite run and a recorded manual walkthrough

- [ ] **Step 1: Write the end-to-end test**

Create `tests/test_end_to_end.py`:

```python
"""The full path a first-time user takes, against a directory that did not exist."""
import ledger
import workspace
import dashboard


def test_empty_directory_to_dashboard(tmp_path):
    root = tmp_path / "JobDashboard"
    assert not root.exists()

    config = workspace.init(root)

    # Day 1: two jobs taken in.
    staged = workspace.lane_dir(root, config, "staged")
    (staged / "9_Pixar_Emeryville_EnvironmentArtist").mkdir()
    (staged / "7_Riot_LosAngeles_ConceptArtist").mkdir()
    (staged / "9_Pixar_Emeryville_EnvironmentArtist" / "original_job_posting.md").write_text(
        "https://boards.greenhouse.io/example/jobs/1\n\nWe need an environment artist.\n",
        encoding="utf-8",
    )

    html = dashboard.build(root, "2026-02-01")
    assert 'data-count="staged">2<' in html
    assert "https://boards.greenhouse.io/example/jobs/1" in html

    # Day 10: applied to one of them.
    (staged / "7_Riot_LosAngeles_ConceptArtist").rename(
        workspace.lane_dir(root, config, "applied") / "7_Riot_LosAngeles_ConceptArtist"
    )
    dashboard.build(root, "2026-02-10")

    book = ledger.load(root / "job_ledger.json")
    assert book["7_Riot_LosAngeles_ConceptArtist"]["applied_date"] == "2026-02-10"

    # Day 40: rejected. The apply date must not move.
    ledger.set_status(book, "7_Riot_LosAngeles_ConceptArtist", "closed",
                      "2026-03-12", closure_reason="rejected")
    ledger.save(root / "job_ledger.json", book)

    html = dashboard.build(root, "2026-03-12")
    book = ledger.load(root / "job_ledger.json")
    assert book["7_Riot_LosAngeles_ConceptArtist"]["applied_date"] == "2026-02-10"
    assert 'data-count="rejected">1<' in html
    assert 'data-count="staged">1<' in html

    # Nothing was written outside the workspace.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["JobDashboard"]


def test_a_silence_closure_is_not_counted_as_a_rejection(tmp_path):
    root = tmp_path / "JobDashboard"
    config = workspace.init(root)
    (workspace.lane_dir(root, config, "applied") / "8_Acme_Remote_Illustrator").mkdir()
    dashboard.build(root, "2026-01-01")

    book = ledger.load(root / "job_ledger.json")
    ledger.set_status(book, "8_Acme_Remote_Illustrator", "closed",
                      "2026-04-01", closure_reason="closed_no_response")
    ledger.save(root / "job_ledger.json", book)

    html = dashboard.build(root, "2026-04-01")
    assert 'data-count="rejected">0<' in html
    assert 'data-count="closed_no_response">1<' in html
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: PASS, 2 passed

- [ ] **Step 3: Run the whole suite**

Run: `python -m pytest tests/ -v`
Expected: all green. Fix anything red before continuing.

- [ ] **Step 4: Do the manual walkthrough as Benny**

In Claude Desktop's Code tab, with the plugin installed, and pointing at a folder that does not exist yet:

1. "Set up my job search in ~/BennyTest"
2. Answer the interview as a graphics artist would
3. Paste a real posting URL for an art or design role
4. "Build the application for that one"
5. Open `CareerDashboard.html` by double-clicking it in Finder
6. Click a card's "open folder" link

**Done when:** the dashboard opens with no server running, the card is there, the link opens the folder, and the materials inside are real.

Write down anything that felt confusing. That list is the input to the Session 2 plan.

- [ ] **Step 5: Run the guard and push**

```bash
python tools/no_personal_data.py
```

Expected: `no_personal_data: clean`. **If it reports anything, stop and fix it before pushing.**

- [ ] **Step 6: Record the result and commit**

Update `docs/BUILD_PLAN.md`: tick the v0 checkboxes that are now genuinely done, and add a short "what felt confusing" list from Step 4.

```bash
git add tests/test_end_to_end.py docs/BUILD_PLAN.md
git commit -m "test: add end-to-end walkthrough on an empty directory"
git push
```

---

## What this plan does NOT build

Deliberately deferred to the Session 2 plan (durability and the human layer):

- `track-application` — status updates from pasted emails, interview cards
- `session-briefing` — the start-of-session "here's where you stand" summary
- `housekeeping` — the end-of-session tidy-up prompt
- `freshness.py` — checking whether postings are still live, with a control test
- The sent-immutability hook

And to the Session 3 plan (documents and library):

- `generate.py` — docx and pdf output
- `make-guide` — the HTML study library
- Reading stats

Until Session 2 ships, a user can take in jobs, build applications, and move folders by hand; the dashboard picks up the moves on the next run. That is a real, usable slice.
