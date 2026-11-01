from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from lifesim.config import load_scenario
from lifesim.engine import run


def run_batch(scenario_paths: List[str]) -> pd.DataFrame:
    rows_data: List[Dict[str, Any]] = []

    for path_string in scenario_paths:
        scenario_file_path = Path(path_string)
        if not scenario_file_path.exists():
            continue

        scenario_config = load_scenario(str(scenario_file_path))
        scenario_ledger = run(scenario_config)

        sim_metrics = scenario_ledger.metrics
        net_worth_metrics = sim_metrics.get("net_worth", {})
        cashflow_metrics = sim_metrics.get("cashflow", {})
        liquidity_metrics = sim_metrics.get("liquidity", {})

        ending_net_worth = net_worth_metrics.get("ending", 0.0)
        ending_liquid_net_worth = net_worth_metrics.get("ending_liquid", 0.0)
        savings_rate_value = cashflow_metrics.get("savings_rate", 0.0)
        lowest_checking_balance = liquidity_metrics.get("lowest_checking", 0.0)

        goals_achieved_count = sum(
            1 for goal_result in scenario_ledger.goal_results if goal_result.get("achieved")
        )

        cash_runway_days_value = float("nan")
        transaction_dataframe = scenario_ledger.to_df()

        if not transaction_dataframe.empty:
            non_transfers_dataframe = transaction_dataframe[transaction_dataframe["tx_kind"] != "transfer"]
            expense_transactions_dataframe = non_transfers_dataframe[non_transfers_dataframe["amount"] < 0]

            if not expense_transactions_dataframe.empty:
                last_tx_date = pd.to_datetime(transaction_dataframe["date"].iloc[-1])
                cutoff_tx_date = last_tx_date - pd.Timedelta(days=90)
                recent_expenses_dataframe = expense_transactions_dataframe[
                    pd.to_datetime(expense_transactions_dataframe["date"]) >= cutoff_tx_date
                ]

                if not recent_expenses_dataframe.empty:
                    total_recent_spending = abs(float(recent_expenses_dataframe["amount"].sum()))
                    first_tx_date = pd.to_datetime(transaction_dataframe["date"].iloc[0])
                    actual_cutoff_date = max(cutoff_tx_date, first_tx_date)
                    days_in_recent_period = (last_tx_date - actual_cutoff_date).days
                    if days_in_recent_period > 0:
                        daily_expense_amount = total_recent_spending / days_in_recent_period
                        if daily_expense_amount > 0:
                            cash_runway_days_value = float(ending_liquid_net_worth / daily_expense_amount)

        rows_data.append({
            "Scenario": scenario_file_path.name,
            "Total Net Worth": ending_net_worth,
            "Liquid Net Worth": ending_liquid_net_worth,
            "Savings Rate": savings_rate_value,
            "Cash Runway Days": round(cash_runway_days_value, 2) if not pd.isna(cash_runway_days_value) else cash_runway_days_value,
            "Lowest Checking Balance": lowest_checking_balance,
            "Goals Achieved Count": goals_achieved_count
        })

    if not rows_data:
        empty_dataframe = pd.DataFrame(columns=[
            "Scenario", "Total Net Worth", "Liquid Net Worth",
            "Savings Rate", "Cash Runway Days", "Lowest Checking Balance",
            "Goals Achieved Count"
        ])
        return empty_dataframe.set_index("Scenario")

    summary_dataframe = pd.DataFrame(rows_data)
    return summary_dataframe.set_index("Scenario")
