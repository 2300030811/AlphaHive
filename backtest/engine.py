"""
AlphaHive walk-forward backtest engine.

This module is an original AlphaHive implementation inspired by the
metrics-first discipline in Vibe-Trading. It does not copy reference code.

The key rule: every strategy decides exposure with information available
before the return being measured. Signals are shifted by one bar to avoid
look-ahead bias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd


SEBI_DISCLAIMER = (
    "For educational purposes only. Not investment advice. "
    "AlphaHive is not SEBI-registered. "
    "All trading decisions are entirely your own."
)


@dataclass(frozen=True)
class BacktestConfig:
    ticker: str
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    transaction_cost_bps: float = 10.0

    def validate(self) -> None:
        if not self.ticker:
            raise ValueError("ticker is required")
        start = pd.Timestamp(self.start_date)
        end = pd.Timestamp(self.end_date)
        if start >= end:
            raise ValueError("start_date must be before end_date")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps cannot be negative")


SignalFunction = Callable[[pd.DataFrame], pd.Series]


class WalkForwardBacktester:
    """Runs long/cash walk-forward simulations on daily OHLCV data."""

    def __init__(self, bars_per_year: int = 252):
        self.bars_per_year = bars_per_year

    def run(
        self,
        prices: pd.DataFrame,
        config: BacktestConfig,
        signal_fn: SignalFunction,
        strategy_name: str,
    ) -> dict:
        config.validate()
        df = self._prepare_prices(prices)
        if len(df) < 30:
            raise ValueError("At least 30 price rows are required for backtesting")

        raw_signal = signal_fn(df).reindex(df.index).fillna(0.0).clip(0.0, 1.0)

        # Shift exposure so today's signal only affects the next bar's return.
        exposure = raw_signal.shift(1).fillna(0.0)
        returns = df["close"].pct_change().fillna(0.0)
        turnover = exposure.diff().abs().fillna(exposure.abs())
        cost = turnover * (config.transaction_cost_bps / 10000.0)
        strategy_returns = (exposure * returns) - cost

        equity = config.initial_capital * (1.0 + strategy_returns).cumprod()
        benchmark_equity = config.initial_capital * (1.0 + returns).cumprod()
        trades = self._extract_trades(df, exposure, returns)

        # serialize strategy returns for downstream validation
        daily_returns_list = list(strategy_returns.fillna(0.0).astype(float).tolist())

        return {
            "strategy": strategy_name,
            "ticker": config.ticker,
            "start_date": str(df.index[0].date()),
            "end_date": str(df.index[-1].date()),
            "initial_capital": round(config.initial_capital, 2),
            "transaction_cost_bps": config.transaction_cost_bps,
            "metrics": self._metrics(equity, strategy_returns, trades, config.initial_capital),
            "equity_curve": self._curve(equity),
            "benchmark_curve": self._curve(benchmark_equity),
            "exposure_days": int((exposure > 0).sum()),
            "data_points": len(df),
            "daily_returns": daily_returns_list,
            "trades": trades,
            "disclaimer": SEBI_DISCLAIMER,
        }

    def _prepare_prices(self, prices: pd.DataFrame) -> pd.DataFrame:
        df = prices.copy()
        df.columns = [str(c).lower() for c in df.columns]
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        df = df.sort_index()

        required = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required OHLCV columns: {missing}")

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df[~df.index.duplicated(keep="last")]
        return df

    def _metrics(
        self,
        equity: pd.Series,
        returns: pd.Series,
        trades: list[dict],
        initial_capital: float,
    ) -> dict:
        if equity.empty:
            return self._empty_metrics(initial_capital)

        total_return = float(equity.iloc[-1] / initial_capital - 1)
        periods = max(len(equity), 1)
        annual_return = float((1 + total_return) ** (self.bars_per_year / periods) - 1)
        volatility = float(returns.std())
        sharpe = float(returns.mean() / (volatility + 1e-10) * math.sqrt(self.bars_per_year))

        peak = equity.cummax()
        drawdown = (equity - peak) / peak.replace(0, 1)
        max_drawdown = float(drawdown.min())

        completed = [trade for trade in trades if trade.get("return_pct") is not None]
        wins = [trade for trade in completed if trade["return_pct"] > 0]
        win_rate = len(wins) / len(completed) if completed else 0.0

        return {
            "final_value": round(float(equity.iloc[-1]), 2),
            "total_return": round(total_return, 6),
            "annual_return": round(annual_return, 6),
            "max_drawdown": round(max_drawdown, 6),
            "sharpe": round(sharpe, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": len(completed),
            "best_day": round(float(returns.max()), 6),
            "worst_day": round(float(returns.min()), 6),
        }

    def _empty_metrics(self, initial_capital: float) -> dict:
        return {
            "final_value": initial_capital,
            "total_return": 0.0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "win_rate": 0.0,
            "trade_count": 0,
            "best_day": 0.0,
            "worst_day": 0.0,
        }

    def _extract_trades(
        self,
        df: pd.DataFrame,
        exposure: pd.Series,
        returns: pd.Series,
    ) -> list[dict]:
        trades: list[dict] = []
        in_trade = False
        entry_date = None
        entry_price = None

        for idx, value in exposure.items():
            if not in_trade and value > 0:
                in_trade = True
                entry_date = idx
                entry_price = float(df.loc[idx, "close"])
            elif in_trade and value <= 0:
                exit_price = float(df.loc[idx, "close"])
                trades.append(self._trade(entry_date, idx, entry_price, exit_price))
                in_trade = False
                entry_date = None
                entry_price = None

        if in_trade and entry_date is not None and entry_price is not None:
            final_idx = df.index[-1]
            trades.append(self._trade(entry_date, final_idx, entry_price, float(df["close"].iloc[-1])))

        return trades

    def _trade(self, entry_date, exit_date, entry_price: float, exit_price: float) -> dict:
        holding_days = max((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days, 0)
        return {
            "entry_date": str(pd.Timestamp(entry_date).date()),
            "exit_date": str(pd.Timestamp(exit_date).date()),
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round((exit_price / entry_price - 1) if entry_price else 0.0, 6),
            "holding_days": holding_days,
        }

    def _curve(self, equity: pd.Series) -> list[dict]:
        return [
            {"date": str(pd.Timestamp(idx).date()), "value": round(float(value), 2)}
            for idx, value in equity.items()
        ]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicators used by AlphaHive and baseline strategies."""
    out = df.copy()
    close = out["close"]
    volume = out["volume"]

    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["ema_50"] = close.ewm(span=50, adjust=False).mean()
    out["ema_200"] = close.ewm(span=200, adjust=False).mean()
    out["rsi_14"] = _rsi(close, 14)
    out["volume_avg_30"] = volume.rolling(30, min_periods=10).mean()
    out["volume_ratio"] = volume / out["volume_avg_30"].replace(0, pd.NA)
    return out


