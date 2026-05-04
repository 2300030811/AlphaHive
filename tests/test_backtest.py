import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.compare import run_backtest_comparison
from backtest.engine import (
    BacktestConfig,
    WalkForwardBacktester,
    alphahive_proxy_signal,
    buy_and_hold_signal,
    ema_crossover_signal,
    rsi_signal,
)


def make_prices(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series([100 + i * 0.18 + (i % 17) * 0.08 for i in range(rows)])
    return pd.DataFrame({
        "date": dates,
        "open": close * 0.995,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1_000_000 + (pd.Series(range(rows)) % 30) * 10_000,
    })


def test_walk_forward_backtest_outputs_metrics():
    config = BacktestConfig(
        ticker="RELIANCE.NS",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    result = WalkForwardBacktester().run(
        prices=make_prices(),
        config=config,
        signal_fn=alphahive_proxy_signal,
        strategy_name="AlphaHive Proxy",
    )

    assert result["strategy"] == "AlphaHive Proxy"
    assert result["metrics"]["final_value"] > 0
    assert "sharpe" in result["metrics"]
    assert result["equity_curve"]
    assert result["disclaimer"]


def test_baseline_signals_are_aligned_to_prices():
    prices = make_prices()
    for signal_fn in [buy_and_hold_signal, rsi_signal, ema_crossover_signal, alphahive_proxy_signal]:
        signal = signal_fn(prices)
        assert len(signal) == len(prices)
        assert signal.index.equals(prices.index) or len(signal.index) == len(prices.index)
        assert signal.dropna().between(0, 1).all()


if __name__ == "__main__":
    test_walk_forward_backtest_outputs_metrics()
    test_baseline_signals_are_aligned_to_prices()
    print("backtest tests passed")
