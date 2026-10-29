import datetime
from .config import ScenarioModel
from .schedule import should_fire
from .amounts import get_amount
from .ledger import Ledger

def run(scenario: ScenarioModel) -> Ledger:
    ledger = Ledger()

    balances = {
        name: int(round(acc.balance * 100))
        for name, acc in scenario.accounts.items()
    }

    current_date = scenario.start

    for _ in range(scenario.days):
        for flow in scenario.flows:
            if should_fire(flow.schedule, current_date, scenario.start):
                amount = get_amount(flow.amount)
                if flow.type == 'income':
                    account = flow.to_account or 'checking'
                    if account in balances:
                        balances[account] += amount
                        ledger.append(current_date, flow.name, amount, account, balances[account])
                elif flow.type == 'expense':
                    account = flow.from_account or 'checking'
                    if account in balances:
                        balances[account] -= amount
                        ledger.append(current_date, flow.name, -amount, account, balances[account])

        current_date += datetime.timedelta(days=1)

    return ledger
