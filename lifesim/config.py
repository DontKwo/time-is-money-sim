import yaml
from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

class AccountModel(BaseModel):
    balance: float
    overdraft_limit: Optional[float] = 0.0
    overdraft_fee: Optional[float] = 0.0

class GasEstimate(BaseModel):
    mpg: float
    cost_per_gallon: float
    miles_per_period: float

class GroceryEstimate(BaseModel):
    people: int
    cost_per_person_per_period: float

class AmountModel(BaseModel):
    fixed: Optional[float] = None
    normal: Optional[List[float]] = None
    uniform: Optional[List[float]] = None
    lognormal: Optional[List[float]] = None
    gas_estimate: Optional[GasEstimate] = None
    grocery_estimate: Optional[GroceryEstimate] = None

class ScheduleModel(BaseModel):
    monthly: Optional[int] = None
    weekly: Optional[str] = None
    yearly: Optional[Dict[str, int]] = None
    once: Optional[str] = None

class FlowModel(BaseModel):
    name: str
    type: str # income, expense, transfer
    schedule: ScheduleModel
    amount: AmountModel
    from_account: Optional[str] = Field(default=None, alias="from")
    to_account: Optional[str] = Field(default=None, alias="to")
    category: Optional[str] = None
    tags: Optional[List[str]] = None

class ScenarioModel(BaseModel):
    start: date
    days: int
    seed: Optional[int] = 42
    include: Optional[List[str]] = []
    exclude: Optional[List[str]] = []
    accounts: Dict[str, AccountModel]
    flows: List[FlowModel]

import os

def load_scenario(path: str) -> ScenarioModel:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    includes = data.get("include", [])
    excludes = set(data.get("exclude", []))

    base_dir = os.path.dirname(os.path.abspath(path))

    # find repo root by traversing up
    current_dir = base_dir
    repo_root = base_dir
    while current_dir != os.path.dirname(current_dir):
        if os.path.exists(os.path.join(current_dir, "requirements.txt")) or os.path.exists(os.path.join(current_dir, ".git")):
            repo_root = current_dir
            break
        current_dir = os.path.dirname(current_dir)

    merged_accounts = {}
    merged_flows = []

    for inc in includes:
        inc_path = os.path.join(repo_root, inc)
        if not os.path.exists(inc_path):
            inc_path = os.path.join(base_dir, inc) # fallback to relative to scenario
        with open(inc_path, "r") as f:
            inc_data = yaml.safe_load(f)

            if "accounts" in inc_data:
                merged_accounts.update(inc_data["accounts"])
            if "flows" in inc_data:
                merged_flows.extend(inc_data["flows"])

    if "accounts" in data:
        merged_accounts.update(data["accounts"])
    if "flows" in data:
        merged_flows.extend(data["flows"])

    # filter flows by exclude list
    filtered_flows = [flow for flow in merged_flows if flow["name"] not in excludes]

    # handle duplicate flow names
    import logging
    seen_names = {}
    for flow in filtered_flows:
        base_name = flow["name"]
        if base_name in seen_names:
            seen_names[base_name] += 1
            new_name = f"{base_name}_{seen_names[base_name]}"
            logging.warning(f"Duplicate flow name '{base_name}' found. Renaming to '{new_name}'.")
            flow["name"] = new_name
        else:
            seen_names[base_name] = 1

    data["accounts"] = merged_accounts
    data["flows"] = filtered_flows

    return ScenarioModel(**data)
