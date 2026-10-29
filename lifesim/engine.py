import datetime
import hashlib
from .config import ScenarioModel
from .schedule import should_fire
from .amounts import get_amount
from .ledger import Ledger

import numpy as np

def run(scenario: ScenarioModel) -> Ledger:
    ledger = Ledger()

    flow_rngs = {}
    base_seed = scenario.seed if scenario.seed is not None else 42
    for flow in scenario.flows:
        # Create a deterministic seed per flow based on the scenario seed and flow name
        seed_str = f"{base_seed}_{flow.name}"
        flow_seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
        flow_rngs[flow.name] = np.random.default_rng(flow_seed)

    balances = {
        name: int(round(acc.balance * 100))
        for name, acc in scenario.accounts.items()
    }

    current_date = scenario.start

    # Precompute loop-invariants
    default_account = list(scenario.accounts.keys())[0] if scenario.accounts else 'checking'
    # Sort flows so income happens first
    daily_flows = sorted(scenario.flows, key=lambda f: 0 if f.type == 'income' else 1)

    for _ in range(scenario.days):
        for flow in daily_flows:
            if should_fire(flow.schedule, current_date, scenario.start):
                if flow.skip_prob > 0 and flow_rngs[flow.name].random() < flow.skip_prob:
                    continue

                amount = get_amount(flow.amount, flow_rngs[flow.name])
                if flow.type == 'income':
                    account = flow.to_account or default_account
                    if account in balances:
                        balances[account] += amount
                        ledger.append(current_date, flow.name, amount, account, balances[account])
                elif flow.type == 'expense':
                    account = flow.from_account or default_account
                    if account in balances:
                        acc_model = scenario.accounts[account]
                        od_limit_cents = int(round(acc_model.overdraft_limit * 100)) if acc_model.overdraft_limit is not None else None

                        if od_limit_cents is not None and (balances[account] - amount) < -od_limit_cents:
                            # Skip transaction if it exceeds overdraft limit
                            continue

                        was_non_negative = balances[account] >= 0
                        balances[account] -= amount
                        ledger.append(current_date, flow.name, -amount, account, balances[account])

                        is_negative = balances[account] < 0
                        if is_negative and acc_model.overdraft_fee and acc_model.overdraft_fee > 0:
                            fee_cents = int(round(acc_model.overdraft_fee * 100))
                            balances[account] -= fee_cents
                            ledger.append(current_date, f"{flow.name} Overdraft Fee", -fee_cents, account, balances[account])

                elif flow.type == 'transfer':
                    f_account = flow.from_account or default_account
                    t_account = flow.to_account or default_account
                    if f_account in balances and t_account in balances:
                        acc_model = scenario.accounts[f_account]
                        od_limit_cents = int(round(acc_model.overdraft_limit * 100)) if acc_model.overdraft_limit is not None else None

                        if od_limit_cents is not None and (balances[f_account] - amount) < -od_limit_cents:
                            # Skip transfer if it exceeds overdraft limit on from_account
                            continue

                        was_non_negative = balances[f_account] >= 0
                        balances[f_account] -= amount
                        ledger.append(current_date, flow.name, -amount, f_account, balances[f_account])

                        balances[t_account] += amount
                        ledger.append(current_date, flow.name, amount, t_account, balances[t_account])

                        is_negative = balances[f_account] < 0
                        if is_negative and acc_model.overdraft_fee and acc_model.overdraft_fee > 0:
                            fee_cents = int(round(acc_model.overdraft_fee * 100))
                            balances[f_account] -= fee_cents
                            ledger.append(current_date, f"{flow.name} Overdraft Fee", -fee_cents, f_account, balances[f_account])

        current_date += datetime.timedelta(days=1)

    return ledger
