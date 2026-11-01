from datetime import date
from typing import List, Dict, Any
import pandas as pd


class Ledger:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.daily_records: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.goal_results: List[Dict[str, Any]] = []

    def append(
        self,
        tx_date: date,
        flow_name: str,
        amount: int,
        account: str,
        balance: int,
        category: str = "uncategorized",
        tx_kind: str = "flow",
    ) -> None:
        self.records.append({
            "date": tx_date,
            "flow": flow_name,
            "amount": amount / 100.0,
            "account": account,
            "balance": balance / 100.0,
            "category": category,
            "tx_kind": tx_kind,
        })

    def to_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def daily_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.daily_records)
