import calendar
import math
from datetime import date, timedelta
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
from .config import AccountModel, FlowModel
from .schedule import resolve_day_of_month
from .rng import derive_rng

LIABILITY_KINDS = {"credit_card", "loan", "mortgage", "student_loan", "auto_loan"}
INVESTMENT_KINDS = {"investment", "traditional_401k", "roth_401k", "traditional_ira", "roth_ira", "hsa", "529", "college_529"}


class AccountManager:
    def __init__(self, accounts: Dict[str, AccountModel], base_seed: int = 42) -> None:
        self.configs: Dict[str, AccountModel] = accounts
        self.balances: Dict[str, int] = {}
        self.initial_principals: Dict[str, int] = {}
        self.cost_bases: Dict[str, int] = {}
        self.growth_remainders: Dict[str, float] = {name: 0.0 for name in accounts}
        self.monthly_unposted_interest: Dict[str, float] = {name: 0.0 for name in accounts}
        self.account_rngs: Dict[str, np.random.Generator] = {}
        self.overdraft_fee_count_today: Dict[str, int] = {name: 0 for name in accounts}
        self.roth_conversion_seasoning: List[Tuple[date, int]] = []

        # Credit card state
        self.in_grace_period: Dict[str, bool] = {}
        self.unposted_card_interest: Dict[str, float] = {name: 0.0 for name in accounts}
        self.unredeemed_rewards: Dict[str, int] = {name: 0 for name in accounts}
        self.reward_remainders: Dict[str, float] = {name: 0.0 for name in accounts}
        self.statement_balance_cents: Dict[str, int] = {name: 0 for name in accounts}
        self.remaining_statement_due_cents: Dict[str, int] = {name: 0 for name in accounts}
        self.payments_since_statement_cents: Dict[str, int] = {name: 0 for name in accounts}
        self.minimum_due_cents: Dict[str, int] = {name: 0 for name in accounts}

        # Loan state
        self.unposted_loan_interest: Dict[str, float] = {name: 0.0 for name in accounts}
        self.scheduled_pi_cents: Dict[str, int] = {}
        self.asset_values_cents: Dict[str, int] = {}

        # Tracking metrics
        self.declined_tx_count: int = 0
        self.total_overdraft_fees_cents: int = 0
        self.total_late_fees_cents: int = 0
        self.total_interest_paid_cents: int = 0
        self.ytd_mortgage_interest_cents: int = 0
        self.ytd_property_tax_cents: int = 0
        self.ytd_taxable_interest_cents: int = 0
        self.ytd_qualified_dividends_cents: int = 0
        self.ytd_realized_cap_gains_cents: int = 0
        self.ytd_realized_cap_losses_cents: int = 0
        self.ytd_529_contributions_cents: Dict[str, int] = {}
        self.ytd_529_non_qualified_earnings_cents: int = 0

        for name, config in accounts.items():
            self.account_rngs[name] = derive_rng(base_seed, "account", name)
            is_liability = config.kind in LIABILITY_KINDS
            if config.principal is not None:
                principal_cents = abs(int(round(config.principal * 100.0)))
                self.balances[name] = -principal_cents
                self.initial_principals[name] = principal_cents
            elif is_liability:
                dollar_bal = config.balance
                principal_cents = abs(int(round(dollar_bal * 100.0)))
                self.balances[name] = -principal_cents
                self.initial_principals[name] = principal_cents
            else:
                self.balances[name] = int(round(config.balance * 100.0))

            if config.kind in ("investment", "college_529"):
                if config.initial_cost_basis is not None:
                    self.cost_bases[name] = int(round(config.initial_cost_basis * 100.0))
                else:
                    self.cost_bases[name] = max(0, self.balances[name])

            if config.kind == "credit_card":
                self.in_grace_period[name] = self.balances[name] == 0
                if self.balances[name] < 0:
                    stmt = -self.balances[name]
                    self.statement_balance_cents[name] = stmt
                    self.remaining_statement_due_cents[name] = stmt

            if config.kind in ("loan", "mortgage", "student_loan", "auto_loan"):
                self.scheduled_pi_cents[name] = self._compute_scheduled_pi(config, self.initial_principals[name])
                self.asset_values_cents[name] = int(round(config.asset_value * 100.0))

    def _compute_scheduled_pi(self, config: AccountModel, principal_cents: int) -> int:
        if config.monthly_payment is not None:
            return int(round(config.monthly_payment * 100.0))
        n_periods = config.term_months or 360
        monthly_rate = config.apr / 12.0
        if monthly_rate == 0.0:
            return int(math.ceil(principal_cents / max(1, n_periods)))
        growth_factor = (1.0 + monthly_rate) ** n_periods
        numerator = principal_cents * monthly_rate * growth_factor
        denominator = growth_factor - 1.0
        return int(round(numerator / denominator))

    def _get_active_rate(self, name: str, current_date: date) -> float:
        config = self.configs[name]
        for step in config.rate_steps:
            if step.start <= current_date and (step.end is None or current_date <= step.end):
                return step.rate
        if config.expected_return is not None:
            return config.expected_return
        if config.apy is not None:
            return config.apy
        return config.annual_growth_rate

    def _get_active_volatility(self, name: str, current_date: date) -> float:
        config = self.configs[name]
        for step in config.rate_steps:
            if step.start <= current_date and (step.end is None or current_date <= step.end):
                if step.volatility is not None:
                    return step.volatility
        return config.volatility

    def record_deposit(self, account_name: str, amount_cents: int) -> None:
        self.balances[account_name] = self.balances.get(account_name, 0) + amount_cents
        config = self.configs.get(account_name)
        if config and config.kind == "college_529":
            self.ytd_529_contributions_cents[account_name] = self.ytd_529_contributions_cents.get(account_name, 0) + amount_cents
        if config and config.kind in ("investment", "college_529"):
            self.cost_bases[account_name] = self.cost_bases.get(account_name, 0) + amount_cents
        if config and config.kind == "credit_card":
            due_remaining = self.remaining_statement_due_cents.get(account_name, 0)
            self.remaining_statement_due_cents[account_name] = max(0, due_remaining - amount_cents)
            paid_so_far = self.payments_since_statement_cents.get(account_name, 0)
            self.payments_since_statement_cents[account_name] = paid_so_far + amount_cents

    def record_withdrawal(self, account_name: str, amount_cents: int, category: str = "", tags: Optional[List[str]] = None) -> None:
        config = self.configs.get(account_name)
        if config and config.kind in ("investment", "college_529"):
            pre_balance = self.balances.get(account_name, 0)
            if pre_balance > 0:
                fraction_sold = min(1.0, amount_cents / pre_balance)
                existing_basis = self.cost_bases.get(account_name, 0)
                basis_removed = int(round(existing_basis * fraction_sold))
                realized_gain = amount_cents - basis_removed
                self.cost_bases[account_name] = max(0, existing_basis - basis_removed)
                if config.kind == "college_529":
                    tags = tags or []
                    is_qualified = category == "education" or "529_qualified" in tags
                    if not is_qualified and realized_gain > 0:
                        self.ytd_529_non_qualified_earnings_cents += realized_gain
                else:
                    if realized_gain > 0:
                        self.ytd_realized_cap_gains_cents += realized_gain
                    elif realized_gain < 0:
                        self.ytd_realized_cap_losses_cents += abs(realized_gain)
        self.balances[account_name] = self.balances.get(account_name, 0) - amount_cents

    def charge_credit_card(self, card_name: str, amount_cents: int, category: Optional[str] = None) -> bool:
        config = self.configs[card_name]
        if config.credit_limit is not None:
            limit_cents = int(round(config.credit_limit * 100.0))
            projected_owed = -(self.balances[card_name] - amount_cents)
            if projected_owed > limit_cents:
                self.declined_tx_count += 1
                return False

        self.balances[card_name] -= amount_cents
        category_name = category or ""
        rate = config.category_cashback.get(category_name, config.cashback_pct)
        exact_reward = amount_cents * rate + self.reward_remainders[card_name]
        reward_cents = int(round(exact_reward))
        self.reward_remainders[card_name] = exact_reward - reward_cents
        self.unredeemed_rewards[card_name] += reward_cents
        return True

    def accrue_daily_liabilities(self, current_date: date) -> None:
        for name, config in self.configs.items():
            if config.kind == "credit_card":
                promo_active = config.promo_end and current_date <= config.promo_end
                active_apr = config.promo_apr if promo_active and config.promo_apr is not None else config.apr
                if not self.in_grace_period[name] and self.balances[name] < 0 and active_apr > 0.0:
                    owed_cents = -self.balances[name]
                    self.unposted_card_interest[name] += owed_cents * (active_apr / 365.0)

            if config.kind in ("loan", "mortgage", "student_loan", "auto_loan"):
                if self.balances[name] < 0 and config.apr > 0.0:
                    owed_cents = -self.balances[name]
                    self.unposted_loan_interest[name] += owed_cents * (config.apr / 365.0)

    def process_credit_card_due_date(self, card_name: str, current_date: date, ledger: Any) -> None:
        config = self.configs[card_name]
        due_resolved = resolve_day_of_month(current_date.year, current_date.month, config.due_day)
        if current_date.day != due_resolved:
            return

        # 1. Autopay execution
        if config.autopay and config.autopay.enabled:
            mode = config.autopay.mode
            if mode == "statement_balance":
                target_cents = self.remaining_statement_due_cents[card_name]
            elif mode == "minimum_due":
                payments = self.payments_since_statement_cents[card_name]
                target_cents = max(0, self.minimum_due_cents[card_name] - payments)
            elif mode == "full_balance":
                target_cents = max(0, -self.balances[card_name])
            else:
                fixed_cents = int(round(config.autopay.fixed_amount * 100.0))
                target_cents = min(max(0, -self.balances[card_name]), fixed_cents)

            if target_cents > 0:
                from_account = config.autopay.from_account
                self.record_withdrawal(from_account, target_cents)
                self.record_deposit(card_name, target_cents)
                ledger.append(current_date, f"{card_name} Autopay", -target_cents, from_account, self.balances[from_account])
                ledger.append(current_date, f"{card_name} Autopay", target_cents, card_name, self.balances[card_name])

        # 2. Grace period check
        if self.remaining_statement_due_cents[card_name] == 0:
            self.in_grace_period[card_name] = True
        else:
            self.in_grace_period[card_name] = False

        # 3. Late fee check
        min_due = self.minimum_due_cents[card_name]
        payments_made = self.payments_since_statement_cents[card_name]
        if min_due > 0 and payments_made < min_due:
            late_fee_cents = int(round(config.late_fee * 100.0))
            self.balances[card_name] -= late_fee_cents
            self.total_late_fees_cents += late_fee_cents
            ledger.append(current_date, f"{card_name} Late Fee", -late_fee_cents, card_name, self.balances[card_name])

    def process_credit_card_statement(self, card_name: str, current_date: date, ledger: Any) -> None:
        config = self.configs[card_name]
        stmt_day_resolved = resolve_day_of_month(current_date.year, current_date.month, config.statement_day)
        if current_date.day != stmt_day_resolved:
            return

        # 1. Post accrued interest
        accrued_interest = int(round(self.unposted_card_interest[card_name]))
        self.unposted_card_interest[card_name] -= accrued_interest
        if accrued_interest > 0:
            self.balances[card_name] -= accrued_interest
            self.total_interest_paid_cents += accrued_interest
            ledger.append(current_date, f"{card_name} Interest Charge", -accrued_interest, card_name, self.balances[card_name])

        # 2. Redeem cashback rewards
        reward_cents = self.unredeemed_rewards[card_name]
        if reward_cents > 0:
            if config.rewards_to_account is None:
                self.balances[card_name] += reward_cents
                ledger.append(current_date, f"{card_name} Cashback Statement Credit", reward_cents, card_name, self.balances[card_name])
            else:
                target_account = config.rewards_to_account
                self.balances[target_account] = self.balances.get(target_account, 0) + reward_cents
                ledger.append(current_date, f"{card_name} Cashback Reward", reward_cents, target_account, self.balances[target_account])
            self.unredeemed_rewards[card_name] = 0

        # 3. Statement snapshot and minimum due
        stmt_balance = max(0, -self.balances[card_name])
        self.statement_balance_cents[card_name] = stmt_balance
        self.remaining_statement_due_cents[card_name] = stmt_balance
        self.payments_since_statement_cents[card_name] = 0

        if stmt_balance == 0:
            self.minimum_due_cents[card_name] = 0
        else:
            pct_min = int(round(stmt_balance * config.min_payment_pct)) + accrued_interest
            floor_cents = int(round(config.min_payment_floor * 100.0))
            self.minimum_due_cents[card_name] = min(stmt_balance, max(floor_cents, pct_min))

    def process_loan_payment(self, loan_name: str, current_date: date, ledger: Any) -> None:
        config = self.configs[loan_name]
        pay_day_resolved = resolve_day_of_month(current_date.year, current_date.month, config.payment_day)
        if current_date.day != pay_day_resolved:
            return
        if config.payment_start and current_date < config.payment_start:
            return
        if config.payment_end and current_date > config.payment_end:
            return
        if self.balances[loan_name] >= 0:
            return

        # 1. Post accrued interest
        interest_cents = int(round(self.unposted_loan_interest[loan_name]))
        self.unposted_loan_interest[loan_name] -= interest_cents
        if interest_cents > 0:
            self.balances[loan_name] -= interest_cents
            self.total_interest_paid_cents += interest_cents
            if config.kind == "mortgage":
                self.ytd_mortgage_interest_cents += interest_cents
            ledger.append(current_date, f"{loan_name} Interest", -interest_cents, loan_name, self.balances[loan_name])

        # 2. Transfer P&I
        funding_account = config.payment_from_account or "checking"
        scheduled_pi = self.scheduled_pi_cents.get(loan_name, 0)
        extra_principal = int(round(config.extra_monthly_principal * 100.0))
        total_pi = scheduled_pi + extra_principal
        pi_transfer_cents = min(-self.balances[loan_name], total_pi)

        if pi_transfer_cents > 0:
            self.balances[funding_account] = self.balances.get(funding_account, 0) - pi_transfer_cents
            self.balances[loan_name] += pi_transfer_cents
            ledger.append(current_date, f"{loan_name} Payment", -pi_transfer_cents, funding_account, self.balances[funding_account])
            ledger.append(current_date, f"{loan_name} Payment", pi_transfer_cents, loan_name, self.balances[loan_name])

        # 3. Mortgage escrow and PMI
        if config.kind == "mortgage":
            current_asset = self.asset_values_cents.get(loan_name, int(round(config.asset_value * 100.0)))
            tax_portion = current_asset * config.property_tax_annual_pct
            insurance_portion = config.home_insurance_annual * 100.0
            escrow_cents = int(round((tax_portion + insurance_portion) / 12.0))
            property_tax_cents = int(round(tax_portion / 12.0))
            if escrow_cents > 0:
                self.balances[funding_account] = self.balances.get(funding_account, 0) - escrow_cents
                self.ytd_property_tax_cents += property_tax_cents
                ledger.append(current_date, f"{loan_name} Escrow Tax and Insurance", -escrow_cents, funding_account, self.balances[funding_account])

            current_ltv = (-self.balances[loan_name]) / max(1, current_asset)
            if config.pmi_annual_pct > 0.0 and current_ltv > config.pmi_drop_ltv:
                init_p = self.initial_principals.get(loan_name, current_asset)
                pmi_cents = int(round(init_p * config.pmi_annual_pct / 12.0))
                if pmi_cents > 0:
                    self.balances[funding_account] = self.balances.get(funding_account, 0) - pmi_cents
                    ledger.append(current_date, f"{loan_name} PMI", -pmi_cents, funding_account, self.balances[funding_account])

    def process_investment_returns_and_savings(self, current_date: date, ledger: Any) -> None:
        _, last_day = calendar.monthrange(current_date.year, current_date.month)
        is_month_end = current_date.day == last_day

        for name, config in self.configs.items():
            if config.kind in LIABILITY_KINDS:
                continue

            active_rate = self._get_active_rate(name, current_date)
            active_volatility = self._get_active_volatility(name, current_date)

            # Savings / HYSA / Checking interest
            if config.kind in ("savings", "hysa", "cd", "checking") and active_volatility == 0.0:
                if self.balances[name] > 0 and active_rate != 0.0:
                    daily_rate = (1.0 + active_rate) ** (1.0 / 365.0) - 1.0
                    if config.interest_posting == "daily":
                        exact_growth = self.balances[name] * daily_rate + self.growth_remainders[name]
                        growth_cents = int(round(exact_growth))
                        self.growth_remainders[name] = exact_growth - growth_cents
                        if growth_cents > 0:
                            self.balances[name] += growth_cents
                            ledger.append(current_date, f"{name} Investment Growth", growth_cents, name, self.balances[name])
                    else:
                        effective_balance = self.balances[name] + self.monthly_unposted_interest[name]
                        self.monthly_unposted_interest[name] += effective_balance * daily_rate
                        if is_month_end:
                            posted = int(round(self.monthly_unposted_interest[name]))
                            self.monthly_unposted_interest[name] -= posted
                            if posted > 0:
                                self.balances[name] += posted
                                self.ytd_taxable_interest_cents += posted
                                ledger.append(current_date, f"{name} Monthly Interest", posted, name, self.balances[name])

            # Investment & retirement accounts
            elif config.kind in INVESTMENT_KINDS:
                div_deduction = config.dividend_yield if config.return_includes_dividends else 0.0
                net_annual_return = active_rate - config.expense_ratio - div_deduction

                if self.balances[name] > 0:
                    if active_volatility == 0.0:
                        daily_rate = (1.0 + net_annual_return) ** (1.0 / 365.0) - 1.0
                    else:
                        rng = self.account_rngs[name]
                        log_expected = math.log(max(1e-6, 1.0 + net_annual_return))
                        variance_drag = 0.5 * (active_volatility ** 2)
                        daily_drift = (log_expected - variance_drag) / 365.0
                        daily_sigma = active_volatility / math.sqrt(365.0)
                        daily_log_return = float(rng.normal(daily_drift, daily_sigma))
                        daily_rate = math.exp(daily_log_return) - 1.0

                    exact_growth = self.balances[name] * daily_rate + self.growth_remainders[name]
                    growth_cents = int(round(exact_growth))
                    self.growth_remainders[name] = exact_growth - growth_cents
                    if growth_cents != 0:
                        self.balances[name] += growth_cents
                        ledger.append(current_date, f"{name} Investment Growth", growth_cents, name, self.balances[name])

                # Dividend distribution
                if config.dividend_yield > 0.0 and self.balances[name] > 0:
                    should_fire_div = False
                    if config.dividend_schedule == "monthly" and is_month_end:
                        period_yield = config.dividend_yield / 12.0
                        should_fire_div = True
                    elif config.dividend_schedule == "quarterly" and is_month_end and current_date.month in (3, 6, 9, 12):
                        period_yield = config.dividend_yield / 4.0
                        should_fire_div = True

                    if should_fire_div:
                        div_cents = int(round(self.balances[name] * period_yield))
                        if div_cents > 0:
                            if config.drip:
                                self.record_deposit(name, div_cents)
                                ledger.append(current_date, f"{name} Dividend Reinvestment", div_cents, name, self.balances[name])
                            else:
                                target_acc = config.dividend_to_account or "checking"
                                self.balances[target_acc] = self.balances.get(target_acc, 0) + div_cents
                                if config.kind == "investment":
                                    self.ytd_qualified_dividends_cents += div_cents
                                ledger.append(current_date, f"{name} Cash Dividend", div_cents, target_acc, self.balances[target_acc])

            # Physical asset appreciation
            if config.asset_appreciation_rate != 0.0:
                current_val = self.asset_values_cents.get(name, 0)
                daily_appr = (1.0 + config.asset_appreciation_rate) ** (1.0 / 365.25) - 1.0
                new_val = int(round(current_val * (1.0 + daily_appr)))
                self.asset_values_cents[name] = new_val

            # Month-end checking maintenance fee
            if config.kind == "checking" and is_month_end and config.monthly_maintenance_fee > 0.0:
                waiver_cents = int(round(config.min_balance_for_fee_waiver * 100.0))
                if self.balances[name] < waiver_cents:
                    fee_cents = int(round(config.monthly_maintenance_fee * 100.0))
                    self.balances[name] -= fee_cents
                    ledger.append(current_date, f"{name} Maintenance Fee", -fee_cents, name, self.balances[name])
