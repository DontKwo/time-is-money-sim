import calendar
from datetime import date
from typing import Any, Dict, List, Tuple
import numpy as np

from .config import PolicyModel, ScenarioModel
from .schedule import should_fire, shift_date
from .amounts import resolve_flow_amount_cents
from .macro import MacroState
from .taxes import YearTaxAccumulator, compute_april_settlement_cents
from .payroll import (
    PayrollState,
    process_paycheck,
    process_bonus,
    process_espp_purchase,
    process_year_end_true_up,
    process_rsu_vest,
    _resolve_annual_salary,
    _infer_pay_periods,
)
from .accounts import AccountManager, INVESTMENT_KINDS
from .policies import (
    apply_shortfall_cover,
    apply_payday_skim,
    apply_excess_sweep,
    apply_debt_payoff,
    apply_emergency_fund_target,
    apply_portfolio_rebalance,
    apply_retirement_drawdown,
    apply_roth_conversion_ladder,
    apply_sinking_fund,
)
from .events import EventManager
from .goals import GoalTracker
from .rng import derive_rng
from .ledger import Ledger


def step_1_macro_rollover(
    day_index: int,
    current_date: date,
    current_tax_year: int,
    tax_state: YearTaxAccumulator,
    payroll_state: PayrollState,
    accounts_manager: AccountManager,
    prior_year_tax_states: Dict[int, YearTaxAccumulator],
    annual_contributions_ytd: Dict[str, int],
    macro_state: MacroState,
) -> Tuple[int, YearTaxAccumulator]:
    # Archive prior year tax state and reset accumulators on Jan 1
    if day_index > 0 and current_date.month == 1 and current_date.day == 1:
        tax_state.ytd_gross_cents = payroll_state.ytd_gross_cents
        tax_state.ytd_fica_wages_cents = payroll_state.ytd_fica_wages_cents
        tax_state.ytd_taxable_ordinary_cents = payroll_state.ytd_taxable_ordinary_cents
        tax_state.ytd_taxable_interest_cents = accounts_manager.ytd_taxable_interest_cents
        tax_state.ytd_qualified_dividends_cents = accounts_manager.ytd_qualified_dividends_cents
        tax_state.ytd_realized_cap_gains_cents = accounts_manager.ytd_realized_cap_gains_cents
        tax_state.ytd_mortgage_interest_cents = accounts_manager.ytd_mortgage_interest_cents
        tax_state.ytd_property_tax_cents = accounts_manager.ytd_property_tax_cents
        tax_state.ytd_fed_withheld_cents = payroll_state.ytd_fed_withheld_cents
        tax_state.ytd_state_withheld_cents = payroll_state.ytd_state_withheld_cents
        tax_state.ytd_fica_withheld_cents = payroll_state.ytd_fica_withheld_cents
        tax_state.ytd_529_non_qualified_earnings_cents = accounts_manager.ytd_529_non_qualified_earnings_cents

        ytd_state_529_deductible = 0
        for acc_name, contrib in accounts_manager.ytd_529_contributions_cents.items():
            config = accounts_manager.configs.get(acc_name)
            if config and config.kind == "college_529" and config.state_tax_deduction_limit is not None:
                limit_cents = int(round(config.state_tax_deduction_limit * 100.0))
                ytd_state_529_deductible += min(contrib, limit_cents)
        tax_state.ytd_state_529_deductible_cents = ytd_state_529_deductible

        prior_year_tax_states[current_tax_year] = tax_state

        current_tax_year = current_date.year
        tax_state = YearTaxAccumulator(current_tax_year)
        payroll_state.reset_year(current_tax_year)
        accounts_manager.ytd_taxable_interest_cents = 0
        accounts_manager.ytd_qualified_dividends_cents = 0
        accounts_manager.ytd_realized_cap_gains_cents = 0
        accounts_manager.ytd_mortgage_interest_cents = 0
        accounts_manager.ytd_property_tax_cents = 0
        accounts_manager.ytd_529_contributions_cents.clear()
        accounts_manager.ytd_529_non_qualified_earnings_cents = 0
        annual_contributions_ytd.clear()

    macro_state.advance_day(current_date)
    return current_tax_year, tax_state


