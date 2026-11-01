import calendar
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import numpy as np

from .config import (
    ScenarioModel,
    FlowModel,
    PaycheckModel,
)
from .schedule import build_fire_counts, should_fire, shift_date
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
    apply_sinking_fund,
)
from .events import EventManager
from .goals import GoalTracker
from .analysis import compute_summary
from .rng import derive_rng
from .ledger import Ledger


def run(scenario: ScenarioModel) -> Ledger:
    ledger = Ledger()
    base_seed = scenario.seed if scenario.seed is not None else 42

    # 1. Initialize macro, accounts, and payroll state
    macro_rng = derive_rng(base_seed, "macro", "cpi")
    macro_state = MacroState(scenario.inflation, scenario.start, rng=macro_rng)

    accounts_manager = AccountManager(scenario.accounts, base_seed=base_seed)
    balances = accounts_manager.balances
    default_account = list(scenario.accounts.keys())[0] if scenario.accounts else "checking"

    sim_end_date = scenario.end or (scenario.start + timedelta(days=max(0, scenario.days - 1)))

    current_tax_year = scenario.start.year
    payroll_state = PayrollState(current_tax_year)
    paycheck_rngs = {p.name: derive_rng(base_seed, "payroll", p.name) for p in scenario.paychecks}
    paycheck_fire_counts = {
        p.name: build_fire_counts(p.schedule, scenario.start, sim_end_date, paycheck_rngs[p.name])
        for p in scenario.paychecks
    }

    # 2. Initialize flows and taxes state
    flow_rngs = {f.name: derive_rng(base_seed, "flow", f.name) for f in scenario.flows}
    flow_fire_counts = {
        f.name: build_fire_counts(f.schedule, scenario.start, sim_end_date, flow_rngs[f.name])
        for f in scenario.flows
    }
    last_executed_flow_cents: Dict[str, int] = {}

    tax_state = YearTaxAccumulator(current_tax_year)
    prior_year_tax_states: Dict[int, YearTaxAccumulator] = {}

    # 3. Initialize events, policies, and goals
    event_manager = EventManager(
        scenario.events,
        scenario.flows,
        scenario.paychecks,
        accounts_manager,
        payroll_state,
        base_seed=base_seed,
    )

    policies = sorted(scenario.policies, key=lambda policy: policy.priority)
    policy_fire_counts = {
        p.name: build_fire_counts(p.schedule, scenario.start, sim_end_date)
        if p.schedule else {}
        for p in scenario.policies
    }
    annual_contributions_ytd: Dict[str, int] = {}
    monthly_debt_payments_made: Dict[str, int] = {}

    goal_tracker = GoalTracker(scenario.goals)
    daily_expenses_history: List[int] = []

    # Daily execution loop
    for day_index in range(scenario.days):
        current_date = scenario.start + timedelta(days=day_index)

        # Step 1: Year rollover & macro update
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
            prior_year_tax_states[current_tax_year] = tax_state

            current_tax_year = current_date.year
            tax_state = YearTaxAccumulator(current_tax_year)
            payroll_state.reset_year(current_tax_year)
            accounts_manager.ytd_taxable_interest_cents = 0
            accounts_manager.ytd_qualified_dividends_cents = 0
            accounts_manager.ytd_realized_cap_gains_cents = 0
            accounts_manager.ytd_mortgage_interest_cents = 0
            accounts_manager.ytd_property_tax_cents = 0
            annual_contributions_ytd.clear()

        macro_state.advance_day(current_date)

        # Step 2: Scripted events & stochastic shocks
        event_manager.process_reversions(current_date)
        event_manager.process_daily_events(current_date, scenario.start, balances, ledger)

        # Step 3: Paychecks, bonuses, RSU vests, & year-end payroll hooks
        for paycheck in scenario.paychecks:
            if not paycheck.enabled:
                continue

            pay_count = paycheck_fire_counts.get(paycheck.name, {}).get(current_date, 0)
            if pay_count > 0:
                for _ in range(pay_count):
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
                        tag = policy.trigger_tag or "payday"
                        if tag in paycheck.tags or tag == "payday":
                            gross_est = _resolve_annual_salary(paycheck, current_date, scenario.start)
                            periods = _infer_pay_periods(paycheck)
                            inflow_cents = int(round((gross_est / periods) * 100.0))
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
                _, last_day_of_month = calendar.monthrange(current_date.year, current_date.month)
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

        # Step 4: Regular income flows & dividends
        for flow in scenario.flows:
            if not flow.enabled or flow.type != "income":
                continue

            income_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
            if income_fire_count <= 0:
                continue

            for _ in range(income_fire_count):
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
                target_acc = flow.to_account or default_account
                if target_acc not in balances:
                    continue

                accounts_manager.record_deposit(target_acc, amount_cents)
                ledger.append(
                    current_date,
                    flow.name,
                    amount_cents,
                    target_acc,
                    balances[target_acc],
                    category=flow.category or "income",
                    tx_kind="flow",
                )

                # Trigger payday_skim policies matching flow tags
                for policy in policies:
                    if not policy.enabled or policy.kind != "payday_skim":
                        continue
                    tag = policy.trigger_tag or "payday"
                    if tag in flow.tags:
                        apply_payday_skim(
                            policy,
                            amount_cents,
                            balances,
                            ledger,
                            current_date,
                            scenario.accounts,
                            annual_contributions_ytd,
                        )

        # Step 5: April 15 annual tax settlement
        if scenario.taxes and scenario.taxes.enabled and scenario.taxes.april_true_up:
            base_tax_day = date(current_date.year, 4, 15)
            shifted_tax_day = shift_date(base_tax_day, weekend_rule="after", respect_us_holidays=True)
            if current_date == shifted_tax_day:
                prior_year = current_date.year - 1
                if prior_year in prior_year_tax_states:
                    prior_state = prior_year_tax_states[prior_year]
                    settlement_cents = compute_april_settlement_cents(
                        prior_state, scenario.taxes, macro_state.inflation_index
                    )
                    settlement_acc = scenario.taxes.settlement_account or default_account
                    if settlement_cents > 0:
                        balances[settlement_acc] -= settlement_cents
                        ledger.append(
                            current_date,
                            "Annual Tax True-Up Owed",
                            -settlement_cents,
                            settlement_acc,
                            balances[settlement_acc],
                            category="taxes",
                            tx_kind="tax",
                        )
                    elif settlement_cents < 0:
                        refund_cents = -settlement_cents
                        balances[settlement_acc] += refund_cents
                        ledger.append(
                            current_date,
                            "Annual Tax Refund",
                            refund_cents,
                            settlement_acc,
                            balances[settlement_acc],
                            category="taxes",
                            tx_kind="tax",
                        )

        # Step 6: Scheduled loan & mortgage payments
        accounts_manager.accrue_daily_liabilities(current_date)
        for acc_name, acc_model in scenario.accounts.items():
            if acc_model.kind in ("loan", "mortgage", "student_loan", "auto_loan"):
                funding_acc = acc_model.payment_from_account or default_account
                for policy in policies:
                    if policy.enabled and policy.kind == "shortfall_cover" and policy.to_account == funding_acc:
                        pi_target = accounts_manager.scheduled_pi_cents.get(acc_name, 0)
                        min_cover = int(round(policy.minimum_balance * 100.0))
                        apply_shortfall_cover(
                            funding_acc,
                            pi_target,
                            policy.from_accounts,
                            balances,
                            ledger,
                            current_date,
                            min_cover,
                        )
                accounts_manager.process_loan_payment(acc_name, current_date, ledger)

        # Step 7: Scheduled expense flows
        day_expense_cents = 0
        for flow in scenario.flows:
            if not flow.enabled or flow.type != "expense":
                continue

            exp_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
            if exp_fire_count <= 0:
                continue

            for _ in range(exp_fire_count):
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
                acc_name = flow.from_account or default_account
                if acc_name not in balances:
                    continue

                acc_model = scenario.accounts[acc_name]

                # Credit card expense handling
                if acc_model.kind == "credit_card":
                    charged = accounts_manager.charge_credit_card(acc_name, amount_cents, flow.category)
                    if charged:
                        ledger.append(
                            current_date,
                            flow.name,
                            -amount_cents,
                            acc_name,
                            balances[acc_name],
                            category=flow.category or "expense",
                            tx_kind="flow",
                        )
                        day_expense_cents += amount_cents
                    continue

                # Bank account auto-transfers
                for rule in scenario.auto_transfers or []:
                    if rule.to_account != acc_name or rule.from_account not in balances:
                        continue
                    minimum_balance = int(round(rule.minimum_balance * 100))
                    projected = balances[acc_name] - amount_cents
                    needed = max(0, minimum_balance - projected)
                    transfer_amt = min(needed, max(0, balances[rule.from_account]))
                    if transfer_amt > 0:
                        balances[rule.from_account] -= transfer_amt
                        balances[acc_name] += transfer_amt
                        tx_name = f"Automatic transfer: {rule.from_account} to {acc_name}"
                        ledger.append(
                            current_date,
                            tx_name,
                            -transfer_amt,
                            rule.from_account,
                            balances[rule.from_account],
                            tx_kind="transfer",
                        )
                        ledger.append(
                            current_date,
                            tx_name,
                            transfer_amt,
                            acc_name,
                            balances[acc_name],
                            tx_kind="transfer",
                        )

                # Shortfall cover policies
                for policy in policies:
                    if policy.enabled and policy.kind == "shortfall_cover" and policy.to_account == acc_name:
                        min_cover = int(round(policy.minimum_balance * 100.0))
                        apply_shortfall_cover(
                            acc_name,
                            amount_cents,
                            policy.from_accounts,
                            balances,
                            ledger,
                            current_date,
                            min_cover,
                        )

                # Overdraft limit check
                od_lim = acc_model.overdraft_limit
                limit_cents = int(round(od_lim * 100)) if od_lim is not None else None
                if limit_cents is not None and (balances[acc_name] - amount_cents) < -limit_cents:
                    accounts_manager.declined_tx_count += 1
                    continue

                balances[acc_name] -= amount_cents
                day_expense_cents += amount_cents
                ledger.append(
                    current_date,
                    flow.name,
                    -amount_cents,
                    acc_name,
                    balances[acc_name],
                    category=flow.category or "expense",
                    tx_kind="flow",
                )

                # Overdraft fee check
                if balances[acc_name] < 0 and acc_model.overdraft_fee and acc_model.overdraft_fee > 0:
                    fee_count = accounts_manager.overdraft_fee_count_today.get(acc_name, 0)
                    if fee_count < acc_model.max_overdraft_fees_per_day:
                        fee_cents = int(round(acc_model.overdraft_fee * 100))
                        balances[acc_name] -= fee_cents
                        accounts_manager.total_overdraft_fees_cents += fee_cents
                        accounts_manager.overdraft_fee_count_today[acc_name] = fee_count + 1
                        ledger.append(
                            current_date,
                            f"{flow.name} Overdraft Fee",
                            -fee_cents,
                            acc_name,
                            balances[acc_name],
                            category="fees",
                            tx_kind="fee",
                        )

        daily_expenses_history.append(day_expense_cents)

        # Step 8: Scheduled transfer flows
        for flow in scenario.flows:
            if not flow.enabled or flow.type != "transfer":
                continue

            trans_fire_count = flow_fire_counts.get(flow.name, {}).get(current_date, 0)
            if trans_fire_count <= 0:
                continue

            for _ in range(trans_fire_count):
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
                from_acc = flow.from_account or default_account
                to_acc = flow.to_account or default_account
                if from_acc not in balances or to_acc not in balances:
                    continue

                src_config = scenario.accounts.get(from_acc)
                od_lim = src_config.overdraft_limit if src_config else None
                limit_cents = int(round(od_lim * 100)) if od_lim is not None else None
                if limit_cents is not None and (balances[from_acc] - amount_cents) < -limit_cents:
                    continue

                dest_config = scenario.accounts.get(to_acc)
                ira_cap = dest_config.annual_contribution_limit if dest_config else None
                if ira_cap is not None:
                    cap_cents = int(round(ira_cap * 100.0))
                    used_cents = annual_contributions_ytd.get(to_acc, 0)
                    allowed_cents = min(amount_cents, max(0, cap_cents - used_cents))
                else:
                    allowed_cents = amount_cents

                if allowed_cents <= 0:
                    continue

                accounts_manager.record_withdrawal(from_acc, allowed_cents)
                accounts_manager.record_deposit(to_acc, allowed_cents)
                annual_contributions_ytd[to_acc] = annual_contributions_ytd.get(to_acc, 0) + allowed_cents
                ledger.append(
                    current_date,
                    flow.name,
                    -allowed_cents,
                    from_acc,
                    balances[from_acc],
                    category=flow.category or "transfer",
                    tx_kind="transfer",
                )
                ledger.append(
                    current_date,
                    flow.name,
                    allowed_cents,
                    to_acc,
                    balances[to_acc],
                    category=flow.category or "transfer",
                    tx_kind="transfer",
                )

                if balances[from_acc] < 0 and src_config and src_config.overdraft_fee and src_config.overdraft_fee > 0:
                    fee_cents = int(round(src_config.overdraft_fee * 100))
                    balances[from_acc] -= fee_cents
                    ledger.append(
                        current_date,
                        f"{flow.name} Overdraft Fee",
                        -fee_cents,
                        from_acc,
                        balances[from_acc],
                        category="fees",
                        tx_kind="fee",
                    )

                # Optional employer match multiplier on transfer
                if flow.employer_match_multiplier and flow.employer_match_multiplier > 0.0:
                    raw_match = int(round(allowed_cents * flow.employer_match_multiplier))
                    if flow.employer_match_cap_per_event is not None:
                        event_cap = int(round(flow.employer_match_cap_per_event * 100.0))
                        match_cents = min(raw_match, event_cap)
                    else:
                        match_cents = raw_match

                    if match_cents > 0:
                        accounts_manager.record_deposit(to_acc, match_cents)
                        ledger.append(
                            current_date,
                            f"{flow.name} Employer Match",
                            match_cents,
                            to_acc,
                            balances[to_acc],
                            category="income",
                            tx_kind="match",
                        )

        # Step 9: Credit card due-date & statement-day cycle
        for card_name, card_config in scenario.accounts.items():
            if card_config.kind == "credit_card":
                if card_config.autopay and card_config.autopay.enabled:
                    autopay_from = card_config.autopay.from_account
                    for policy in policies:
                        if (
                            policy.enabled
                            and policy.kind == "shortfall_cover"
                            and policy.to_account == autopay_from
                        ):
                            due_amt = accounts_manager.remaining_statement_due_cents.get(card_name, 0)
                            min_cover = int(round(policy.minimum_balance * 100.0))
                            apply_shortfall_cover(
                                autopay_from,
                                due_amt,
                                policy.from_accounts,
                                balances,
                                ledger,
                                current_date,
                                min_cover,
                            )
                accounts_manager.process_credit_card_due_date(card_name, current_date, ledger)
                accounts_manager.process_credit_card_statement(card_name, current_date, ledger)

        # Step 10: Automated cashflow & portfolio policies
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
                p_count = policy_fire_counts.get(policy.name, {}).get(current_date, 0)
                if p_count <= 0:
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
            elif policy.kind == "sinking_fund":
                apply_sinking_fund(
                    policy,
                    balances,
                    ledger,
                    current_date,
                    scenario.flows,
                )

        # Step 11: Account returns, HYSA interest, bank fees, & physical asset updates
        accounts_manager.process_investment_returns_and_savings(current_date, ledger)

        # Step 12: End-of-day snapshot & milestone evaluation
        accounts_manager.overdraft_fee_count_today = {name: 0 for name in scenario.accounts}

        pos_balances = sum(balance_cents for balance_cents in balances.values() if balance_cents > 0)
        asset_sum = sum(asset_cents for asset_cents in accounts_manager.asset_values_cents.values())
        total_assets_cents = pos_balances + asset_sum
        total_debt_cents = sum(-debt_cents for debt_cents in balances.values() if debt_cents < 0)
        total_net_worth_cents = total_assets_cents - total_debt_cents

        liquid_pos = sum(
            balances[account_name]
            for account_name, account_cfg in scenario.accounts.items()
            if account_cfg.kind in ("checking", "savings", "hysa", "cd") and balances.get(account_name, 0) > 0
        )
        liquid_debt = sum(
            -balances[account_name]
            for account_name, account_cfg in scenario.accounts.items()
            if account_cfg.kind in ("credit_card", "loan", "mortgage", "student_loan", "auto_loan")
            and balances.get(account_name, 0) < 0
        )
        liquid_cents = liquid_pos - liquid_debt

        daily_record: Dict[str, Any] = {
            "date": current_date,
            "total_net_worth": round(total_net_worth_cents / 100.0, 2),
            "liquid_net_worth": round(liquid_cents / 100.0, 2),
            "vested_net_worth": round(total_net_worth_cents / 100.0, 2),
            "total_assets": round(total_assets_cents / 100.0, 2),
            "total_debt": round(total_debt_cents / 100.0, 2),
        }
        for acc_name, bal in balances.items():
            daily_record[acc_name] = round(bal / 100.0, 2)
        ledger.daily_records.append(daily_record)

        # Evaluate financial goals
        invested_dollars = sum(
            balances[acc]
            for acc, cfg in scenario.accounts.items()
            if cfg.kind in INVESTMENT_KINDS and balances.get(acc, 0) > 0
        ) / 100.0
        annual_exp_est = trailing_expense * 365.25
        goal_tracker.evaluate_daily(
            current_date,
            scenario.start,
            balances,
            total_net_worth_cents / 100.0,
            liquid_cents / 100.0,
            invested_dollars,
            annual_exp_est,
            scenario.accounts,
        )

    ledger.goal_results = goal_tracker.results
    ledger.metrics = compute_summary(scenario, ledger)
    return ledger
