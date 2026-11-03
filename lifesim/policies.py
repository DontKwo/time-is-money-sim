from datetime import date, timedelta
from typing import Optional, Dict, Any, List
from .config import PolicyModel, AccountModel, SweepAllocation, FlowModel
from .schedule import build_fire_counts


def apply_shortfall_cover(
    to_account: str,
    required_cents: int,
    from_accounts: List[str],
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    minimum_balance_cents: int = 0,
) -> int:
    current_balance = balances.get(to_account, 0)
    target_needed = (minimum_balance_cents + required_cents) - current_balance
    if target_needed <= 0:
        return 0

    transferred_total = 0
    for source in from_accounts:
        source_available = max(0, balances.get(source, 0))
        if source_available <= 0:
            continue
        pull_cents = min(target_needed, source_available)
        balances[source] -= pull_cents
        balances[to_account] = balances.get(to_account, 0) + pull_cents
        ledger.append(
            current_date,
            f"Shortfall Cover from {source} to {to_account}",
            pull_cents,
            to_account,
            balances[to_account],
        )
        ledger.append(
            current_date,
            f"Shortfall Cover from {source} to {to_account}",
            -pull_cents,
            source,
            balances[source],
        )
        transferred_total += pull_cents
        target_needed -= pull_cents
        if target_needed <= 0:
            break

    return transferred_total


def apply_payday_skim(
    policy: PolicyModel,
    inflow_cents: int,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    accounts_config: Dict[str, AccountModel],
    annual_contributions_ytd: Dict[str, int],
) -> int:
    if inflow_cents <= 0:
        return 0

    from_acc = policy.from_account or "checking"
    if policy.fixed_amount is not None:
        skim_target_cents = int(round(policy.fixed_amount * 100.0))
    elif policy.pct_of_inflow is not None:
        skim_target_cents = int(round(inflow_cents * policy.pct_of_inflow))
    else:
        skim_target_cents = 0

    available_from = max(0, balances.get(from_acc, 0))
    actual_skim_cents = min(skim_target_cents, available_from)
    if actual_skim_cents <= 0:
        return 0

    to_acc = policy.to_account or "savings"
    target_config = accounts_config.get(to_acc)
    limit = target_config.annual_contribution_limit if target_config else None

    if limit is not None and policy.respect_annual_limit:
        annual_cap_cents = int(round(limit * 100.0))
        already_contributed = annual_contributions_ytd.get(to_acc, 0)
        remaining_room = max(0, annual_cap_cents - already_contributed)
        primary_cents = min(actual_skim_cents, remaining_room)
        overflow_cents = actual_skim_cents - primary_cents
    else:
        primary_cents = actual_skim_cents
        overflow_cents = 0

    if primary_cents > 0:
        balances[from_acc] -= primary_cents
        balances[to_acc] = balances.get(to_acc, 0) + primary_cents
        annual_contributions_ytd[to_acc] = annual_contributions_ytd.get(to_acc, 0) + primary_cents
        ledger.append(current_date, f"{policy.name}: {from_acc} to {to_acc}", primary_cents, to_acc, balances[to_acc])
        ledger.append(current_date, f"{policy.name}: {from_acc} to {to_acc}", -primary_cents, from_acc, balances[from_acc])

    if overflow_cents > 0 and policy.overflow_to_account:
        overflow_target = policy.overflow_to_account
        balances[from_acc] -= overflow_cents
        balances[overflow_target] = balances.get(overflow_target, 0) + overflow_cents
        ledger.append(
            current_date,
            f"{policy.name} Overflow: {from_acc} to {overflow_target}",
            overflow_cents,
            overflow_target,
            balances[overflow_target],
        )
        ledger.append(
            current_date,
            f"{policy.name} Overflow: {from_acc} to {overflow_target}",
            -overflow_cents,
            from_acc,
            balances[from_acc],
        )

    return actual_skim_cents