def step_2_events_and_shocks(
    event_manager: EventManager,
    current_date: date,
    start_date: date,
    balances: Dict[str, int],
    ledger: Ledger,
) -> None:
    # Process event reversions and execute daily events
    event_manager.process_reversions(current_date)
    event_manager.process_daily_events(current_date, start_date, balances, ledger)


def step_3_payroll_and_rsus(
    current_date: date,
    scenario: ScenarioModel,
    payroll_state: PayrollState,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    macro_state: MacroState,
    paycheck_fire_counts: Dict[str, Dict[date, int]],
    paycheck_rngs: Dict[str, np.random.Generator],
    policies: List[PolicyModel],
    annual_contributions_ytd: Dict[str, int],
    base_seed: int,
) -> None:
    # Execute paychecks, bonuses, ESPP purchases, 401(k) true-ups, and RSUs
    for paycheck in scenario.paychecks:
        if not paycheck.enabled:
            continue

        pay_count = paycheck_fire_counts.get(paycheck.name, {}).get(current_date, 0)
        if pay_count > 0:
            for repetition_index in range(pay_count):
                process_paycheck(
                    paycheck,
                    current_date,
                    scenario.start,
                    payroll_state,
                    balances,
                    ledger,
                    scenario.taxes,
                    macro_state,
                    paycheck_rngs[paycheck.name],
                )
                # Trigger matching payday_skim policies
                for policy in policies:
                    if not policy.enabled or policy.kind != "payday_skim":
                        continue
                    policy_tag = policy.trigger_tag or "payday"
                    if policy_tag in paycheck.tags or policy_tag == "payday":
                        gross_estimate = _resolve_annual_salary(paycheck, current_date, scenario.start)
                        period_count = _infer_pay_periods(paycheck)
                        inflow_cents = int(round((gross_estimate / period_count) * 100.0))
                        apply_payday_skim(
                            policy,
                            inflow_cents,
                            balances,
                            ledger,
                            current_date,
                            scenario.accounts,
                            annual_contributions_ytd,
                        )

        # Process paycheck bonuses
        for bonus in paycheck.bonuses:
            if not bonus.enabled:
                continue
            if should_fire(bonus.schedule, current_date, scenario.start):
                bonus_rng = derive_rng(base_seed, "bonus", f"{paycheck.name}_{bonus.name}")
                process_bonus(
                    bonus,
                    paycheck,
                    current_date,
                    scenario.start,
                    payroll_state,
                    balances,
                    ledger,
                    scenario.taxes,
                    macro_state,
                    bonus_rng,
                )

        # ESPP purchases on designated month-ends
        if paycheck.espp and paycheck.espp.enabled:
            unused_first_weekday, last_day_of_month = calendar.monthrange(current_date.year, current_date.month)
            if current_date.month in paycheck.espp.purchase_months and current_date.day == last_day_of_month:
                process_espp_purchase(paycheck, current_date, payroll_state, balances, ledger)

        # Employer 401(k) annual true-up on Dec 31
        if current_date.month == 12 and current_date.day == 31:
            process_year_end_true_up(paycheck, current_date, payroll_state, balances, ledger)

    # RSU grants
    for grant in scenario.rsu_grants:
        if grant.enabled and should_fire(grant.schedule, current_date, scenario.start):
            rsu_rng = derive_rng(base_seed, "rsu", grant.name)
            process_rsu_vest(
                grant,
                current_date,
                scenario.start,
                payroll_state,
                balances,
                ledger,
                rsu_rng,
                accounts_manager.cost_bases,
            )


