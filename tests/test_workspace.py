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