def apply_excess_sweep(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    accounts_config: Dict[str, AccountModel],
    annual_contributions_ytd: Dict[str, int],
) -> int:
    from_acc = policy.from_account or "checking"
    current_balance = balances.get(from_acc, 0)
    threshold_cents = int(round(policy.threshold * 100.0))
    keep_buffer_cents = int(round(policy.keep_buffer * 100.0))

    if current_balance <= threshold_cents:
        return 0

    excess_cents = current_balance - keep_buffer_cents
    if excess_cents <= 0 or not policy.allocations:
        return 0

    total_weight = sum(item.weight for item in policy.allocations)
    if total_weight <= 0:
        return 0

    allocated_sum = 0
    for alloc in policy.allocations:
        portion_weight = alloc.weight / total_weight
        portion_cents = int(round(excess_cents * portion_weight))
        if portion_cents <= 0:
            continue

        target_acc = alloc.to_account
        target_config = accounts_config.get(target_acc)
        limit = target_config.annual_contribution_limit if target_config else None

        if limit is not None and alloc.respect_annual_limit:
            cap_cents = int(round(limit * 100.0))
            used_so_far = annual_contributions_ytd.get(target_acc, 0)
            available_room = max(0, cap_cents - used_so_far)
            direct_cents = min(portion_cents, available_room)
            overflow_cents = portion_cents - direct_cents
        else:
            direct_cents = portion_cents
            overflow_cents = 0

        if direct_cents > 0:
            balances[from_acc] -= direct_cents
            balances[target_acc] = balances.get(target_acc, 0) + direct_cents
            annual_contributions_ytd[target_acc] = annual_contributions_ytd.get(target_acc, 0) + direct_cents
            ledger.append(current_date, f"{policy.name} Sweep to {target_acc}", direct_cents, target_acc, balances[target_acc])
            ledger.append(current_date, f"{policy.name} Sweep to {target_acc}", -direct_cents, from_acc, balances[from_acc])
            allocated_sum += direct_cents

        if overflow_cents > 0 and alloc.overflow_to_account:
            overflow_acc = alloc.overflow_to_account
            balances[from_acc] -= overflow_cents
            balances[overflow_acc] = balances.get(overflow_acc, 0) + overflow_cents
            ledger.append(current_date, f"{policy.name} Overflow to {overflow_acc}", overflow_cents, overflow_acc, balances[overflow_acc])
            ledger.append(current_date, f"{policy.name} Overflow to {overflow_acc}", -overflow_cents, from_acc, balances[from_acc])
            allocated_sum += overflow_cents

    return allocated_sum


def apply_debt_payoff(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    accounts_config: Dict[str, AccountModel],
    monthly_debt_payments_made: Dict[str, int],
) -> int:
    from_acc = policy.from_account or "checking"
    buffer_cents = int(round(policy.keep_checking_buffer * 100.0))
    checking_available = max(0, balances.get(from_acc, 0) - buffer_cents)
    if checking_available <= 0:
        return 0

    if policy.total_monthly_budget is not None:
        budget_cents = int(round(policy.total_monthly_budget * 100.0))
        paid_this_month = sum(monthly_debt_payments_made.get(acc, 0) for acc in policy.target_accounts)
        extra_cents = int(round(policy.extra_payment * 100.0))
        remaining_budget = max(extra_cents, budget_cents - paid_this_month)
    else:
        remaining_budget = int(round(policy.extra_payment * 100.0))

    available_payment = min(checking_available, remaining_budget)
    if available_payment <= 0:
        return 0

    active_debts = [acc for acc in policy.target_accounts if balances.get(acc, 0) < 0]
    if not active_debts:
        return 0

    # Sort active debts according to avalanche or snowball strategy
    if policy.strategy == "avalanche":
        active_debts.sort(key=lambda item: (-accounts_config[item].apr, -balances[item]))
    else:
        active_debts.sort(key=lambda item: (-balances[item], -accounts_config[item].apr))

    remaining_pool = available_payment
    total_paid = 0

    for debt_account in active_debts:
        if remaining_pool <= 0:
            break
        owed_cents = -balances[debt_account]
        payment_cents = min(remaining_pool, owed_cents)

        balances[from_acc] -= payment_cents
        balances[debt_account] += payment_cents
        monthly_debt_payments_made[debt_account] = monthly_debt_payments_made.get(debt_account, 0) + payment_cents
        ledger.append(
            current_date,
            f"{policy.name} ({policy.strategy}) to {debt_account}",
            payment_cents,
            debt_account,
            balances[debt_account],
        )
        ledger.append(
            current_date,
            f"{policy.name} ({policy.strategy}) to {debt_account}",
            -payment_cents,
            from_acc,
            balances[from_acc],
        )

        remaining_pool -= payment_cents
        total_paid += payment_cents

    return total_paid


