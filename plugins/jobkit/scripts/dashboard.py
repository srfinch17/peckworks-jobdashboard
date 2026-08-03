#!/usr/bin/env python3
"""Generate CareerDashboard.html - one self-contained file, no server.

THE CONSTRAINT THAT SHAPES THIS FILE: a page opened from file:// cannot fetch()
a sibling JSON file. Browsers treat each local file as its own origin and CORS
blocks it, and it fails SILENTLY - you get a blank page, not an error. So every
value is written into the markup here, at generation time. The JavaScript in the
page only filters and expands data that is already present.

Usage:
  python dashboard.py <workspace-path> [--no-open]
"""
import html
import re
import sys
import webbrowser
from datetime import date
from pathlib import Path

import ledger
import workspace

FOLDER_RE = re.compile(r"^(\d+)_([^_]+)_([^_]+)_(.+)$")


def parse_folder(name: str) -> dict:
    """Split <score>_<Company>_<Location>_<Role>. Degrade gracefully."""
    match = FOLDER_RE.match(name)
    if not match:
        return {"score": None, "company": name, "location": "", "role": ""}
    score, company, location, role = match.groups()
    return {
        "score": int(score),
        "company": company,
        "location": _humanize(location),
        "role": _humanize(role),
    }


def _humanize(token: str) -> str:
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", token)
    return spaced.replace("-", " ").strip()


def _posting_url(root: Path, config: dict, lane: str, folder: str) -> str:
    """Line 1 of original_job_posting.md is the source URL, by convention."""
    path = workspace.lane_dir(root, config, lane) / folder / "original_job_posting.md"
    if not path.exists():
        return ""
    try:
        # utf-8-sig strips a leading BOM if present (several Windows editors
        # write one by default); it is a no-op otherwise. splitlines() already
        # handles CRLF.
        first = path.read_text(encoding="utf-8-sig").splitlines()[0].strip()
    except (OSError, IndexError, UnicodeDecodeError):
        return ""
    return first if first.startswith(("http://", "https://")) else ""


def _folder_uri(root: Path, config: dict, lane: str, folder: str) -> str:
    # Path.as_uri() over hand-rolled quoting: WHATWG file-URL parsing detects
    # a Windows drive letter on the RAW "C:" prefix, so a percent-encoded
    # "C%3A" (what a naive quote() of the whole path produces) is not
    # recognized as a drive letter and the link fails to resolve.
    return (workspace.lane_dir(root, config, lane) / folder).as_uri()


def build(root, today: str = None) -> str:
    root = Path(root)
    today = today or date.today().isoformat()
    config = workspace.load_config(root)

    on_disk = workspace.scan(root, config)
    book = ledger.load(root / "job_ledger.json")
    book, _ = ledger.sync(book, on_disk, today)

    # Fill in facts the folder name carries, without ever overwriting the ledger.
    for folder, lane in on_disk.items():
        entry = book[folder]
        parsed = parse_folder(folder)
        for key in ("score", "company", "location", "role"):
            entry.setdefault(key, parsed[key])
        if not entry.get("posting_url"):
            found = _posting_url(root, config, lane, folder)
            if found:
                entry["posting_url"] = found

    ledger.save(root / "job_ledger.json", book)

    def card(folder: str, entry: dict) -> dict:
        lane = entry.get("lane", "missing")
        waited = ledger.days_since(entry.get("applied_date"), today)
        return {
            "folder": folder,
            "company": entry.get("company") or folder,
            "role": entry.get("role") or "",
            "location": entry.get("location") or "",
            "score": entry.get("score"),
            "status": entry.get("status", "none"),
            "closure_reason": entry.get("closure_reason", ""),
            "applied_date": entry.get("applied_date", ""),
            "days_waiting": waited,
            "stale": waited is not None and waited >= config.get("stale_after_days", 21),
            "posting_url": entry.get("posting_url", ""),
            "folder_uri": _folder_uri(root, config, lane, folder) if lane in config["lanes"] else "",
        }

    cards = {folder: card(folder, entry) for folder, entry in book.items()}

    staged = [cards[f] for f, e in book.items() if e.get("lane") == "staged"]
    applied = [(f, e) for f, e in book.items() if e.get("lane") == "applied"]
    active = [cards[f] for f, e in applied if e.get("status") != "closed"]
    closed = [cards[f] for f, e in applied if e.get("status") == "closed"]

    staged.sort(key=lambda c: (-(c["score"] or 0), c["company"]))
    active.sort(key=lambda c: (c["days_waiting"] is None, -(c["days_waiting"] or 0)))
    closed.sort(key=lambda c: c["company"])

    return render({
        "today": today,
        "counts": ledger.counts(book),
        "vocabulary": config.get("vocabulary", {}),
        "staged": staged,
        "active": active,
        "closed": closed,
    })


