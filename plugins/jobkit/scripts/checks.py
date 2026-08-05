#!/usr/bin/env python3
"""Build-time guards for generated documents.

Text in, list of problems out. An empty list means clean.

The inflation check exists because the dangerous sentence is usually surrounded
by honest ones. "Similar to the piece you made for X" is fine. "Which builds on
your years of X" invents a credential when the baseline records one project.
"""
import re

DEFAULT_MAX_WORDS = 700
DEFAULT_MAX_SECTIONS = 8

# Superlatives read as a claim about the candidate unless the sentence is
# plainly about an employer/place. The preposition right before the word is
# a necessary tell ("at a", "for a", "with a") but NOT a sufficient one: "I
# performed at a world-class level" has the same preposition and is still a
# claim about the person. So suppression requires BOTH the preposition
# before AND an employer/place noun right after ("studio", "team", ...) -
# see _describes_employer, which every superlative pattern is checked
# against post-match rather than folding into the regex itself.
_EMPLOYER_PREP_RE = re.compile(r"\b(?:at|for|with) an?\s*$", re.IGNORECASE)
_EMPLOYER_NOUN_RE = re.compile(
    r"^\s*(?:[\w-]+\s+){0,1}"
    r"(?:studios?|teams?|compan(?:y|ies)|firms?|agenc(?:y|ies)|clients?|schools?)\b",
    re.IGNORECASE,
)

def _describes_employer(text: str, start: int, end: int) -> bool:
    """True only when the match is sandwiched between an employer preposition
    and an employer/place noun - "worked AT A world-class STUDIO", not
    "performed AT A world-class level" (no noun) and not "a world-class eye"
    (no preposition either)."""
    return bool(_EMPLOYER_PREP_RE.search(text[:start])
                and _EMPLOYER_NOUN_RE.match(text[end:]))


# Regex strings (not match text) of the patterns above that describe scale or
# quality and so need the employer check - see _describes_employer.
EMPLOYER_GATED_PATTERNS = {
    r"\bworld-class\b", r"\bunparalleled\b", r"\bbattle-tested\b",
    r"\bhighly skilled\b", r"\badvanced expertise\b", r"\bproven track record\b",
}

INFLATION_PATTERNS = [
    (r"\byears of (?:your|his|her|their|my)\b", "a comparison turned into a claim about time"),
    (r"\bextensive experience\b", "unearned scale"),
    (r"\bdeep (?:expertise|experience|knowledge)\b", "unearned depth"),
    (r"\bexpert (?:in|at|with)\b", "unearned mastery"),
    (r"\bmastery of\b", "unearned mastery"),
    (r"\bseasoned\b", "unearned tenure"),
    (r"\bveteran\b", "unearned tenure"),
    (r"\bbuilds on your years\b", "a comparison turned into a claim about time"),
    # possessive-free and numeric time claims: "years of professional work",
    # "10+ years of", "a decade of" all invent a tenure the baseline may not have.
    (r"\byears? of\b", "an unearned claim about time"),
    (r"\bdecades? of\b", "an unearned claim about time"),
    # superlatives: scale or quality asserted with nothing to back it. Skipped
    # only when the phrase both follows an employer preposition AND precedes
    # an employer/place noun ("worked at a world-class studio") - not the
    # candidate - that's ordinary, true prose. See _describes_employer.
    (r"\bworld-class\b", "a superlative claim"),
    (r"\bunparalleled\b", "a superlative claim"),
    (r"\bbattle-tested\b", "a superlative claim"),
    (r"\bhighly skilled\b", "a superlative claim"),
    (r"\badvanced expertise\b", "unearned depth"),
    (r"\bproven track record\b", "an unearned claim of results"),
    # authorship verbs: not necessarily false, but the check can't know who did
    # what, so it flags for the user to confirm against their own baseline -
    # the record of what they actually did - and tells them what to do about it.
    (r"\bled the (?:team|effort|project)\b",
     "check your baseline (the record of what you actually did) - if it only shows "
     "you as part of the team, soften this to say that"),
    (r"\barchitected\b",
     "check your baseline (the record of what you actually did) - if you built one "
     "piece rather than the whole system, soften this to say that"),
    (r"\bspearheaded\b",
     "check your baseline (the record of what you actually did) - if you took part "
     "rather than initiated and drove it, soften this to say that"),
]


def _word_count(text: str) -> int:
    # ponytail: strips the common markdown/URL noise (links, headings, bullets)
    # before counting; not a markdown parser, just enough to stop syntax from
    # inflating the word count. Extend if a new syntax shape starts slipping through.
    stripped = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    stripped = re.sub(r"https?://\S+", "", stripped)
    stripped = re.sub(r"^#{1,6}\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*[-*+]\s+", "", stripped, flags=re.MULTILINE)
    return len(stripped.split())


def envelope(text: str, max_words: int = DEFAULT_MAX_WORDS,
             max_sections: int = DEFAULT_MAX_SECTIONS) -> list:
    problems = []
    words = _word_count(text)
    if words > max_words:
        problems.append(f"too long: {words} words, limit is {max_words}")
    sections = len(re.findall(r"^## (?!#)", text, flags=re.MULTILINE))
    if sections > max_sections:
        problems.append(f"too many sections: {sections}, limit is {max_sections}")
    return problems


def banned_phrases(text: str, banned: list) -> list:
    low = text.lower()
    return [phrase for phrase in banned if phrase and phrase.lower() in low]


def inflation(text: str) -> list:
    hits = []
    for pattern, why in INFLATION_PATTERNS:
        gated = pattern in EMPLOYER_GATED_PATTERNS
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if gated and _describes_employer(text, match.start(), match.end()):
                continue
            hits.append(f"{match.group()} ({why})")
    return hits


def run_all(text: str, profile: dict) -> list:
    limits = profile.get("envelope", {})
    problems = envelope(
        text,
        max_words=limits.get("max_words", DEFAULT_MAX_WORDS),
        max_sections=limits.get("max_sections", DEFAULT_MAX_SECTIONS),
    )
    problems += [f"banned phrase: {p}" for p in banned_phrases(text, profile.get("banned_phrases", []))]
    problems += [f"inflation: {h}" for h in inflation(text)]
    return problems
