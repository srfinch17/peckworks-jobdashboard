# JobKit — Design

Written 2026-08-02. Supersedes the shape described in `docs/ARCHITECTURE.md` where the two
disagree (see "Changes from the 2026-08-01 docs" at the end).

---

## 1. What this is

A Claude Code plugin that turns an empty folder into a job-search workspace. The user pastes
job links; the plugin builds a tracked folder per job with a tailored resume, keeps a ledger,
and regenerates a self-contained `CareerDashboard.html` that opens by double-click.

**First user:** Benny, a graphics artist, on a Mac, non-technical, using Claude Desktop's Code
tab. He has a portfolio hosted elsewhere; the plugin never touches it.

**Origin:** a genericized rebuild of a private workspace that has run ~95 applications since
early 2026. The structure and the operating rules transfer. No personal content transfers.

**The hard rule that runs through everything:** the tool never makes the art. It handles the
admin around the art. No image generation, no touching portfolio files, no writing anything
that claims to be the user's creative work.

---

## 2. Distribution: one plugin, no MCP server

A **plugin** is a directory bundling skills, commands, hooks, and scripts, installed from a
marketplace repo. A **skill** is a `SKILL.md` file — procedural instructions loaded on demand.
An **MCP server** is a running process exposing callable tools.

This product is a workflow plus a large body of operating rules. Rules are markdown, not
function calls, so it ships as a plugin containing skills. No MCP server is written, nothing
is signed, nothing has to stay running. Updates are `git pull`.

```
/plugin marketplace add <owner>/peckworks-jobdashboard
/plugin install jobkit
```

**Open gate (Phase 0, ~10 minutes):** confirm a user-installed marketplace plugin is visible
to Claude Desktop's Code tab. If it is not, the fallback is Claude Code CLI via one `npm`
command; **the plugin artifact is identical either way.** This gate cannot invalidate the
design, only the install instructions.

### Why skills rather than one CLAUDE.md

The source workspace holds its rules in a single 80KB `CLAUDE.md` with 25 top-level sections,
loaded on every turn. Those sections map nearly one-to-one onto skills. Splitting them means
only the relevant few KB load per turn.

---

## 3. Two directories

### The plugin (read-only, versioned, updated by git pull)

```
peckworks-jobdashboard/
├── .claude-plugin/marketplace.json
├── plugins/jobkit/
│   ├── .claude-plugin/plugin.json
│   ├── skills/
│   │   ├── jobkit-setup/SKILL.md
│   │   ├── session-briefing/SKILL.md
│   │   ├── job-intake/SKILL.md
│   │   ├── build-application/SKILL.md
│   │   ├── track-application/SKILL.md
│   │   ├── freshness-check/SKILL.md
│   │   ├── make-guide/SKILL.md
│   │   └── housekeeping/SKILL.md
│   ├── commands/            # /intake /dashboard /status /guide /help
│   ├── hooks/               # refuse edits under the applied lane
│   ├── scripts/             # dashboard.py ledger.py freshness.py generate.py
│   ├── vendor/              # react + babel, for JSX guides
│   └── templates/           # workspace scaffold, resume templates, starter recipes
├── docs/
└── tools/no_personal_data.py    # pre-commit guard, exits nonzero on a hit
```

### The workspace (the user's, created by setup)

```
~/JobDashboard/
├── CLAUDE.md                  # the user's own overrides. Plugin never rewrites this.
├── jobkit.json                # lane names, vocabulary, scoring rubric, feature switches
├── profile.json               # contact, location policy, style rules, banned phrases
├── Baseline/                  # baseline resume(s). SOURCE OF TRUTH.
├── Jobs to Apply to/          # built, not sent
├── Jobs I Have Applied To/
├── Jobs Not Applied To Because Reasons/
├── Skipped/                   # never built, with the reason
├── Expired/                   # posting confirmed dead. NEVER deleted.
├── guides/                    # the HTML library
├── job_ledger.json            # keyed on FOLDER NAME
├── reading_stats.json
├── intake_site_recipes.md
└── CareerDashboard.html       # generated
```

Human-readable lane names are deliberate: the user sees these in Finder. The lane→folder
mapping lives in `jobkit.json`; no script hardcodes a folder name.

**The one invariant:** nothing is ever written outside the workspace path. Setup asks once,
stores it in `jobkit.json`, and every script takes it as an explicit argument rather than
inferring it from the current directory.

---

## 4. Customization without breaking updates

Three layers, most specific wins:

1. **Plugin skills** — shipped, versioned, updated by git pull
2. **`jobkit.json` / `profile.json`** — the user's data: scoring rubric, banned phrases,
   lane names, feature switches
3. **Workspace `CLAUDE.md`** — the user's prose overrides ("always mention my Blender work")

