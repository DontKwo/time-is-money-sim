import pytest
import pandas as pd
from datetime import datetime
import os
from unittest.mock import patch
from lifesim.plots import plot_balances

def test_plot_balances_empty_df(tmp_path):
    df = pd.DataFrame()
    filename = tmp_path / "test_plot.png"

    # We shouldn't call any plt functions if df is empty
    with patch('matplotlib.pyplot.figure') as mock_figure:
        plot_balances(df, str(filename))
        mock_figure.assert_not_called()

    assert not os.path.exists(filename)

def test_plot_balances_creates_file(tmp_path):
    data = {
        'date': [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
        'account': ['Checking', 'Checking', 'Savings'],
        'balance': [1000, 1500, 5000]
    }
    df = pd.DataFrame(data)
    filename = tmp_path / "test_plot_balances.png"

    plot_balances(df, str(filename))

    assert os.path.exists(filename)
    assert os.path.getsize(filename) > 0
