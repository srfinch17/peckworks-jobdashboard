#!/usr/bin/env python3
"""The job ledger.

Keyed on FOLDER NAME. Never on a hash of a file that gets edited - that pattern
orphans a job's history the moment someone adds a note to it.

Two rules this module enforces mechanically:
  1. applied_date is set ONLY when a folder is observed moving into the applied
     lane. It is never backfilled from a later status event and never defaulted
     to today. Unknown stays unset.
  2. A closed job carries a closure_reason. "They rejected me" and "I gave up
     after 82 days" are different facts and one field cannot hold both.

first_seen is different in kind from applied_date: the moment sync() first
learns of a folder IS an observation, so setting it at creation is honest.
It is set once and never touched again, and is never backfilled onto an
entry that predates the field.
"""
import json
import os
from datetime import date
from pathlib import Path

STATUSES = (
    "none",
    "awaiting",
    "phone_screen",
    "interview_scheduled",
    "interviewed",
    "offer",
    "closed",
)

CLOSURE_REASONS = ("rejected", "closed_no_response", "withdrawn")

# Lanes that mean "I have not applied to this." A status change that implies
# an application (anything but "none") is refused while a folder sits here -
# see set_status. staged means "not yet"; skipped/not_applied mean "chose
# not to." expired is deliberately absent: a job that WAS applied to and
# then died is archived there, and that history must survive the move.
NOT_APPLIED_LANES = ("staged", "skipped", "not_applied")

INTERVIEW_STATUSES = ("phone_screen", "interview_scheduled", "interviewed")


