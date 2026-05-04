"""
AlphaHive backtest comparison runner.

Runs the AlphaHive proxy strategy against simple baselines:
Buy & Hold, RSI, and EMA crossover.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pandas as pd

from backtest.engine import (
    BacktestConfig,
    SEBI_DISCLAIMER,
    WalkForwardBacktester,
    alphahive_proxy_signal,
    buy_and_hold_signal,
    ema_crossover_signal,
    rsi_signal,
)
from backtest.validation import run_validation


STRATEGIES = {
    "AlphaHive Proxy": alphahive_proxy_signal,
    "Buy & Hold": buy_and_hold_signal,
    "RSI": rsi_signal,
    "EMA Crossover": ema_crossover_signal,
}


async def run_backtest_comparison(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    transaction_cost_bps: float = 10.0,
) -> dict:
    ticker = normalize_ticker(ticker)
    config = BacktestConfig(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        transaction_cost_bps=transaction_cost_bps,
    )
    config.validate()

    prices = await load_price_history(ticker, start_date, end_date)
    if prices.empty:
        raise ValueError(f"No price data available for {ticker}")

    backtester = WalkForwardBacktester()
    strategy_results = [
        backtester.run(prices, config, signal_fn, name)
        for name, signal_fn in STRATEGIES.items()
    ]

    winner = max(
        strategy_results,
        key=lambda result: result["metrics"]["total_return"],
    )

    # Attach validation summary for the winning strategy when daily returns present
    validation_summary = None
    try:
        dr = winner.get("daily_returns")
        if dr:
            validation_summary = run_validation(dr)
    except Exception:
        validation_summary = None

    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "transaction_cost_bps": transaction_cost_bps,
        "methodology": {
            "type": "walk_forward_daily_long_cash",
            "lookahead_bias_control": "Signals are shifted by one trading bar before returns are applied.",
            "alphahive_note": (
                "AlphaHive Proxy is a deterministic MVP approximation of the full "
                "research signal. It does not run historical LLM/news swarm analysis. "
                "Use the live-signal validation trail for realized outcome tracking."
            ),
        },
        "validation": {
            "available": True,
            "endpoint": f"/validation/{ticker}",
            "history_endpoint": f"/history/{ticker}",
            "note": (
                "This comparison is a deterministic proxy on historical prices. "
                "Stored live signals can be checked later for realized outcomes."
            ),
        },
        "winner": {
            "strategy": winner["strategy"],
            "total_return": winner["metrics"]["total_return"],
            "sharpe": winner["metrics"]["sharpe"],
        },
        "validation": validation_summary,
        "strategies": strategy_results,
        "disclaimer": SEBI_DISCLAIMER,
    }


async def load_price_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily OHLCV data using yfinance, with DataLoader fallback."""
    try:
        import yfinance as yf

        loop = asyncio.get_event_loop()

        def fetch():
            stock = yf.Ticker(ticker)
            return stock.history(start=start_date, end=_exclusive_end_date(end_date), auto_adjust=True)

        raw = await loop.run_in_executor(None, fetch)
        df = normalize_price_frame(raw)
        if not df.empty:
            return df
    except Exception:
        pass

    # Fallback to AlphaHive's existing loader. It fetches by lookback window,
    # then we trim to the requested dates.
    from data.loader import data_loader

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    days = max((end - start).days + 20, 60)
    fallback = await data_loader.get_price_history(ticker, days=days)
    fallback = normalize_price_frame(fallback)
    if fallback.empty:
        return fallback
    mask = (fallback["date"] >= start) & (fallback["date"] <= end)
    return fallback.loc[mask].reset_index(drop=True)


def normalize_price_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.reset_index() if "Date" in raw.index.names or raw.index.name else raw.copy()
    df.columns = [str(col).lower() for col in df.columns]
    if "datetime" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"datetime": "date"})
    if "date" not in df.columns and df.index.name:
        df = df.reset_index().rename(columns={df.index.name: "date"})

    keep = [col for col in ["date", "open", "high", "low", "close", "volume"] if col in df.columns]
    df = df[keep]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.dropna(subset=["close"]).reset_index(drop=True)


def normalize_ticker(ticker: str) -> str:
    symbol = ticker.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = f"{symbol}.NS"
    return symbol


def _exclusive_end_date(end_date: str) -> str:
    end = datetime.fromisoformat(end_date).date() + timedelta(days=1)
    return end.isoformat()