def step_4_income_and_dividends(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    macro_state: MacroState,
    flow_fire_counts: Dict[str, Dict[date, int]],
    flow_rngs: Dict[str, np.random.Generator],
    last_executed_flow_cents: Dict[str, int],
    default_account: str,
    policies: List[PolicyModel],
    annual_contributions_ytd: Dict[str, int],
    payroll_state: PayrollState,
) -> None:
    # Process Social Security benefit deposits on day 3
    if scenario.social_security and scenario.social_security.enabled:
        social_sec_config = scenario.social_security
        if current_date.day == 3 and current_date >= social_sec_config.start_date:
            start_marker = (social_sec_config.start_date.month, social_sec_config.start_date.day)
            prior_to_anniversary = 1 if (current_date.month, current_date.day) < start_marker else 0
            years_elapsed = max(0, current_date.year - social_sec_config.start_date.year - prior_to_anniversary)
            cola_factor = (1.0 + social_sec_config.annual_cola) ** years_elapsed
            benefit_cents = int(round(social_sec_config.monthly_benefit * cola_factor * 100.0))
            target_account = social_sec_config.to_account or default_account
            if target_account in balances:
                accounts_manager.record_deposit(target_account, benefit_cents)
                ledger.append(
                    current_date,
                    "Social Security Benefit",
                    benefit_cents,
                    target_account,
                    balances[target_account],
                    category="income",
                    tx_kind="income",
                )
                taxable_ss_cents = int(round(benefit_cents * social_sec_config.taxable_pct))
                payroll_state.ytd_taxable_ordinary_cents += taxable_ss_cents

    # Process regular income flows and trigger matching payday_skim policies
    for flow in scenario.flows:
        if not flow.enabled or flow.type != "income":
            continue

        income_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
        if income_fire_count <= 0:
            continue

        for repetition_index in range(income_fire_count):
            if flow.skip_prob > 0.0 and flow_rngs[flow.name].random() < flow.skip_prob:
                continue

            amount_cents = resolve_flow_amount_cents(
                flow,
                current_date,
                scenario.start,
                flow_rngs[flow.name],
                macro_state,
                last_executed_flow_cents.get(flow.name),
                balances,
            )
            last_executed_flow_cents[flow.name] = amount_cents
            target_account = flow.to_account or default_account
            if target_account not in balances:
                continue

            accounts_manager.record_deposit(target_account, amount_cents)
            ledger.append(
                current_date,
                flow.name,
                amount_cents,
                target_account,
                balances[target_account],
                category=flow.category or "income",
                tx_kind="flow",
            )

            # Trigger payday_skim policies matching flow tags
            for policy in policies:
                if not policy.enabled or policy.kind != "payday_skim":
                    continue
                policy_tag = policy.trigger_tag or "payday"
                if policy_tag in flow.tags:
                    apply_payday_skim(
                        policy,
                        amount_cents,
                        balances,
                        ledger,
                        current_date,
                        scenario.accounts,
                        annual_contributions_ytd,
                    )


def step_5_tax_settlement(
    current_date: date,
    scenario: ScenarioModel,
    macro_state: MacroState,
    prior_year_tax_states: Dict[int, YearTaxAccumulator],
    default_account: str,
    balances: Dict[str, int],
    ledger: Ledger,
) -> None:
    # Process annual tax settlement or refund on shifted April 15
    if scenario.taxes and scenario.taxes.enabled and scenario.taxes.april_true_up:
        base_tax_day = date(current_date.year, 4, 15)
        shifted_tax_day = shift_date(base_tax_day, weekend_rule="after", respect_holidays=True)
        if current_date == shifted_tax_day:
            prior_tax_year = current_date.year - 1
            if prior_tax_year in prior_year_tax_states:
                prior_state = prior_year_tax_states[prior_tax_year]
                settlement_cents = compute_april_settlement_cents(
                    prior_state, scenario.taxes, macro_state.inflation_index
                )
                settlement_account = scenario.taxes.settlement_account or default_account
                if settlement_cents > 0:
                    balances[settlement_account] -= settlement_cents
                    ledger.append(
                        current_date,
                        "Annual Tax True-Up Owed",
                        -settlement_cents,
                        settlement_account,
                        balances[settlement_account],
                        category="taxes",
                        tx_kind="tax",
                    )
                elif settlement_cents < 0:
                    refund_cents = -settlement_cents
                    balances[settlement_account] += refund_cents
                    ledger.append(
                        current_date,
                        "Annual Tax Refund",
                        refund_cents,
                        settlement_account,
                        balances[settlement_account],
                        category="taxes",
                        tx_kind="tax",
                    )