Every skill ends by checking the workspace `CLAUDE.md`; if it contradicts anything above, it
wins. `git pull` therefore never clobbers the user's rules. Anything the config cannot express
is a sentence he writes himself. If a customization proves general, it graduates into the
plugin.

---

## 5. Data model

### Ledger

Keyed on **folder name**, with `posting_url` as a secondary identity so a rename can be
re-matched rather than orphaned.

```json
"7_Disney_LeadSoftwareEngineer": {
  "lane": "applied",
  "score": 7,
  "company": "Disney",
  "role": "Lead Software Engineer",
  "location": "Burbank, CA",
  "posting_url": "https://…",
  "source_site": "greenhouse.io",
  "intermediary": null,
  "applied_date": "2026-05-01",
  "status": "closed",
  "closure_reason": "rejected",
  "correspondence": ["2026-05-14_rejection.md"],
  "history": [
    "2026-04-20: staged",
    "2026-05-01: applied",
    "2026-05-14: closed (rejected)"
  ]
}
```

**`status` and `closure_reason` are separate fields.** Values for `closure_reason`:
`rejected` | `closed_no_response` | `withdrawn`. The dashboard reports them as distinct
numbers and **only `rejected` counts as a rejection.** A first-time job seeker reads that
number as feedback about himself; it must be true.

**Lanes:** `staged` | `applied` | `not_applied` | `skipped` | `expired`. Every lane the
filesystem has is a lane the ledger scans — including `expired`.

**Pruning:** an entry whose folder is not found in any lane is marked `missing`, never
silently retained at its last known status.

**Writes are atomic:** write to `.tmp`, then `os.replace()`.

### Job folder

Required: `original_job_posting.md` (**source URL on line 1**, verbatim body),
`note.md` (fit, gaps, decisions, post-round debriefs at the top).
Optional: tailored `.txt` resume, cover letter, `correspondence/`, generated `.docx`/`.pdf`.

Folder name: `<score>_<Company>_<Location>_<Role>`. The tracker warns on non-conforming names
at scan time rather than degrading silently.

### Sidecars

One identity scheme everywhere: **folder name**. Interviews, apply methods, and correspondence
all key on it. No sidecar uses a different key from the ledger.

---

## 6. Intake

The loop that runs fifty times. `job-intake` accepts a pasted URL, pasted text, or both.

1. **Extract in tiers, and announce which tier ran** — pasted text → public ATS JSON
   (Greenhouse / Lever / Ashby / Workday / ADP) → browser automation if available. The user
   always knows how much to trust the result.
2. **A JS shell is an EXTRACTION failure, never a freshness verdict.** Report "could not
   read"; never move to `Expired/` on it.
3. **Pull the employer's whole requisition list, not just the target job.** Sibling reqs
   routinely state what the target omits — a blank location field next to five populated ones
   is a decision, not an absence. Costs one extra request.
4. **Source tiering:** the employer's own ATS is truth. A board listing is a copy that may be
   stale, re-titled, or mis-attributed. When they disagree the ATS wins; when the board is
   silent, ask the ATS before asking the user.
5. **Score 1–10** against the rubric in `profile.json`. Below threshold (default 6) →
   `Skipped/` **with the reason written down**, never silently dropped.
6. **Name any intermediary in the same breath as the job** — agency, staffing firm,
   aggregator, content mill, contest-dressed-as-a-job, rights-grab terms. Never below the fold.
7. **On a login or captcha wall: stop and say so in plain words** — which site, what it needs,
   that it will wait. Never return a wall as if it were content.
8. **Append to `intake_site_recipes.md`** — what worked, what selector or endpoint, what broke,
   dated. Stale recipes get marked stale, not deleted.
9. **Regenerate the dashboard.**

---

## 7. Build

`build-application` reads `profile.json` + `Baseline/` + the posting.

- Tailored resume `.txt` **against the baseline only.** Never invents experience.
- Cover letter **off by default**; generated only when the application requires one.
- **Envelope check before writing** — length, section count. Refuse and report rather than
  emit a six-page resume.
- **Sanitizer** applies the user's banned-phrase and style rules from `profile.json`.
- **Competence-inflation check.** Framing defaults DOWN: a thin baseline entry becomes
  "familiar with," never "extensive experience in." Grep drafts for the sentence shape where a
  comparison becomes a claim.
- `.txt` is the source of truth. `.docx` / `.pdf` are generated from it via `python-docx` and
  `reportlab`.

---

## 8. Update model: the user drives, the plugin records

Claude is passive here by design. The user is the sensor — emails and phone calls reach him,
not the tool. `track-application` handles reports in plain language:

| User says | Effect |
|---|---|
| "I applied to the NBCU one" | Move to applied lane; `applied_date` = today **because the move is a real signal**; refresh |
| pastes a rejection email | `status: closed`, `closure_reason: rejected`; email saved to `correspondence/`; refresh |
| "no word in two months" | `closure_reason: closed_no_response`. **Not counted as a rejection anywhere.** |
| "they want to schedule an interview" | Interview card created, **date blank and marked PENDING** |
| "it's Tuesday at 9" | Slot filled; card moves to the upcoming-interviews panel |
| "the interview happened, here's how it went" | Debrief written to the TOP of `note.md`; status → interviewed |

Every pasted email is saved into that job's folder. The dashboard shows a message count per
card and links to them.

**Binding rules:**

- **Never fabricate a date.** A proposed slot is not a confirmed slot. An unknown apply date
  stays unset and the card sorts to the bottom. *This rule gets a test, not a comment — see
  §12.*
- **State the signal tier, no hype.** form/automated email < recruiter or agency contact <
  named human with specifics < hiring-manager conversation < portfolio review or technical
  round < offer. No excitement language below the hiring-manager tier.
- **A 30+ day silence from an employer known to send dispositions is functionally closed**,
  and is recorded as `closed_no_response`, not as a rejection.

---

## 9. Session bookends

The part that makes this usable by a non-technical person. The source workspace lacks it
because its owner does this by hand.

### Session start — `session-briefing`

Generated from the ledger, no guessing. Runs before the user has to ask for anything.

```
Job Dashboard — Tuesday, Aug 4

  ⚠  Interview TOMORROW 9:00am — NBCUniversal, Motion Designer
      Want to run a mock round, or review your notes?

  8 ready to apply · 23 out · 2 interviewing · 4 closed

  Anything new since we last talked?
   · Pixel Forge — applied 34 days ago, no word. Want to close it out?
   · Riot Games — you said they'd email this week. Hear anything?
   · 3 postings are 21+ days old. Check if they're still up?

  Or just paste a job link and I'll take it from there.
```

It **leads the user to the updates he owes** rather than waiting for him to know he owes them.

### Session end — `housekeeping`

Offered, not left to the user's initiative:

> Want me to tidy up before you go? I'll refresh the dashboard, save what we learned about
> wherever you're finding jobs, and note what's waiting on you next time. [yes / not now]

On yes: regenerate the dashboard, append to `intake_site_recipes.md`, record any preference
the user expressed into the workspace `CLAUDE.md`, write next-session context.

### `/help`

Plain English, phrased as things to *say*, not commands to run.

---

## 10. Dashboard

A first-class deliverable, not a report. One self-contained `CareerDashboard.html` in the
workspace root.

- **Inline CSS, inline SVG, vanilla JS. Opens from `file://` by double-click.** No server, no
  build step, no npm, no CDN for anything load-bearing. Fonts degrade to a `system-ui` stack.
- **All data is baked into the markup at generation time.** A `file://` page cannot `fetch()`
  a sibling JSON file — CORS blocks it and it fails silently, looking like an empty page. JS
  in the page is only for filtering, search, and expanding cards on data already present.
- Shows: pipeline counts by lane; upcoming interviews; a staged lane; an active-applications
  lane with days-since-applied; closed, split by reason.
- Every card links to its job folder via a `file://` URL, plus a chip linking to the original
  posting.
- **"No response in N days" is surfaced**, so stale applications stop inflating the in-flight
  count.
- Dark theme. Vocabulary comes from `jobkit.json` so it reads correctly for a non-engineer.
- Regenerated by **every** state-changing skill at the end of its turn. A dashboard that lags
  gets trusted, which is worse than no dashboard.
- `webbrowser.open()` on completion, and the path is printed for bookmarking.

---

## 11. The library

`make-guide` builds standalone HTML study pages into `guides/`, registered on the dashboard.

- **Plain self-contained HTML is the default** — inline CSS, inline SVG, opens offline.
- JSX guides remain supported via vendored React + Babel (~400KB in `plugins/jobkit/vendor/`)
  so existing pages still build, but no build step is required for a new guide.
- **Read tracking ships enabled**, reading the local browser history. It is disclosed in the
  README and in setup output: reads local history to mark guides as read, nothing leaves the
  machine.

---

## 12. Guards

Rules that live in prose get violated; rules that live in checks do not. **A comment is a
reminder, not a guard** — the source workspace has a comment promising `applied_date` is never
fabricated sitting directly above code that fabricates it on 57 records.

| Guard | Mechanism |
|---|---|
| Sent materials immutable | Hook refuses edits to application files under the applied lane |
| No personal data in the repo | `tools/no_personal_data.py` greps a forbidden-string list, **exits nonzero**, wired as pre-commit. **Nothing is pushed before this passes.** |
| Resume length | Envelope check refuses to generate outside bounds |
| Style / banned phrases | Sanitizer at build time, list from `profile.json` |
| No competence inflation | Grep drafts for comparison-becomes-claim; framing defaults down |
| **`applied_date` never fabricated** | **Test:** a job going staged → applied(known date) → denied(later date) must retain the known date. Fails loudly if a backfill is reintroduced. |
| Detector sanity | Any freshness/expiry detector gets a control test against a known-live posting before its output is trusted. A uniform confident result is a broken instrument, not a thorough one. |
| Ledger integrity | Atomic write; schema validated on load; folder-missing marked `missing`, never silently retained |

