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
import json
import re
import sys
import webbrowser
from datetime import date
from pathlib import Path

import ledger
import reading_stats
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
    # Two splits, so runs of capitals stay whole:
    #   lower -> upper           "LookDev"      -> "Look Dev"
    #   caps-run -> Titlecase    "3DGeneralist" -> "3D Generalist"
    #                            "VFXArtist"    -> "VFX Artist"
    # Without the second rule a naive digit->upper split gives "3 DGeneralist".
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", token)
    spaced = re.sub(r"(?<=[A-Z0-9])(?=[A-Z][a-z])", " ", spaced)
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


# ----------------------------------------------------------------------------
# Library: scan guides/*.html for a title + description, parsed with a narrow
# regex rather than a full HTML parser (stdlib html.parser would be overkill
# for two fields). Everything pulled out is HTML-escaped again before it goes
# back into the page, so a hostile title (raw "<" or "&") can't break the page.
# ----------------------------------------------------------------------------
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DESC_RE = re.compile(
    r'<meta\s+(?:name=["\']description["\']\s+content=["\'](?P<c1>.*?)["\']'
    r'|content=["\'](?P<c2>.*?)["\']\s+name=["\']description["\'])',
    re.IGNORECASE | re.DOTALL,
)


def _meta_re(name: str) -> re.Pattern:
    return re.compile(
        rf'<meta\s+(?:name=["\']{name}["\']\s+content=["\'](?P<c1>.*?)["\']'
        rf'|content=["\'](?P<c2>.*?)["\']\s+name=["\']{name}["\'])',
        re.IGNORECASE | re.DOTALL,
    )


_CATEGORY_RE = _meta_re("jobkit-category")
_ICON_RE = _meta_re("jobkit-icon")

# Guide authors can declare category/icon explicitly via meta tags; when they
# don't, this short keyword table infers both from the title. A nicety, not
# a classifier, so keep it short - anything unmatched falls back to "Guides".
_CATEGORY_KEYWORDS = [
    (("colour", "color", "light", "composition", "design"), "Craft", "palette"),
    (("photo", "camera", "shoot", "lighting"), "Craft", "camera"),
    (("portfolio", "reel", "resume", "interview", "career", "negotiat"), "Career", "users"),
    (("python", "javascript", "software", "code", "sql", "git", "tool"), "Tools", "wrench"),
]


def _infer_category(title: str) -> tuple:
    lowered = title.lower()
    for keywords, category, icon in _CATEGORY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return category, icon
    return "Guides", "book"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def scan_guides(guides_dir: Path) -> list:
    """Return [{name, title, desc, href, category, icon}, ...] for guides/*.html."""
    if not guides_dir.is_dir():
        return []
    items = []
    for path in sorted(guides_dir.glob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        title_match = _TITLE_RE.search(text)
        title = _clean(title_match.group(1)) if title_match else ""
        title = title or path.stem
        desc_match = _DESC_RE.search(text)
        desc = _clean(desc_match.group("c1") or desc_match.group("c2")) if desc_match else ""

        cat_match = _CATEGORY_RE.search(text)
        category = _clean(cat_match.group("c1") or cat_match.group("c2")) if cat_match else ""
        icon_match = _ICON_RE.search(text)
        icon = _clean(icon_match.group("c1") or icon_match.group("c2")) if icon_match else ""
        if not category or not icon:
            inferred_cat, inferred_icon = _infer_category(title)
            category = category or inferred_cat
            icon = icon or inferred_icon

        items.append({
            "name": path.stem,
            "title": title,
            "desc": desc,
            "href": f"guides/{path.name}",
            "category": category,
            "icon": icon,
        })
    return items


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

    good_book = {f: e for f, e in book.items() if isinstance(e, dict)}
    if len(good_book) != len(book):
        print(f"dashboard: skipping {len(book) - len(good_book)} unreadable ledger "
              "record(s) (not a JSON object)")

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
            "first_seen": entry.get("first_seen", ""),
            "closed_date": entry.get("closed_date", ""),
            "status_date": entry.get("status_date", ""),
            "days_waiting": waited,
            "stale": waited is not None and waited >= config.get("stale_after_days", 21),
            "posting_url": entry.get("posting_url", ""),
            "folder_uri": _folder_uri(root, config, lane, folder) if lane in config["lanes"] else "",
        }

    cards = {}
    for folder, entry in good_book.items():
        try:
            cards[folder] = card(folder, entry)
        except Exception as exc:
            # One bad record (an unexpected field type, an unreadable date
            # that even days_since's own guard didn't anticipate, ...) must
            # never take the whole dashboard down for every other job.
            print(f"dashboard: skipping ledger record {folder!r} ({exc})")

    staged = [cards[f] for f, e in good_book.items() if f in cards and e.get("lane") == "staged"]
    applied = [(f, e) for f, e in good_book.items() if f in cards and e.get("lane") == "applied"]
    active_all = [cards[f] for f, e in applied if e.get("status") != "closed"]
    closed = [cards[f] for f, e in applied if e.get("status") == "closed"]

    # An interview is the most important thing on the board, so it gets its
    # own panel instead of blending into "waiting to hear". Moved, not
    # duplicated.
    interviews = [c for c in active_all if c["status"] in ("interview_scheduled", "interviewed")]
    active = [c for c in active_all if c["status"] not in ("interview_scheduled", "interviewed")]

    staged.sort(key=lambda c: (-(c["score"] or 0), c["company"]))
    # Newest applied first. An unset applied_date sorts to "" which is
    # lexicographically less than any ISO date, so reverse=True pushes it to
    # the bottom - it can never masquerade as today's application.
    active.sort(key=lambda c: c["applied_date"] or "", reverse=True)
    interviews.sort(key=lambda c: c["applied_date"] or "", reverse=True)
    closed.sort(key=lambda c: c["company"])

    read_pages = {}
    if config.get("features", {}).get("reading_stats", True):
        read_pages = reading_stats.harvest(root).get("pages", {})

    return render({
        "today": today,
        "counts": ledger.counts(book),
        "vocabulary": config.get("vocabulary", {}),
        "staged": staged,
        "active": active,
        "interviews": interviews,
        "closed": closed,
        "library": scan_guides(root / "guides"),
        "read_pages": read_pages,
    })


