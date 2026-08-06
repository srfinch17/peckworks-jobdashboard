---
name: build-application
description: Use when the user asks to build, write, tailor, draft, or prepare an application, resume, or cover letter for a specific job already in the workspace. Also use when they say "build the X one" or ask what to send to a company they have taken in.
---

# Building an application

## Read first, in this order

1. `profile.json` - who they are, their rules, their banned phrases
2. `Baseline/` - **the only source of truth for any claim**
3. The job folder's `original_job_posting.md` and `note.md`
4. The workspace `CLAUDE.md`

## Hard disqualifiers ABORT the build

Before writing anything, and again the moment new posting detail surfaces
mid-build: check the full posting against the profile's hard disqualifiers
(`deal_breakers`, location bounds, any license or credential requirement, anything
the user marked never). Board summaries hide disqualifiers that the full text
states plainly.

If one is hit, **STOP. Do not finish the build.** Instead:

1. Quote the disqualifying line from the posting, verbatim.
2. Move the job folder to the skip lane and write `skipped.md` with the quoted
   evidence and the reason, per the `job-intake` skill's skip format.
3. Report the abort to the user with the quote.

Completing a build on a disqualified posting is worse than failing, because it
looks like progress. A clean skip record with evidence is the successful outcome
here.

## The one rule everything else serves

**Every claim traces to the baseline.** No invented metrics, no invented tools, no
rounding a number up because it reads better, no skill they did not list. If the
posting wants something the baseline does not have, the resume does not claim it -
you say so to the user instead, as a gap.

A fabricated line survives right up until someone asks about it in a room.

## Re-derive every claim from source, never from a prior document

**Every claim about the user's own work re-derives from `Baseline/` and the
artifact inventory, NEVER from a previously generated document.** When
tailoring for a new job, read `Baseline/`, not the resume you built for the
last one. Generation chains compound drift: a verb shifts one synonym per
document, each hop reads like a faithful paraphrase, and eventually the claim
describes something that does not exist. The chain must stay depth one:
source to draft, never draft to draft.

**A distinctive claim is still a claim.** "The only," "the first," "the
largest" reads as enthusiasm, which is exactly why nobody checks it. Verify it
against whatever corpus would disprove it (the portfolio inventory, the
baseline's own history), or cut it.

**Hedging a credential the baseline states plainly is a defect in the other
direction.** Marking a real qualification as partial invents a weakness on
exactly the items a screener verifies. Framing defaults down for thin
evidence, per the rule above, and it never defaults down for solid evidence.
Both halves matter equally.

## Write the resume

Tailored `.txt` in the job folder, named
`Resume_<Company>_<Role>.txt`. Text is the source of truth; Word and PDF are
generated from it later.

Select and order what the baseline already contains to match what the posting asks
for. That is the entire job: selection and ordering, never invention.

## Framing defaults DOWN

The dangerous sentence is always surrounded by honest ones, which is exactly why it
gets through.

- Thin in the baseline -> "familiar with". **Never** "extensive experience in".
- One project -> "built a", never "years of".
- A comparison is fine. A comparison that becomes a claim is a fabrication.
  - Fine: "Similar to the environment work in my Redwood piece."
  - Fabrication: "Which builds on your years of environment art."

Warning: for creative work this binds hardest to role attribution. If the baseline
says they did backgrounds, no sentence may imply they did the whole piece. If it says
they were one of six, no sentence may read as though they led it. When the baseline is
vague about what part was theirs, **ask them** - do not choose the flattering reading.

## The scar rule

**Never cite a piece of work as support for a capability it does not
demonstrate.** Check what the baseline actually says happened on that piece
before citing it, not just that the piece exists. A project whose own record
shows a technique failing is not evidence that technique works.

A documented limit, stated first, is the most credible material available.
Honest process material, what was hard, what got cut, what the piece
deliberately does not attempt, reads as senior to anyone who knows the field.
Unqualified polish claims read as inflation instead. When the user is citing a
piece to support a claim, **ask them what was hard about it or what it
deliberately does not attempt**, and prefer that material over a superlative.
Leading with a measured limitation and deriving the approach from it can turn
the weakest-sounding claim into the strongest one.

## When a fact is corrected, fix the source artifact FIRST

**The template outranks the prompt.** When generation copies from a template,
exemplar, or prior artifact, a correction stated in conversation loses to a stale
value sitting in that artifact: in one measured run, a correction stated in bold
instructions was still overridden by the template's stale value in 3 of 7
generations. So when the user corrects a fact:

1. Fix it in the artifact the fact lives in (`Baseline/`, `profile.json`, a
   template) BEFORE generating anything.
2. Then sweep EVERY staged document in the workspace for the stale value, not
   just the new draft. The field sweep that produced this rule found two older
   staged documents still carrying the corrected value.
3. Sweep the way `checks.py` matches: whitespace-normalized (a line-wrapped
   instance is invisible to a plain search), and count the matches before and
   after so a failed fix fails loudly instead of silently no-opping.

**Off by default.** Write one only when the application requires it. Most are never
read, and skipping it keeps the build fast.

## Run the checks before you show them anything

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_document.py" "<job-folder>/Resume_<Company>_<Role>.txt" "<workspace>/profile.json"
```

If it exits nonzero, **fix the document and run it again.** Do not show the user a
draft that failed its own checks, and do not talk them out of a check. If a check
seems wrong, say so and let them decide.

One check needs judgment, not autopilot: `inflation()` also flags authorship verbs
like "led the team", "architected" and "spearheaded". These are not always lies -
the check cannot know who did what. Treat that flag as a prompt to verify the
sentence against the baseline, and ask the user if the baseline does not settle it.
Do not auto-rewrite the sentence; a useful prompt that gets silently overridden
every time is a prompt the user learns to ignore.

## Refresh the dashboard

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>" --no-open
```

## Then say the quiet part

The draft is theirs to defend. Tell them plainly: read it before it goes anywhere,
and if there is a line they could not talk about for two minutes in a room, cut it.
Something you helped write is not something they can defend live, and that gap is
where interviews are lost.

## Harvest before you finish

If this turn taught something durable (the user corrected you, a site or an
employer behaved unexpectedly, a draft was rejected for a stateable reason),
save the lesson NOW per the `jobkit-learn` skill: site lessons to
`intake_site_recipes.md`, lessons about the user to the workspace `CLAUDE.md`
under `# Lessons learned`, dated, with the why. A repeated correction means
the first one was never saved.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
