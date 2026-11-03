import sqlite3
from pathlib import Path
from datetime import date
from lifesim.ledger import Ledger
from lifesim.db import export_ledger_to_sqlite

def test_export_ledger_to_sqlite(tmp_path: Path) -> None:
    ledger = Ledger()
    tx_date = date(2026, 1, 1)

    ledger.append(tx_date, "Rent", -150000, "checking", 350000, "housing")
    ledger.daily_records.append({
        "date": tx_date,
        "total_net_worth": 3500.0,
        "liquid_net_worth": 3500.0,
        "vested_net_worth": 3500.0,
        "total_assets": 3500.0,
        "total_debt": 0.0,
        "checking": 3500.0
    })

    db_path = tmp_path / "test.sqlite"
    export_ledger_to_sqlite(ledger, str(db_path))

    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_records'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT date, flow, category FROM transactions")
    tx_rows = cursor.fetchall()
    assert len(tx_rows) == 1
    assert tx_rows[0] == ("2026-01-01", "Rent", "housing")

    cursor.execute("SELECT date, checking FROM daily_records")
    daily_rows = cursor.fetchall()
    assert len(daily_rows) == 1
    assert daily_rows[0] == ("2026-01-01", 3500.0)

    conn.close()