# ----------------------------------------------------------------------------
# Visual identity: dark "mission-control" theme, ported (structure + styling
# only, no content) from the reference dashboard this project rebuilds.
# ----------------------------------------------------------------------------
FAVICON = ('<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,'
           'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiIgcm9sZT0iaW1nIiBhcmlhLWxhYmVsPSJDYXJlZXIgbWlzc2lvbi1jb250cm9sIG1hcmsg4oCUIGEgcmlzaW5nIHRlYWwtYW1iZXItb3JhbmdlIHN0YWlyY2FzZSI+CiAgPHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiByeD0iNyIgZmlsbD0iIzBEMTAxNSIvPgogIDxyZWN0IHdpZHRoPSIzMiIgaGVpZ2h0PSIzMiIgcng9IjciIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzJDMzQ0MiIgc3Ryb2tlLXdpZHRoPSIxIi8+CiAgPHJlY3QgeD0iNS41IiB5PSIxOCIgd2lkdGg9IjUuNSIgaGVpZ2h0PSI4IiByeD0iMS42IiBmaWxsPSIjMkJFMENFIi8+CiAgPHJlY3QgeD0iMTMuMjUiIHk9IjEyLjUiIHdpZHRoPSI1LjUiIGhlaWdodD0iMTMuNSIgcng9IjEuNiIgZmlsbD0iI0Y1QzEzRCIvPgogIDxyZWN0IHg9IjIxIiB5PSI2LjUiIHdpZHRoPSI1LjUiIGhlaWdodD0iMTkuNSIgcng9IjEuNiIgZmlsbD0iI0ZGOEEzRCIvPgo8L3N2Zz4K">')

# Google Fonts is the one allowed CDN load: nothing load-bearing depends on
# it (every stack below ends in a system fallback), so the page still looks
# deliberate with it blocked. Ported from the reference's FONTS constant.
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700'
         '&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" '
         'rel="stylesheet">')

THEME_VARS = """
  :root{
    --ink:#0D1015; --ink-2:#151A21; --ink-3:#1C2330;
    --line:#2C3442; --line-soft:#212834;
    --text:#EAEDF3; --muted:#94A0B2; --muted-2:#5F6A7B;
    --signal:#FF8A3D; --have:#2BE0CE; --partial:#F5C13D; --adjacent:#6E9BFF;
    --violet:#B98CFF; --gap:#5F6A7B; --offer:#2EE36E; --deny:#FF5C82; --r:14px;
  }
"""