def apply_emergency_fund_target(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    trailing_90d_daily_expense: float = 0.0,
) -> int:
    from_acc = policy.from_account or "checking"
    to_acc = policy.to_account or "savings"
    buffer_cents = int(round(policy.keep_checking_buffer * 100.0))
    available_checking = max(0, balances.get(from_acc, 0) - buffer_cents)
    if available_checking <= 0:
        return 0

    if policy.target_months_expenses is not None and trailing_90d_daily_expense > 0.0:
        monthly_expense_dollars = trailing_90d_daily_expense * 30.4375
        target_dollars = monthly_expense_dollars * policy.target_months_expenses
        target_cents = int(round(target_dollars * 100.0))
    elif policy.target_balance is not None:
        target_cents = int(round(policy.target_balance * 100.0))
    else:
        return 0

    current_savings = balances.get(to_acc, 0)
    needed_cents = max(0, target_cents - current_savings)
    transfer_cents = min(available_checking, needed_cents)

    if transfer_cents > 0:
        balances[from_acc] -= transfer_cents
        balances[to_acc] = current_savings + transfer_cents
        ledger.append(current_date, f"{policy.name} to {to_acc}", transfer_cents, to_acc, balances[to_acc])
        ledger.append(current_date, f"{policy.name} to {to_acc}", -transfer_cents, from_acc, balances[from_acc])

    return transfer_cents


def apply_portfolio_rebalance(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    accounts_manager: Any,
) -> int:
    target_weights = policy.target_weights
    if not target_weights:
        return 0

    total_portfolio_cents = sum(max(0, balances.get(acc, 0)) for acc in target_weights)
    if total_portfolio_cents <= 0:
        return 0

    # Check drift band
    max_drift = 0.0
    for acc, weight in target_weights.items():
        actual_weight = max(0, balances.get(acc, 0)) / total_portfolio_cents
        drift = abs(actual_weight - weight)
        if drift > max_drift:
            max_drift = drift

    if max_drift < policy.drift_band:
        return 0

    # Rebalance by calculating target cents per account
    total_rebalanced_cents = 0
    for acc, weight in target_weights.items():
        desired_cents = int(round(total_portfolio_cents * weight))
        delta_cents = desired_cents - balances.get(acc, 0)
        if delta_cents > 0:
            accounts_manager.record_deposit(acc, delta_cents)
            ledger.append(current_date, f"Rebalance to {acc}", delta_cents, acc, balances[acc])
            total_rebalanced_cents += delta_cents
        elif delta_cents < 0:
            withdrawal = abs(delta_cents)
            accounts_manager.record_withdrawal(acc, withdrawal)
            ledger.append(current_date, f"Rebalance from {acc}", -withdrawal, acc, balances[acc])

    return total_rebalanced_cents


def apply_retirement_drawdown(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    payroll_state: Any,
) -> int:
    to_acc = policy.to_account or "checking"
    if policy.target_checking_balance is not None:
        target_cents = int(round(policy.target_checking_balance * 100.0))
        needed_cents = max(0, target_cents - balances.get(to_acc, 0))
    elif policy.fixed_withdrawal is not None:
        needed_cents = int(round(policy.fixed_withdrawal * 100.0))
    else:
        return 0

    if needed_cents <= 0:
        return 0

    pulled_total = 0
    remaining_needed = needed_cents
    gross_up_factor = 1.0 - policy.pretax_gross_up_rate

    order = policy.withdrawal_order or ["savings", "investment", "traditional_401k", "traditional_ira", "roth_401k", "roth_ira", "hsa"]
    for source_acc in order:
        available_cents = max(0, balances.get(source_acc, 0))
        if available_cents <= 0:
            continue

        is_pretax = source_acc in ("traditional_401k", "traditional_ira")
        if is_pretax:
            max_net_possible = int(round(available_cents * gross_up_factor))
            net_pull = min(remaining_needed, max_net_possible)
            gross_pull = min(available_cents, int(round(net_pull / gross_up_factor)))
            withholding = gross_pull - net_pull

            balances[source_acc] -= gross_pull
            balances[to_acc] = balances.get(to_acc, 0) + net_pull
            if payroll_state:
                payroll_state.ytd_taxable_ordinary_cents += gross_pull
                payroll_state.ytd_fed_withheld_cents += withholding

            ledger.append(current_date, f"Drawdown Pretax from {source_acc}", -gross_pull, source_acc, balances[source_acc])
            ledger.append(current_date, f"Drawdown Net to {to_acc}", net_pull, to_acc, balances[to_acc])
            pulled_total += net_pull
            remaining_needed -= net_pull
        else:
            net_pull = min(remaining_needed, available_cents)
            balances[source_acc] -= net_pull
            balances[to_acc] = balances.get(to_acc, 0) + net_pull
            ledger.append(current_date, f"Drawdown from {source_acc}", -net_pull, source_acc, balances[source_acc])
            ledger.append(current_date, f"Drawdown to {to_acc}", net_pull, to_acc, balances[to_acc])
            pulled_total += net_pull
            remaining_needed -= net_pull

        if remaining_needed <= 0:
            break

    return pulled_total


