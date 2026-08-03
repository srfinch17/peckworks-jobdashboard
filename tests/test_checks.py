import checks


RESUME = """# Jane Q
## Summary
Modeler and texture artist.
## Experience
Made things.
## Education
Art school.
"""


def test_envelope_passes_a_document_inside_bounds():
    assert checks.envelope(RESUME, max_words=500, max_sections=6) == []


def test_envelope_flags_a_document_that_is_too_long():
    long_text = "word " * 900
    problems = checks.envelope(long_text, max_words=500, max_sections=6)
    assert any("too long" in p for p in problems)


def test_envelope_flags_too_many_sections():
    text = "\n".join(f"## Section {i}\nbody\n" for i in range(12))
    problems = checks.envelope(text, max_words=5000, max_sections=6)
    assert any("sections" in p for p in problems)


def test_envelope_counts_only_h2_headings():
    text = "# Title\n## One\n### Sub\n## Two\n"
    assert checks.envelope(text, max_words=500, max_sections=2) == []


def test_banned_phrases_finds_a_hit_case_insensitively():
    hits = checks.banned_phrases("I am a proven self-starter", ["self-starter"])
    assert hits == ["self-starter"]


def test_banned_phrases_returns_empty_when_clean():
    assert checks.banned_phrases("Modeler and texture artist.", ["self-starter"]) == []


def test_inflation_flags_years_of_your_life():
    hits = checks.inflation("which builds on your years of environment art")
    assert hits


def test_inflation_flags_extensive_experience():
    assert checks.inflation("Extensive experience in Houdini")


def test_inflation_flags_expert_claims():
    assert checks.inflation("Expert in Substance Painter")


def test_inflation_allows_a_plain_comparison():
    """Comparisons are fine. It is the comparison-becomes-a-claim shape that lies."""
    assert checks.inflation("Similar to the environment work in my Pixar piece") == []


def test_inflation_allows_hedged_framing():
    assert checks.inflation("Familiar with Houdini") == []


def test_run_all_collects_every_category():
    profile = {
        "banned_phrases": ["self-starter"],
        "envelope": {"max_words": 20, "max_sections": 2},
    }
    text = "## A\n## B\n## C\n" + "Expert in everything, a real self-starter. " * 10
    problems = checks.run_all(text, profile)
    assert any("too long" in p for p in problems)
    assert any("sections" in p for p in problems)
    assert any("self-starter" in p for p in problems)
    assert any("inflation" in p for p in problems)


def test_run_all_is_empty_for_a_clean_document():
    profile = {"banned_phrases": ["self-starter"], "envelope": {"max_words": 500, "max_sections": 6}}
    assert checks.run_all(RESUME, profile) == []


def test_run_all_uses_defaults_when_profile_is_bare():
    assert checks.run_all(RESUME, {}) == []
