from datetime import date
from typing import List, Dict, Any, Optional
import pandas as pd

from .analysis import deflate_daily_records


class Ledger:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.daily_records: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.goal_results: List[Dict[str, Any]] = []
        self.inflation_indices: Dict[date, float] = {}

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

    def real_df(self, base_date: Optional[date] = None) -> pd.DataFrame:
        indices = self.inflation_indices
        if base_date is not None and base_date in indices:
            base_factor = indices[base_date]
            indices = {dt: (val / base_factor) for dt, val in indices.items()}
        deflated_records = deflate_daily_records(self.daily_records, indices)
        return pd.DataFrame(deflated_records)
