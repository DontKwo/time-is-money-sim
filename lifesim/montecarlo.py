from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import numpy as np

from .config import ScenarioModel
from .engine import run


@dataclass
class MonteCarloResult:
    num_runs: int
    days: int
    dates: List[date]
    net_worth_percentiles: Dict[str, np.ndarray]
    liquid_net_worth_percentiles: Dict[str, np.ndarray]
    prob_ever_overdrawn: float
    prob_negative_ending_net_worth: float
    min_checking_p5: float
    goal_stats: List[Dict[str, Any]]
    summary_metrics: Dict[str, Any] = field(default_factory=dict)


def run_monte_carlo(scenario: ScenarioModel, num_runs: int = 500) -> MonteCarloResult:
    base_seed = scenario.seed if scenario.seed is not None else 42
    total_days = scenario.days

    nw_matrix = np.zeros((num_runs, total_days), dtype=np.float64)
    liquid_matrix = np.zeros((num_runs, total_days), dtype=np.float64)
    min_checking_runs = np.zeros(num_runs, dtype=np.float64)

    ever_overdrawn_count = 0
    negative_ending_nw_count = 0
    goal_achieved_counts: Dict[str, int] = {goal.name: 0 for goal in scenario.goals}
    goal_days_to_achieve: Dict[str, List[int]] = {goal.name: [] for goal in scenario.goals}
    sim_dates: List[date] = []

    for trial_index in range(num_runs):
        trial_seed = (base_seed + trial_index * 10007) % (2**31)
        trial_scenario = scenario.model_copy(deep=True)
        trial_scenario.seed = trial_seed

        trial_ledger = run(trial_scenario)
        daily_df = trial_ledger.daily_df()

        if trial_index == 0:
            sim_dates = list(daily_df["date"])

        nw_matrix[trial_index, :] = daily_df["total_net_worth"].values[:total_days]
        liquid_matrix[trial_index, :] = daily_df["liquid_net_worth"].values[:total_days]

        if "checking" in daily_df.columns:
            lowest_checking = float(daily_df["checking"].min())
            min_checking_runs[trial_index] = lowest_checking
            if (daily_df["checking"] < 0.0).any():
                ever_overdrawn_count += 1
        else:
            min_checking_runs[trial_index] = 0.0

        if nw_matrix[trial_index, -1] < 0.0:
            negative_ending_nw_count += 1

        for goal_result in trial_ledger.goal_results:
            goal_name = goal_result["name"]
            if goal_result["achieved"]:
                goal_achieved_counts[goal_name] = goal_achieved_counts.get(goal_name, 0) + 1
                if goal_result["days_to_achieve"] is not None:
                    goal_days_to_achieve[goal_name].append(goal_result["days_to_achieve"])

    percentile_levels = [5, 10, 25, 50, 75, 90, 95]
    percentile_keys = ["p5", "p10", "p25", "p50", "p75", "p90", "p95"]

    nw_percentiles: Dict[str, np.ndarray] = {}
    liquid_percentiles: Dict[str, np.ndarray] = {}

    for level, key in zip(percentile_levels, percentile_keys):
        nw_percentiles[key] = np.percentile(nw_matrix, level, axis=0)
        liquid_percentiles[key] = np.percentile(liquid_matrix, level, axis=0)

    goal_stats: List[Dict[str, Any]] = []
    for goal in scenario.goals:
        goal_name = goal.name
        achieved_count = goal_achieved_counts.get(goal_name, 0)
        prob_achieved = round(achieved_count / max(1, num_runs), 4)
        days_list = goal_days_to_achieve.get(goal_name, [])

        if days_list:
            median_days = int(np.median(days_list))
            median_date = str(scenario.start + timedelta(days=median_days))
        else:
            median_days = None
            median_date = None

        goal_stats.append({
            "name": goal_name,
            "prob_achieved": prob_achieved,
            "median_achieved_date": median_date,
            "median_days_to_achieve": median_days,
        })

    min_checking_p5 = float(np.percentile(min_checking_runs, 5))
    prob_overdrawn = round(ever_overdrawn_count / max(1, num_runs), 4)
    prob_negative_nw = round(negative_ending_nw_count / max(1, num_runs), 4)

    return MonteCarloResult(
        num_runs=num_runs,
        days=total_days,
        dates=sim_dates,
        net_worth_percentiles=nw_percentiles,
        liquid_net_worth_percentiles=liquid_percentiles,
        prob_ever_overdrawn=prob_overdrawn,
        prob_negative_ending_net_worth=prob_negative_nw,
        min_checking_p5=round(min_checking_p5, 2),
        goal_stats=goal_stats,
    )

