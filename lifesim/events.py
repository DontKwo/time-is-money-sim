import math
from datetime import date, timedelta
from typing import Optional, Dict, Any, List, Callable
import numpy as np
from .config import (
    EventModel,
    FlowModel,
    PaycheckModel,
    AccountModel,
    ScenarioModel,
)
from .rng import derive_rng
from .amounts import get_amount


class EventManager:
    def __init__(
        self,
        events: List[EventModel],
        flows: List[FlowModel],
        paychecks: List[PaycheckModel],
        accounts_manager: Any,
        payroll_state: Any,
        base_seed: int = 42,
    ) -> None:
        self.events = events
        self.flows = flows
        self.paychecks = paychecks
        self.accounts_manager = accounts_manager
        self.payroll_state = payroll_state
        self.reversions: Dict[date, List[Callable[[], None]]] = {}
        self.last_shock_date: Dict[str, date] = {}
        self.ytd_medical_oop_cents: Dict[int, int] = {}
        self.event_rngs: Dict[str, np.random.Generator] = {
            item.name: derive_rng(base_seed, "event", item.name) for item in events
        }

    def process_reversions(self, current_date: date) -> None:
        reversion_callbacks = self.reversions.pop(current_date, [])
        for callback in reversion_callbacks:
            callback()

    def _matches_flow(self, flow: FlowModel, pattern: str) -> bool:
        return flow.name == pattern or pattern in flow.tags

    def _matches_paycheck(self, paycheck: PaycheckModel, pattern: str) -> bool:
        return paycheck.name == pattern or pattern in paycheck.tags

    def _calculate_vested_fraction(self, paycheck: PaycheckModel, current_date: date, sim_start: date) -> float:
        if not (
            paycheck.retirement_401k
            and paycheck.retirement_401k.employer_match
            and paycheck.retirement_401k.employer_match.vesting
        ):
            return 1.0

        vesting = paycheck.retirement_401k.employer_match.vesting
        hire_date = vesting.hire_date or paycheck.schedule.start or sim_start
        months_employed = (current_date.year - hire_date.year) * 12 + (current_date.month - hire_date.month)

        if vesting.kind == "immediate":
            return 1.0
        if vesting.kind == "cliff":
            return 1.0 if months_employed >= vesting.cliff_months else 0.0

        # Graded schedule
        if not vesting.graded_schedule:
            return 1.0
        eligible_months = [m for m in vesting.graded_schedule.keys() if m <= months_employed]
        if not eligible_months:
            return 0.0
        highest_eligible = max(eligible_months)
        return float(vesting.graded_schedule[highest_eligible])

    def process_daily_events(
        self,
        current_date: date,
        sim_start: date,
        balances: Dict[str, int],
        ledger: Any,
        scenario: ScenarioModel,
    ) -> None:
        # 1. Scripted date events
        for event in self.events:
            if not event.enabled or event.date != current_date:
                continue

            reversion_date = event.end_date + timedelta(days=1) if event.end_date else None

            # Flow toggles
            if event.disable_flows:
                for target in event.disable_flows:
                    for flow in self.flows:
                        if self._matches_flow(flow, target):
                            flow.enabled = False
                            if reversion_date:
                                self.reversions.setdefault(reversion_date, []).append(
                                    lambda f=flow: setattr(f, "enabled", True)
                                )

            if event.enable_flows:
                for target in event.enable_flows:
                    for flow in self.flows:
                        if self._matches_flow(flow, target):
                            flow.enabled = True
                            if reversion_date:
                                self.reversions.setdefault(reversion_date, []).append(
                                    lambda f=flow: setattr(f, "enabled", False)
                                )

            # Paycheck toggles
            if event.disable_paychecks:
                for target in event.disable_paychecks:
                    for paycheck in self.paychecks:
                        if self._matches_paycheck(paycheck, target):
                            paycheck.enabled = False
                            if reversion_date:
                                self.reversions.setdefault(reversion_date, []).append(
                                    lambda p=paycheck: setattr(p, "enabled", True)
                                )

            if event.enable_paychecks:
                for target in event.enable_paychecks:
                    for paycheck in self.paychecks:
                        if self._matches_paycheck(paycheck, target):
                            paycheck.enabled = True
                            if reversion_date:
                                self.reversions.setdefault(reversion_date, []).append(
                                    lambda p=paycheck: setattr(p, "enabled", False)
                                )

            # Job termination & match forfeiture
            if event.terminate_job:
                job_target = event.terminate_job
                for paycheck in self.paychecks:
                    if paycheck.name == job_target:
                        paycheck.enabled = False
                        vested_frac = self._calculate_vested_fraction(paycheck, current_date, sim_start)
                        unvested_frac = 1.0 - vested_frac
                        total_match = self.payroll_state.ytd_employer_match_by_job_cents.get(job_target, 0)
                        unvested_cents = int(round(total_match * unvested_frac))
                        if unvested_cents > 0 and paycheck.retirement_401k and paycheck.retirement_401k.employer_match:
                            ret_acc = paycheck.retirement_401k.employer_match.to_account
                            balances[ret_acc] -= unvested_cents
                            ledger.append(
                                current_date,
                                f"{job_target} Unvested 401k Forfeiture",
                                -unvested_cents,
                                ret_acc,
                                balances[ret_acc],
                            )

            # Flow amount adjustments
            if event.set_flow_amount:
                for flow_name, new_amount in event.set_flow_amount.items():
                    for flow in self.flows:
                        if flow.name == flow_name:
                            old_amount = flow.amount
                            flow.amount = new_amount
                            if reversion_date:
                                self.reversions.setdefault(reversion_date, []).append(
                                    lambda f=flow, a=old_amount: setattr(f, "amount", a)
                                )

            # Open mid-simulation accounts
            if event.open_account:
                for new_acc_name, new_acc_model in event.open_account.items():
                    self.accounts_manager.configs[new_acc_name] = new_acc_model
                    is_liability = new_acc_model.kind in (
                        "credit_card", "loan", "mortgage", "student_loan", "auto_loan"
                    )
                    init_bal = new_acc_model.principal if new_acc_model.principal is not None else new_acc_model.balance
                    init_cents = int(round(init_bal * 100.0))
                    balances[new_acc_name] = -abs(init_cents) if is_liability else init_cents
                    self.accounts_manager.growth_remainders[new_acc_name] = 0.0
                    self.accounts_manager.monthly_unposted_interest[new_acc_name] = 0.0
                    self.accounts_manager.unposted_card_interest[new_acc_name] = 0.0
                    self.accounts_manager.unposted_loan_interest[new_acc_name] = 0.0
                    self.accounts_manager.in_grace_period[new_acc_name] = True
                    self.accounts_manager.remaining_statement_due_cents[new_acc_name] = 0
                    self.accounts_manager.payments_since_statement_cents[new_acc_name] = 0
                    self.accounts_manager.minimum_due_cents[new_acc_name] = 0
                    self.accounts_manager.unredeemed_rewards[new_acc_name] = 0
                    self.accounts_manager.reward_remainders[new_acc_name] = 0.0
                    if is_liability:
                        self.accounts_manager.initial_principals[new_acc_name] = abs(init_cents)
                        computed_pi = self.accounts_manager._compute_scheduled_pi(new_acc_model, abs(init_cents))
                        self.accounts_manager.scheduled_pi_cents[new_acc_name] = computed_pi
                        self.accounts_manager.asset_values_cents[new_acc_name] = int(round(new_acc_model.asset_value * 100.0))

            # Relocation
            if event.relocation:
                rel = event.relocation
                if scenario.taxes is not None:
                    scenario.taxes.state_code = rel.state_code
                    if rel.state_flat_rate is not None:
                        scenario.taxes.state_flat_rate = rel.state_flat_rate
                    if rel.state_brackets is not None:
                        scenario.taxes.state_brackets = rel.state_brackets

                # Apply cost of living adjustment to all active expense flows
                for flow in self.flows:
                    if flow.type == "expense":
                        amt_model = flow.amount
                        if amt_model.fixed is not None:
                            amt_model.fixed = round(amt_model.fixed * rel.living_cost_factor, 2)

                        if amt_model.normal is not None and len(amt_model.normal) == 2:
                            amt_model.normal = [
                                round(amt_model.normal[0] * rel.living_cost_factor, 2),
                                round(amt_model.normal[1] * rel.living_cost_factor, 2)
                            ]

                        if amt_model.uniform is not None and len(amt_model.uniform) == 2:
                            amt_model.uniform = [
                                round(amt_model.uniform[0] * rel.living_cost_factor, 2),
                                round(amt_model.uniform[1] * rel.living_cost_factor, 2)
                            ]

                        if amt_model.lognormal_dollars is not None and len(amt_model.lognormal_dollars) == 2:
                            amt_model.lognormal_dollars = [
                                round(amt_model.lognormal_dollars[0] * rel.living_cost_factor, 2),
                                amt_model.lognormal_dollars[1]
                            ]

                        if amt_model.gas_estimate is not None:
                            amt_model.gas_estimate.cost_per_gallon = round(amt_model.gas_estimate.cost_per_gallon * rel.living_cost_factor, 2)

                        if amt_model.grocery_estimate is not None:
                            amt_model.grocery_estimate.cost_per_person_per_period = round(amt_model.grocery_estimate.cost_per_person_per_period * rel.living_cost_factor, 2)


            # Refinance loan
            if event.refinance_loan:
                ref = event.refinance_loan
                loan_account = ref.loan_account
                acc_config = self.accounts_manager.configs.get(loan_account)
                if acc_config:
                    current_owed = abs(balances.get(loan_account, 0))
                    acc_config.apr = ref.new_apr
                    acc_config.term_months = ref.new_term_months
                    self.accounts_manager.scheduled_pi_cents[loan_account] = (
                        self.accounts_manager._compute_scheduled_pi(acc_config, current_owed)
                    )
                    closing_cost_cents = int(round(ref.closing_cost * 100.0))
                    if closing_cost_cents > 0:
                        funding = ref.closing_cost_from_account
                        balances[funding] = balances.get(funding, 0) - closing_cost_cents
                        ledger.append(
                            current_date, f"{loan_account} Refinance Closing Cost", -closing_cost_cents, funding, balances[funding]
                        )

            # One-time flow
            if event.one_time_flow:
                otf = event.one_time_flow
                charge_rng = self.event_rngs[event.name]
                amount_cents = get_amount(otf.amount, charge_rng)
                from_account = otf.from_account or "checking"
                to_account = otf.to_account or "checking"

                if otf.type == "expense":
                    balances[from_account] = balances.get(from_account, 0) - amount_cents
                    ledger.append(current_date, otf.name or event.name, -amount_cents, from_account, balances[from_account])
                elif otf.type == "income":
                    balances[to_account] = balances.get(to_account, 0) + amount_cents
                    ledger.append(current_date, otf.name or event.name, amount_cents, to_account, balances[to_account])
                else:  # transfer
                    balances[from_account] = balances.get(from_account, 0) - amount_cents
                    balances[to_account] = balances.get(to_account, 0) + amount_cents
                    ledger.append(current_date, otf.name or event.name, -amount_cents, from_account, balances[from_account])
                    ledger.append(current_date, otf.name or event.name, amount_cents, to_account, balances[to_account])

        # 2. Stochastic Poisson shocks
        for shock in self.events:
            if not shock.enabled or shock.poisson_per_year is None:
                continue
            if shock.start and current_date < shock.start:
                continue
            if shock.end and current_date > shock.end:
                continue

            last_date = self.last_shock_date.get(shock.name)
            if last_date and (current_date - last_date).days < shock.cooldown_days:
                continue

            prob_today = 1.0 - math.exp(-shock.poisson_per_year / 365.25)
            rng = self.event_rngs[shock.name]
            if float(rng.uniform(0.0, 1.0)) < prob_today:
                self.last_shock_date[shock.name] = current_date
                base_cents = get_amount(shock.amount, rng) if shock.amount else 0

                if shock.insurance_oop_max is not None:
                    year_num = current_date.year
                    oop_max_cents = int(round(shock.insurance_oop_max * 100.0))
                    already_paid = self.ytd_medical_oop_cents.get(year_num, 0)
                    available_oop_room = max(0, oop_max_cents - already_paid)
                    charge_cents = min(base_cents, available_oop_room)
                    self.ytd_medical_oop_cents[year_num] = already_paid + charge_cents
                else:
                    charge_cents = base_cents

                target_account = shock.account or "checking"
                if shock.type == "expense":
                    balances[target_account] = balances.get(target_account, 0) - charge_cents
                    ledger.append(current_date, shock.name, -charge_cents, target_account, balances[target_account])
                else:
                    balances[target_account] = balances.get(target_account, 0) + charge_cents
                    ledger.append(current_date, shock.name, charge_cents, target_account, balances[target_account])
