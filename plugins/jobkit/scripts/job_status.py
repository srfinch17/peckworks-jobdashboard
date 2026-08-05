#!/usr/bin/env python3
"""Change a job's status through ledger.set_status - the only front door.

Usage:
  python3 job_status.py <workspace> <folder-fragment> <status> [--reason R] [--date YYYY-MM-DD] [--move]
  python3 job_status.py <workspace> <folder-fragment> --applied [--date YYYY-MM-DD]
  python3 job_status.py <workspace> --company <name>

--company is the lesson-33 pre-interview check: every record for that
employer, across every lane and status (including skipped/not_applied/
expired/missing), so a duplicate application shows up before the interview
does instead of on the eve of it.

<status> is one of: awaiting, phone_screen, interview_scheduled, interviewed,
offer, closed. "closed" requires --reason (rejected, closed_no_response, or
withdrawn) - ledger.set_status refuses it otherwise, and this script prints
that refusal plainly rather than reimplementing the rule.

--date defaults to today. It is never invented for anything else - an unset
applied_date stays unset.

Applying is not a status change, it is a folder move: pass --applied (or
"applied" as the status together with --move) to move the folder into the
applied lane. This never sets applied_date directly; the move is re-synced
immediately afterward so ledger.sync() OBSERVES it and stamps applied_date
honestly, the same as any other move. Closing never moves a folder - a closed
job stays in the applied lane with its closure_reason.

Exit 0 on success. Exit 1 on a user error: no match, an ambiguous match, or a
change the ledger itself refuses (bad status, missing closure_reason, wrong
lane). Exit 2 on a usage or workspace error.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import dashboard
import ledger
import workspace


def _resolve_one(book: dict, fragment: str):
    """(folder, None) on exactly one match, else (None, message). Never guesses."""
    matches = ledger.resolve(book, fragment)
    if not matches:
        return None, f"No job folder matches '{fragment}'."
    if len(matches) > 1:
        lines = [f"'{fragment}' matches {len(matches)} jobs. Be more specific:"]
        lines += [f"  {i}. {m}" for i, m in enumerate(matches, 1)]
        return None, "\n".join(lines)
    return matches[0], None


def _apply_move(root: Path, config: dict, book: dict, on_disk: dict, folder: str):
    """Move folder's directory into the applied lane. Returns an error string, or None."""
    current_lane = book[folder].get("lane", "missing")
    if current_lane == "applied":
        return f"{folder} is already in the applied lane."
    if current_lane not in config["lanes"]:
        return (f"{folder} is in lane {current_lane!r}, which has no folder on disk "
                "to move (it is probably missing).")
    src = workspace.safe_join(root, config["lanes"][current_lane], folder)
    if not src.is_dir():
        return f"{folder}'s folder is not on disk (lane says {current_lane!r}); nothing to move."
    dest = workspace.safe_join(root, config["lanes"]["applied"], folder)
    if dest.exists():
        return f"a folder named {folder!r} already exists in the applied lane."
    src.rename(dest)
    on_disk[folder] = "applied"
    return None


