# Build Plan

Phased so that every phase ends with something that runs. v0 is scoped to a single focused
evening. Do not start Phase 1 until v0 works end to end.

---

## Phase 0: the 10-minute gate (do this FIRST)

Everything downstream assumes a user-installed plugin is visible to Claude Desktop's Code tab.

- [ ] Create `.claude-plugin/marketplace.json` and a stub plugin with one trivial skill.
- [ ] `git init`, commit, push to GitHub (public).
- [ ] From Claude Code: `/plugin marketplace add <owner>/peckworks-jobdashboard`, then
      `/plugin install jobkit`. Confirm the skill is invocable.
- [ ] If a Mac is reachable, confirm the same in Claude Desktop's Code tab.

**If the Code tab does not see it:** fall back to Claude Code CLI for the first user. Note the result here
and move on. The plugin artifact does not change.

---

## v0: the evening slice

Goal: the first user points Claude at a folder, answers questions, pastes one job link, and gets a real
folder with real materials and a dashboard that shows it. Text files only.

### v0.1 Scaffold
- [x] `marketplace.json`, `plugin.json`, directory skeleton
- [x] `templates/workspace/` with the directory structure and starter `site_recipes.md`
      (built by `workspace.init`, not a static template dir: lane folders, `guides/`,
      `Baseline/`, starter `CLAUDE.md`, starter `intake_site_recipes.md` - same result)

### v0.2 `jobkit-setup` skill
The onboarding interview. This is the most important skill in the product because it produces the
data everything else runs on.
- [x] Ask for and store the workspace path; create the structure; never write outside it
      (`workspace.safe_join`, exercised by `test_nothing_written_outside_the_workspace`)
- [x] Interview to `profile.json`: name, contact, location + relocation policy, target roles,
      what an application consists of in their field, style rules and banned phrases
- [x] Interview to `baseline/`: for an artist, the **portfolio inventory** (per piece: title,
      link, medium, software, their specific role, year, client vs personal, tags); plus any
      employment history and education
- [x] Environment check: Python 3, `python-docx`, `reportlab`, browser MCP availability. Report
      what is present, what is missing, and the exact command to fix each. Never hard-fail.
- [x] Write `jobkit.json`

**Design rule:** the interview must be resumable and must never invent an answer. Unknown stays
unknown, exactly like the source workspace refuses to fabricate an application date.

### v0.3 `job-intake` skill
- [x] Accept a pasted URL, pasted text, or both
- [x] Tier the extraction (pasted text, then public ATS JSON, then browser) and SAY which tier ran
- [x] On a login or captcha wall: stop, name the site and the action needed, wait. Never return a
      wall as if it were content.
- [x] Create the staged-lane job folder containing `original_job_posting.md` (source URL on
      line 1) and `note.md` (the plan's `applications/staging/<slug>/posting.md` /
      `posting_raw.md` / `notes.md` layout was superseded by this simpler two-file shape)
- [x] Flag a suspected intermediary (agency, staffing firm, aggregator, content mill) in the same
      breath as the job itself, never below the fold
- [x] Append or update `site_recipes.md` with what worked

### v0.4 `build-application` skill
- [ ] **Piece selection** (the artist-critical feature): rank portfolio pieces against the posting,
      propose the lead 6 to 10 with a one-line reason each, write `portfolio_selection.md`
      (not present in the current skill; resume selection/ordering is, a dedicated
      `portfolio_selection.md` writeup is not)
- [x] Read `profile.json` + `baseline/` + the posting
- [x] Tailored resume `.txt` against the baseline only, never inventing experience
- [x] Short cover letter / intro `.txt`, plain and brief (off by default, written on request)
- [x] **Competence-inflation check on every draft.** Framing defaults DOWN: a thin baseline entry
      becomes "familiar with," never "extensive experience in." Grep for the sentence shape where a
      comparison becomes a claim. **For an artist the sharpest case is role attribution: if the
      inventory says he did backgrounds, no draft may imply he did the whole piece.**
      `LESSONS_HARVEST.md` item 27. (`checks.py`, unit-tested in `tests/test_checks.py`)
- [x] Envelope check before writing: length, section count. Refuse and report if outside.
      (`checks.py` envelope check, run via `check_document.py`)
- [x] Style check against the user's banned-phrase list from `profile.json`

### v0.5 `refresh-dashboard` script and skill
The visible payoff of the whole product. Treat it as a feature, not a report. See
`ARCHITECTURE.md` section 6 for the full spec.
- [x] Scan the workspace, read the ledger, emit ONE self-contained `dashboard.html`
- [x] **Bake all data into the markup at generation time.** A `file://` page cannot `fetch()` a
      local JSON file; it fails silently and looks like an empty dashboard. This is the single
      constraint most likely to burn an afternoon if forgotten.