PAGE_CSS = THEME_VARS + """
  *{box-sizing:border-box;}
  html{scroll-behavior:smooth;}
  body{margin:0; background:var(--ink); color:var(--text);
    font-family:"IBM Plex Sans",system-ui,-apple-system,sans-serif; line-height:1.55; -webkit-font-smoothing:antialiased;
    background-image:linear-gradient(var(--line-soft) 1px,transparent 1px),linear-gradient(90deg,var(--line-soft) 1px,transparent 1px);
    background-size:46px 46px,46px 46px; background-position:center top;}
  body::before{content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:radial-gradient(120% 80% at 50% -10%, transparent 30%, var(--ink) 78%);}
  .wrap{max-width:1180px; margin:0 auto; padding:0 24px; position:relative; z-index:1;}
  a{color:inherit; text-decoration:none;}
  ::selection{background:var(--signal); color:#1a1205;}
  a:focus-visible, .jcard:focus-visible, .gcard:focus-visible, .jmain:focus-visible{
    outline:2px solid var(--ca,var(--signal)); outline-offset:3px; border-radius:12px;}
  @media (prefers-reduced-motion: reduce){
    *{transition:none !important;}
    .jcard:hover, .gcard:hover, .fig:hover{transform:none !important;}
  }
  .mono{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,monospace;}
  .eyebrow{font-family:"IBM Plex Mono",monospace; font-size:.72rem; letter-spacing:.22em;
    text-transform:uppercase; color:var(--muted);}
  /* topbar */
  .topbar{position:sticky; top:0; z-index:30; backdrop-filter:blur(8px);
    background:rgba(14,17,22,.82); border-bottom:1px solid var(--line);}
  .topbar .wrap{display:flex; align-items:center; gap:18px; height:54px;}
  .brand{font-family:"Space Grotesk",sans-serif; font-weight:600; letter-spacing:-.01em;}
  .brand .dot{color:var(--signal);}
  .navcodes{display:flex; gap:4px; flex-wrap:wrap; margin-left:auto;}
  .navcodes a{font-family:"IBM Plex Mono",monospace; font-size:.7rem; color:var(--muted);
    padding:4px 9px; border:1px solid transparent; border-radius:7px;}
  .navcodes a:hover{color:var(--text); border-color:var(--line); background:var(--ink-2);}
  /* hero */
  .hero{padding:44px 0 22px;}
  .thesis{font-family:"Space Grotesk",sans-serif; font-weight:600; font-size:clamp(1.7rem,4.4vw,2.6rem);
    line-height:1.08; letter-spacing:-.02em; margin:12px 0 4px;}
  .thesis .hl{color:var(--signal);}
  .stamp{font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--muted-2);}
  /* stat ribbon */
  .ribbon{display:flex; flex-wrap:wrap; margin-top:22px; border:1px solid var(--line); border-radius:16px;
    background:linear-gradient(180deg,var(--ink-3),var(--ink-2)); overflow:hidden;
    box-shadow:0 1px 0 rgba(255,255,255,.02) inset;}
  .fig{flex:1 1 0; min-width:112px; text-align:center; padding:16px 10px 14px; border-right:1px solid var(--line-soft);
    position:relative; transition:background .15s;}
  .fig::before{content:""; position:absolute; left:0; right:0; top:0; height:2px; background:var(--accent); opacity:.85;}
  .fig:hover{background:color-mix(in srgb,var(--accent) 8%,transparent);}
  .fig:last-child{border-right:none;}
  .ficon{display:flex; justify-content:center; margin-bottom:8px; color:var(--accent);}
  .fnum{font-family:"Space Grotesk",sans-serif; font-weight:700; font-size:1.7rem; line-height:1; display:block; color:var(--accent);}
  .flab{font-family:"IBM Plex Mono",monospace; font-size:.6rem; letter-spacing:.12em; text-transform:uppercase;
    color:var(--muted); margin-top:6px; display:block;}
  /* section panels, each carries its own accent via --pa */
  .panel{position:relative; margin-top:24px; border:1px solid var(--line); border-radius:18px;
    padding:20px 22px 24px; overflow:hidden;
    background:linear-gradient(180deg, color-mix(in srgb,var(--pa) 7%,var(--ink-2)) 0, var(--ink-2) 190px);
    box-shadow:0 14px 30px -22px rgba(0,0,0,.7);}
  .panel::before{content:""; position:absolute; top:0; left:0; right:0; height:3px;
    background:linear-gradient(90deg,var(--pa), color-mix(in srgb,var(--pa) 25%,transparent));}
  .p-ready{--pa:var(--signal);} .p-active{--pa:var(--have);} .p-closed{--pa:var(--muted);} .p-lib{--pa:var(--violet);}
  .p-interviews{--pa:var(--partial);}
  .phead{display:flex; align-items:center; gap:13px; margin-bottom:4px; flex-wrap:wrap;}
  .phead .picon{flex:none; width:36px; height:36px; display:grid; place-items:center; border-radius:11px;
    color:var(--pa); background:color-mix(in srgb,var(--pa) 15%,transparent);
    border:1px solid color-mix(in srgb,var(--pa) 42%,transparent);}
  .phead h2{font-family:"Space Grotesk",sans-serif; font-weight:600; font-size:1.14rem; margin:0;
    letter-spacing:-.01em; white-space:nowrap;}
  .phead .rule{flex:1; height:1px; background:linear-gradient(90deg,color-mix(in srgb,var(--pa) 55%,transparent),transparent);}
  .phead .pcount{font-family:"IBM Plex Mono",monospace; font-size:.7rem; white-space:nowrap;
    color:color-mix(in srgb,var(--pa) 70%,var(--muted));
    padding:4px 10px; border-radius:20px; border:1px solid color-mix(in srgb,var(--pa) 30%,transparent);
    background:color-mix(in srgb,var(--pa) 9%,transparent);}
  .empty{font-family:"IBM Plex Mono",monospace; font-size:.82rem; color:var(--muted); padding:14px 2px;}
  /* search */
  .toolbar{margin:22px 0 0;}
  .libsearch{display:flex; align-items:center; gap:8px; background:var(--ink-3); max-width:420px;
    border:1px solid var(--line); border-radius:10px; padding:9px 13px;}
  .libsearch:focus-within{border-color:color-mix(in srgb,var(--signal) 55%,transparent);}
  .libsearch svg{width:16px; height:16px; color:var(--muted); flex:none;}
  .libsearch input{flex:1; background:none; border:none; outline:none; color:var(--text);
    font-family:"IBM Plex Sans",sans-serif; font-size:.9rem; min-width:0;}
  .libsearch input::placeholder{color:var(--muted-2);}
  /* job cards */
  .grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(268px,1fr)); gap:12px; margin-top:14px;}
  .jcard{display:flex; flex-direction:column; gap:8px; border:1px solid var(--line); border-radius:12px;
    background:var(--ink-2); padding:13px 15px; transition:border-color .15s, transform .15s, background .15s;}
  .jcard:hover{border-color:color-mix(in srgb,var(--pa) 60%,transparent); transform:translateY(-2px); background:var(--ink-3);}
  .jmain{display:block; color:inherit;}
  .jtop{display:flex; align-items:flex-start; gap:9px;}
  .jscore{flex:none; width:26px; height:26px; display:grid; place-items:center; border-radius:8px;
    font-family:"IBM Plex Mono",monospace; font-weight:700; font-size:.8rem; background:var(--ink-3); color:var(--muted-2);}
  .jcard.hi .jscore{background:var(--pa); color:var(--ink);}
  .jco{flex:1; min-width:0; font-family:"Space Grotesk",sans-serif; font-weight:600; font-size:.96rem;
    line-height:1.25; overflow-wrap:anywhere;}
  .jopen{flex:none; margin-top:3px; font-family:"IBM Plex Mono",monospace; font-size:.62rem; color:var(--muted-2);}
  .jcard:hover .jopen{color:var(--pa);}
  .jrole{color:var(--muted); font-size:.78rem; padding-left:35px;}
  .jmeta{display:flex; flex-wrap:wrap; align-items:center; gap:7px 8px;}
  .chip{font-family:"IBM Plex Mono",monospace; font-size:.63rem; font-weight:600; letter-spacing:.03em;
    padding:3px 9px; border-radius:20px; border:1px solid var(--line); color:var(--muted); white-space:nowrap;}
  .chip.score{color:var(--pa); border-color:color-mix(in srgb,var(--pa) 50%,transparent);
    background:color-mix(in srgb,var(--pa) 12%,transparent);}
  .chip.stale{color:var(--partial); border-color:color-mix(in srgb,var(--partial) 50%,transparent);
    background:color-mix(in srgb,var(--partial) 12%,transparent);}
  .chip.rejected{color:var(--deny); border-color:color-mix(in srgb,var(--deny) 45%,transparent);
    background:color-mix(in srgb,var(--deny) 10%,transparent);}
  a.chip{transition:color .15s, border-color .15s;}
  a.chip:hover{color:var(--text); border-color:var(--pa);}
  /* library: filter toolbar (search + category chips) */
  .libtools{display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:14px 0 4px;}
  .libtools .libsearch{max-width:320px;}
  .chips{display:flex; flex-wrap:wrap; gap:7px;}
  .chip{font-family:"IBM Plex Mono",monospace; cursor:default;}
  button.chip{cursor:pointer; background:var(--ink-2); transition:color .14s, background .14s, border-color .14s;}
  button.chip:hover{color:var(--text); border-color:color-mix(in srgb,var(--pa) 55%,var(--muted-2));}
  button.chip.active{color:var(--ink); background:var(--pa); border-color:var(--pa);}
  button.chip .cn{opacity:.62; margin-left:6px; font-weight:500;}
  button.chip.active .cn{opacity:.82;}
  .nores{display:none; font-family:"IBM Plex Mono",monospace; font-size:.85rem; color:var(--muted);
    padding:22px 4px; text-align:center;}
  /* library cards */
  .cards{display:grid; grid-template-columns:repeat(auto-fill,minmax(236px,1fr)); gap:12px; margin-top:14px;}
  .gcard{display:flex; flex-direction:column; gap:6px; border:1px solid var(--line); border-left:3px solid var(--pa);
    border-radius:12px; background:var(--ink-2); padding:14px 15px;
    transition:border-color .15s, transform .15s, background .15s, box-shadow .15s;}
  .gcard:hover{transform:translateY(-2px); background:var(--ink-3);
    border-color:color-mix(in srgb,var(--pa) 60%,transparent);
    box-shadow:0 12px 24px -18px color-mix(in srgb,var(--pa) 90%,#000);}
  .gcard-read{background:color-mix(in srgb,var(--have) 6%,var(--ink-2));
    border-left-color:var(--have);}
  .gread{font-family:"IBM Plex Mono",monospace; font-size:.62rem; margin-top:2px;}
  .gread.read{color:var(--have);}
  .gread.unread{color:var(--muted-2);}
  .gbadge{align-self:flex-start; display:inline-flex; align-items:center; gap:5px;
    font-family:"IBM Plex Mono",monospace; font-size:.58rem; font-weight:600;
    letter-spacing:.08em; padding:3px 8px; border-radius:6px; color:var(--pa);
    border:1px solid color-mix(in srgb,var(--pa) 45%,transparent); background:color-mix(in srgb,var(--pa) 12%,transparent);}
  .gname{font-family:"Space Grotesk",sans-serif; font-weight:600; font-size:.95rem; line-height:1.25;}
  .gdesc{color:var(--muted); font-size:.78rem; line-height:1.45;}
  footer{margin:60px 0 40px; color:var(--muted-2); font-family:"IBM Plex Mono",monospace; font-size:.72rem; text-align:center;}
"""


