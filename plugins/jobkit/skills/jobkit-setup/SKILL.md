---
name: jobkit-setup
description: Use when the user wants to set up, install, initialize, or start a JobKit job-search workspace, says "set up my job search", names a folder to use for job hunting, or when any other JobKit skill finds that no jobkit.json exists yet.
---

# Setting up a Peckworks JobKit workspace

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

## Step 1, the environment check

Do this FIRST, before anything else touches disk. Check and REPORT. Never
hard-fail; a tool that refuses to start gets uninstalled.

```bash
python3 --version
```

If that fails, JobKit cannot run. Say so plainly: modern macOS (12.3+) ships
only `python3`, never bare `python`, and every command JobKit runs uses
`python3` for exactly that reason. One macOS wrinkle to expect: on a fresh Mac,
the first `python3` may pop up a dialog offering to install the "command line
developer tools." That is normal and safe; tell the user to click Install and
wait for it to finish, then run the check again. If `python3 --version` still
fails after that, tell them to install Python 3 from python.org before
continuing and stop.

Report what is present and what is missing, with the exact command to fix each.
`python-docx` and `reportlab` are only needed for Word and PDF output, say that
plainly and say text files work without them.

Check whether a browser automation tool is available. If not, say what still works
without it: pasted text and structured job-board data, which is most of the value.

## Step 2, the workspace path

Ask where they want it. Suggest `~/JobDashboard`. Confirm the full path back to
them before creating anything.

Then run:

```bash
python3 -c "import sys; sys.path.insert(0, r'${CLAUDE_PLUGIN_ROOT}/scripts'); import workspace; workspace.init(r'<path>')"
```

This creates the five lane folders (jobs to apply to, applied, not applied,
skipped, expired), a `Baseline/` folder for their resume, a `guides/` folder for
their library (pre-loaded with a Getting Started guide they can read from the
dashboard any time), a starter `CLAUDE.md`, and a starter `intake_site_recipes.md`.
Tell them what each of those is in plain words. Do not recreate `CLAUDE.md` or
`intake_site_recipes.md`, `workspace.init` already wrote them; just point the
user at them and say they can edit `CLAUDE.md` any time to change how JobKit
behaves for them.

**Store the path.** Every later command needs it. Nothing is ever written outside it.

## Step 3, tell them about read tracking

Peckworks JobKit watches their browser history for visits to guide pages inside
this workspace, so the dashboard can show them what they have actually read.
It only looks at `file://` pages under the workspace folder, it writes the
result to `reading_stats.json` in the workspace, and nothing is ever sent
anywhere. Ask if they want to turn it off; if so, set
`features.reading_stats` to `false` in the workspace's `jobkit.json`. It is on
by default.

Be straight about which browsers it can see: Chrome, Chromium, Brave, and
Edge (every profile, not just the first). Safari does not let apps read its
history, so guides opened in Safari are never marked as read. If the user is
a Safari person and wants read tracking, suggest opening guide pages in
Chrome; if they do not care, say nothing more about it.

## Step 4, the interview

Write answers into `profile.json` in the workspace, using
`${CLAUDE_PLUGIN_ROOT}/templates/profile.example.json` as the shape. Save after
each answer.

Ask in this order, one at a time:

1. Name, email, phone. (Email and phone go on the resume, confirm they want them there.)
2. Where they live, and whether they will relocate. Ask about remote separately.
3. What kind of work they want. Let them answer in their own words, then read
   back the job titles you would search for and let them correct you.
4. Links to their portfolio or work samples. **Links only. JobKit never makes art
   and never touches the files themselves.**
5. What has to be true for a job to be worth applying to. Then what makes one an
   instant no. These become the scoring rubric.
6. Anything they never want written on their behalf, words, phrases, claims.
   These become `banned_phrases`. The em dash character is pre-seeded in there
   already as a starting default; say so, and let them remove it if they want
   it back.

## Step 5, the baseline

`Baseline/` is the source of truth. **Every claim in every generated document must
trace back to something in here.** Nothing else is ever invented.

**`profile.json` is a convenience copy, not the source of truth.** It is an
intermediate summary, and intermediate summaries rot silently against the
artifacts they summarize. Two rules follow, and any other JobKit skill that
reads `profile.json` should carry them too:

- **When a check contradicts the profile, the artifact wins.** Correct
  `profile.json` to match `Baseline/`, never the other way around. Re-verify
  profile claims against the actual baseline and portfolio rather than
  trusting `profile.json` indefinitely, on a schedule or at every build.
- **Know which copy answers the question being asked.** "What did we send" is
  answered only by the sent copy already in the job folder. "What is true
  about the user" is answered only by `Baseline/` and the portfolio itself.
  They diverge by design; reading the wrong one produces a confident false
  finding.

Two paths:

- **They have a resume.** Open the folder for them first so "save it into
  Baseline" is a drag-and-drop, not a navigation puzzle: on macOS run
  `open "<workspace-path>/Baseline"`, on Windows `explorer "<workspace-path>\Baseline"`.
  Then ask them to save it there and tell you the filename. Read it. Read back
  what you found, and ask what is missing or wrong.
- **They do not.** Build one together. Walk through their history one role at a
  time. For each: what they did, what was actually theirs, what tools, what
  changed because of them. Write it to `Baseline/baseline_resume.txt`.

Say this to the user, in plain words, before you ask: on team projects, JobKit
needs to know exactly which part was theirs, because whatever the baseline says
is what every later resume and cover letter will claim, and nothing else.

**The single most dangerous field is "what part was yours."** If they worked on
backgrounds, the baseline says backgrounds. No document JobKit ever writes may
imply they did the whole piece, for example, credit for shots or scenes they
did not touch. Ask about it explicitly for every collaborative project, and
write the answer down verbatim.

## Step 6, first dashboard

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>"
```

This writes `CareerDashboard.html` in the workspace root and opens it in their
browser. Tell them to bookmark it, and tell them it is a plain file on their
computer that works offline, with no login and no server; the only thing it
fetches over the internet is two Google fonts for the visual style, and
nothing about them or their job search is ever uploaded. It updates itself
every time they add or change a job.

If they later want to add a page to the library (`guides/`), a guide can declare
its own category and icon with two meta tags, `<meta name="jobkit-category"
content="Craft">` and `<meta name="jobkit-icon" content="palette">`. Without
both, the dashboard guesses a category and icon from the title. The icon names
it understands are: `layers`, `send`, `clock`, `calendar`, `x-circle`,
`archive`, `cap`, `search`, `palette`, `camera`, `book`, `wrench`, `users`,
`sparkles`. An unrecognized name falls back to `book`.

## Step 7, tell them what to do next

Close with exactly three lines, no more:

1. **Paste me a job link** and I will take it from there.
2. **Double-click `CareerDashboard.html`** whenever you want to see where things stand.
3. When you have a minute, **read "Getting Started with JobKit"** in the
   dashboard's Library section; it is the full tour, including how to change
   how I behave for you.

Do not explain further. They will discover the rest by asking, and
`/jobkit-help` lists it.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
