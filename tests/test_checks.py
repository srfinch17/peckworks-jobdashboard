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


def test_inflation_flags_decade_of_experience():
    assert checks.inflation("over a decade of Houdini experience")


def test_inflation_flags_numeric_years_of_experience():
    assert checks.inflation("10+ years of experience with Unreal")


def test_inflation_flags_bare_years_of_work():
    assert checks.inflation("years of professional Houdini work")


def test_inflation_flags_decade_of_professional_experience():
    assert checks.inflation("a decade of professional experience")


def test_inflation_flags_world_class_superlative():
    assert checks.inflation("world-class environment artist")


def test_inflation_flags_unparalleled_superlative():
    assert checks.inflation("unparalleled attention to detail")


def test_inflation_flags_false_authorship_led_the_team():
    assert checks.inflation("led the team that shipped the environment art")


def test_inflation_flags_false_authorship_architected():
    assert checks.inflation("architected the entire lighting pipeline")


def test_inflation_flags_false_authorship_spearheaded():
    assert checks.inflation("spearheaded the pipeline rewrite")


def test_inflation_flags_battle_tested_superlative():
    assert checks.inflation("battle-tested skills in Substance")


def test_inflation_flags_proven_track_record():
    assert checks.inflation("proven track record of delivering")


def test_inflation_flags_highly_skilled_superlative():
    assert checks.inflation("highly skilled in Maya")


def test_inflation_flags_advanced_expertise():
    assert checks.inflation("advanced expertise in look development")


def test_inflation_allows_contributed_to():
    assert checks.inflation("contributed to the environment pass") == []


def test_inflation_allows_worked_on():
    assert checks.inflation("worked on the backgrounds for the title sequence") == []


def test_inflation_allows_a_comparison_to_a_named_piece():
    assert checks.inflation("similar to the environment work in my Redwood piece") == []


def test_inflation_allows_one_of_several_contributors():
    assert checks.inflation("one of six artists on the crowd system") == []


def test_inflation_allows_assisted_with():
    assert checks.inflation("assisted with the environment pass") == []


def test_inflation_allows_helped_build():
    assert checks.inflation("helped build the pipeline") == []


def test_inflation_allows_supported_the_pipeline_team():
    assert checks.inflation("supported the pipeline team") == []


def test_inflation_allows_a_world_class_employer():
    assert checks.inflation("worked at a world-class studio") == []


def test_inflation_allows_a_world_class_contract_team():
    assert checks.inflation("contracted for a world-class team") == []


def test_inflation_allows_an_award_winning_employer():
    assert checks.inflation("interned at an award-winning studio") == []


def test_inflation_flags_world_class_as_a_self_description():
    assert checks.inflation("world-class environment artist")


def test_inflation_flags_a_world_class_eye():
    assert checks.inflation("a world-class eye for composition")


def test_inflation_flags_unparalleled_attention():
    assert checks.inflation("unparalleled attention to detail")


def test_inflation_flags_i_am_a_world_class_generalist():
    assert checks.inflation("I am a world-class generalist")


LINK_HEAVY = """## Links
- [ArtStation](https://www.artstation.com/example/portfolio/gallery)
- [Personal website](https://example.com/portfolio/gallery/index)
- [Demo reel](https://vimeo.com/showcase/1234567890)
- [LinkedIn](https://www.linkedin.com/in/example-profile-name)
"""


def test_envelope_does_not_count_markdown_syntax_and_urls_as_words():
    assert checks.envelope(LINK_HEAVY, max_words=8, max_sections=6) == []


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
