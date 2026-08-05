# Assessment

Written 2026-08-01, before any code. Read this before building.

## 1. What actually exists to harvest

The source workspace is not one program. It is roughly 3,500 lines of Python across 12 scripts, a
963-line CLAUDE.md of accumulated operating rules, ~49 generated HTML study pages, and a set of
JSON sidecars. Rough shape:

| Piece | Lines | Transfers? |
|---|---|---|
| `dashboard.py` | 1,710 | STRUCTURE yes, content no (half of it is a personal guide registry + theme) |
| `daily_feed.py` | 624 | NO for v1 (board scraping, see section 4) |
| `generate.py` | 406 | YES, closest to drop-in (txt to docx/pdf) |
| `job_tracker.py` | 319 | YES as a design, but REBUILD (its content-hash keying is a known defect) |
| `freshness_check.py` | 113 | YES |
| `resume_audit.py`, `sent_integrity.py`, `guard_sent_resumes.py` | 158 | YES as a pattern (mechanical guards), rules become config |
| `reading_stats.py` | 70 | **HARD NO** (2026-08-01). Mines Chrome history. Fine on your own machine, not something you ship to someone else. **Reversed 2026-08-04** at the owner's request: ships ON by default. Narrower than what was rejected here: only `file://` visits under the workspace are recorded, everything else is discarded unread, nothing is uploaded, the temp copy of the history database is deleted after each harvest, it is disclosed in the README and during setup, and it is switchable off via `features.reading_stats`. |
| CLAUDE.md operating rules | 963 | The most valuable asset here. See `LESSONS_HARVEST.md`. |

**The genuinely valuable thing is not the code. It is the 963 lines of hard-won rules.** Most of
that code is a weekend to rewrite cleanly. The rules took six months and several expensive
mistakes to learn.

## 2. The open gate: nobody has talked to the first user

This project was assessed once before (2026-07-19) and deliberately shelved pending a ~30 minute
requirements conversation with the first user. **That conversation still has not happened.**

Why it mattered then and still matters:

> A graphics artist's job search is portfolio-driven, not resume/ATS-driven. Resume tailoring is
> maybe 40% of what he needs. The other 60% is unknown until someone asks him.

Specifically unknown: where his leads come from (ArtStation / Behance / studio career pages /
Discord / agencies / gig platforms), what "an application" even consists of in his corner of the
industry, whether he has a portfolio site, and freelance versus studio mix.

**How this plan proceeds anyway, without guessing:** the engine is built domain-neutral and every
domain-specific thing becomes DATA, produced by an onboarding interview and stored in
`profile.json`. Job sources, application artifact types, what a "fit" means, the vocabulary on the
dashboard: all config. If the first user turns out to need something different, that is an edit to a JSON
file and a prompt, not a rewrite.

**The one thing that cannot be deferred:** the piece-selection feature (section 3). Build it and
it is the difference between a useful tool and a resume machine aimed at someone who does not
primarily need resumes.

## 3. The insight that makes this worth building for an artist

In the source workspace, the core intelligence is: *given a job posting and a baseline of
everything I have done, choose and phrase the 22 to 24 bullets that best match this posting.*

The artist equivalent is not "write bullets." It is:

> **Given this posting, which 6 to 10 portfolio pieces should lead, in what order, and why?**

Same engine. Same baseline-is-truth discipline. Same never-fabricate rule. Completely different
output. A studio art-director spends 40 seconds on a portfolio; which pieces are on top IS the
application. If this repo ships one thing that a resume tool would not, it should be that.

Corollary: the baseline for an artist is a **portfolio inventory**, not an employment history.
Per piece: title, file/link, medium, software used, role (solo / team / what part was yours),
year, client or personal, and tags. That inventory is the source of truth, and the
never-fabricate rule applies to it exactly as it applies to a resume.

## 4. Decisions made here, with reasons

**No board scraping. Paste-first intake.** The source workspace has a feed that hits LinkedIn
guest endpoints and a Dice API. Running that against your own account is your risk to take.
Shipping it to someone else's kid is a different risk posture: terms-of-service exposure that
lands on him, plus a fragility that breaks silently and teaches him to trust a broken tool. v1
takes pasted URLs and pasted text, and fetches ATS pages (Greenhouse, Lever, Ashby, Workday) via
their documented public JSON endpoints, which are stable and meant to be read.

**No Chrome history mining.** `reading_stats.py` is clever on your own machine and unacceptable in
a distributed tool. Dropped entirely.

**Amendment, 2026-08-04.** Reversed at the owner's request. The feature ships ON by default. What
makes the shipped version narrower than what was rejected above: only `file://` visits under the
workspace are recorded, everything else is discarded unread; nothing is uploaded; the temporary
copy of the history database is deleted after each harvest; it is disclosed in the README and
during setup; and it is switchable off via `features.reading_stats` in `jobkit.json`.

**The tool never generates art and never edits portfolio files.** It reads an inventory the user
writes. It can suggest ordering and selection. It cannot produce a "piece." Non-negotiable, both
ethically and because a tool that does this gets the user blacklisted in art communities.

**Rebuild the tracker, do not port it.** The source tracker keys its ledger on a content hash of
the posting file, which means editing that file orphans the job's status history. That is a
documented, permanent papercut. The new one keys on folder identity. Fix inherited defects rather
than inheriting them.

**Sent materials are immutable.** Once an application leaves the staging directory, its files are
never edited. This is enforced mechanically in the source workspace and should be here too. It is
what makes the record trustworthy later.

## 5. Scope reality

The request is "get it done today." Honest numbers:

- **Full parity with the source workspace: 2 to 3 weekends.** That estimate was made in July and
  nothing since has made it smaller.
- **A real, usable v0 that the first user could actually run: one focused evening**, if scoped to
  onboarding + intake + one build + a dashboard, with materials as .txt only.
- **docx/pdf generation adds an evening** on its own, mostly because the layout rules are fiddly
  and the source `generate.py` needs its personal assumptions stripped.

`BUILD_PLAN.md` scopes v0 to what genuinely fits in an evening and phases the rest. The risk of
trying to do all of it tonight is the usual one: three things at 70 percent instead of four at
100, and nothing the first user can actually open.

