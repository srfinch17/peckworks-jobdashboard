# JobKit

A job-search workspace you drive by talking to Claude. Point it at an empty folder, answer some
questions about yourself, then paste job links at it. It builds a tracked folder per job with
tailored application materials, and a local dashboard that shows the whole pipeline.

Distributed as a **Claude plugin** (works in Claude Code and in Claude Desktop's Code tab).

The dashboard is a single self-contained HTML file you open by double-clicking. No server, no
build step, no internet. It is the visible payoff of the whole thing.

**Status: in development.** Design: `docs/superpowers/specs/2026-08-02-jobkit-design.md`.
Plan: `docs/superpowers/plans/2026-08-03-jobkit-core-loop.md`.

## What it reads on your machine

Everything JobKit writes stays inside the workspace folder you name. Two things are worth
stating plainly rather than burying:

**Reading history.** The library marks a guide as read by checking your local browser history
(Chrome, Chromium, Brave or Edge) for visits to guide files inside your workspace. It copies the
history database, keeps only `file://` visits under the workspace, and discards everything else
without recording it. Nothing is uploaded. The record lives in `reading_stats.json` in your own
workspace. If no browser is found it does nothing and says so. Turn it off by setting
`features.reading_stats` to `false` in `jobkit.json`.

**Job postings.** Fetching a posting contacts that employer's site or job board, the same as
opening the link yourself. Nothing about you is sent with it.

## Contributing

After cloning, re-create the pre-commit guard (git does not version hooks):

```sh
printf '#!/bin/sh\npython tools/no_personal_data.py || exit 1\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Then create `tools/forbidden_strings.local.txt` with one forbidden string per line.
The guard refuses to run without it.

## Origin

A genericized rebuild of a working private job-search workspace that has run ~95 applications
since early 2026. This repo takes the STRUCTURE and the LESSONS from it. It does not take the
content: no personal history, no company data, no sent resumes. See
`docs/LESSONS_HARVEST.md` for what transferred and what deliberately did not.

## First user

Benny, a graphics artist starting a job search on a Mac. Which means portfolio-first, not
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
