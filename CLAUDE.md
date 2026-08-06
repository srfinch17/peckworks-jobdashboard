# JobKit (peckworks-jobdashboard)

A Claude Code plugin that turns an empty folder into a job-search workspace: paste job
links, get tracked folders with tailored materials and a self-contained dashboard. This
repo is PUBLIC and is a genericized rebuild of the maintainer's private job-search
workspace. Design: `docs/superpowers/specs/2026-08-02-jobkit-design.md`. The operating
rules the product encodes: `docs/LESSONS_HARVEST.md` (numbered lessons; mark FOLDED when
built in, never delete).

## Commands

- Tests: `python -m pytest tests/ -q` (all green is the bar; 249 as of 2026-08-06)
- Personal-data guard: `python tools/no_personal_data.py` (also wired as the pre-commit
  hook; needs the gitignored `tools/forbidden_strings.local.txt` and REFUSES to run
  without it)
- Sample dashboard for eyeballing: init a workspace under the system temp dir, add job
  folders, run `plugins/jobkit/scripts/dashboard.py <ws> --no-open`

## Hard rules (each is enforced by a check; do not weaken the check to pass it)

1. **No personal data in this repo, ever.** No real names beyond the maintainer's public
   GitHub handle where allowlisted, no employer names from the private search, no home
   paths, no real emails. The guard blocks commits; exceptions go in the content-keyed
   allowlists in `tools/no_personal_data.py`, never keyed on line numbers, never by
   weakening a pattern. Invented studios only in examples and fixtures (LumenForge,
   BrightPathStudios, Marrowfield...).
2. **No em-dash characters in anything under `plugins/`** (skills, scripts, templates,
   rendered output). Use commas, colons, periods, parentheses.
3. **Skills invoke `python3`, never bare `python`** (macOS, the target platform, has no
   bare `python`).
4. **`applied_date` is set only from an observed move into the applied lane.** Never
   backfilled, never defaulted, never guessed. `status` and `closure_reason` are separate
   fields; only `closure_reason == "rejected"` counts as a rejection. Tests guard both;
   they are the point, not formalities.
5. **The dashboard is one self-contained HTML file.** `fetch(` never appears in output (a
   `file://` page cannot fetch a sibling file and fails SILENTLY); all data baked in at
   generation time; only Google Fonts may load externally and must degrade to system
   stacks. Theme tokens are ported from the maintainer's mission-control identity; do not
   invent palettes.
6. **Ledger writes are atomic; the board refresh after a mutation is code**
   (`job_status.py`), not skill prose.

## Discipline that held (keep it)

- **Prove new tests RED before the fix.** A test that cannot fail is not a guard.
- **When narrowing any guard, carve-out, or allowlist: write the exploit FIRST** and
  prove it still blocks. Five narrowings opened false negatives during the build.
- **`counts()`-style functions mixing lane (where a folder sits) with status (what
  happened): audit the full lane x status matrix**, not the reported cell. Partial fixes
  expose siblings; the errors always flatter.
- **A SKILL.md is a set of claims about the code.** Every path, flag, and function it
  names must exist; grep before shipping. Tested-but-dead code is not a feature.
- **User-facing surfaces are read by a non-technical person.** Plain-English errors with
  the path echoed, exit 2 for usage problems, no raw tracebacks on reachable input.
- **Before any human first-run, dry-run the docs' own example inputs literally** on the
  target platform's defaults (lesson 38: the canonical `~/JobDashboard` phrase was itself
  a reproducer; a silent no-op counts as a failure even when nothing crashes).

## Architecture in one breath

Plugin (read-only after install, updated via marketplace) + workspace (the user's,
created by setup). Every skill ends by reading the workspace `CLAUDE.md`, which wins;
lessons are appended there (dated, with the why) and to `intake_site_recipes.md` for
site behavior, so the product learns locally without the plugin changing. Modules:
`workspace.py` (dirs, config, path containment) -> `ledger.py` (records, dates, counts)
-> `dashboard.py` (HTML) ; `checks.py` (envelope, banned phrases, inflation) is pure
text-in/problems-out; `job_status.py` is the status CLI.

## Open items (do not re-ask; tracked in project memory)

- The Phase 0 install gate (plugin visible in Claude Desktop's Code tab) has never been
  run by a human. Product is NOT install-verified. Mention at most once per session.
- The requirements conversation with the first user has not happened; Phase 4 of
  `docs/BUILD_PLAN.md` stays empty until it does.
- Early public git history predates sanitization (home path, employer names in old
  commits). Tree is clean; judged not worth a history rewrite.
