"""Backtest statistical validation utilities.

Provides Monte Carlo permutation test for Sharpe, bootstrap CI for Sharpe,
and a simple walk-forward consistency checker.
"""
from __future__ import annotations

import math
import random
from typing import Sequence, Tuple

import numpy as np
import pandas as pd


def _annualized_sharpe(returns: Sequence[float], bars_per_year: int = 252) -> float:
    arr = np.array(returns, dtype=float)
    if arr.size == 0:
        return 0.0
    mu = np.nanmean(arr)
    sigma = np.nanstd(arr, ddof=0)
    if sigma == 0:
        return 0.0
    return float(mu / sigma * math.sqrt(bars_per_year))


def monte_carlo_permutation_test(
    returns: Sequence[float], n_simulations: int = 1000, seed: int | None = None
) -> dict:
    """Shuffle returns and compute p-value that observed Sharpe is better than random.

    Returns dict with observed_sharpe, p_value, simulations.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    obs = _annualized_sharpe(returns)
    arr = np.array(returns, dtype=float)
    count = 0
    sims = []
    for _ in range(n_simulations):
        np.random.shuffle(arr)
        s = _annualized_sharpe(arr)
        sims.append(s)
        if s >= obs:
            count += 1
    p_value = (count + 1) / (n_simulations + 1)
    return {"observed_sharpe": obs, "p_value": p_value, "simulations": sims}


def bootstrap_sharpe_ci(
    returns: Sequence[float], n_bootstrap: int = 2000, alpha: float = 0.05, seed: int | None = None
) -> dict:
    """Bootstrap Sharpe confidence interval.

    Returns dict with lower, upper, mean_sharpe and sample of bootstrapped sharpe values.
    """
    if seed is not None:
        np.random.seed(seed)

    arr = np.array(returns, dtype=float)
    n = len(arr)
    if n == 0:
        return {"lower": 0.0, "upper": 0.0, "mean": 0.0, "samples": []}

    samples = []
    for _ in range(n_bootstrap):
        idx = np.random.randint(0, n, size=n)
        sample = arr[idx]
        samples.append(_annualized_sharpe(sample))

    lower = float(np.percentile(samples, 100 * (alpha / 2)))
    upper = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    mean = float(np.mean(samples))
    return {"lower": lower, "upper": upper, "mean": mean, "samples": samples}


def walk_forward_consistency(returns: Sequence[float], n_splits: int = 5) -> dict:
    """Split returns into sequential windows and report per-window stats.

    Returns per-window total_return and sharpe, plus a consistency score.
    """
    arr = np.array(returns, dtype=float)
    n = len(arr)
    if n == 0:
        return {"windows": [], "consistency": 0.0}

    # Determine split indices
    sizes = [n // n_splits] * n_splits
    for i in range(n % n_splits):
        sizes[i] += 1

    windows = []
    idx = 0
    for sz in sizes:
        if sz <= 0:
            windows.append({"total_return": 0.0, "sharpe": 0.0})
            continue
        w = arr[idx: idx + sz]
        total = float(np.prod(1 + w) - 1) if w.size > 0 else 0.0
        sharpe = _annualized_sharpe(w)
        windows.append({"total_return": total, "sharpe": sharpe, "n": int(w.size)})
        idx += sz

    # consistency metric: proportion of windows with same sign of total_return
    signs = [1 if w["total_return"] > 0 else (-1 if w["total_return"] < 0 else 0) for w in windows]
    pos = sum(1 for s in signs if s > 0)
    neg = sum(1 for s in signs if s < 0)
    consistency = max(pos, neg) / max(1, len([s for s in signs if s != 0])) if any(s != 0 for s in signs) else 0.0

    return {"windows": windows, "consistency": float(consistency)}


def run_validation(daily_returns: Sequence[float]) -> dict:
    """Run all validation checks and return combined report."""
    arr = list(float(x) for x in daily_returns)
    mc = monte_carlo_permutation_test(arr, n_simulations=1000)
    bs = bootstrap_sharpe_ci(arr, n_bootstrap=1000)
    wf = walk_forward_consistency(arr, n_splits=5)

    return {
        "monte_carlo": {"observed_sharpe": mc["observed_sharpe"], "p_value": mc["p_value"]},
        "bootstrap_sharpe": {"lower": bs["lower"], "upper": bs["upper"], "mean": bs["mean"]},
        "walk_forward": wf,
    }
