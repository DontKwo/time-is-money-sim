from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import pandas as pd

from .config import ScenarioModel
from .engine import run


@dataclass
class ComparisonResult:
    table: pd.DataFrame
    daily_net_worths: Dict[str, pd.Series]
    baseline_name: str
    scenario_metrics: Dict[str, Dict[str, Any]]


@dataclass
class SensitivityResult:
    table: pd.DataFrame
    baseline_ending_nw: float
    levers_tested: List[str]


def compare_scenarios(named_scenarios: Dict[str, ScenarioModel]) -> ComparisonResult:
    scenario_names = list(named_scenarios.keys())
    baseline_name = scenario_names[0]

    rows: List[Dict[str, Any]] = []
    daily_nw_dict: Dict[str, pd.Series] = {}
    scenario_metrics: Dict[str, Dict[str, Any]] = {}

    baseline_ending_nw = 0.0

    for index_val, (scenario_name, scenario) in enumerate(named_scenarios.items()):
        ledger = run(scenario)
        daily_df = ledger.daily_df()
        daily_series = daily_df.set_index("date")["total_net_worth"]
        daily_nw_dict[scenario_name] = daily_series
        scenario_metrics[scenario_name] = ledger.metrics

        nw_stats = ledger.metrics.get("net_worth", {})
        ending_nw = nw_stats.get("ending", 0.0)
        liq_stats = ledger.metrics.get("liquidity", {})
        lowest_chk = liq_stats.get("lowest_checking", 0.0)

        if index_val == 0:
            baseline_ending_nw = ending_nw
            delta_nw = 0.0
        else:
            delta_nw = round(ending_nw - baseline_ending_nw, 2)

        # Look for FI milestone
        fi_goal = next(
            (
                goal_item
                for goal_item in ledger.goal_results
                if goal_item["kind"] in ("financial_independence", "coast_fire") and goal_item["achieved"]
            ),
            None,
        )
        fi_date = str(fi_goal["achieved_date"]) if fi_goal else "Not Reached"

        rows.append({
            "scenario": scenario_name,
            "ending_net_worth": ending_nw,
            "delta_vs_baseline": delta_nw,
            "lowest_checking": lowest_chk,
            "fi_date": fi_date,
        })

    table_df = pd.DataFrame(rows)
    return ComparisonResult(
        table=table_df,
        daily_net_worths=daily_nw_dict,
        baseline_name=baseline_name,
        scenario_metrics=scenario_metrics,
    )


