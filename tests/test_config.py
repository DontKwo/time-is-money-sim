import pytest
import os
import yaml
from lifesim.config import load_scenario

def test_load_scenario_path_traversal(tmp_path):
    # Create a dummy "sensitive" file outside the repo root
    sensitive_file = tmp_path / "sensitive.txt"
    sensitive_file.write_text("sensitive data")

    # Create a dummy repository structure
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "requirements.txt").write_text("")

    # Create scenario in the repository
    scenario_dir = repo_root / "scenarios"
    scenario_dir.mkdir()

    scenario_file = scenario_dir / "main.yaml"

    # The path traversal attempts to go up to tmp_path and read sensitive.txt
    traversal_path = "../../sensitive.txt"

    scenario_content = {
        "start": "2024-01-01",
        "days": 30,
        "include": [traversal_path],
        "accounts": {},
        "flows": []
    }

    with open(scenario_file, "w") as f:
        yaml.dump(scenario_content, f)

    # Attempting to load the scenario with a path traversal should raise a ValueError
    with pytest.raises(ValueError, match="Invalid include path: '.*' escapes allowed directories."):
        load_scenario(str(scenario_file))

def test_load_scenario_valid_include(tmp_path):
    # Create a dummy repository structure
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "requirements.txt").write_text("")

    # Create scenario in the repository
    scenario_dir = repo_root / "scenarios"
    scenario_dir.mkdir()

    valid_include_file = scenario_dir / "valid_include.yaml"
    valid_include_content = {
        "accounts": {
            "test_account": {
                "balance": 1000.0
            }
        },
        "flows": []
    }
    with open(valid_include_file, "w") as f:
        yaml.dump(valid_include_content, f)

    scenario_file = scenario_dir / "main.yaml"

    scenario_content = {
        "start": "2024-01-01",
        "days": 30,
        "include": ["valid_include.yaml"],
        "accounts": {},
        "flows": []
    }

    with open(scenario_file, "w") as f:
        yaml.dump(scenario_content, f)

    # Valid include should work without error
    scenario = load_scenario(str(scenario_file))
    assert "test_account" in scenario.accounts
