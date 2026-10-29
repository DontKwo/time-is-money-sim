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
    repo_root = os.path.dirname(base_dir) # assumes scenarios/ is in repo root

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

    data["accounts"] = merged_accounts
    data["flows"] = filtered_flows

    return ScenarioModel(**data)
