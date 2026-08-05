---
name: jobkit-learn
description: Use when the user corrects JobKit's behaviour, says "remember this" / "don't do that again" / "always do X from now on", when something surprising happened during intake or building (an extraction failed, an employer behaved unexpectedly, a draft was rejected), or at the end of a working session to ask whether anything is worth keeping. Harvests lessons into the workspace so they change future behaviour.
---

# Harvesting lessons

The plugin's files are read-only on this machine: they update only when its
maintainer publishes a new version. The workspace is where THIS user's search
gets smarter. Every other skill reads the workspace `CLAUDE.md` last and lets
it win, so a lesson written there is not a note, it is a behaviour change.

A lesson that is never written down will be relearned the expensive way. A
lesson written where nothing reads it is a note, not a lesson. Both files
below are read back on every task, which is the whole point.

## When to harvest, without being asked

- **The user corrects you.** "No, not like that", "stop doing X", "I told you
  before". A second correction of the same thing means the first one was
  never saved. Save it now.
- **An extraction surprised you.** A site changed, a recipe went stale, a new
  trick worked. This goes in `intake_site_recipes.md`, dated, next to that
  site's section.
- **An employer's behaviour taught something.** Their ATS never sends
  rejections; they reply in exactly 20 days; their postings omit salary but
  their sibling reqs carry it.
- **A draft was rejected.** WHY it was rejected is the lesson, in the user's
  words where possible.
- **End of a session with real work in it.** Ask once, in plain words:
  "Anything from today worth me remembering?" Accept "no" the first time.

## Where each kind of lesson goes

| Lesson is about | Write it to |
|---|---|
| A job site or board (how it behaves, what broke, what worked) | `intake_site_recipes.md`, in that site's section, dated |
| This user (preferences, corrections, their field's customs) | workspace `CLAUDE.md`, under `# Lessons learned`, dated |
| A specific employer | that job's `note.md`, AND `CLAUDE.md` if it generalises |

Format for `CLAUDE.md` lessons: one dated bullet, one or two sentences, with
the WHY. A rule without its reason gets deleted by the next person to read it.

## Rules

- **Confirm before writing a lesson drawn from inference.** A direct "remember
  this" needs no confirmation. Your own guess about what the user wants does:
  say the lesson back in one sentence and let them approve or fix it.
- **Never write personal facts anywhere but the workspace.** Lessons contain
  employer names, outcomes, and the user's history. They live in the
  workspace, which is local and private, and nowhere else.
- **Update, don't duplicate.** Before appending, check whether a lesson on the
  same subject already exists. Sharpen it in place and re-date it.
- **Delete lessons that turn out to be wrong.** A stale lesson is worse than
  none, because it is trusted.

## Sending lessons back to the maintainer (optional, never automatic)

Lessons about SITES generalise: a recipe fix for a public job board helps
every JobKit user. Lessons about the USER never leave the machine.

If the user wants to contribute site lessons upstream, copy the relevant
`intake_site_recipes.md` sections into a new file `recipes_to_share.md` in
the workspace, check it contains nothing personal (no employer application
history, no names, no outcomes; site recipes about public boards are fine),
show the user exactly what is in it, and tell them they can send that file
to whoever maintains their JobKit install. Nothing is ever sent anywhere by
this skill itself.

The reverse direction is the plugin update: when the maintainer publishes
improvements, the user's installed plugin picks them up through the normal
plugin update flow. The user's own `CLAUDE.md` and recipes are never touched
by an update, so nothing learned locally is ever lost to one.

## Last

Read the workspace `CLAUDE.md`. If anything there contradicts this skill, it wins.