def _print_company_report(book: dict, company: str) -> int:
    """Lesson 33's pre-interview check: every record for this employer, one
    line each, lane + status + dates + posting URL, so a duplicate shows up
    reading a terminal instead of listing folders by hand the night before."""
    # A ledger entry only carries a `company` field once dashboard.build()
    # has enriched it from the folder name (or it was set some other way).
    # Fall back to the same parse here, in memory only (never saved), so
    # --company works even before the dashboard has ever run.
    for folder, entry in book.items():
        if isinstance(entry, dict) and not entry.get("company"):
            entry["company"] = dashboard.parse_folder(folder)["company"]
    folders = ledger.records_for_company(book, company)
    if not folders:
        print(f"No records for '{company}'.")
        return 0
    print(f"{len(folders)} record(s) for '{company}':")
    for folder in folders:
        entry = book[folder]
        lane = entry.get("lane", "missing")
        status = entry.get("status", "none")
        applied = entry.get("applied_date") or "-"
        status_date = entry.get("status_date") or "-"
        posting_url = entry.get("posting_url") or "-"
        print(f"  {folder}")
        print(f"    lane={lane} status={status} applied={applied} "
              f"status_date={status_date} posting_url={posting_url}")
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="job_status.py", add_help=True)
    parser.add_argument("workspace")
    parser.add_argument("fragment", nargs="?", default=None)
    parser.add_argument("status", nargs="?", default=None)
    parser.add_argument("--reason", default=None, choices=list(ledger.CLOSURE_REASONS))
    parser.add_argument("--date", default=None)
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--applied", action="store_true")
    parser.add_argument("--company", default=None,
                         help="Print every record for this employer, across every lane/status.")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already printed a usage message to stderr; nothing left to do.
        return exc.code if isinstance(exc.code, int) else 2

    if args.company:
        root = Path(args.workspace).expanduser().resolve()
        if not root.exists():
            print(f"No such path: {root}")
            return 2
        if not (root / "jobkit.json").exists():
            print(f"No JobKit workspace at {root} (no jobkit.json). Run setup first.")
            return 2
        try:
            config = workspace.load_config(root)
            on_disk = workspace.scan(root, config)
            book = ledger.load(root / "job_ledger.json")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"Config or ledger at {root} is unreadable: {exc}")
            return 2
        book, _ = ledger.sync(book, on_disk, date.today().isoformat())
        return _print_company_report(book, args.company)

    if args.fragment is None:
        print("Give a folder fragment and status, or use --company. See --help.")
        return 2

    if args.applied and args.status not in (None, "applied"):
        print("Cannot combine --applied with a status other than 'applied'.")
        return 2

    applying = args.applied or (args.status == "applied" and args.move)
    if args.status == "applied" and not applying:
        print("Setting status to 'applied' needs --move, or use --applied instead.")
        return 2
    if not applying and args.status is None:
        print("Give a status, or pass --applied. See --help.")
        return 2

    if args.date:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            print(f"--date {args.date!r} is not a valid YYYY-MM-DD date.")
            return 2
    today = args.date or date.today().isoformat()

    root = Path(args.workspace).expanduser().resolve()
    if not root.exists():
        print(f"No such path: {root}")
        return 2
    if not (root / "jobkit.json").exists():
        print(f"No JobKit workspace at {root} (no jobkit.json). Run setup first.")
        return 2
    try:
        config = workspace.load_config(root)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Config at {root} is unreadable: {exc}")
        return 2

    ledger_path = root / "job_ledger.json"
    try:
        on_disk = workspace.scan(root, config)
        book = ledger.load(ledger_path)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"job_ledger.json at {root} is unreadable ({exc}).")
        return 2

    book, _ = ledger.sync(book, on_disk, today)

    folder, error = _resolve_one(book, args.fragment)
    if error:
        print(error)
        return 1

    if applying:
        move_error = _apply_move(root, config, book, on_disk, folder)
        if move_error:
            print(move_error)
            return 1
        try:
            book, _ = ledger.sync(book, on_disk, today)
            ledger.save(ledger_path, book)
        except PermissionError as exc:
            print(f"Could not save {ledger_path} ({exc}). A synced folder (Dropbox "
                  "or OneDrive) can lock files; close anything using them and try again.")
            return 2
        applied_date = book[folder].get("applied_date", "unknown")
        print(f"{folder}: moved to the applied lane; applied_date={applied_date}")
        return 0

    try:
        entry = ledger.set_status(book, folder, args.status, today, closure_reason=args.reason)
    except (ValueError, KeyError) as exc:
        print(str(exc))
        return 1

    try:
        ledger.save(ledger_path, book)
    except PermissionError as exc:
        print(f"Could not save {ledger_path} ({exc}). A synced folder (Dropbox "
              "or OneDrive) can lock files; close anything using them and try again.")
        return 2

    print(f"{folder}: {entry['history'][-1]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # last-resort guard: no raw traceback on any reachable input
        print(f"Unexpected error: {exc}")
        sys.exit(2)