def step_6_loan_payments(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    default_account: str,
    policies: List[PolicyModel],
    balances: Dict[str, int],
    ledger: Ledger,
) -> None:
    # Accrue loan interest and process scheduled loan and mortgage payments
    accounts_manager.accrue_daily_liabilities(current_date)
    for account_name, account_model in scenario.accounts.items():
        if account_model.kind in ("loan", "mortgage", "student_loan", "auto_loan"):
            funding_account = account_model.payment_from_account or default_account
            for policy in policies:
                if policy.enabled and policy.kind == "shortfall_cover" and policy.to_account == funding_account:
                    target_principal_interest = accounts_manager.scheduled_pi_cents.get(account_name, 0)
                    min_cover_cents = int(round(policy.minimum_balance * 100.0))
                    apply_shortfall_cover(
                        funding_account,
                        target_principal_interest,
                        policy.from_accounts,
                        balances,
                        ledger,
                        current_date,
                        min_cover_cents,
                    )
            accounts_manager.process_loan_payment(account_name, current_date, ledger)


def step_7_expense_flows(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    macro_state: MacroState,
    flow_fire_counts: Dict[str, Dict[date, int]],
    flow_rngs: Dict[str, np.random.Generator],
    last_executed_flow_cents: Dict[str, int],
    default_account: str,
    policies: List[PolicyModel],
) -> int:
    # Execute expense flows across cards, shortfall cover, and checking
    day_expense_cents = 0
    for flow in scenario.flows:
        if not flow.enabled or flow.type != "expense":
            continue

        expense_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
        if expense_fire_count <= 0:
            continue

        for repetition_index in range(expense_fire_count):
            if flow.skip_prob > 0.0 and flow_rngs[flow.name].random() < flow.skip_prob:
                continue

            amount_cents = resolve_flow_amount_cents(
                flow,
                current_date,
                scenario.start,
                flow_rngs[flow.name],
                macro_state,
                last_executed_flow_cents.get(flow.name),
                balances,
            )
            last_executed_flow_cents[flow.name] = amount_cents
            account_name = flow.from_account or default_account
            if account_name not in balances:
                continue

            account_model = scenario.accounts[account_name]

            # Credit card expense handling
            if account_model.kind == "credit_card":
                charge_successful = accounts_manager.charge_credit_card(account_name, amount_cents, flow.category)
                if charge_successful:
                    ledger.append(
                        current_date,
                        flow.name,
                        -amount_cents,
                        account_name,
                        balances[account_name],
                        category=flow.category or "expense",
                        tx_kind="flow",
                    )
                    day_expense_cents += amount_cents
                continue

            # Bank account auto-transfers
            for rule in scenario.auto_transfers or []:
                if rule.to_account != account_name or rule.from_account not in balances:
                    continue
                minimum_balance_cents = int(round(rule.minimum_balance * 100))
                projected_balance = balances[account_name] - amount_cents
                needed_cents = max(0, minimum_balance_cents - projected_balance)
                transfer_cents = min(needed_cents, max(0, balances[rule.from_account]))
                if transfer_cents > 0:
                    balances[rule.from_account] -= transfer_cents
                    balances[account_name] += transfer_cents
                    transfer_tx_name = f"Automatic transfer: {rule.from_account} to {account_name}"
                    ledger.append(
                        current_date,
                        transfer_tx_name,
                        -transfer_cents,
                        rule.from_account,
                        balances[rule.from_account],
                        tx_kind="transfer",
                    )
                    ledger.append(
                        current_date,
                        transfer_tx_name,
                        transfer_cents,
                        account_name,
                        balances[account_name],
                        tx_kind="transfer",
                    )

            # Shortfall cover policies
            for policy in policies:
                if policy.enabled and policy.kind == "shortfall_cover" and policy.to_account == account_name:
                    min_cover_cents = int(round(policy.minimum_balance * 100.0))
                    apply_shortfall_cover(
                        account_name,
                        amount_cents,
                        policy.from_accounts,
                        balances,
                        ledger,
                        current_date,
                        min_cover_cents,
                    )

            # Overdraft limit check
            overdraft_limit_dollars = account_model.overdraft_limit
            limit_cents = int(round(overdraft_limit_dollars * 100)) if overdraft_limit_dollars is not None else None
            if limit_cents is not None and (balances[account_name] - amount_cents) < -limit_cents:
                accounts_manager.declined_tx_count += 1
                continue

            balances[account_name] -= amount_cents
            day_expense_cents += amount_cents
            ledger.append(
                current_date,
                flow.name,
                -amount_cents,
                account_name,
                balances[account_name],
                category=flow.category or "expense",
                tx_kind="flow",
            )

            # Overdraft fee check
            if balances[account_name] < 0 and account_model.overdraft_fee and account_model.overdraft_fee > 0:
                fee_count = accounts_manager.overdraft_fee_count_today.get(account_name, 0)
                if fee_count < account_model.max_overdraft_fees_per_day:
                    fee_cents = int(round(account_model.overdraft_fee * 100))
                    balances[account_name] -= fee_cents
                    accounts_manager.total_overdraft_fees_cents += fee_cents
                    accounts_manager.overdraft_fee_count_today[account_name] = fee_count + 1
                    ledger.append(
                        current_date,
                        f"{flow.name} Overdraft Fee",
                        -fee_cents,
                        account_name,
                        balances[account_name],
                        category="fees",
                        tx_kind="fee",
                    )

    return day_expense_cents


