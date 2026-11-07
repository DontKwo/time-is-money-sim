import os
from lifesim.config import load_scenario

def test_duplicate_flow_names(tmp_path):
    scenario_file = tmp_path / "scenario.yaml"
    with open(scenario_file, "w") as f:
        f.write("""
start: 2026-01-01
days: 30
accounts:
  checking: {balance: 1000}
flows:
  - name: DuplicateFlow
    type: expense
    schedule: {monthly: 1}
    amount: {fixed: 100}
  - name: DuplicateFlow
    type: expense
    schedule: {monthly: 1}
    amount: {fixed: 50}
""")

    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    try:
        scenario = load_scenario("scenario.yaml")
        assert len(scenario.flows) == 2
        assert scenario.flows[0].name == "DuplicateFlow"
        assert scenario.flows[1].name == "DuplicateFlow_2"
    finally:
        os.chdir(orig_dir)
