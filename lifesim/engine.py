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

    for _ in range(scenario.days):
        for flow in scenario.flows:
            if should_fire(flow.schedule, current_date, scenario.start):
                amount = get_amount(flow.amount, flow_rngs[flow.name])
                default_account = list(scenario.accounts.keys())[0] if scenario.accounts else 'checking'
                if flow.type == 'income':
                    account = flow.to_account or default_account
                    if account in balances:
                        balances[account] += amount
                        ledger.append(current_date, flow.name, amount, account, balances[account])
                elif flow.type == 'expense':
                    account = flow.from_account or default_account
                    if account in balances:
                        balances[account] -= amount
                        ledger.append(current_date, flow.name, -amount, account, balances[account])
                elif flow.type == 'transfer':
                    f_account = flow.from_account or default_account
                    t_account = flow.to_account or default_account
                    if f_account in balances and t_account in balances:
                        balances[f_account] -= amount
                        ledger.append(current_date, flow.name, -amount, f_account, balances[f_account])
                        balances[t_account] += amount
                        ledger.append(current_date, flow.name, amount, t_account, balances[t_account])

        current_date += datetime.timedelta(days=1)

    return ledger
