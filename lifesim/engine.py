from datetime import timedelta
from typing import Dict, List
from .config import ScenarioModel
from .schedule import build_fire_counts
from .macro import MacroState
from .taxes import YearTaxAccumulator
from .payroll import PayrollState
from .accounts import AccountManager
from .events import EventManager
from .goals import GoalTracker
from .analysis import compute_summary
from .rng import derive_rng
from .ledger import Ledger
from .steps import (
    step_1_macro_rollover, step_2_events_and_shocks, step_3_payroll_and_rsus,
    step_4_income_and_dividends, step_5_tax_settlement, step_6_loan_payments,
    step_7_expense_flows, step_8_transfers, step_9_credit_cards,
    step_10_policies, step_11_returns_and_interest, step_12_snapshot_and_goals,
)


def run(scenario: ScenarioModel) -> Ledger:
    ledger = Ledger()
    base_seed = scenario.seed if scenario.seed is not None else 42
    macro_rng = derive_rng(base_seed, "macro", "cpi")
    macro_state = MacroState(scenario.inflation, scenario.start, rng=macro_rng)
    accounts_manager = AccountManager(scenario.accounts, base_seed=base_seed)
    balances = accounts_manager.balances
    default_account = list(scenario.accounts.keys())[0] if scenario.accounts else "checking"
    sim_end_date = scenario.end or (scenario.start + timedelta(days=max(0, scenario.days - 1)))
    current_tax_year = scenario.start.year
    payroll_state = PayrollState(current_tax_year)
    paycheck_rngs = {item.name: derive_rng(base_seed, "payroll", item.name) for item in scenario.paychecks}
    paycheck_fire_counts = {
        item.name: build_fire_counts(item.schedule, scenario.start, sim_end_date, paycheck_rngs[item.name])
        for item in scenario.paychecks
    }
    flow_rngs = {flow.name: derive_rng(base_seed, "flow", flow.name) for flow in scenario.flows}
    flow_fire_counts = {
        flow.name: build_fire_counts(flow.schedule, scenario.start, sim_end_date, flow_rngs[flow.name])
        for flow in scenario.flows
    }
    last_executed_flow_cents: Dict[str, int] = {}
    tax_state = YearTaxAccumulator(current_tax_year)
    prior_year_tax_states: Dict[int, YearTaxAccumulator] = {}

    event_manager = EventManager(
        scenario.events, scenario.flows, scenario.paychecks, accounts_manager, payroll_state, base_seed=base_seed
    )
    policies = sorted(scenario.policies, key=lambda policy: policy.priority)
    policy_fire_counts = {
        item.name: build_fire_counts(item.schedule, scenario.start, sim_end_date)
        for item in scenario.policies if item.schedule
    }
    annual_contributions_ytd: Dict[str, int] = {}
    monthly_debt_payments_made: Dict[str, int] = {}
    goal_tracker = GoalTracker(scenario.goals)
    daily_expenses_history: List[int] = []

    for day_index in range(scenario.days):
        current_date = scenario.start + timedelta(days=day_index)
        current_tax_year, tax_state = step_1_macro_rollover(
            day_index, current_date, current_tax_year, tax_state, payroll_state, accounts_manager,
            prior_year_tax_states, annual_contributions_ytd, macro_state
        )
        step_2_events_and_shocks(event_manager, current_date, scenario.start, balances, ledger)
        step_3_payroll_and_rsus(
            current_date, scenario, payroll_state, accounts_manager, balances, ledger, macro_state,
            paycheck_fire_counts, paycheck_rngs, policies, annual_contributions_ytd, base_seed
        )
        step_4_income_and_dividends(
            current_date, scenario, accounts_manager, balances, ledger, macro_state, flow_fire_counts,
            flow_rngs, last_executed_flow_cents, default_account, policies, annual_contributions_ytd, payroll_state
        )
        step_5_tax_settlement(
            current_date, scenario, macro_state, prior_year_tax_states, default_account, balances, ledger
        )
        step_6_loan_payments(current_date, scenario, accounts_manager, default_account, policies, balances, ledger)
        day_expense = step_7_expense_flows(
            current_date, scenario, accounts_manager, balances, ledger, macro_state, flow_fire_counts,
            flow_rngs, last_executed_flow_cents, default_account, policies
        )
        daily_expenses_history.append(day_expense)
        step_8_transfers(
            current_date, scenario, accounts_manager, balances, ledger, macro_state, flow_fire_counts,
            flow_rngs, last_executed_flow_cents, default_account, annual_contributions_ytd
        )
        step_9_credit_cards(current_date, scenario, accounts_manager, policies, balances, ledger)
        step_10_policies(
            current_date, scenario, accounts_manager, balances, ledger, policies, policy_fire_counts,
            annual_contributions_ytd, monthly_debt_payments_made, daily_expenses_history, payroll_state
        )
        step_11_returns_and_interest(current_date, accounts_manager, ledger)
        step_12_snapshot_and_goals(
            current_date, scenario, accounts_manager, balances, ledger, goal_tracker, daily_expenses_history
        )
        ledger.inflation_indices[current_date] = macro_state.inflation_index

    ledger.goal_results, ledger.metrics = goal_tracker.results, compute_summary(scenario, ledger)
    return ledger
