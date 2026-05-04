"""
AlphaHive — Audit Logger
=========================
Writes structured JSON Lines (.jsonl) log files for traceability and debugging.

Each line is a JSON object with a `stage` field so you can grep for
swarm decisions, specialist verdicts, debate output, or final signals.

Log file lives at: ./logs/alphahive_audit_{date}.jsonl
Rotate daily. Each run appends; no file is overwritten.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("alphahive.audit")

_LOGS_DIR = Path(os.getenv("ALPHAHIVE_LOGS_DIR", "logs"))
_AUDIT_LOG: Path | None = None


def _get_log_path() -> Path:
    global _AUDIT_LOG
    if _AUDIT_LOG is None:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _AUDIT_LOG = _LOGS_DIR / f"alphahive_audit_{today}.jsonl"
    return _AUDIT_LOG


def log(stage: str, ticker: str, **kwargs) -> None:
    """
    Write one JSON Line to the audit log.

    Args:
        stage:   One of SWARM_ROUND1 | SWARM_ROUND2 | SPECIALIST
                 DEBATE | SIGNAL | ERROR
        ticker:  Stock ticker (e.g. RELIANCE.NS)
        **kwargs: Remaining fields — merged into the line as-is
    """
    line = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "ticker": ticker,
        **kwargs,
    }
    path = _get_log_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Audit log write failed (non-fatal): {e}")


def log_swarm_decision(
    ticker: str,
    agent_name: str,
    agent_type: str,
    round_num: int,
    action: str,
    confidence: float,
    reasoning: str,
) -> None:
    log(
        stage="SWARM_ROUND1" if round_num == 1 else "SWARM_ROUND2",
        ticker=ticker,
        agent_name=agent_name,
        agent_type=agent_type,
        round=round_num,
        action=action,
        confidence=confidence,
        reasoning=reasoning,
    )


def log_specialist(
    ticker: str,
    analyst: str,
    score: int | float,
    verdict: str,
    summary: str,
) -> None:
    log(
        stage="SPECIALIST",
        ticker=ticker,
        analyst=analyst,
        score=score,
        verdict=verdict,
        summary=summary,
    )


def log_debate(
    ticker: str,
    bull_score: float,
    bear_score: float,
    final_call: str,
) -> None:
    log(
        stage="DEBATE",
        ticker=ticker,
        bull_score=bull_score,
        bear_score=bear_score,
        final_call=final_call,
    )


def log_signal(ticker: str, signal: dict) -> None:
    """Log the complete final signal dict."""
    log(
        stage="SIGNAL",
        ticker=ticker,
        final_call=signal.get("signal", {}).get("final_call", "UNKNOWN"),
        bullish_prob=signal.get("signal", {}).get("bullish_probability", 0),
        risk_level=signal.get("signal", {}).get("risk_level", "UNKNOWN"),
        confidence=signal.get("signal", {}).get("confidence", "UNKNOWN"),
    )
