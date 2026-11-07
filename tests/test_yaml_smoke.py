from pathlib import Path
from typing import List
import pytest
import yaml

from lifesim.config import load_scenario, ScenarioModel
from lifesim.engine import run

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "scenarios"
DEFAULTS_DIR = REPO_ROOT / "defaults"

SCENARIO_FILES = sorted(list(SCENARIOS_DIR.glob("*.yaml")))
DEFAULT_FILES = sorted(list(DEFAULTS_DIR.glob("*.yaml")))


@pytest.mark.parametrize("scenario_file", SCENARIO_FILES, ids=lambda p: p.name)
def test_scenario_smoke(scenario_file: Path) -> None:
    scenario = load_scenario(str(scenario_file))
    ledger = run(scenario)

    daily_dataframe = ledger.daily_df()
    assert not daily_dataframe.empty
    assert len(daily_dataframe) == scenario.days
    assert "total_net_worth" in daily_dataframe.columns
    assert "net_worth" in ledger.metrics


@pytest.mark.parametrize("default_file", DEFAULT_FILES, ids=lambda p: p.name)
def test_defaults_pack_validation(default_file: Path, tmp_path: Path) -> None:
    with open(default_file, "r", encoding="utf-8") as f_in:
        content = yaml.safe_load(f_in)
    assert isinstance(content, dict)

    # Test that a scenario including this default pack loads and runs cleanly
    test_scenario_path = tmp_path / f"test_include_{default_file.name}"
    abs_include_path = default_file.resolve().as_posix()
    test_scenario_path.write_text(f"""
start: 2026-01-01
days: 35
include:
  - {abs_include_path}
accounts:
  checking:
    balance: 5000.0
""")

    scenario = load_scenario(str(test_scenario_path))
    ledger = run(scenario)
    assert not ledger.daily_df().empty