def load(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def save(path, book: dict) -> None:
    """Write atomically. A truncated ledger is unrecoverable for a non-technical user."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(book, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def sync(book: dict, on_disk: dict, today: str) -> tuple[dict, list]:
    """Reconcile the ledger against what is actually on disk.

    on_disk maps folder name -> lane. Returns (book, events).
    """
    events = []

    for folder, lane in on_disk.items():
        entry = book.get(folder)
        if not isinstance(entry, dict):
            # Missing, or a corrupted record (e.g. hand-edited into a plain
            # string) - either way nothing in it can be trusted, so it is
            # treated as never seen before rather than crashing the sync.
            entry = {
                "lane": lane,
                "status": "none",
                "first_seen": today,
                "history": [f"{today}: first seen in {lane}"],
            }
            if lane == "applied":
                # We never observed the move, so the apply date is unknown.
                # Leave it unset - it must never be guessed.
                entry["status"] = "awaiting"
            book[folder] = entry
            events.append(("new", folder, lane))
            continue

        previous = entry.get("lane")
        if previous == lane:
            continue

        entry["lane"] = lane
        entry.setdefault("history", []).append(f"{today}: {previous} -> {lane}")
        events.append(("moved", folder, lane))

        if lane == "applied" and "applied_date" not in entry:
            # An OBSERVED move into applied is a real signal. This is the only
            # place applied_date is ever set automatically.
            entry["applied_date"] = today
            if entry.get("status") in ("none", None):
                entry["status"] = "awaiting"

    for folder, entry in book.items():
        if folder in on_disk:
            continue
        if not isinstance(entry, dict):
            continue  # corrupted record for a folder that isn't on disk either; nothing to do
        if entry.get("lane") == "missing":
            continue
        entry.setdefault("history", []).append(f"{today}: folder not found -> missing")
        entry["lane"] = "missing"
        events.append(("missing", folder, "missing"))

    return book, events


def set_status(book: dict, folder: str, status: str, today: str, closure_reason=None) -> dict:
    if folder not in book:
        raise KeyError(folder)
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}; valid: {', '.join(STATUSES)}")
    if status == "closed":
        if closure_reason not in CLOSURE_REASONS:
            raise ValueError(
                "closing a job needs a closure_reason: " + ", ".join(CLOSURE_REASONS)
            )
    elif closure_reason is not None:
        raise ValueError("closure_reason only applies when status is 'closed'")

    entry = book[folder]
    if status != "none" and entry.get("lane") in NOT_APPLIED_LANES:
        # This is the source of the impossible ribbon: a status implying an
        # application (awaiting, interviewed, closed/rejected, ...) hand-set
        # on a folder sitting in a lane that means "never applied to it."
        raise ValueError(
            f"cannot set status {status!r} on {folder!r}: it is in the "
            f"{entry.get('lane')!r} lane, which means it was never applied to"
        )
    previous = entry.get("status", "none")
    entry["status"] = status
    # status_date tracks the most recent status change, e.g. the date a job
    # became interview_scheduled. Not to be confused with applied_date, which
    # tracks one specific lane move and follows its own stricter rule above.
    entry["status_date"] = today
    if closure_reason is not None:
        entry["closure_reason"] = closure_reason
    if status == "closed":
        entry["closed_date"] = today
    # These two are historical facts, same reasoning as closure_reason: an
    # interview or an offer does not stop having happened just because the
    # job later closes or its folder moves on. Set once, never cleared.
    if status in INTERVIEW_STATUSES:
        entry["ever_interviewed"] = True
    if status == "offer":
        entry["ever_offer"] = True

    label = f"{status} ({closure_reason})" if closure_reason else status
    entry.setdefault("history", []).append(f"{today}: {previous} -> {label}")
    return entry


def resolve(book: dict, fragment: str) -> list:
    """Every folder matching fragment. The caller disambiguates - never guess."""
    needle = fragment.lower()
    return sorted(name for name in book if needle in name.lower())


def counts(book: dict) -> dict:
    # Two axes live in here on purpose, and the fix is to never let them
    # contradict each other:
    #   - "WHERE is it now": staged/not_applied/skipped/expired/missing/
    #     in_flight. Reset by a lane move; this is current placement.
    #   - "WHAT has happened to it, ever": applied/interviews/offers/
    #     rejected/closed_no_response/withdrawn. A fact, once true, stays
    #     true no matter where the folder sits later - archiving a rejected
    #     job into "expired" must not make it un-applied-to.
    # Before this fix "applied" was axis 1 (current lane) while "rejected"
    # was axis 2 (historical), so a rejected-then-archived job could show
    # 0 applied and 1 rejected: rejections from jobs the board claims were
    # never applied to. Every WHAT-happened field below is now keyed off
    # `status`, which set_status only ever advances past "none" for a
    # folder that is (or was, per NOT_APPLIED_LANES) actually applied to.
    tally = {
        "staged": 0,
        "applied": 0,
        "not_applied": 0,
        "skipped": 0,
        "expired": 0,
        "missing": 0,
        "in_flight": 0,
        "interviews": 0,
        "offers": 0,
        "rejected": 0,
        "closed_no_response": 0,
        "withdrawn": 0,
    }
    for entry in book.values():
        if not isinstance(entry, dict):
            continue  # a corrupted record; nothing safe to count here
        lane = entry.get("lane", "missing")
        if lane in tally and lane != "applied":
            tally[lane] += 1

        status = entry.get("status", "none")
        if status != "none":
            # A real application happened at some point - set_status
            # refuses to reach here for a folder that never left staged/
            # skipped/not_applied, and sync() only sets it for an observed
            # or first-seen move into "applied". Historical, like rejected.
            tally["applied"] += 1
        if entry.get("ever_interviewed"):
            tally["interviews"] += 1
        if entry.get("ever_offer"):
            tally["offers"] += 1

        if status == "closed":
            # A rejection (or any other closure) is a historical fact. It does
            # not stop having happened because the folder was later archived
            # or deleted, so this counts regardless of current lane.
            reason = entry.get("closure_reason")
            if reason in tally:
                tally[reason] += 1
            continue

        # "Waiting to hear back" is current placement, not a historical fact:
        # it must decay once the job resolves or the folder is filed away
        # somewhere that no longer means "still open" (expired/skipped/
        # not_applied/staged). "missing" still counts because nothing
        # resolved it - the folder was just tidied away, and dropping it
        # would read as good news ("one fewer thing to wait on") when
        # nothing actually happened.
        if status != "none" and lane in ("applied", "missing"):
            tally["in_flight"] += 1
    return tally


def days_since(date_str, today: str):
    """None for an unset, non-string, or unparseable date - a hand-typed
    typo like "2026-13-45" must degrade a single chip, not crash the build."""
    if not date_str:
        return None
    try:
        return (date.fromisoformat(today) - date.fromisoformat(date_str)).days
    except (ValueError, TypeError):
        return None