def run_sensitivity_analysis(scenario: ScenarioModel, delta_pct: float = 0.10) -> SensitivityResult:
    base_ledger = run(scenario)
    base_ending_nw = base_ledger.metrics.get("net_worth", {}).get("ending", 0.0)

    rows: List[Dict[str, Any]] = []
    levers_tested: List[str] = []

    # 1. Income flows & Paychecks (+/- delta_pct)
    if scenario.paychecks:
        low_scen = scenario.model_copy(deep=True)
        high_scen = scenario.model_copy(deep=True)
        for paycheck in low_scen.paychecks:
            if paycheck.annual_salary is not None:
                paycheck.annual_salary *= (1.0 - delta_pct)
        for paycheck in high_scen.paychecks:
            if paycheck.annual_salary is not None:
                paycheck.annual_salary *= (1.0 + delta_pct)

        low_nw = run(low_scen).metrics.get("net_worth", {}).get("ending", 0.0)
        high_nw = run(high_scen).metrics.get("net_worth", {}).get("ending", 0.0)
        spread = round(abs(high_nw - low_nw), 2)
        levers_tested.append("Salary Income")
        rows.append({
            "lever": "Salary Income",
            "category": "income",
            "baseline_val": scenario.paychecks[0].annual_salary,
            "low_ending_nw": round(low_nw, 2),
            "high_ending_nw": round(high_nw, 2),
            "spread": spread,
        })

    # 2. Spending Categories (+/- delta_pct)
    categories = sorted(
        set(flow.category for flow in scenario.flows if flow.type == "expense" and flow.category)
    )
    for category_name in categories:
        low_scen = scenario.model_copy(deep=True)
        high_scen = scenario.model_copy(deep=True)
        for flow_item in low_scen.flows:
            if flow_item.category == category_name and flow_item.amount and flow_item.amount.fixed is not None:
                flow_item.amount.fixed *= (1.0 - delta_pct)
        for flow_item in high_scen.flows:
            if flow_item.category == category_name and flow_item.amount and flow_item.amount.fixed is not None:
                flow_item.amount.fixed *= (1.0 + delta_pct)

        low_spending_nw = run(low_scen).metrics.get("net_worth", {}).get("ending", 0.0)
        high_spending_nw = run(high_scen).metrics.get("net_worth", {}).get("ending", 0.0)
        spread = round(abs(low_spending_nw - high_spending_nw), 2)
        lever_name = f"Spending: {category_name}"
        levers_tested.append(lever_name)
        rows.append({
            "lever": lever_name,
            "category": category_name,
            "baseline_val": None,
            "low_ending_nw": round(high_spending_nw, 2),
            "high_ending_nw": round(low_spending_nw, 2),
            "spread": spread,
        })

    # 3. Investment Returns (+/- 1% = 0.01)
    for account_name, account_cfg in scenario.accounts.items():
        has_growth = account_cfg.annual_growth_rate > 0.0
        has_return = account_cfg.expected_return is not None and account_cfg.expected_return > 0.0
        if has_growth or has_return:
            low_scen = scenario.model_copy(deep=True)
            high_scen = scenario.model_copy(deep=True)
            if low_scen.accounts[account_name].expected_return is not None:
                low_scen.accounts[account_name].expected_return = max(0.0, low_scen.accounts[account_name].expected_return - 0.01)
                high_scen.accounts[account_name].expected_return = high_scen.accounts[account_name].expected_return + 0.01
            else:
                low_scen.accounts[account_name].annual_growth_rate = max(0.0, low_scen.accounts[account_name].annual_growth_rate - 0.01)
                high_scen.accounts[account_name].annual_growth_rate = high_scen.accounts[account_name].annual_growth_rate + 0.01

            low_nw = run(low_scen).metrics.get("net_worth", {}).get("ending", 0.0)
            high_nw = run(high_scen).metrics.get("net_worth", {}).get("ending", 0.0)
            spread = round(abs(high_nw - low_nw), 2)
            lever_name = f"Return: {account_name}"
            levers_tested.append(lever_name)
            rows.append({
                "lever": lever_name,
                "category": "investments",
                "baseline_val": account_cfg.expected_return or account_cfg.annual_growth_rate,
                "low_ending_nw": round(low_nw, 2),
                "high_ending_nw": round(high_nw, 2),
                "spread": spread,
            })

    # 4. 401(k) Contribution Rate (+/- 2% = 0.02)
    for paycheck_idx, paycheck in enumerate(scenario.paychecks):
        if paycheck.retirement_401k and paycheck.retirement_401k.enabled:
            low_scen = scenario.model_copy(deep=True)
            high_scen = scenario.model_copy(deep=True)
            low_scen.paychecks[paycheck_idx].retirement_401k.traditional_pct = max(0.0, paycheck.retirement_401k.traditional_pct - 0.02)
            high_scen.paychecks[paycheck_idx].retirement_401k.traditional_pct = min(1.0, paycheck.retirement_401k.traditional_pct + 0.02)

            low_nw = run(low_scen).metrics.get("net_worth", {}).get("ending", 0.0)
            high_nw = run(high_scen).metrics.get("net_worth", {}).get("ending", 0.0)
            spread = round(abs(high_nw - low_nw), 2)
            lever_name = f"401k Deferral: {paycheck.name}"
            levers_tested.append(lever_name)
            rows.append({
                "lever": lever_name,
                "category": "retirement",
                "baseline_val": paycheck.retirement_401k.traditional_pct,
                "low_ending_nw": round(low_nw, 2),
                "high_ending_nw": round(high_nw, 2),
                "spread": spread,
            })

    table_df = pd.DataFrame(rows)
    if not table_df.empty:
        table_df = table_df.sort_values("spread", ascending=False).reset_index(drop=True)

    return SensitivityResult(
        table=table_df,
        baseline_ending_nw=base_ending_nw,
        levers_tested=levers_tested,
    )