def step_8_transfers(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    macro_state: MacroState,
    flow_fire_counts: Dict[str, Dict[date, int]],
    flow_rngs: Dict[str, np.random.Generator],
    last_executed_flow_cents: Dict[str, int],
    default_account: str,
    annual_contributions_ytd: Dict[str, int],
) -> None:
    # Execute scheduled transfer flows between accounts
    for flow in scenario.flows:
        if not flow.enabled or flow.type != "transfer":
            continue

        transfer_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
        if transfer_fire_count <= 0:
            continue

        for repetition_index in range(transfer_fire_count):
            if flow.skip_prob > 0.0 and flow_rngs[flow.name].random() < flow.skip_prob:
                continue

            amount_cents = resolve_flow_amount_cents(
                flow,
                current_date,
                scenario.start,
                flow_rngs[flow.name],
                macro_state,
                last_executed_flow_cents.get(flow.name),
                balances,
            )
            last_executed_flow_cents[flow.name] = amount_cents
            source_account = flow.from_account or default_account
            destination_account = flow.to_account or default_account
            if source_account not in balances or destination_account not in balances:
                continue

            source_config = scenario.accounts.get(source_account)
            overdraft_limit_dollars = source_config.overdraft_limit if source_config else None
            limit_cents = int(round(overdraft_limit_dollars * 100)) if overdraft_limit_dollars is not None else None
            if limit_cents is not None and (balances[source_account] - amount_cents) < -limit_cents:
                continue

            destination_config = scenario.accounts.get(destination_account)
            ira_contribution_limit = (
                destination_config.annual_contribution_limit if destination_config else None
            )
            if ira_contribution_limit is not None:
                cap_cents = int(round(ira_contribution_limit * 100.0))
                used_cents = annual_contributions_ytd.get(destination_account, 0)
                allowed_cents = min(amount_cents, max(0, cap_cents - used_cents))
            else:
                allowed_cents = amount_cents

            if allowed_cents <= 0:
                continue

            accounts_manager.record_withdrawal(source_account, allowed_cents, category=flow.category or "", tags=flow.tags)
            accounts_manager.record_deposit(destination_account, allowed_cents)
            annual_contributions_ytd[destination_account] = annual_contributions_ytd.get(destination_account, 0) + allowed_cents
            ledger.append(
                current_date,
                flow.name,
                -allowed_cents,
                source_account,
                balances[source_account],
                category=flow.category or "transfer",
                tx_kind="transfer",
            )
            ledger.append(
                current_date,
                flow.name,
                allowed_cents,
                destination_account,
                balances[destination_account],
                category=flow.category or "transfer",
                tx_kind="transfer",
            )

            if (
                balances[source_account] < 0
                and source_config
                and source_config.overdraft_fee
                and source_config.overdraft_fee > 0
            ):
                fee_cents = int(round(source_config.overdraft_fee * 100))
                balances[source_account] -= fee_cents
                ledger.append(
                    current_date,
                    f"{flow.name} Overdraft Fee",
                    -fee_cents,
                    source_account,
                    balances[source_account],
                    category="fees",
                    tx_kind="fee",
                )

            # Optional employer match multiplier on transfer
            if flow.employer_match_multiplier and flow.employer_match_multiplier > 0.0:
                raw_match_cents = int(round(allowed_cents * flow.employer_match_multiplier))
                if flow.employer_match_cap_per_event is not None:
                    event_cap_cents = int(round(flow.employer_match_cap_per_event * 100.0))
                    match_cents = min(raw_match_cents, event_cap_cents)
                else:
                    match_cents = raw_match_cents

                if match_cents > 0:
                    accounts_manager.record_deposit(destination_account, match_cents)
                    ledger.append(
                        current_date,
                        f"{flow.name} Employer Match",
                        match_cents,
                        destination_account,
                        balances[destination_account],
                        category="income",
                        tx_kind="match",
                    )


