# Lessons Harvest

Every operating rule from the source workspace, with a decision. This file is the actual product.
The code is a weekend; these rules cost six months and several expensive mistakes.

Legend: **TRANSFER** = ships as-is. **ADAPT** = the principle ships, the specifics become config.
**DROP** = deliberately excluded, reason given.

---

## Tier 0: the rules that prevent real damage

### 1. The baseline is the only source of truth. Never fabricate. **TRANSFER**
Every claim in every generated document must trace to something the user actually recorded about
themselves. No invented metrics, no invented skills, no rounding a number up because it reads
better. For an artist this binds to the portfolio inventory: never claim a role on a piece that
the inventory does not state.

*Why it is tier 0:* a fabricated line survives right up until someone asks about it in a room.

### 2. Provenance is not competence. **TRANSFER, and it matters MORE here**
Something the tool helped produce is not something the user can defend live. The source workspace
learned this by losing a final-round interview where a demo could not be defended.

For a graphics artist the stakes are higher, not lower, because "did you actually make this" is
the central trust question in art hiring right now. Two hard rules follow:
- The tool never generates creative work.
- Any document the tool drafts is a draft the user must be able to speak to in their own words.

### 3. Sent materials are immutable. **TRANSFER**
Once an application moves to `sent/`, its files are never edited. That directory is the record of
what was actually submitted. Enforce with a hook, not a reminder.

### 4. Poster is not the employer. **ADAPT**
An agency, staffing firm, aggregator, or reposter distorts a listing: wrong salary in both
directions, mis-attributed employer, dead reqs left up, unnamed end client. In the source
workspace this held 6 out of 6 times.

Artist-flavored version of the same tell: content mills, "exposure" postings, contests dressed as
jobs, agencies that will not name the studio, and rights-grab terms. The intermediary gets named
in the same breath as the lead, never below the fold.

### 5. Signal tiers, stated out loud. **TRANSFER, high value for a first job search**
An automated email is not a callback. Rank every event and say the tier when reporting it:

> form/automated email < recruiter or agency contact < a named human scheduling with specifics <
> hiring manager conversation < portfolio review or test < offer

No excitement language below the hiring-manager tier. The origin of this rule was a templated
staffing-firm email getting framed as a breakthrough, and the crash when the truth landed. For
someone early in their career, riding that rollercoaster is genuinely costly.

### 6. Never fabricate a date or a status. **TRANSFER**
If the true applied-date is unknown, it stays unset and the card sinks to the bottom. It never
gets a plausible-looking guess. The source workspace stamped 23 jobs with a wrong date this way
once and had to unwind all of it.

Corollary now written into the design: the ledger distinguishes "they said no" from "we concluded
no after long silence." One value cannot hold both.

---

## Tier 1: rules that keep the data trustworthy

### 7. Guards, not reminders. **TRANSFER as the core design pattern**
Every rule that got violated repeatedly in the source workspace was one that lived in prose. Every
rule that stopped being violated became a mechanical check: a sanitizer at build time, an envelope
check that refuses to generate, a hook that denies a write. Where this repo states a rule, it
should also state the check that enforces it.

### 8. The format envelope. **TRANSFER**
Refuse to generate a document outside stated bounds (page count, section count, length). Caught a
real 8-page resume that would otherwise have been sent.

### 9. Source URL on line 1 of the posting file. **TRANSFER**
Trivial, and it is what makes every downstream link work.

### 10. Postings die fast. **TRANSFER**
Days, not weeks. Verify before any submission push. Default action on a confirmed-dead posting is
MOVE to `expired/`, never delete, because the tailored materials stay reusable. Never retire on a
guess: an inconclusive check keeps the job.

### 11. A uniform confident result is usually a broken instrument. **TRANSFER as a testing rule**
An expired-detector once reported all 8 postings dead. A control test against a known-live posting
produced the identical result: the detector was matching template strings. It would have destroyed
six built folders. **Any detector gets a control test against a known-good input before its output
is trusted.**

### 12. Do not key a record on the content of a file that gets edited. **TRANSFER as a fix**
The source tracker hashes the posting file. Editing that file orphans the job's history. Known,
permanent, worked around rather than fixed. Here: key on folder identity from the start.

### 13. Search targets versus answers. **TRANSFER as an internal build rule**
Never tell a subprocess (or a subagent) to go find its input in a large file. Hand it the slice.
The source workspace measured this: pointing 17 agents at a 207,000-character file cost roughly
121,000 tokens per output; per-job slices cut it to 66,000.

---

## Tier 2: workflow shape

### 14. Directory-as-status. **TRANSFER**
A job's folder location IS its state (staging, sent, declined, expired, skipped). Moving a folder
is the state change. No parallel bookkeeping to drift.

### 15. Score-prefixed folder names. **ADAPT**
Fit score in the folder name makes the filesystem self-sorting. Keep, but the scoring rubric comes
from `profile.json` since "fit" means something different per field.

### 16. Record the skip, not just the build. **TRANSFER**
When a job is passed on, write the reason. The skip log is how a search gets smarter about what to
stop chasing.

### 17. Site recipes accumulate. **TRANSFER, this is the self-improvement mechanism**
One markdown file, one section per site, updated on both success and failure with a date. Readable
and editable by the user. See `ARCHITECTURE.md` section 5.

### 18. Announce which extraction tier ran. **TRANSFER**
The user should always know whether the data came from their paste, a structured endpoint, or a
best-effort browser read, because that determines how much to trust it.

### 19. Report before deleting. **TRANSFER**
Any cleanup operation shows a categorized list and waits for a yes. Applies to the tool's own
housekeeping.

---

## Tier 3: adapted, because they encode one person's specifics

