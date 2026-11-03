from pathlib import Path
from typing import List

import pandas as pd

from .config import load_scenario
from .engine import run
from .analysis import compute_summary


def run_batch(scenario_paths: List[str]) -> pd.DataFrame:
    records: List[dict] = []

    for path_str in scenario_paths:
        path = Path(path_str)
        scenario = load_scenario(str(path))
        ledger = run(scenario)

        metrics = compute_summary(scenario, ledger)
        goals = ledger.goal_results

        # Calculate goals achieved
        goals_achieved = sum(1 for g in goals if g.get("achieved", False))

        # Extract metrics safely from nested dictionaries
        nw = metrics.get("net_worth", {})
        cf = metrics.get("cashflow", {})
        liq = metrics.get("liquidity", {})

        records.append({
            "Scenario": path.name,
            "Total Net Worth": nw.get("ending", 0.0),
            "Liquid Net Worth": nw.get("ending_liquid", 0.0),
            "Savings Rate": cf.get("savings_rate", 0.0),
            "Cash Runway Days": liq.get("cash_runway_days", 0.0),
            "Lowest Checking Balance": liq.get("lowest_checking", 0.0),
            "Goals Achieved Count": goals_achieved,
        })

    return pd.DataFrame(records)


def format_batch_summary(df: pd.DataFrame) -> str:
    # Use pandas to_string to format the dataframe as a string matrix
    return df.to_string(index=False, justify="right")