def step_9_credit_cards(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    policies: List[PolicyModel],
    balances: Dict[str, int],
    ledger: Ledger,
) -> None:
    # Process credit card autopay, due dates, and statement dates
    for card_name, card_config in scenario.accounts.items():
        if card_config.kind == "credit_card":
            if card_config.autopay and card_config.autopay.enabled:
                autopay_source = card_config.autopay.from_account
                for policy in policies:
                    if (
                        policy.enabled
                        and policy.kind == "shortfall_cover"
                        and policy.to_account == autopay_source
                    ):
                        statement_due_cents = accounts_manager.remaining_statement_due_cents.get(card_name, 0)
                        min_cover_cents = int(round(policy.minimum_balance * 100.0))
                        apply_shortfall_cover(
                            autopay_source,
                            statement_due_cents,
                            policy.from_accounts,
                            balances,
                            ledger,
                            current_date,
                            min_cover_cents,
                        )
            accounts_manager.process_credit_card_due_date(card_name, current_date, ledger)
            accounts_manager.process_credit_card_statement(card_name, current_date, ledger)


def step_10_policies(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    policies: List[PolicyModel],
    policy_fire_counts: Dict[str, Dict[date, int]],
    annual_contributions_ytd: Dict[str, int],
    monthly_debt_payments_made: Dict[str, int],
    daily_expenses_history: List[int],
    payroll_state: PayrollState,
) -> None:
    # Execute debt payoff, sweeps, and retirement drawdown policies
    if current_date.day == 1:
        monthly_debt_payments_made.clear()

    recent_window = daily_expenses_history[-90:] if daily_expenses_history else []
    total_recent = sum(recent_window)
    num_recent_days = max(1, len(recent_window))
    trailing_expense = (total_recent / (100.0 * num_recent_days)) if recent_window else 0.0

    for policy in policies:
        if not policy.enabled:
            continue
        if policy.start and current_date < policy.start:
            continue
        if policy.end and current_date > policy.end:
            continue
        if policy.schedule is not None:
            policy_count = policy_fire_counts.get(policy.name, {}).get(current_date, 0)
            if policy_count <= 0:
                continue

        if policy.kind == "debt_payoff":
            apply_debt_payoff(
                policy,
                balances,
                ledger,
                current_date,
                scenario.accounts,
                monthly_debt_payments_made,
            )
        elif policy.kind == "emergency_fund_target":
            apply_emergency_fund_target(
                policy,
                balances,
                ledger,
                current_date,
                trailing_expense,
            )
        elif policy.kind == "excess_sweep":
            apply_excess_sweep(
                policy,
                balances,
                ledger,
                current_date,
                scenario.accounts,
                annual_contributions_ytd,
            )
        elif policy.kind == "portfolio_rebalance":
            apply_portfolio_rebalance(
                policy,
                balances,
                ledger,
                current_date,
                accounts_manager,
            )
        elif policy.kind == "retirement_drawdown":
            apply_retirement_drawdown(
                policy,
                balances,
                ledger,
                current_date,
                payroll_state,
            )
        elif policy.kind == "roth_conversion_ladder":
            apply_roth_conversion_ladder(
                policy,
                balances,
                ledger,
                current_date,
                payroll_state,
                accounts_manager,
            )
        elif policy.kind == "sinking_fund":
            apply_sinking_fund(
                policy,
                balances,
                ledger,
                current_date,
                scenario.flows,
            )