- [x] Inline CSS, inline SVG, vanilla JS only. No server, no build step, no npm, no CDN for
      anything load-bearing. Fonts degrade to `system-ui`.
- [x] Pipeline counts, staging lane, sent lane, per-job cards
- [x] Every card links to its job folder via `file://` so one click opens the materials
- [x] Dark theme that actually looks good. This is the thing the first user will show people.
- [x] `webbrowser.open()` it on completion AND print the path for bookmarking
- [x] Vocabulary comes from `jobkit.json` so it reads correctly for a non-engineer
- [x] Reserve a layout slot for a future library section so adding it is not a redesign
      (built further than "reserved": the library section is live, reading from `guides/`)
- [x] Every state-changing skill re-runs this at the end of its turn. A stale dashboard gets
      trusted, which is worse than no dashboard.

**v0 done when:** empty folder to a dashboard card you can click through to the materials, one
job, no manual file editing, and the page opens by double-click with no server running.

Confirmed end-to-end on code paths (`tests/test_end_to_end.py`, all against directories that did
not exist when the test started) and via a real command-line invocation of `dashboard.py` and
`check_document.py` from a system temp directory (Task 10, Session 1). **Not yet confirmed:** the
live Claude Desktop walkthrough (brief step 4) - that requires a human driving Claude and is not
done by this task.

**Genuine bug found, not fixed (see `task-10-report.md`):** `dashboard.py`, run as a CLI script
against a workspace path that was never initialized with `workspace.init` (no `jobkit.json`
yet), exits 1 via an unhandled `FileNotFoundError` traceback rather than a clean usage-style
error message.

---

## Phase 1: durability (second session)

- [ ] `track-application` skill + `ledger.py`, **keyed on folder identity, not a content hash**
      (fixing the known defect in the source tracker)
- [ ] Status vocabulary: staged, applied, screening, interview, offer, declined, withdrawn
- [ ] **Store a closure REASON, not just a status** (`rejected` / `closed_no_response` /
      `withdrawn`). A single `denied` value cannot hold the difference between "they said no" and
      "we concluded no after silence," and a first-time job seeker reads their own denied count as
      feedback about themselves. See `LESSONS_HARVEST.md` item 24.
- [ ] Surface "no response in N days" on the dashboard rather than letting stale applications sit
      in the active lane inflating the in-flight count
- [ ] `applied_date` set only from a real signal, immutable once set, never fabricated
- [ ] Move-folder-on-status-change, and the **sent-immutability guard**: a hook that refuses edits
      to any application file under `sent/`
- [ ] `freshness.py`: flag postings older than N days, verify, move confirmed-dead to `expired/`
      with a stub recording date, reason, and URL. Never remove on a guess.

## Phase 2: documents (third session)

- [ ] `generate.py`: txt to docx + pdf via `python-docx` and `reportlab`
- [ ] Envelope enforcement at generation time, with a `--force` escape that demands a reason
- [ ] Sanitizer applying the user's own style rules mechanically at build time
- [ ] Templates: engineer-style resume and artist-style resume (shorter, portfolio-led)
- [ ] **Deferred, not v1:** practice-interview personas (a research-grounded interviewer persona
      for a mock round). See `LESSONS_HARVEST.md` item 28.
- [ ] **Deferred, not v1:** same-day debrief capture and prep grown from the user's own live
      questions. See `LESSONS_HARVEST.md` item 37.

## Phase 3: polish

- [ ] Source-site brand chips on dashboard cards. ⚠️ Shorten an unrecognized host by STRIPPING
      noise subdomains (`careers.`, `jobs.`, `apply.`), never by truncating the tail: chopping
      `careers.brightpath-studios.com` to a fixed width produces `careers.brightpath-studios.co`, which
      reads as a typo rather than a domain.
- [ ] Interview / callback tracking sidecar
- [ ] `jobkit-doctor`: diagnose a broken workspace (missing deps, malformed ledger, orphaned folders)
- [ ] Signal-tier calibration in the tracker's own language (see `LESSONS_HARVEST.md` item 5)

## Phase 4: only after the first user has used it

Deliberately empty. The requirements conversation has not happened, so anything specified here
would be a guess. Fill it from what actually breaks in his hands.

---

## Working rules for this build

1. **Build from structure, never copy-and-redact.** Do not paste a source-workspace file in and
   strip the personal parts. That is how a name, a company, or a file path leaks into a public
   repo. Open the original for reference, write the new one fresh.
2. **Nothing personal in this repo.** No real personal names, no employer names,
   no sent materials, no ledger contents, no interview notes.
3. **Every guard is code, not a note.** The source workspace learned repeatedly that a rule living
   in prose gets violated and a rule living in a check does not.
4. **One runnable check per non-trivial script.** Smallest thing that fails if the logic breaks.
5. **Test on a genuinely empty directory** every time. The most likely v1 bug is assuming a file
   that only exists because an earlier run made it.