def _icon(name: str, size: int = 18) -> str:
    """Small lucide-style stroke icon. Color follows currentColor.

    An unknown name falls back to the generic "book" icon rather than
    rendering nothing - a guide author can mistype jobkit-icon and still get
    a card, not a blank square.
    """
    paths = _ICON_PATHS.get(name, _ICON_PATHS["book"])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{paths}</svg>')


_ICON_PATHS = {
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="M3 13l9 5 9-5"/>',
    "send": '<path d="M21 3 3 10l7 3 3 7 8-17Z"/><path d="M10 13 21 3"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5l3.2 2"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M16 3v4M8 3v4M3.5 10h17"/>',
    "x-circle": '<circle cx="12" cy="12" r="8.5"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "archive": '<rect x="3" y="4" width="18" height="4.5" rx="1"/>'
               '<path d="M4.5 8.5v9a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-9"/><path d="M10 13h4"/>',
    "cap": '<path d="M12 4 2.5 9l9.5 5 9.5-5-9.5-5Z"/>'
           '<path d="M6.5 11.5V17c0 1.5 2.5 3 5.5 3s5.5-1.5 5.5-3v-5.5"/><path d="M21.5 9v6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    # per-guide topic icons, chosen by category/keyword (see _infer_category)
    "palette": '<path d="M12 3a9 8 0 1 0 0 16c1 0 1.6-.5 1.6-1.3 0-.6-.4-1-.4-1.6 0-.7.5-1.1 1.2-1.1H16a4 4 0 0 0 4-4c0-4.4-3.6-8-8-8Z"/>'
               '<circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7.5" r="1"/><circle cx="15" cy="8" r="1"/>',
    "camera": '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/>'
              '<circle cx="12" cy="13.5" r="3.5"/>',
    "book": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21V5.5Z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20"/>',
    "wrench": '<path d="M14.5 6.5a4 4 0 0 0-5.4 4.9L4 16.5 7.5 20l5.1-5.1a4 4 0 0 0 4.9-5.4l-2.7 2.7-2.2-2.2Z"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 2.7-5.5 6-5.5s6 2.5 6 5.5"/>'
             '<circle cx="17" cy="8.5" r="2.3"/><path d="M15.5 14.5c2.6.4 4.5 2.6 4.5 5.5"/>',
    "sparkles": '<path d="M11 3 12.4 8 17 9.4 12.4 10.8 11 15.8 9.6 10.8 5 9.4 9.6 8Z"/><path d="M18 15l.9 2.6 2.6.9-2.6.9L18 22l-.9-2.6-2.6-.9 2.6-.9Z"/>',
}


