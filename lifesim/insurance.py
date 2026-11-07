from datetime import date
from typing import Dict, Any

class TermLifePolicy:
    def __init__(self, name: str, monthly_premium: float, death_benefit: float) -> None:
        self.name: str = name
        self.monthly_premium_cents: int = int(round(monthly_premium * 100.0))
        self.death_benefit_cents: int = int(round(death_benefit * 100.0))

    def deduct_premium(
        self,
        current_date: date,
        balances: Dict[str, int],
        ledger: Any,
        account: str = "checking",
    ) -> int:
        premium_cents: int = self.monthly_premium_cents
        balances[account] = balances.get(account, 0) - premium_cents
        ledger.append(current_date, f"{self.name} Premium", -premium_cents, account, balances[account])
        return premium_cents

    def payout_death_benefit(
        self,
        current_date: date,
        balances: Dict[str, int],
        ledger: Any,
        account: str = "checking",
    ) -> int:
        benefit_cents: int = self.death_benefit_cents
        balances[account] = balances.get(account, 0) + benefit_cents
        ledger.append(current_date, f"{self.name} Death Benefit", benefit_cents, account, balances[account])
        return benefit_cents


class DisabilityPolicy:
    def __init__(self, name: str, monthly_premium: float, monthly_benefit: float) -> None:
        self.name: str = name
        self.monthly_premium_cents: int = int(round(monthly_premium * 100.0))
        self.monthly_benefit_cents: int = int(round(monthly_benefit * 100.0))

    def deduct_premium(
        self,
        current_date: date,
        balances: Dict[str, int],
        ledger: Any,
        account: str = "checking",
    ) -> int:
        premium_cents: int = self.monthly_premium_cents
        balances[account] = balances.get(account, 0) - premium_cents
        ledger.append(current_date, f"{self.name} Premium", -premium_cents, account, balances[account])
        return premium_cents

    def payout_disability_benefit(
        self,
        current_date: date,
        balances: Dict[str, int],
        ledger: Any,
        account: str = "checking",
    ) -> int:
        benefit_cents: int = self.monthly_benefit_cents
        balances[account] = balances.get(account, 0) + benefit_cents
        ledger.append(current_date, f"{self.name} Disability Benefit", benefit_cents, account, balances[account])
        return benefit_cents
