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
        if entry is None:
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
        entry["history"].append(f"{today}: {previous} -> {lane}")
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
        if entry.get("lane") == "missing":
            continue
        entry["history"].append(f"{today}: folder not found -> missing")
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

    label = f"{status} ({closure_reason})" if closure_reason else status
    entry.setdefault("history", []).append(f"{today}: {previous} -> {label}")
    return entry


def resolve(book: dict, fragment: str) -> list:
    """Every folder matching fragment. The caller disambiguates - never guess."""
    needle = fragment.lower()
    return sorted(name for name in book if needle in name.lower())


def counts(book: dict) -> dict:
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
        lane = entry.get("lane", "missing")
        if lane in tally:
            tally[lane] += 1

        status = entry.get("status", "none")
        if status == "closed":
            # A rejection (or any other closure) is a historical fact. It does
            # not stop having happened because the folder was later archived
            # or deleted, so this counts regardless of current lane.
            reason = entry.get("closure_reason")
            if reason in tally:
                tally[reason] += 1
            continue

        # "Waiting to hear back" takes BOTH fields, because neither alone is
        # enough:
        #   status != "none"  -> it has been applied to and (the branch above
        #     already returned for "closed") not closed. But status only ever
        #     moves forward, so it never decays when the job stops being live.
        #   lane in (applied, missing) -> it is still somewhere consistent
        #     with a live application. A folder sitting in expired/skipped/
        #     not_applied/staged is not being waited on, whatever its stale
        #     status says. "missing" counts because nothing closed it - the
        #     folder was just tidied away, and dropping it would read as good
        #     news ("one fewer thing to wait on") when nothing resolved.
        # applied_date is deliberately NOT used: sync() leaves it unset when a
        # folder is first seen already in the applied lane, and that is still
        # a real open application.
        if status != "none" and lane in ("applied", "missing"):
            tally["in_flight"] += 1
            if status in ("interview_scheduled", "interviewed"):
                tally["interviews"] += 1

        # offers stays gated on current lane == "applied" - confirmed
        # correct by the reviewer, left untouched by the in_flight fix.
        if lane == "applied" and status == "offer":
            tally["offers"] += 1
    return tally


def days_since(date_str, today: str):
    if not date_str:
        return None
    return (date.fromisoformat(today) - date.fromisoformat(date_str)).days
