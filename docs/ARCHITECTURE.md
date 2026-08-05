# Architecture

## 1. The platform question, resolved

The ask was "a plugin for Claude Desktop." That phrase covers three different things, and picking
the wrong one wastes the whole build. Verified against Anthropic's docs 2026-08-01
(https://claude.com/docs/third-party/claude-desktop/extensions):

| Thing | What it is | Fits us? |
|---|---|---|
| **Connector / `.mcpb` extension** | A bundled MCP server, double-click install, Connectors settings page | No. An MCP server exposes tools; it does not carry skills, workflow prompts, or operating rules. Wrong shape for a workflow product. |
| **Plugin** | A directory bundling `skills/`, `commands/`, `agents/`, `hooks/`, and optionally `.mcp.json`. Installed from the Plugins settings page. | **Yes. This is it.** |
| **Local MCP server** | Added manually under Settings, Developer | No. Same shape problem, plus manual setup. |

**The decisive detail:** Claude Desktop now has a **Code tab running an embedded Claude Code
engine**, and per the docs that tab "reads Claude Code's own plugin configuration on the host."
Claude Desktop's other surface (Cowork) runs in a VM.

That matters because this product is fundamentally *files plus scripts*: it creates directories,
writes documents, runs Python. That needs a real filesystem and a shell. The Code tab has both.

**So: build one Claude Code plugin.** It works in the Claude Code CLI and in Claude Desktop's Code
tab. Same artifact, both surfaces, no MCP server to write, no bundle to sign.

⚠️ **Verify before building on it:** confirm on a Mac that the Code tab picks up a
user-installed marketplace plugin. The docs describe org-managed deployment in detail and the
user-install path more briefly. This is a 10 minute check and it gates everything, so do it first.
Fallback if it does not: the first user installs Claude Code CLI (one `npm` command) and runs it there.
The plugin is unchanged either way.

## 2. Repo layout

```
peckworks-jobdashboard/
├── .claude-plugin/
│   └── marketplace.json         # makes this repo installable as a marketplace
├── plugins/
│   └── jobkit/
│       ├── .claude-plugin/
│       │   └── plugin.json      # name, version, description
│       ├── skills/
│       │   ├── jobkit-setup/SKILL.md
│       │   ├── job-intake/SKILL.md
│       │   ├── build-application/SKILL.md
│       │   ├── track-application/SKILL.md
│       │   └── refresh-dashboard/SKILL.md
│       ├── commands/            # thin slash-command wrappers
│       ├── scripts/             # the Python: generate, tracker, dashboard, freshness
│       └── templates/           # workspace scaffold + document templates
└── docs/
```

Install path for the first user:
```
/plugin marketplace add <owner>/peckworks-jobdashboard
/plugin install jobkit
```
Then: "set up my job search in ~/JobSearch".

## 3. Two directories, kept separate

**The plugin** lives wherever Claude installs it. Read-only, versioned, updated by git.

**The workspace** is a directory the first user picks (say `~/JobSearch`). The plugin creates and owns the
structure inside it:

```
~/JobSearch/
├── jobkit.json              # config: paths, vocabulary, feature switches
├── profile.json             # who the user is, what they want, location policy
├── baseline/                # SOURCE OF TRUTH. portfolio inventory + work history
├── applications/
│   ├── staging/             # built, not yet sent. EDITABLE.
│   ├── sent/                # submitted. IMMUTABLE.
│   ├── declined/            # built, decided against
│   └── expired/             # posting went dead
├── skipped/                 # never built, with the reason
├── ledger.json              # tracker state, keyed on folder identity
├── site_recipes.md          # how to extract from each site. THE PLUGIN WRITES TO THIS.
└── dashboard.html           # generated
```

Nothing is written outside the workspace directory. The setup skill asks for the path once and
stores it; every script takes it as an argument rather than guessing.

## 4. Intake: paste-first, browser-optional

Three tiers, degrading gracefully. The tool announces which tier it used, so the user always knows
how much to trust the result.

1. **Pasted text** (always works). User copies the posting body. Zero dependencies, zero bot walls.
2. **Public ATS JSON** (no browser). If the URL is Greenhouse / Lever / Ashby / Workday / ADP
   WorkforceNow, fetch the public endpoint. Clean structured data, no scraping, stable.

   ⚠️ **A JS shell is an EXTRACTION failure, never a "the job is dead" verdict.** Several ATS
   platforms render nothing useful to a plain fetch while exposing a clean unauthenticated JSON API
   keyed on an ID that is already sitting in the apply URL. ADP is the proven case: the page returns
   a browser-compatibility notice, while
   `workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions?cid=<CID>`
   returns every open requisition. Report an unreadable page as "could not read," never as expired.

   🔑 **Pull the employer's WHOLE req list, not just the one job.** Most ATS APIs return all open
   reqs in a single call, and the sibling reqs routinely state what the target posting omits. Proven
   case: a job that named no office anywhere and had a deliberately blank location field, whose
   employer's other engineering req listed all four US offices plus a written remote policy. A single
   blank field is ambiguous; a blank field next to five populated ones is a decision, and you only
   see the difference by fetching the list. Cost: one extra request.

   **Source tiering that follows:** the employer's own ATS is truth. A board listing is a copy that
   may be stale, re-titled, or mis-attributed. When they disagree, the ATS wins; when the board is
   silent, ask the ATS before asking the user.
3. **Browser** (optional). If a browser automation MCP server is available, navigate and extract
   per `site_recipes.md`.

**On the browser dependency:** do not make it a hard requirement. Check for it at setup, and if
absent, say plainly what tier 1 and 2 still give (which is most of the value) and how to add it
later. A tool that refuses to start because a dependency is missing is a tool a 20-something
uninstalls.

**On login and captcha walls:** when a page needs a human, the tool must stop and say so in plain
words: which site, what it needs (log in / click the box / solve a captcha), and that it will wait.
It must never silently return a half-scraped page or a login-wall HTML shell as if it were a job
posting. Silent partial success is the failure mode that poisons a dataset.

## 5. Self-improvement: `site_recipes.md`

The "not static" requirement, made concrete. One markdown file in the workspace, one section per
site, each holding: what worked, what selectors or endpoint, known walls, and last-verified date.

The loop:
- Intake reads the recipe for the site before trying.
- On success with a NEW site or a new method, append a recipe.
- On failure with an EXISTING recipe, mark it stale with the date and what broke, then fall back a
  tier and record what worked instead.

This is a plain file the user can read and edit, which is the point. It is also the honest version
of "self-improving": the tool accumulates verified knowledge in the open rather than claiming to
learn in some way nobody can inspect.

Ship a starter file with the four ATS endpoints (stable, documented) and nothing else. Let the
board-specific recipes accumulate from real use.

## 6. The dashboard: one file, no server, double-click to open

This is a first-class deliverable, not a reporting afterthought. It is the thing that makes the
whole workspace feel real instead of feeling like a folder of documents. It must look good.

**Hard requirements:**
- **One self-contained `.html` file** in the workspace root. Inline CSS, inline SVG, vanilla JS.
- **Opens from `file://` by double-click.** No web server, no build step, no npm.
- **Fully offline.** No CDN for anything load-bearing. Web fonts may be requested but must
  degrade to a `system-ui` stack that still looks deliberate.
- **The generator opens it** when it finishes, and also prints the path so the user can bookmark
  it. Use Python's `webbrowser.open(path)`, which handles macOS and Windows without branching.

⚠️ **The constraint that dictates the design: `file://` pages cannot `fetch()` local JSON.**
Browser CORS rules block reading a sibling file from a `file://` origin, and it fails in a way
that looks like an empty page rather than an error. So:

> **Bake the data into the HTML at generation time.** The Python generator reads the ledger and
> scans the folders, then writes the values directly into the markup it emits. The page never
> loads data at runtime.

JavaScript in the page is therefore only for interaction on data that is already present:
filtering, search, expanding a card, switching a view. That is the same approach the source
workspace arrived at, and it is why that dashboard works with no server.

**What it shows (v0):**
- Pipeline counts across the lanes (staging, applied, interviewing, closed)
- A staging lane of built-not-yet-sent applications, each card linking to its folder
- A sent lane with status and the date it was applied
- Per card: role, company, location, the source site, and a link to the original posting
- Cards link to the job folder with a `file://` URL, so one click opens the materials

**What it does NOT do in v1:** no guide library, no reading stats, no feed panel. Reserve the
layout slot for a library section so adding it later is not a redesign.

**Regeneration is cheap and automatic.** Any skill that changes state (intake, build, status
change) re-runs the generator at the end of its turn. A dashboard that silently lags behind the
folders is worse than no dashboard, because it gets trusted.

## 7. Document generation

`.txt` is the source of truth for every document. `.docx` and `.pdf` are generated from it.

- Python, `python-docx` + `reportlab`, both pip-installable and cross-platform (no Word, no
  LibreOffice, no macOS-specific path).
- Generation is a single script with an explicit output directory argument.
- A **format envelope** check runs before writing: page count, section count, length. Refuse and
  report rather than emitting a 6-page resume. This is the single highest-value guard inherited
  from the source workspace, because it caught a real 8-page failure that would otherwise have
  been sent.
- Banned-phrase and style rules come from `profile.json`, not from code. The source workspace
  hardcodes one person's rules (an em-dash ban, specific forbidden words). Here they are a list
  the user owns.

**macOS note:** the first user's machine needs Python 3 and two pip packages. The setup skill should check
for Python and print the exact install line rather than assuming. macOS ships Python 3, so this is
usually a one-line pip install.

## 8. What is deliberately NOT in v1

- Board scraping / automated lead feeds (see `ASSESSMENT.md` section 4)
- Reading-stats / browser-history mining (dropped permanently)
- The study-guide library and its HTML generator (a separate product; the dashboard reserves a
  slot for it)
- Interview prep page generation
- Persona review boards
- Any AI generation of creative work, ever