def render(context: dict) -> str:
    vocab = context["vocabulary"]
    counts = context["counts"]

    def label(key: str, fallback: str) -> str:
        return html.escape(vocab.get(key, fallback))

    tiles = [
        ("staged", label("staged", "Ready to apply"), "signal", "layers"),
        ("applied", label("applied", "Applied"), "adjacent", "send"),
        ("in_flight", label("in_flight", "Waiting to hear"), "have", "clock"),
        ("interviews", label("interviews", "Interviews"), "partial", "calendar"),
        ("rejected", label("rejected", "Not selected"), "deny", "x-circle"),
        ("closed_no_response", label("closed_no_response", "No response"), "muted-2", "archive"),
    ]
    ribbon = "".join(
        f'<div class="fig" style="--accent:var(--{color})">'
        f'<span class="ficon">{_icon(icon)}</span>'
        f'<span class="fnum" data-count="{key}">{counts.get(key, 0)}</span>'
        f'<span class="flab">{text}</span></div>'
        for key, text, color, icon in tiles
    )

    ready_label = label("staged", "Ready to apply")
    inflight_label = label("in_flight", "Waiting to hear")
    interviews_label = label("interviews", "Interviews")

    sections = "".join([
        _section(interviews_label, context["interviews"], "interviews", "p-interviews", "calendar",
                 hide_if_empty=True),
        _section(ready_label, context["staged"], "staged", "p-ready", "layers"),
        _section(inflight_label, context["active"], "active", "p-active", "clock"),
        _section("Closed", context["closed"], "closed", "p-closed", "archive"),
        _library_section(context["library"], context["read_pages"]),
    ])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Peckworks JobKit</title>
{FAVICON}
{FONTS}
<style>{PAGE_CSS}</style>
</head><body>
<div class="topbar"><div class="wrap">
  <span class="brand">Peckworks<span class="dot">&bull;</span>JobKit</span>
  <nav class="navcodes">
    <a href="#interviews">Interviews</a><a href="#staged">Ready</a><a href="#active">Waiting</a><a href="#closed">Closed</a><a href="#library">Library</a>
  </nav>