def apply_roth_conversion_ladder(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    payroll_state: Any,
    account_manager: Any,
) -> int:
    from_acc = policy.from_account or "traditional_401k"
    to_acc = policy.to_account or "roth_ira"

    conversion_dollars = policy.conversion_amount
    if conversion_dollars is None or conversion_dollars <= 0:
        return 0

    conversion_cents = int(round(conversion_dollars * 100.0))
    available_cents = max(0, balances.get(from_acc, 0))
    transfer_cents = min(conversion_cents, available_cents)

    if transfer_cents <= 0:
        return 0

    balances[from_acc] -= transfer_cents
    balances[to_acc] = balances.get(to_acc, 0) + transfer_cents

    if payroll_state:
        payroll_state.ytd_taxable_ordinary_cents += transfer_cents

    ledger.append(
        current_date,
        "Roth IRA Conversion",
        -transfer_cents,
        from_acc,
        balances[from_acc],
        tx_kind="transfer"
    )
    ledger.append(
        current_date,
        "Roth IRA Conversion",
        transfer_cents,
        to_acc,
        balances[to_acc],
        tx_kind="transfer"
    )

    if account_manager and hasattr(account_manager, "roth_conversion_seasoning"):
        account_manager.roth_conversion_seasoning.append((current_date, transfer_cents))

    return transfer_cents


def apply_sinking_fund(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    flows: List[FlowModel],
) -> int:
    from_account = policy.from_account or "checking"
    to_account = policy.to_account or "savings"
    lookahead = policy.lookahead_days or 365
    target_names = set(policy.target_flows)

    matching_flows = [
        flow for flow in flows
        if flow.name in target_names or any(tag in target_names for tag in flow.tags)
    ]
    if not matching_flows:
        return 0

    end_window = current_date + timedelta(days=lookahead)
    total_outlay_cents = 0
    for flow in matching_flows:
        fixed_val = flow.amount.fixed if flow.amount and flow.amount.fixed is not None else 0.0
        cents_per_event = int(round(fixed_val * 100.0))
        fire_map = build_fire_counts(flow.schedule, current_date, end_window)
        total_fires = sum(fire_map.values())
        total_outlay_cents += cents_per_event * total_fires

    if total_outlay_cents <= 0:
        return 0

    if policy.schedule:
        policy_fire_map = build_fire_counts(policy.schedule, current_date, end_window)
        exec_count = max(1, sum(policy_fire_map.values()))
    else:
        exec_count = 1

    target_transfer_cents = int(round(total_outlay_cents / exec_count))
    available_cents = max(0, balances.get(from_account, 0))
    transfer_cents = min(target_transfer_cents, available_cents)
    if transfer_cents <= 0:
        return 0

    balances[from_account] -= transfer_cents
    balances[to_account] = balances.get(to_account, 0) + transfer_cents
    ledger.append(current_date, f"{policy.name} to {to_account}", transfer_cents, to_account, balances[to_account])
    ledger.append(current_date, f"{policy.name} to {to_account}", -transfer_cents, from_account, balances[from_account])
    return transfer_cents


def apply_backdoor_roth(
    policy: PolicyModel,
    balances: Dict[str, int],
    ledger: Any,
    current_date: date,
    payroll_state: Any,
) -> int:
    """Executes a Backdoor Roth IRA conversion including pro-rata taxation."""
    from_acc = policy.from_account or "checking"
    to_acc = policy.to_account or "roth_ira"
    trad_ira = "traditional_ira"

    conversion_dollars = policy.fixed_amount if policy.fixed_amount is not None else policy.conversion_amount
    if conversion_dollars is None or conversion_dollars <= 0:
        return 0

    conversion_cents = int(round(conversion_dollars * 100.0))
    available_cents = max(0, balances.get(from_acc, 0))
    transfer_cents = min(conversion_cents, available_cents)

    if transfer_cents <= 0:
        return 0

    pre_tax_trad_balance = max(0, balances.get(trad_ira, 0))
    total_trad_balance = pre_tax_trad_balance + transfer_cents

    taxable_pct = pre_tax_trad_balance / total_trad_balance if total_trad_balance > 0 else 0.0
    taxable_cents = int(round(transfer_cents * taxable_pct))

    balances[from_acc] -= transfer_cents
    balances[to_acc] = balances.get(to_acc, 0) + transfer_cents

    if payroll_state:
        payroll_state.ytd_taxable_ordinary_cents += taxable_cents

    ledger.append(current_date, "Backdoor Roth Contribution", -transfer_cents, from_acc, balances[from_acc], tx_kind="transfer")
    ledger.append(current_date, "Backdoor Roth Conversion", transfer_cents, to_acc, balances[to_acc], tx_kind="transfer")

    return transfer_cents
