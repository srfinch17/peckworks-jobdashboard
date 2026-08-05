---
name: track-application
description: Use whenever the user reports something happening to a job already in the workspace - "I applied to the X one", "they rejected me", pasting a rejection email, "I got an interview", "they want to schedule a call", "it's Tuesday at 9", "I haven't heard back from X", "the interview happened", "I got an offer", "I withdrew" or "I pulled out". This is the only path that should ever touch job_ledger.json.
---

# Recording what happened to a job

Every status change goes through `job_status.py`, never by hand-editing
`job_ledger.json`. That file enforces the status whitelist, requires a
`closure_reason` on anything closed, refuses a status on a job that was never
applied to, and never lets a date get invented. Editing the JSON directly
bypasses all four guards at once.

If there is no `jobkit.json` in the workspace, run `jobkit-setup` first.

## Find the job first

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" <status> [options]
```

`<fragment>` is matched against every folder name. If more than one job
matches, the script lists them and refuses to guess - ask the user which one
they mean and run it again with a fragment specific enough to pick one. If
nothing matches, say so; do not fall back to editing anything by hand.

## What the user says, mapped to a call

| They say | Do this |
|---|---|
| "I applied to the X one" | `--applied` (see below) |
| pastes a rejection email | save the email into the job folder, then `closed --reason rejected` |
| "no word in two months" / "I haven't heard back" | `closed --reason closed_no_response` |
| "they want to schedule an interview" | `interview_scheduled`, leave the date off |
| "it's Tuesday at 9" (confirming a slot) | re-run `interview_scheduled` with `--date <that date>` once it is a real confirmed date |
| "the interview happened" | `interviewed`, then write a debrief to the top of the job's `note.md` |
| "I got an offer" | `offer` |
| "I pulled out" / "I withdrew" | `closed --reason withdrawn` |

## "I applied to the X one"

Run with `--applied`, not with a hand-set status or a hand-set date:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" --applied
```

This moves the job's folder into the applied lane and lets `job_status.py`
re-sync the ledger immediately, so the move is OBSERVED and `applied_date` is
stamped honestly - the same rule `sync()` enforces everywhere else. **Never
pass `--date` here to set an apply date yourself.** If the user says they
applied on a specific earlier day and the folder is only moving now, tell them
the dashboard will show today's date because that is the day the move was
observed, and that is more honest than a typed-in guess.

## Rejection email

Save the pasted email verbatim into the job's folder (for example
`rejection_email.txt`) before or right after recording the status, so the
record survives even if the ledger entry is ever edited or the conversation is
lost. Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" closed --reason rejected
```

## Silence is not a rejection

**A closure by silence must never be recorded as `rejected`.** Use
`closed_no_response` instead:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" closed --reason closed_no_response
```

The reasoning matters more than the rule: a rejection is something an
employer decided and told the person. Silence is something that did not
happen. A first-time job seeker reads their own rejection count as a verdict
on themselves - if their own inference that a company has gone quiet gets
folded into the same number as an actual "no", the search reads as far more
brutal than it was. Keep the two facts in two buckets even though both feel
the same in the moment.

## Interview scheduled - never invent the date

**A proposed slot is not a confirmed one.** When someone first says an
interview is being arranged, record only the stage, with no date:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" interview_scheduled
```

Tell the user out loud that it shows as pending until a real time is locked
in. Only when they confirm an actual slot ("it's Tuesday at 9") do you re-run
the same command with `--date` set to that confirmed date. Guessing a
plausible date to fill the gap is exactly the failure this whole system
exists to prevent - an unknown date stays a visible gap on the dashboard, not
a quiet lie.

## The interview happened

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" interviewed
```

Then write a short debrief to the TOP of that job folder's `note.md` (how it
went, what came up, what to follow up on) - prepended, not appended, so the
freshest read is the first thing anyone sees.

## Offer

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" offer
```

## Withdrawn

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/job_status.py" "<workspace-path>" "<fragment>" closed --reason withdrawn
```

## State the signal tier, no hype

When reporting any of this back to the user, name how strong the signal
actually is - do not react to a weak signal as if it were a strong one. Rising
tiers, weakest to strongest:

1. A form or automated email ("your application has been received").
2. A recruiter or agency contact.
3. A named human at the company saying something specific.
4. An actual hiring-manager conversation.
5. A portfolio review or technical round.
6. An offer.

No excitement language below tier 4. "Someone opened your resume" and "the
hiring manager wants to talk" are not the same event, and treating them the
same teaches the user to expect a callback every time a form email arrives.

## Refresh the dashboard

Always, at the end of the turn, whatever changed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py" "<workspace-path>" --no-open
```

## Harvest before you finish

If this turn taught something durable (the user corrected you, a site or an
employer behaved unexpectedly, a draft was rejected for a stateable reason),
save the lesson NOW per the `jobkit-learn` skill: site lessons to
`intake_site_recipes.md`, lessons about the user to the workspace `CLAUDE.md`
under `# Lessons learned`, dated, with the why. A repeated correction means
the first one was never saved.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
