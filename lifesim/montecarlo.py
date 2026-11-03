from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import numpy as np

from .config import ScenarioModel, RateStepModel
from .engine import run


HISTORICAL_CRISES = {
    "1929_depression": [
        {"duration_days": 365, "rate": -0.119, "volatility": 0.25},
        {"duration_days": 365, "rate": -0.251, "volatility": 0.35},
        {"duration_days": 365, "rate": -0.438, "volatility": 0.40},
        {"duration_days": 365, "rate": -0.082, "volatility": 0.30},
    ],
    "1973_stagflation": [
        {"duration_days": 365, "rate": -0.147, "volatility": 0.20},
        {"duration_days": 365, "rate": -0.265, "volatility": 0.25},
        {"duration_days": 365, "rate": 0.372, "volatility": 0.15},
    ],
    "2000_dotcom": [
        {"duration_days": 365, "rate": -0.091, "volatility": 0.20},
        {"duration_days": 365, "rate": -0.119, "volatility": 0.25},
        {"duration_days": 365, "rate": -0.221, "volatility": 0.30},
    ],
    "2008_gfc": [
        {"duration_days": 365, "rate": -0.385, "volatility": 0.45},
        {"duration_days": 365, "rate": 0.265, "volatility": 0.20},
        {"duration_days": 365, "rate": 0.151, "volatility": 0.15},
    ],
}


def simulate_historical_crisis(scenario: ScenarioModel, crisis_type: str) -> dict[str, Any]:
    if crisis_type not in HISTORICAL_CRISES:
        raise ValueError(f"Unknown crisis_type: {crisis_type}. Must be one of {list(HISTORICAL_CRISES.keys())}")

    crisis_scenario = scenario.model_copy(deep=True)
    sequence = HISTORICAL_CRISES[crisis_type]

    for acc_name, acc in crisis_scenario.accounts.items():
        if acc.kind in ("investment", "traditional_401k", "roth_401k", "traditional_ira", "roth_ira", "hsa", "529"):
            acc.rate_steps = []
            current_start = crisis_scenario.start

            for step in sequence:
                end_date = current_start + timedelta(days=step["duration_days"] - 1)
                acc.rate_steps.append(
                    RateStepModel(
                        start=current_start,
                        end=end_date,
                        rate=step["rate"],
                        volatility=step["volatility"],
                    )
                )
                current_start = end_date + timedelta(days=1)

            acc.rate_steps.append(
                RateStepModel(
                    start=current_start,
                    end=None,
                    rate=acc.expected_return if acc.expected_return is not None else acc.annual_growth_rate,
                    volatility=acc.volatility,
                )
            )

    ledger = run(crisis_scenario)
    daily_df = ledger.daily_df()

    total_net_worth = daily_df["total_net_worth"].values
    max_drawdown = 0.0
    peak = total_net_worth[0]

    for nw in total_net_worth:
        if nw > peak:
            peak = nw
        dd = (peak - nw) / peak if peak > 0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        "crisis_type": crisis_type,
        "days_simulated": len(daily_df),
        "start_net_worth": float(total_net_worth[0]),
        "end_net_worth": float(total_net_worth[-1]),
        "max_drawdown_pct": float(max_drawdown * 100.0),
        "is_bankrupt": float(total_net_worth[-1]) < 0.0,
    }


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