---

## 13. Defects fixed rather than ported

Reviewed against the source workspace's live data on 2026-08-02. Full report with repro
commands lives in that workspace as `PROCESS_DEFECTS_2026-08-02.md`.

**Method note.** The source workspace was built feature by feature over ~6 months. Records
that predate a feature are not evidence the feature is broken. An earlier draft of this list
claimed 57 fabricated dates and an inflated dashboard count; both were artifacts of auditing
without first establishing when each field was introduced. Corrected below.

1. **Ledger keyed on a content hash of an edited file**, with a `*.md` glob fallback returning
   `matches[0]` in filesystem order — so a folder without an explicit posting file gets keyed
   on `note.md`, which changes whenever a debrief is added. JobKit keys on folder identity.
2. **Two identity schemes** — the tracker keys by hash while every sidecar, and `dashboard.py`
   itself, keys by folder name. JobKit uses folder name everywhere.
3. **Non-atomic ledger writes**, no backup, no schema validation on load. JobKit writes `.tmp`
   then `os.replace()` and validates on load.
4. **`--set` matched by substring**, forcing a manual score-prefix workaround on duplicate
   companies. JobKit offers numbered disambiguation.
5. **`denied` conflated a received rejection with a silence-closure.** JobKit separates
   `status` from `closure_reason`.
6. **`Expired/` absent from the tracker's directory map** — cosmetic in the source workspace
   (its dashboard counts folders directly and already handles Expired), but it left 23 stale
   `pending` entries in the ledger and 35 untracked. JobKit scans every lane the filesystem
   has and marks vanished folders `missing` rather than retaining a stale status.
7. **`applied_date` backfill read the most recent status update rather than the earliest**,
   so a few closed jobs carry a later date than their own history supports. Affected ~22
   records created before the field existed; the path is dead for new jobs. JobKit sets the
   date only from a real signal and tests that it survives later status changes.

---

## 14. Build order

**Phase 0 — the gate (~10 min).** `git init`, marketplace.json + stub plugin with one trivial
skill, push, install, confirm it is invocable in Claude Desktop's Code tab. Record the result.

**Session 1 — the core loop.** `jobkit-setup` (onboarding interview → `profile.json`,
`jobkit.json`, baseline resume, environment check), `job-intake`, `build-application`,
`dashboard.py`. Done when: empty folder → paste one link → a dashboard card that clicks
through to the materials, with no manual file editing and no server.

**Session 2 — durability and the human layer.** `ledger.py`, `track-application`,
`session-briefing`, `housekeeping`, `freshness.py`, the sent-immutability hook, `/help`.

**Session 3 — documents and library.** `generate.py` (docx/pdf + envelope enforcement),
`make-guide`, reading stats, resume templates.

**Later, explicitly not now:** interview personas, mock rounds, prep-page generation.

### Working rules

1. **Build from structure, never copy-and-redact.** Redaction requires proving an absence,
   which is what human review is worst at. Open the original for reference; write the new file
   fresh.
2. **Nothing personal in this repo.** No real names beyond Benny's first name, no employer
   names, no sent materials, no ledger contents.
3. **Every guard is code, not a note.**
4. **One runnable check per non-trivial script** — the smallest thing that fails if the logic
   breaks.
5. **Test on a genuinely empty directory every time.** The most likely bug is assuming a file
   that exists only because an earlier run made it.
6. **No push until `no_personal_data.py` passes.**

---

## Changes from the 2026-08-01 docs

| Topic | Was | Now | Why |
|---|---|---|---|
| Portfolio piece-selection engine | The non-deferrable core feature | **Cut.** Portfolio lives as links; the tool tailors resumes | User decision: Benny has a hosted portfolio; resume tailoring is the need |
| HTML guide library | Separate product, not v1 | **In scope** | Existing code, wanted |
| Reading stats via browser history | Dropped permanently | **Ships enabled, disclosed** | User decision; it is the user's own machine and own data |
| Board scraping / daily feed | Dropped | Dropped | Unchanged |
| Session briefing + housekeeping | Not present | **Added** | Non-technical user cannot be relied on to initiate maintenance |
| Workspace folder names | `staging/`, `sent/` | Human-readable lane names | The user sees these in Finder |

**Standing assumption, stated once:** the requirements conversation with Benny still has not
happened. Resume-tailoring is a safe guess for any job seeker, but it is a guess. Phase 4
stays deliberately empty and gets filled from what breaks in his hands.
