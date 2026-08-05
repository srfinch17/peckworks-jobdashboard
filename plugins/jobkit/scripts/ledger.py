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
import re
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


def records_for_company(book: dict, company: str) -> list:
    """Every folder for this employer, across every lane and status -
    applied, skipped, not_applied, expired, missing, all of it. Lesson 33:
    a duplicate application is invisible until someone lists a folder by
    hand on the eve of an interview; this is that listing, on demand.
    Case-insensitive; a folder whose entry is missing/malformed or has no
    company field just doesn't match, it never raises."""
    needle = company.strip().lower()
    if not needle:
        return []
    out = []
    for folder, entry in book.items():
        if not isinstance(entry, dict):
            continue
        entry_company = entry.get("company")
        if isinstance(entry_company, str) and entry_company.strip().lower() == needle:
            out.append(folder)
    return sorted(out)


_ROLE_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_role(role) -> str:
    """Lowercase, strip punctuation/spacing down to a bare run of
    alphanumerics, so "Senior VFX Artist", "senior-vfx-artist", and "Senior
    VFX  Artist " all collapse to the same key. A real title difference
    ("VFX Artist" vs "VFX Supervisor") still differs after this."""
    if not isinstance(role, str):
        return ""
    return _ROLE_NORMALIZE_RE.sub("", role.lower())


def duplicate_candidates(book: dict, posting_url: str = None, company: str = None,
                          role: str = None) -> list:
    """Folders that look like the same application as the given
    posting_url/company/role. posting_url is the listing id: an exact match
    on it is a duplicate on its own. Otherwise, company + a normalized role
    (see _normalize_role) must both match - company alone is too broad
    (every application to the same employer would "duplicate")."""
    hits = set()

    if posting_url:
        needle_url = posting_url.strip()
        if needle_url:
            for folder, entry in book.items():
                if not isinstance(entry, dict):
                    continue
                if entry.get("posting_url") == needle_url:
                    hits.add(folder)

    if company:
        norm_role = _normalize_role(role) if role else None
        for folder in records_for_company(book, company):
            if norm_role is None:
                continue  # company alone is not a duplicate signal
            entry = book[folder]
            if _normalize_role(entry.get("role")) == norm_role:
                hits.add(folder)

    return sorted(hits)


def response_intervals(book: dict, company: str) -> list:
    """Days from each application (and each completed interview round) to
    this employer's next OBSERVED response, for every folder for `company`.
    A response is a status change the employer caused: any move away from
    "awaiting", or a close with closure_reason "rejected". closed_no_response
    is the absence of a response and never enters the sample (lesson 34).

    Reads the history log sync()/set_status() already write - no new state
    to keep in sync, and no schema drift risk from a shape only this
    function would care about.

    ponytail: counts one interval per application (apply -> first employer
    response), not a separate interval per completed interview round -
    the per-job baseline this feeds (days_since_last_signal) only ever
    needs one active clock per job at a time, so a second clock per round
    would be tracked but never read. Extend to per-round intervals if a
    future feature reads mid-pipeline round timing specifically.
    """
    intervals = []
    for folder in records_for_company(book, company):
        entry = book[folder]
        applied = entry.get("applied_date")
        if not applied:
            continue
        history = entry.get("history", [])
        for line in history:
            days = _response_delay(applied, line)
            if days is not None:
                intervals.append(days)
                break  # one response per application counted once
    return intervals


_HISTORY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}): (\w+) -> (\w+)(?: \((\w+)\))?")


def _is_employer_response(previous, new, reason) -> bool:
    """A response is a status change the employer caused: any move away
    from awaiting, EXCEPT a close - a close only counts when its reason is
    "rejected". closed_no_response is the absence of a response by
    definition, and withdrawn is the applicant's own move, not theirs."""
    if previous != "awaiting":
        return False
    if new == "closed":
        return reason == "rejected"
    return True


def _response_delay(applied_date: str, history_line: str):
    """The day count from applied_date to `history_line`'s date, if that
    line is an employer-caused response (see _is_employer_response); None
    otherwise, or on a bad date."""
    match = _HISTORY_RE.match(history_line)
    if not match:
        return None
    when, previous, new, reason = match.groups()
    if not _is_employer_response(previous, new, reason):
        return None
    return days_since(applied_date, when)


def days_since_last_signal(entry: dict, today: str):
    """Days since the most recent real signal on this job: the later of
    applied_date and the last employer-caused status change (same test as
    response_intervals - closed_no_response is not a signal). None (never
    0) when there is no applied_date; guessing a start date is exactly what
    this module refuses to do elsewhere."""
    applied = entry.get("applied_date")
    if not applied:
        return None
    last = applied
    for line in entry.get("history", []):
        match = _HISTORY_RE.match(line)
        if not match:
            continue
        when, previous, new, reason = match.groups()
        if not _is_employer_response(previous, new, reason):
            continue
        if when > last:
            last = when
    return days_since(last, today)


def days_since(date_str, today: str):
    """None for an unset, non-string, or unparseable date - a hand-typed
    typo like "2026-13-45" must degrade a single chip, not crash the build."""
    if not date_str:
        return None
    try:
        return (date.fromisoformat(today) - date.fromisoformat(date_str)).days
    except (ValueError, TypeError):
        return None
