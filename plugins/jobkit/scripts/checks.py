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

INFLATION_PATTERNS = [
    (r"\byears of (?:your|his|her|their|my)\b", "a comparison turned into a claim about time"),
    (r"\bextensive experience\b", "unearned scale"),
    (r"\bdeep (?:expertise|experience|knowledge)\b", "unearned depth"),
    (r"\bexpert (?:in|at|with)\b", "unearned mastery"),
    (r"\bmastery of\b", "unearned mastery"),
    (r"\bseasoned\b", "unearned tenure"),
    (r"\bveteran\b", "unearned tenure"),
    (r"\bbuilds on your years\b", "a comparison turned into a claim about time"),
]


def envelope(text: str, max_words: int = DEFAULT_MAX_WORDS,
             max_sections: int = DEFAULT_MAX_SECTIONS) -> list:
    problems = []
    words = len(text.split())
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
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
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
