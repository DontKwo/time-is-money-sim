import yaml
from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

class AccountModel(BaseModel):
    balance: float
    overdraft_limit: Optional[float] = 0.0
    overdraft_fee: Optional[float] = 0.0

class AmountModel(BaseModel):
    fixed: Optional[float] = None

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
    accounts: Dict[str, AccountModel]
    flows: List[FlowModel]

def load_scenario(path: str) -> ScenarioModel:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return ScenarioModel(**data)
