import json
import pytest

import workspace


def test_init_creates_every_lane_directory(tmp_path):
    config = workspace.init(tmp_path)
    for lane in workspace.LANES:
        assert workspace.lane_dir(tmp_path, config, lane).is_dir()
    assert (tmp_path / "Baseline").is_dir()
    assert (tmp_path / "guides").is_dir()


def test_init_writes_config_and_is_reloadable(tmp_path):
    written = workspace.init(tmp_path)
    assert (tmp_path / "jobkit.json").exists()
    assert workspace.load_config(tmp_path) == written


def test_init_is_idempotent_and_preserves_edits(tmp_path):
    config = workspace.init(tmp_path)
    config["score_threshold"] = 8
    (tmp_path / "jobkit.json").write_text(json.dumps(config), encoding="utf-8")
    again = workspace.init(tmp_path)
    assert again["score_threshold"] == 8


def test_init_creates_starter_files(tmp_path):
    workspace.init(tmp_path)
    assert (tmp_path / "intake_site_recipes.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_init_never_overwrites_user_claude_md(tmp_path):
    workspace.init(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# My rules\nNever show me unpaid gigs.\n", encoding="utf-8")
    workspace.init(tmp_path)
    assert "Never show me unpaid gigs" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_init_installs_the_getting_started_guide(tmp_path):
    workspace.init(tmp_path)
    guide = tmp_path / "guides" / "Getting_Started.html"
    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    assert "<title>" in text
    assert 'name="description"' in text
    assert 'name="jobkit-category"' in text
    assert 'name="jobkit-icon"' in text


def test_getting_started_guide_is_self_contained_and_clean(tmp_path):
    workspace.init(tmp_path)
    text = (tmp_path / "guides" / "Getting_Started.html").read_text(encoding="utf-8")
    assert "fetch(" not in text
    assert "XMLHttpRequest" not in text
    assert "—" not in text
    # The customization story: the guide must tell the user their CLAUDE.md wins.
    assert "CLAUDE.md" in text


def test_init_never_overwrites_an_edited_guide(tmp_path):
    workspace.init(tmp_path)
    guide = tmp_path / "guides" / "Getting_Started.html"
    guide.write_text("<html>my edits</html>", encoding="utf-8")
    workspace.init(tmp_path)
    assert guide.read_text(encoding="utf-8") == "<html>my edits</html>"


def test_scan_maps_folders_to_lanes(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_Emeryville_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "8_Riot_LA_ConceptArtist").mkdir()
    found = workspace.scan(tmp_path, config)
    assert found == {
        "7_Pixar_Emeryville_Modeler": "staged",
        "8_Riot_LA_ConceptArtist": "applied",
    }


def test_scan_ignores_dot_and_dunder_folders(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "__pycache__").mkdir()
    (workspace.lane_dir(tmp_path, config, "staged") / ".DS_Store_dir").mkdir()
    assert workspace.scan(tmp_path, config) == {}


def test_scan_ignores_loose_files(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "stray.md").write_text("x", encoding="utf-8")
    assert workspace.scan(tmp_path, config) == {}


def test_safe_join_allows_paths_inside_the_workspace(tmp_path):
    result = workspace.safe_join(tmp_path, "Jobs to Apply to", "7_Pixar_Emeryville_Modeler")
    assert str(result).startswith(str(tmp_path.resolve()))


def test_safe_join_refuses_to_escape_the_workspace(tmp_path):
    with pytest.raises(ValueError, match="outside the workspace"):
        workspace.safe_join(tmp_path, "..", "..", "Desktop", "secrets.txt")


def test_safe_join_refuses_an_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="outside the workspace"):
        workspace.safe_join(tmp_path, "/etc/passwd")


def test_lane_dir_rejects_an_unknown_lane(tmp_path):
    config = workspace.init(tmp_path)
    with pytest.raises(ValueError, match="unknown lane"):
        workspace.lane_dir(tmp_path, config, "nonsense")


# --- FIX 4: duplicate folder name across two lanes must not vanish silently ---

def test_scan_with_warnings_flags_a_folder_that_exists_in_two_lanes(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "7_Pixar_LA_Modeler").mkdir()
    found, warnings = workspace.scan_with_warnings(tmp_path, config)
    assert found["7_Pixar_LA_Modeler"] == "applied"
    assert any("7_Pixar_LA_Modeler" in w and "staged" in w and "applied" in w for w in warnings)


def test_scan_with_warnings_is_empty_for_no_collisions(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler").mkdir()
    _, warnings = workspace.scan_with_warnings(tmp_path, config)
    assert warnings == []


def test_scan_still_returns_a_plain_dict_matching_scan_with_warnings(tmp_path):
    config = workspace.init(tmp_path)
    (workspace.lane_dir(tmp_path, config, "staged") / "7_Pixar_LA_Modeler").mkdir()
    (workspace.lane_dir(tmp_path, config, "applied") / "7_Pixar_LA_Modeler").mkdir()
    found, _ = workspace.scan_with_warnings(tmp_path, config)
    assert workspace.scan(tmp_path, config) == found


# --- FIX 4: a lane renamed in jobkit.json after jobs existed in its old folder ---

def test_find_unmapped_job_dirs_detects_a_renamed_lane(tmp_path):
    config = workspace.init(tmp_path)
    staged_dir = workspace.lane_dir(tmp_path, config, "staged")
    (staged_dir / "7_Pixar_LA_Modeler").mkdir()
    # Rename the lane in config, as if the user edited jobkit.json by hand.
    old_name = config["lanes"]["staged"]
    config["lanes"]["staged"] = "Jobs To Chase"
    unmapped = workspace.find_unmapped_job_dirs(tmp_path, config, {"7_Pixar_LA_Modeler"})
    assert unmapped == {old_name: ["7_Pixar_LA_Modeler"]}


def test_find_unmapped_job_dirs_ignores_dirs_with_no_missing_matches(tmp_path):
    config = workspace.init(tmp_path)
    (tmp_path / "Some Other Folder").mkdir()
    assert workspace.find_unmapped_job_dirs(tmp_path, config, {"7_Pixar_LA_Modeler"}) == {}


def test_find_unmapped_job_dirs_returns_empty_when_nothing_is_missing(tmp_path):
    config = workspace.init(tmp_path)
    assert workspace.find_unmapped_job_dirs(tmp_path, config, set()) == {}


def test_starter_claude_md_has_a_lessons_section(tmp_path):
    """The workspace CLAUDE.md is the plugin's local learning surface: skills
    append dated lessons there and read them back on every task."""
    workspace.init(tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# Lessons learned" in text
    assert "intake_site_recipes.md" in text
