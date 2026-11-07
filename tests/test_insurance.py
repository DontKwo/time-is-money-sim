from datetime import date
from typing import Dict, Any, List

from lifesim.insurance import TermLifePolicy, DisabilityPolicy


class MockLedger:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def append(
        self,
        current_date: date,
        description: str,
        amount_cents: int,
        account: str,
        balance_cents: int,
    ) -> None:
        self.records.append({
            "date": current_date,
            "description": description,
            "amount_cents": amount_cents,
            "account": account,
            "balance_cents": balance_cents,
        })


def test_term_life_policy() -> None:
    policy: TermLifePolicy = TermLifePolicy(
        name="My Term Life",
        monthly_premium=50.0,
        death_benefit=500000.0,
    )

    balances: Dict[str, int] = {"checking": 100000}
    ledger: MockLedger = MockLedger()
    test_date: date = date(2025, 1, 1)

    premium_cents: int = policy.deduct_premium(test_date, balances, ledger, "checking")
    assert premium_cents == 5000
    assert balances["checking"] == 95000
    assert len(ledger.records) == 1
    assert ledger.records[0]["amount_cents"] == -5000
    assert ledger.records[0]["description"] == "My Term Life Premium"

    benefit_cents: int = policy.payout_death_benefit(test_date, balances, ledger, "checking")
    assert benefit_cents == 50000000
    assert balances["checking"] == 50095000
    assert len(ledger.records) == 2
    assert ledger.records[1]["amount_cents"] == 50000000
    assert ledger.records[1]["description"] == "My Term Life Death Benefit"


def test_disability_policy() -> None:
    policy: DisabilityPolicy = DisabilityPolicy(
        name="My Disability",
        monthly_premium=100.0,
        monthly_benefit=5000.0,
    )

    balances: Dict[str, int] = {"checking": 150000}
    ledger: MockLedger = MockLedger()
    test_date: date = date(2025, 1, 1)

    premium_cents: int = policy.deduct_premium(test_date, balances, ledger, "checking")
    assert premium_cents == 10000
    assert balances["checking"] == 140000
    assert len(ledger.records) == 1
    assert ledger.records[0]["amount_cents"] == -10000
    assert ledger.records[0]["description"] == "My Disability Premium"

    benefit_cents: int = policy.payout_disability_benefit(test_date, balances, ledger, "checking")
    assert benefit_cents == 500000
    assert balances["checking"] == 640000
    assert len(ledger.records) == 2
    assert ledger.records[1]["amount_cents"] == 500000
    assert ledger.records[1]["description"] == "My Disability Disability Benefit"
