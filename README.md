# JobKit

A job-search workspace you drive by talking to Claude. Point it at an empty folder, answer some
questions about yourself, then paste job links at it. It builds a tracked folder per job with
tailored application materials, and a local dashboard that shows the whole pipeline.

## Install

1. In Claude Code or Claude Desktop's Code tab, run:
   ```
   /plugin marketplace add srfinch17/peckworks-jobdashboard
   /plugin install jobkit@peckworks-jobdashboard
   ```
2. Say: **"set up my job search in ~/JobDashboard"**
3. Paste a job link.

That's it. The dashboard opens itself the first time and updates every time you add or change
a job.

## Status

**In development.** Design: `docs/superpowers/specs/2026-08-02-jobkit-design.md`.
Plan: `docs/superpowers/plans/2026-08-03-jobkit-core-loop.md`.

The dashboard is a single self-contained HTML file you open by double-clicking: no server, no
build step, and it works offline (the only outbound request is fetching two Google fonts for the
visual identity; nothing about you or your job data is ever sent anywhere). It is the visible
payoff of the whole thing.

## What it reads on your machine

Everything JobKit writes stays inside the workspace folder you name. Two things are worth
stating plainly rather than burying:

**Reading history.** The library marks a guide as read by checking your local browser history
(Chrome, Chromium, Brave or Edge) for visits to guide files inside your workspace. It copies the
history database, keeps only `file://` visits under the workspace, and discards everything else
without recording it. Nothing is uploaded. The record lives in `reading_stats.json` in your own
workspace. If no supported browser is found it quietly does nothing (Safari is not
supported; it does not let other apps read its history). Turn it off by setting
`features.reading_stats` to `false` in `jobkit.json`.

**Job postings.** Fetching a posting contacts that employer's site or job board, the same as
opening the link yourself. Nothing about you is sent with it.

## Origin

A genericized rebuild of a working private job-search workspace that has run ~95 applications
since early 2026. This repo takes the STRUCTURE and the LESSONS from it. It does not take the
content: no personal history, no company data, no sent resumes. See
`docs/LESSONS_HARVEST.md` for what transferred and what deliberately did not.

## First user

The first user is a graphics artist starting a job search on a Mac. That means portfolio-first, not
resume-first, and it means a hard rule that runs through the whole design:

> **The tool never makes the art. It handles the admin around the art.**

No image generation, no touching portfolio files, no writing anything that claims to be the
user's creative work. Art communities are (rightly) wary of AI, and a tool that blurs that line
is worse than no tool.

## Docs

| File | What it is |
|---|---|
| `docs/ASSESSMENT.md` | Honest read: what transfers, what does not, the open requirements gate, real scope |
| `docs/ARCHITECTURE.md` | Plugin shape, distribution, browser strategy, verified platform facts |
| `docs/BUILD_PLAN.md` | Phased build, with a v0 slice scoped to a single evening |
| `docs/LESSONS_HARVEST.md` | Every rule from the source workspace, with a transfer / adapt / drop decision |

## Contributing

After cloning, re-create the pre-commit guard (git does not version hooks):

```sh
printf '#!/bin/sh\npython3 tools/no_personal_data.py || exit 1\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Then create `tools/forbidden_strings.local.txt` with one forbidden string per line.
The guard refuses to run without it.