### 20. Style and banned-phrase rules. **ADAPT**
The source workspace bans a specific punctuation mark and a list of phrases, enforced by a
build-time sanitizer. The MECHANISM ships; the LIST becomes `profile.json` data the user owns.

### 21. Location and relocation policy. **ADAPT**
The source workspace has an intricate rule about which city appears on which document. Generalize
to: a home location, an optional temporary location that is never disclosed, and a per-target
relocation stance.

### 22. Document format standard. **ADAPT**
A fixed section list and layout template. Ships as a template pair: engineer-style, and
artist-style (shorter, portfolio-led, since the portfolio is the real artifact).

### 23. Cover letters are off by default. **TRANSFER**
Generated only when the application requires one. Most are never read. Keeps the build fast.

---

## Added 2026-08-01, later the same day

Learned or sharpened after the first four sections were written. Numbered on from 23 so nothing
above needs renumbering; the tier each belongs to is marked.

### 24. A denial closed by SILENCE is not a received rejection, and one field cannot hold both. **TRANSFER, tier 0**
The source ledger stores `denied` and loses whether the employer said no or whether the user
concluded no after a long silence. Both happened on the same day: one real rejection at 14 days,
one inference after 82 days. **Design fix for JobKit: store the closure REASON alongside the
status** (`rejected` / `closed_no_response` / `withdrawn`), not just the status.

Why it is tier 0: a job seeker reads their own denied count as feedback about themselves. Counting
inferences as employer decisions makes a search feel worse than it was, and this tool is going to a
young person doing this for the first time.

Two dependent rules:
- **Check whether that employer's ATS sends dispositions AT ALL.** If a company sent one at 14 days
  on one req and nothing across 82 days on another, long silence from them means an application
  that fell out of the process, not a pending decision. Treat 30+ days as functionally closed.
- **Stale open applications inflate the in-flight count and quietly distort how the search feels.**
  The dashboard should surface "no response in N days" rather than letting them sit in the active
  lane forever.

### 25. The rendered page being a JS shell says NOTHING about whether the job is live. **TRANSFER, tier 1**
Fetching an ADP posting returns a browser-compatibility notice and no content. The naive read is
"dead posting." The truth was a live req whose data sits behind an unauthenticated JSON API keyed
on the same ID already present in the apply URL.

**Rule: a JS shell is an EXTRACTION failure, never a freshness verdict.** Report it as
"could not read," never as expired, and never let it trigger a move to `expired/`. This is the same
class of error as lesson 11 (a confident uniform result is usually a broken instrument).

### 26. When a posting omits a fact, the same employer's OTHER postings usually state it. **TRANSFER, tier 1**
The highest-value trick found this session. A job listed no office location anywhere in its text
and had a deliberately blank location field. Its four US offices, and a written
remote-consideration policy, were spelled out in the same employer's *other* engineering req on the
same ATS.

**Two things fall out.** First, a single blank field is ambiguous; a blank field sitting next to
five populated ones is a decision, and the difference is only visible if you pull the whole list.
Second, most ATS APIs return every open req in one call, so this costs one extra request.

**Source tiering that follows from it:** the employer's own ATS is truth; a board listing is a
copy that may be stale, re-titled, or mis-attributed. When they disagree, the ATS wins. When the
board is silent, ask the ATS before asking the user.

### 27. The tool must not inflate the user's competence, and the leak is in ANALOGIES. **TRANSFER, tier 0**
Same defect as lesson 2 (provenance is not competence), but pointed at generated prose rather than
at the user's self-assessment. A tool writing "which builds on your years of X" where the baseline
records one small project has fabricated a credential, and the surrounding sentence is usually
honest, which is exactly why it slips through.

**Rules for anything this tool drafts:**
- Framing defaults DOWN. If the baseline is thin on something, the draft says "familiar with,"
  never "extensive experience in."
- **Grep generated drafts for the sentence shape where a comparison becomes a claim.** "Similar to
  the piece you made for X" is fine. "Which is years of your life" is a fabrication.
- **For an artist this binds hardest to role attribution on a portfolio piece.** If the inventory
  says he did backgrounds, the tool never lets a draft imply he did the whole piece. "What part was
  yours" is the single most dangerous field in the entire baseline.

### 28. Practice-interview personas are worth a later phase. **NOT v1, but log it**
Building a research-grounded interviewer persona and running a mock round out loud proved
genuinely useful in the source workspace (it matched a real round once, n=1). A far-future JobKit
feature, not v1, and it would need the same honesty framing: practice the ANSWERS, do not treat
the simulation as a prediction of the QUESTIONS.

## DROPPED, with reasons

| Rule / feature | Why it does not ship |
|---|---|
| Browser-history mining for reading stats | Reads someone's browsing history. Fine on your own machine; not something you ship to another person. **Reversed 2026-08-04** at the owner's request: ships ON by default, narrowed to only `file://` visits under the workspace, everything else discarded unread, nothing uploaded, the temp copy deleted after each harvest, disclosed in the README and during setup, switchable off via `features.reading_stats`. |
| Automated board feed (LinkedIn guest endpoints, Dice API) | Terms-of-service exposure transfers to the user, and it breaks silently. Paste-first instead. |
| Company registry of a specific geography | Entirely personal data. |
| Study-guide library and its HTML generator | A genuinely good idea and a separate product. The dashboard reserves a slot. |
| Named review-board personas | They are real people from one person's interviews. |
| Company-specific interview prep pages | Same. |
| Hardware/LED status hooks | Unrelated to job search. |
| Every specific employer, role, resume, and interview note | Nothing personal enters this repo. Build from structure, never copy-and-redact. |

---

## The one-line version

> The baseline is the only truth, the tool never makes the art, guards beat reminders, an
> intermediary distorts everything it touches, a form email is not a callback, and an instrument
> that agrees with itself too confidently is broken.