def render(context: dict) -> str:
    vocab = context["vocabulary"]
    counts = context["counts"]

    def label(key: str, fallback: str) -> str:
        return html.escape(vocab.get(key, fallback))

    tiles = [
        ("staged", label("staged", "Ready to apply")),
        ("applied", label("applied", "Applied")),
        ("in_flight", label("in_flight", "Waiting to hear")),
        ("interviews", label("interviews", "Interviews")),
        ("rejected", label("rejected", "Not selected")),
        ("closed_no_response", label("closed_no_response", "No response")),
    ]
    tile_html = "\n".join(
        f'<div class="tile"><span class="n" data-count="{key}">{counts.get(key, 0)}</span>'
        f'<span class="l">{text}</span></div>'
        for key, text in tiles
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Dashboard</title>
<style>
:root {{ --bg:#0e1116; --card:#171b22; --line:#252b35; --ink:#e6e9ef;
        --dim:#8b95a5; --accent:#6ea8fe; --warn:#e0b341; --bad:#e06c75; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
header {{ padding:28px 32px 8px; }}
h1 {{ margin:0; font-size:22px; letter-spacing:-.01em; }}
.sub {{ color:var(--dim); font-size:13px; margin-top:4px; }}
.tiles {{ display:flex; flex-wrap:wrap; gap:12px; padding:20px 32px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
         padding:14px 18px; min-width:118px; }}
.tile .n {{ display:block; font-size:26px; font-weight:600; }}
.tile .l {{ display:block; color:var(--dim); font-size:12px; margin-top:2px; }}
section {{ padding:8px 32px 28px; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
      color:var(--dim); border-bottom:1px solid var(--line); padding-bottom:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; }}
.job {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.job h3 {{ margin:0 0 2px; font-size:15px; }}
.job .role {{ color:var(--dim); font-size:13px; }}
.job .meta {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.chip {{ font-size:11px; border:1px solid var(--line); border-radius:999px;
         padding:2px 8px; color:var(--dim); text-decoration:none; }}
.chip:hover {{ color:var(--ink); border-color:var(--accent); }}
.score {{ border-color:var(--accent); color:var(--accent); }}
.stale {{ border-color:var(--warn); color:var(--warn); }}
.rejected {{ border-color:var(--bad); color:var(--bad); }}
.empty {{ color:var(--dim); font-size:13px; padding:8px 0; }}
#q {{ background:var(--card); border:1px solid var(--line); color:var(--ink);
      border-radius:8px; padding:8px 12px; width:260px; margin:0 32px; }}
</style></head><body>
<header>
  <h1>Job Dashboard</h1>
  <div class="sub">Updated {html.escape(context['today'])}</div>
</header>
<div class="tiles">{tile_html}</div>
<input id="q" type="search" placeholder="Filter by company or role" aria-label="Filter jobs">
{_section(label('staged', 'Ready to apply'), context['staged'], 'staged')}
{_section(label('in_flight', 'Waiting to hear'), context['active'], 'active')}
{_section('Closed', context['closed'], 'closed')}
<!-- Library section reserved. Adding it later must not be a redesign. -->
<script>
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const needle = q.value.toLowerCase();
  document.querySelectorAll('.job').forEach(el => {{
    el.style.display = el.dataset.search.includes(needle) ? '' : 'none';
  }});
}});
</script>
</body></html>
"""


def _section(title: str, cards: list, key: str) -> str:
    if not cards:
        body = '<div class="empty">Nothing here yet.</div>'
    else:
        body = '<div class="grid">' + "".join(_card(c) for c in cards) + "</div>"
    return f'<section data-lane="{key}"><h2>{title} ({len(cards)})</h2>{body}</section>'


def _card(c: dict) -> str:
    company = html.escape(str(c["company"]))
    role = html.escape(str(c["role"]))
    location = html.escape(str(c["location"]))
    search = html.escape(f"{c['company']} {c['role']} {c['location']}".lower(), quote=True)

    chips = []
    if c["score"] is not None:
        chips.append(f'<span class="chip score">fit {c["score"]}</span>')
    if location:
        chips.append(f'<span class="chip">{location}</span>')
    if c["days_waiting"] is not None:
        cls = "chip stale" if c["stale"] else "chip"
        chips.append(f'<span class="{cls}">{c["days_waiting"]} days</span>')
    if c["closure_reason"]:
        cls = "chip rejected" if c["closure_reason"] == "rejected" else "chip"
        chips.append(f'<span class="{cls}">{html.escape(c["closure_reason"].replace("_", " "))}</span>')
    if c["folder_uri"]:
        chips.append(f'<a class="chip" href="{html.escape(c["folder_uri"], quote=True)}">open folder</a>')
    if c["posting_url"]:
        chips.append(f'<a class="chip" href="{html.escape(c["posting_url"], quote=True)}">posting</a>')

    return (
        f'<article class="job" data-search="{search}">'
        f"<h3>{company}</h3><div class=\"role\">{role}</div>"
        f'<div class="meta">{"".join(chips)}</div></article>'
    )


def main(argv: list) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python dashboard.py <workspace-path> [--no-open]")
        return 1
    root = Path(args[0]).expanduser().resolve()
    out = root / "CareerDashboard.html"
    out.write_text(build(root), encoding="utf-8")
    print(f"Dashboard -> {out}")
    if "--no-open" not in argv:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
