from datetime import date
from typing import Optional, Dict, Any, List
from .config import GoalModel, AccountModel


class GoalTracker:
    def __init__(self, goals: List[GoalModel]) -> None:
        self.goals = goals
        self.results: List[Dict[str, Any]] = [
            {
                "name": item.name,
                "kind": item.kind,
                "achieved": False,
                "achieved_date": None,
                "days_to_achieve": None,
                "met_by_target_date": None,
                "final_progress_pct": 0.0,
            }
            for item in goals
        ]

    def evaluate_daily(
        self,
        current_date: date,
        sim_start: date,
        balances: Dict[str, int],
        total_net_worth_dollars: float,
        liquid_net_worth_dollars: float,
        invested_assets_dollars: float,
        trailing_annual_expenses_dollars: float,
        accounts_config: Dict[str, AccountModel],
    ) -> None:
        for idx, goal in enumerate(self.goals):
            status = self.results[idx]
            if status["achieved"]:
                continue

            is_met = False
            progress = 0.0

            if goal.kind == "net_worth":
                ratio = total_net_worth_dollars / goal.target_amount if goal.target_amount > 0.0 else 1.0
                progress = min(1.0, max(0.0, ratio))
                is_met = total_net_worth_dollars >= goal.target_amount

            elif goal.kind == "liquid_net_worth":
                ratio = liquid_net_worth_dollars / goal.target_amount if goal.target_amount > 0.0 else 1.0
                progress = min(1.0, max(0.0, ratio))
                is_met = liquid_net_worth_dollars >= goal.target_amount

            elif goal.kind == "account_balance":
                target_acc = goal.account or "checking"
                current_dollars = balances.get(target_acc, 0) / 100.0
                ratio = current_dollars / goal.target_amount if goal.target_amount > 0.0 else 1.0
                progress = min(1.0, max(0.0, ratio))
                is_met = current_dollars >= goal.target_amount

            elif goal.kind == "debt_free":
                total_debt_cents = sum(
                    -balances[account_name]
                    for account_name, account_cfg in accounts_config.items()
                    if account_cfg.kind in ("credit_card", "loan", "mortgage", "student_loan", "auto_loan")
                    and balances.get(account_name, 0) < 0
                )
                is_met = total_debt_cents == 0
                progress = 1.0 if is_met else 0.0

            elif goal.kind == "emergency_months":
                liquid_cash = sum(
                    balances[account_name] / 100.0
                    for account_name, account_cfg in accounts_config.items()
                    if account_cfg.kind in ("checking", "savings", "hysa") and balances.get(account_name, 0) > 0
                )
                monthly_exp = max(1.0, trailing_annual_expenses_dollars / 12.0)
                current_months = liquid_cash / monthly_exp
                ratio = current_months / goal.target_amount if goal.target_amount > 0.0 else 1.0
                progress = min(1.0, max(0.0, ratio))
                is_met = current_months >= goal.target_amount

            elif goal.kind == "financial_independence":
                annual_exp = max(1.0, trailing_annual_expenses_dollars)
                target_fi_number = annual_exp / goal.swr
                progress = min(1.0, max(0.0, invested_assets_dollars / target_fi_number))
                is_met = invested_assets_dollars >= target_fi_number

            elif goal.kind == "coast_fire":
                annual_exp = max(1.0, trailing_annual_expenses_dollars)
                target_fi_number = annual_exp / goal.swr
                years_away = goal.retirement_age_years_away if goal.retirement_age_years_away is not None else 20.0
                growth_multiplier = (1.0 + goal.real_return_assumption) ** years_away
                projected_invested = invested_assets_dollars * growth_multiplier
                progress = min(1.0, max(0.0, projected_invested / target_fi_number))
                is_met = projected_invested >= target_fi_number

            status["final_progress_pct"] = round(progress * 100.0, 2)
            if is_met:
                status["achieved"] = True
                status["achieved_date"] = current_date
                status["days_to_achieve"] = (current_date - sim_start).days
                if goal.target_date:
                    status["met_by_target_date"] = current_date <= goal.target_date
