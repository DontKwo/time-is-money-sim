from datetime import date
from typing import Dict, Any
import pytest
import tempfile
import yaml
import os
from lifesim.config import ScenarioModel
from lifesim.validation import validate_scenario_yaml


def build_base_scenario_payload() -> Dict[str, Any]:
    # Returns minimum valid dictionary for ScenarioModel instantiation
    return {
        "start": date(2026, 1, 1),
        "days": 30,
        "accounts": {
            "checking": {"kind": "checking", "balance": 1000.0},
            "savings": {"kind": "savings", "balance": 2000.0},
        },
    }


def test_valid_scenario_matching_accounts() -> None:
    # Verifies that matching account names pass referential integrity validation
    scenario_payload = build_base_scenario_payload()
    scenario_payload["flows"] = [
        {
            "name": "Groceries",
            "type": "expense",
            "schedule": {"daily": True},
            "amount": {"fixed": 50.0},
            "from_account": "checking",
        }
    ]
    scenario = ScenarioModel(**scenario_payload)
    assert "checking" in scenario.accounts


def test_invalid_flow_referencing_nonexistent_account() -> None:
    # Verifies ValueError when flow references non-existent account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["flows"] = [
        {
            "name": "Groceries",
            "type": "expense",
            "schedule": {"daily": True},
            "amount": {"fixed": 50.0},
            "from_account": "ghost_account",
        }
    ]
    with pytest.raises(ValueError, match="flow 'Groceries' references non-existent account 'ghost_account'"):
        ScenarioModel(**scenario_payload)


def test_invalid_policy_target_account() -> None:
    # Verifies ValueError when policy target_accounts references non-existent account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["policies"] = [
        {
            "name": "Debt Snowball",
            "kind": "debt_payoff",
            "from_account": "checking",
            "target_accounts": ["missing_credit_card"],
        }
    ]
    with pytest.raises(ValueError, match="policy 'Debt Snowball' references non-existent account 'missing_credit_card'"):
        ScenarioModel(**scenario_payload)


def test_account_opened_via_events_is_valid() -> None:
    # Verifies accounts opened via events.open_account are considered valid
    scenario_payload = build_base_scenario_payload()
    scenario_payload["events"] = [
        {
            "name": "Buy Home",
            "date": date(2026, 1, 15),
            "open_account": {
                "mortgage_account": {"kind": "mortgage", "balance": 300000.0}
            },
        }
    ]
    scenario_payload["flows"] = [
        {
            "name": "Mortgage Payment",
            "type": "transfer",
            "schedule": {"monthly": 1},
            "amount": {"fixed": 2000.0},
            "from_account": "checking",
            "to_account": "mortgage_account",
        }
    ]
    scenario = ScenarioModel(**scenario_payload)
    assert scenario is not None


def test_invalid_auto_transfer_account() -> None:
    # Verifies ValueError when auto_transfers reference missing account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["auto_transfers"] = [
        {
            "from_account": "checking",
            "to_account": "nonexistent_hysa",
        }
    ]
    with pytest.raises(ValueError, match="auto_transfer 'checking->nonexistent_hysa' references non-existent account 'nonexistent_hysa'"):
        ScenarioModel(**scenario_payload)


def test_invalid_paycheck_accounts() -> None:
    # Verifies ValueError when paycheck references non-existent accounts
    scenario_payload = build_base_scenario_payload()
    scenario_payload["paychecks"] = [
        {
            "name": "Corporate Job",
            "schedule": {"daily": True},
            "direct_deposit": [{"to": "missing_deposit_account", "remainder": True}],
        }
    ]
    with pytest.raises(ValueError, match="paycheck 'Corporate Job' references non-existent account 'missing_deposit_account'"):
        ScenarioModel(**scenario_payload)


def test_invalid_rsu_grant_account() -> None:
    # Verifies ValueError when RSU grant references missing to_account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["rsu_grants"] = [
        {
            "name": "Tech RSU",
            "schedule": {"daily": True},
            "to_account": "nonexistent_brokerage",
        }
    ]
    with pytest.raises(ValueError, match="rsu_grant 'Tech RSU' references non-existent account 'nonexistent_brokerage'"):
        ScenarioModel(**scenario_payload)


def test_invalid_tax_settlement_account() -> None:
    # Verifies ValueError when taxes reference missing settlement_account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["taxes"] = {
        "enabled": True,
        "settlement_account": "missing_tax_account",
    }
    with pytest.raises(ValueError, match="taxes 'taxes' references non-existent account 'missing_tax_account'"):
        ScenarioModel(**scenario_payload)


def test_invalid_goal_account() -> None:
    # Verifies ValueError when account_balance goal references missing account
    scenario_payload = build_base_scenario_payload()
    scenario_payload["goals"] = [
        {
            "name": "Emergency Fund Milestone",
            "kind": "account_balance",
            "account": "nonexistent_emergency_fund",
        }
    ]
    with pytest.raises(ValueError, match="goal 'Emergency Fund Milestone' references non-existent account 'nonexistent_emergency_fund'"):
        ScenarioModel(**scenario_payload)

def test_validate_scenario_yaml_valid() -> None:
    payload = build_base_scenario_payload()
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        yaml.dump(payload, f)
        temp_name = f.name

    try:
        errors = validate_scenario_yaml(temp_name)
        assert len(errors) == 0
    finally:
        os.unlink(temp_name)

def test_validate_scenario_yaml_invalid_amount() -> None:
    payload = build_base_scenario_payload()
    payload["flows"] = [
        {
            "name": "Groceries",
            "type": "expense",
            "schedule": {"daily": True},
            "amount": {"fixed": -50.0},
            "from_account": "checking",
        }
    ]
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        yaml.dump(payload, f)
        temp_name = f.name

    try:
        errors = validate_scenario_yaml(temp_name)
        assert len(errors) > 0
        assert any("greater than or equal to 0" in e for e in errors)
    finally:
        os.unlink(temp_name)

def test_validate_scenario_yaml_invalid_account() -> None:
    payload = build_base_scenario_payload()
    payload["flows"] = [
        {
            "name": "Groceries",
            "type": "expense",
            "schedule": {"daily": True},
            "amount": {"fixed": 50.0},
            "from_account": "ghost_account",
        }
    ]
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        yaml.dump(payload, f)
        temp_name = f.name

    try:
        errors = validate_scenario_yaml(temp_name)
        assert len(errors) > 0
        assert any("references non-existent account" in e for e in errors)
    finally:
        os.unlink(temp_name)

def test_validate_scenario_yaml_invalid_date() -> None:
    payload = build_base_scenario_payload()
    payload["start"] = "2026-13-45" # invalid date format
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        yaml.dump(payload, f)
        temp_name = f.name

    try:
        errors = validate_scenario_yaml(temp_name)
        assert len(errors) > 0
        assert any("start" in e for e in errors)
    finally:
        os.unlink(temp_name)
