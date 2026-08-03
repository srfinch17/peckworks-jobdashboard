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
    if closure_reason is not None:
        entry["closure_reason"] = closure_reason

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

        if lane != "applied":
            # Still "waiting to hear" only makes sense while the folder is
            # actually in the applied lane. A vanished folder that was never
            # closed is not a confirmed in-flight application anymore - it's
            # unknown, so it is excluded rather than guessed at.
            continue

        tally["in_flight"] += 1
        if status in ("interview_scheduled", "interviewed"):
            tally["interviews"] += 1
        elif status == "offer":
            tally["offers"] += 1
    return tally


def days_since(date_str, today: str):
    if not date_str:
        return None
    return (date.fromisoformat(today) - date.fromisoformat(date_str)).days