</div></div>
<div class="wrap">
  <div class="hero">
    <h1 class="thesis">Peckworks <span class="hl">JobKit</span></h1>
    <div class="stamp">Updated {html.escape(context['today'])}</div>
  </div>
  <div class="ribbon">{ribbon}</div>
  <div class="toolbar">
    <div class="libsearch">{_icon('search')}
      <input id="q" type="search" placeholder="Filter by company or role" aria-label="Filter jobs">
    </div>
  </div>
  {sections}
  <footer>Peckworks JobKit, generated locally. No data leaves this file.</footer>
</div>
<script>
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const needle = q.value.toLowerCase();
  document.querySelectorAll('.jcard').forEach(el => {{
    el.style.display = el.dataset.search.includes(needle) ? '' : 'none';
  }});
}});
</script>
</body></html>
"""


def _section(title: str, cards: list, key: str, panel_class: str, icon: str,
             hide_if_empty: bool = False) -> str:
    if not cards:
        if hide_if_empty:
            # An empty amber "interviews" panel at the top of the page every
            # day is noise, unlike Library's deliberate empty state below.
            return ""
        body = '<div class="empty">Nothing here yet.</div>'
    else:
        body = '<div class="grid">' + "".join(_card(c, key) for c in cards) + "</div>"
    return (
        f'<section class="panel {panel_class}" id="{key}">'
        f'<div class="phead"><span class="picon">{_icon(icon)}</span><h2>{title}</h2>'
        f'<div class="rule"></div><span class="pcount">{len(cards)}</span></div>'
        f'{body}</section>'
    )


_INTERVIEW_LABELS = {"interview_scheduled": "Interview scheduled", "interviewed": "Interviewed"}


def _applied_chip_text(applied_date: str) -> str:
    """Unset must render as a visible gap, never be silently omitted."""
    return f"applied {html.escape(applied_date)}" if applied_date else "applied date unknown"


def _card(c: dict, section: str) -> str:
    company = html.escape(str(c["company"]))
    role = html.escape(str(c["role"]))
    location = html.escape(str(c["location"]))
    search = html.escape(f"{c['company']} {c['role']} {c['location']}".lower(), quote=True)
    score = c["score"]

    chips = []
    if location:
        chips.append(f'<span class="chip">{location}</span>')

    if section == "staged":
        if c["first_seen"]:
            chips.append(f'<span class="chip">added {html.escape(c["first_seen"])}</span>')
    elif section == "interviews":
        label_text = _INTERVIEW_LABELS.get(c["status"], c["status"])
        date_text = f" {html.escape(c['status_date'])}" if c["status_date"] else ""
        chips.append(f'<span class="chip">{html.escape(label_text)}{date_text}</span>')
    elif section == "active":
        chips.append(f'<span class="chip">{_applied_chip_text(c["applied_date"])}</span>')
        if c["days_waiting"] is not None:
            if c["days_waiting"] < 0:
                # A hand-typed applied_date in the future - "-26448 days" is
                # meaningless to a user, so flag it instead of rendering it.
                chips.append('<span class="chip stale">applied date is in the future</span>')
            else:
                cls = "chip stale" if c["stale"] else "chip"
                chips.append(f'<span class="{cls}">{c["days_waiting"]} days</span>')
    elif section == "closed":
        chips.append(f'<span class="chip">{_applied_chip_text(c["applied_date"])}</span>')
        if c["closed_date"]:
            chips.append(f'<span class="chip">closed {html.escape(c["closed_date"])}</span>')

    if c["closure_reason"]:
        cls = "chip rejected" if c["closure_reason"] == "rejected" else "chip"
        chips.append(f'<span class="{cls}">{html.escape(c["closure_reason"].replace("_", " "))}</span>')
    if c["posting_url"]:
        chips.append(f'<a class="chip" href="{html.escape(c["posting_url"], quote=True)}" '
                      'target="_blank" rel="noopener">posting</a>')

    role_html = f'<div class="jrole">{role}</div>' if role else ""
    scorechip = f'<span class="jscore">{score}</span>' if score is not None else '<span class="jscore">&middot;</span>'
    top_cls = " hi" if (score or 0) >= 8 else ""
    open_link = (f'<a class="jmain" href="{html.escape(c["folder_uri"], quote=True)}" title="Open job folder">'
                 f'<div class="jtop">{scorechip}<span class="jco">{company}</span>'
                 f'<span class="jopen">folder &rarr;</span></div>{role_html}</a>') if c["folder_uri"] else (
                 f'<div class="jtop">{scorechip}<span class="jco">{company}</span></div>{role_html}')

    return (
        f'<article class="jcard{top_cls}" data-search="{search}">'
        f'{open_link}'
        f'<div class="jmeta">{"".join(chips)}</div></article>'
    )


def _read_badge(page_stats: dict) -> str:
    if not page_stats:
        return '<span class="gread unread">unread</span>'
    opens = page_stats.get("opens", 0)
    last = html.escape(str(page_stats.get("last", "")))
    return f'<span class="gread read">{opens}&times; &middot; last {last}</span>'


def _library_toolbar(categories: list) -> str:
    chips = ['<button type="button" class="chip active" data-chip="All">All'
             f'<span class="cn">{sum(n for _, n in categories)}</span></button>']
    for name, count in categories:
        chips.append(
            f'<button type="button" class="chip" data-chip="{html.escape(name, quote=True)}">'
            f'{html.escape(name)}<span class="cn">{count}</span></button>'
        )
    return (
        '<div class="libtools">'
        '<div class="libsearch">' + _icon("search") +
        '<input id="libq" type="search" placeholder="Filter guides by title or description" '
        'aria-label="Filter guides"></div>'
        f'<div class="chips">{"".join(chips)}</div></div>'
    )


def _library_section(guides: list, read_pages: dict) -> str:
    if not guides:
        body = ('<div class="empty">No guides yet. Drop an HTML file into '
                 '<span class="mono">guides/</span> and it will show up here.</div>')
    else:
        counts: dict = {}
        for g in guides:
            counts[g["category"]] = counts.get(g["category"], 0) + 1
        categories = sorted(counts.items())

        cards = []
        for g in guides:
            title = html.escape(g["title"])
            href = html.escape(g["href"], quote=True)
            category = html.escape(g["category"], quote=True)
            search = html.escape(f"{g['title']} {g['desc']}".lower(), quote=True)
            desc_html = f'<div class="gdesc">{html.escape(g["desc"])}</div>' if g["desc"] else ""
            page_stats = read_pages.get(g["name"].lower() + ".html") or read_pages.get(g["name"].lower())
            read_cls = " gcard-read" if page_stats else ""
            cards.append(
                f'<a class="gcard{read_cls}" href="{href}" data-category="{category}" data-search="{search}">'
                f'<span class="gbadge">{_icon(g["icon"], 16)} {html.escape(g["category"])}</span>'
                f'<div class="gname">{title}</div>{desc_html}{_read_badge(page_stats)}</a>'
            )
        body = (_library_toolbar(categories) +
                f'<div class="cards">{"".join(cards)}</div>'
                '<div class="nores">No guides match.</div>')
    return (
        '<section class="panel p-lib" id="library">'
        f'<div class="phead"><span class="picon">{_icon("cap")}</span><h2>Library</h2>'
        f'<div class="rule"></div><span class="pcount">{len(guides)}</span></div>'
        f'{body}</section>'
        '<script>(function(){'
        'var q=document.getElementById("libq"); if(!q) return;'
        'var chips=document.querySelectorAll("#library .chip");'
        'var cards=document.querySelectorAll("#library .gcard");'
        'var nores=document.querySelector("#library .nores");'
        'var active="All";'
        'function apply(){'
        'var needle=q.value.toLowerCase(); var shown=0;'
        'cards.forEach(function(c){'
        'var matchCat = active==="All" || c.dataset.category===active;'
        'var matchQ = c.dataset.search.indexOf(needle)!==-1;'
        'var show = matchCat && matchQ;'
        'c.style.display = show ? "" : "none";'
        'if(show) shown++;'
        '});'
        'nores.style.display = shown===0 ? "" : "none";'
        '}'
        'chips.forEach(function(ch){ch.addEventListener("click",function(){'
        'chips.forEach(function(x){x.classList.remove("active");});'
        'ch.classList.add("active"); active=ch.dataset.chip; apply();'
        '});});'
        'q.addEventListener("input",apply);'
        '})();</script>'
    )


def main(argv: list) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python dashboard.py <workspace-path> [--no-open]")
        return 1
    root = Path(args[0]).expanduser().resolve()

    if not root.exists():
        print(f"No such path: {root}")
        return 2
    if not (root / "jobkit.json").exists():
        print(f"No JobKit workspace at {root} (no jobkit.json). Run setup first.")
        return 2
    try:
        workspace.load_config(root)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Config at {root} is unreadable: {exc}")
        return 2

    out = root / "CareerDashboard.html"
    try:
        html = build(root)
    except KeyError as exc:
        print(f"jobkit.json at {root} is missing required key {exc}. "
              "Run setup again, or restore jobkit.json from a backup.")
        return 2
    except json.JSONDecodeError as exc:
        print(f"job_ledger.json at {root} is unreadable ({exc}). "
              "Fix or remove that file, then try again.")
        return 2
    except PermissionError as exc:
        print(f"Could not write in {root} ({exc}). A synced folder (Dropbox "
              "or OneDrive) can lock files; close anything using them and try again.")
        return 2

    try:
        out.write_text(html, encoding="utf-8")
    except PermissionError as exc:
        print(f"Could not write {out} ({exc}). A synced folder (Dropbox "
              "or OneDrive) can lock files; close anything using them and try again.")
        return 2
    print(f"Dashboard -> {out}")
    if "--no-open" not in argv:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