def alphahive_proxy_signal(df: pd.DataFrame) -> pd.Series:
    """
    Original deterministic proxy for AlphaHive's directional research signal.

    This is intentionally simple for MVP backtesting: it approximates the
    combined technical/sentiment posture without running the live LLM swarm
    against historical news. It is labeled as a proxy by the API response.
    """
    data = compute_indicators(df)
    score = pd.Series(50.0, index=data.index)

    score += (data["ema_20"] > data["ema_50"]).astype(float) * 10
    score += (data["ema_50"] > data["ema_200"]).astype(float) * 15
    score += data["rsi_14"].between(45, 65).astype(float) * 10
    score -= (data["rsi_14"] > 72).astype(float) * 12
    score -= (data["rsi_14"] < 25).astype(float) * 8
    score += ((data["volume_ratio"] > 1.4) & (data["close"] > data["close"].shift(1))).astype(float) * 8
    score -= ((data["volume_ratio"] > 1.4) & (data["close"] < data["close"].shift(1))).astype(float) * 8

    return (score >= 60).astype(float)


def buy_and_hold_signal(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0, index=df.index)


def rsi_signal(df: pd.DataFrame) -> pd.Series:
    data = compute_indicators(df)
    exposure = pd.Series(0.0, index=data.index)
    previous = 0.0
    for idx, rsi in data["rsi_14"].items():
        if pd.isna(rsi):
            exposure.loc[idx] = previous
        elif rsi < 35:
            previous = 1.0
            exposure.loc[idx] = previous
        elif rsi > 70:
            previous = 0.0
            exposure.loc[idx] = previous
        else:
            exposure.loc[idx] = previous
    return exposure


def ema_crossover_signal(df: pd.DataFrame) -> pd.Series:
    data = compute_indicators(df)
    return (data["ema_50"] > data["ema_200"]).astype(float)


def _rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50.0)