def step_11_returns_and_interest(
    current_date: date,
    accounts_manager: AccountManager,
    ledger: Ledger,
) -> None:
    # Process daily investment compounding and savings account interest
    accounts_manager.process_investment_returns_and_savings(current_date, ledger)


def step_12_snapshot_and_goals(
    current_date: date,
    scenario: ScenarioModel,
    accounts_manager: AccountManager,
    balances: Dict[str, int],
    ledger: Ledger,
    goal_tracker: GoalTracker,
    daily_expenses_history: List[int],
) -> None:
    # Record closing balance snapshots and evaluate scenario goals
    accounts_manager.overdraft_fee_count_today = {name: 0 for name in scenario.accounts}

    positive_balances = sum(
        balance_cents for balance_cents in balances.values() if balance_cents > 0
    )
    asset_sum_cents = sum(
        asset_cents for asset_cents in accounts_manager.asset_values_cents.values()
    )
    total_assets_cents = positive_balances + asset_sum_cents
    total_debt_cents = sum(
        -debt_cents for debt_cents in balances.values() if debt_cents < 0
    )
    total_net_worth_cents = total_assets_cents - total_debt_cents

    liquid_positive_cents = sum(
        balances[account_name]
        for account_name, account_config in scenario.accounts.items()
        if account_config.kind in ("checking", "savings", "hysa", "cd")
        and balances.get(account_name, 0) > 0
    )
    liquid_debt_cents = sum(
        -balances[account_name]
        for account_name, account_config in scenario.accounts.items()
        if account_config.kind in ("credit_card", "loan", "mortgage", "student_loan", "auto_loan")
        and balances.get(account_name, 0) < 0
    )
    liquid_cents = liquid_positive_cents - liquid_debt_cents

    daily_record: Dict[str, Any] = {
        "date": current_date,
        "total_net_worth": round(total_net_worth_cents / 100.0, 2),
        "liquid_net_worth": round(liquid_cents / 100.0, 2),
        "vested_net_worth": round(total_net_worth_cents / 100.0, 2),
        "total_assets": round(total_assets_cents / 100.0, 2),
        "total_debt": round(total_debt_cents / 100.0, 2),
    }
    for account_name, balance_cents in balances.items():
        daily_record[account_name] = round(balance_cents / 100.0, 2)
    ledger.daily_records.append(daily_record)

    # Evaluate financial goals
    recent_window = daily_expenses_history[-90:] if daily_expenses_history else []
    total_recent = sum(recent_window)
    num_recent_days = max(1, len(recent_window))
    trailing_expense = (total_recent / (100.0 * num_recent_days)) if recent_window else 0.0

    invested_dollars = sum(
        balances[account_name]
        for account_name, account_config in scenario.accounts.items()
        if account_config.kind in INVESTMENT_KINDS and balances.get(account_name, 0) > 0
    ) / 100.0
    annual_expense_estimate = trailing_expense * 365.25
    goal_tracker.evaluate_daily(
        current_date,
        scenario.start,
        balances,
        total_net_worth_cents / 100.0,
        liquid_cents / 100.0,
        invested_dollars,
        annual_expense_estimate,
        scenario.accounts,
    )
