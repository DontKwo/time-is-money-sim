from typing import Any, Dict
import pandas as pd

from .config import load_scenario
from .engine import run


def run_sensitivity_grid(base_scenario_path: str, param_name: str, values: list[float]) -> pd.DataFrame:
    results: list[Dict[str, Any]] = []

    for val in values:
        scenario = load_scenario(base_scenario_path, overrides=[f"{param_name}={val}"])
        ledger = run(scenario)

        nw_metrics = ledger.metrics.get("net_worth", {})
        ending_nw = nw_metrics.get("ending", 0.0)

        goals_achieved = sum(1 for goal_status in ledger.goal_results if goal_status["achieved"])
        total_goals = len(ledger.goal_results)

        row_data: Dict[str, Any] = {
            param_name: val,
            "ending_net_worth": ending_nw,
            "goals_achieved": goals_achieved,
            "total_goals": total_goals,
        }
        for goal_status in ledger.goal_results:
            row_data[f"goal_{goal_status['name']}_achieved"] = goal_status["achieved"]

        results.append(row_data)

    return pd.DataFrame(results)
