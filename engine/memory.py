"""Persistent signal memory and reflection tracking for AlphaHive.

This is a lightweight file-backed store that keeps past signals and the
latest reflection summaries per ticker so future debates can see what happened
last time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("alphahive.engine.memory")


class SignalMemory:
    def __init__(self, storage_path: str | None = None):
        default_path = Path(__file__).resolve().parents[1] / ".alphahive_memory" / "signal_memory.json"
        configured = storage_path or os.getenv("ALPHAHIVE_SIGNAL_MEMORY_PATH")
        self.storage_path = Path(configured) if configured else default_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = os.getenv("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = 45.0

    def _load(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"signals": {}, "reflections": {}}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load signal memory: {e}")
            return {"signals": {}, "reflections": {}}

    def _save(self, payload: dict[str, Any]) -> None:
        try:
            self.storage_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save signal memory: {e}")

    def store_signal(self, ticker: str, signal: dict) -> None:
        """Persist a newly generated AlphaHive signal."""
        payload = self._load()
        entry = {
            "ticker": ticker,
            "timestamp": signal.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "signal": signal,
            "evaluated": False,
            "evaluation": None,
        }
        payload.setdefault("signals", {}).setdefault(ticker, []).append(entry)
        self._save(payload)

    def get_pending_signals(self, ticker: str) -> list[dict]:
        payload = self._load()
        signals = payload.get("signals", {}).get(ticker, [])
        return [item for item in signals if not item.get("evaluated")]

    def _find_signal_record(self, payload: dict[str, Any], ticker: str, signal_date: str) -> tuple[int | None, dict | None]:
        records = payload.get("signals", {}).get(ticker, [])
        target_date = datetime.fromisoformat(signal_date.replace("Z", "+00:00")).date()
        for idx, record in enumerate(records):
            try:
                record_date = datetime.fromisoformat(record.get("timestamp", "").replace("Z", "+00:00")).date()
                if record_date == target_date:
                    return idx, record
            except Exception:
                continue
        return None, None

    def evaluate_signal(self, ticker: str, signal_date: str, horizon_days: int = 5) -> dict:
        """Fetch forward price action and label whether the signal was correct."""
        payload = self._load()
        idx, record = self._find_signal_record(payload, ticker, signal_date)
        if record is None:
            raise ValueError(f"No stored signal found for {ticker} on {signal_date}")

        try:
            import yfinance as yf

            signal_dt = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            start = signal_dt.date().isoformat()
            end = (signal_dt + timedelta(days=horizon_days + 3)).date().isoformat()
            history = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        except Exception as e:
            evaluation = {
                "status": "unavailable",
                "reason": f"Failed to fetch price history: {e}",
                "horizon_days": horizon_days,
            }
            record["evaluated"] = True
            record["evaluation"] = evaluation
            if idx is not None:
                payload["signals"][ticker][idx] = record
                self._save(payload)
            return evaluation

        if history is None or getattr(history, "empty", False):
            evaluation = {"status": "unavailable", "reason": "No forward price history available", "horizon_days": horizon_days}
        else:
            history = history.reset_index() if hasattr(history, "reset_index") else history
            close_values = None

            def _try_get(source, *keys):
                for key in keys:
                    try:
                        return source[key]
                    except Exception:
                        continue
                return None

            columns = [str(col).lower() for col in getattr(history, "columns", [])]
            if hasattr(history, "columns"):
                if "close" in columns:
                    close_values = _try_get(history, "close", "Close")
                elif "adj close" in columns:
                    close_values = _try_get(history, "adj close", "Adj Close")
                elif "adj_close" in columns:
                    close_values = _try_get(history, "adj_close", "Adj_Close")
                elif "Close" in getattr(history, "columns", []):
                    close_values = _try_get(history, "Close", "close")
            if close_values is None:
                close_values = getattr(history, "Close", None) or getattr(history, "close", None)

            if close_values is None:
                evaluation = {"status": "unavailable", "reason": "No close price history available", "horizon_days": horizon_days}
            else:
                if hasattr(close_values, "iloc"):
                    start_price = float(close_values.iloc[0])
                    end_price = float(close_values.iloc[min(len(close_values) - 1, horizon_days)])
                else:
                    values = list(close_values)
                    start_price = float(values[0])
                    end_price = float(values[min(len(values) - 1, horizon_days)])
            actual_return_pct = ((end_price / start_price) - 1.0) * 100 if start_price else 0.0

            final_call = record.get("signal", {}).get("signal", {}).get("final_call")
            if final_call == "BULLISH":
                correct = actual_return_pct > 0.0
            elif final_call == "BEARISH":
                correct = actual_return_pct < 0.0
            else:
                correct = abs(actual_return_pct) < 1.0

            evaluation = {
                "status": "evaluated",
                "horizon_days": horizon_days,
                "actual_return_pct": round(actual_return_pct, 2),
                "correct": bool(correct),
                "signal_call": final_call,
            }

        record["evaluated"] = True
        record["evaluation"] = evaluation
        if idx is not None:
            payload["signals"][ticker][idx] = record
            self._save(payload)
        return evaluation

    async def _call_llm(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "temperature": 0.3,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "")
        except Exception as e:
            logger.warning(f"Signal reflection LLM call failed: {e}")
            return ""

    async def reflect(self, ticker: str) -> str:
        """Generate a short reflection from the latest evaluated signals."""
        payload = self._load()
        signals = payload.get("signals", {}).get(ticker, [])
        recent = [item for item in signals if item.get("evaluated") and item.get("evaluation")]

        if not recent:
            reflection = "No evaluated signals yet for this ticker."
            payload.setdefault("reflections", {}).setdefault(ticker, []).append(
                {"timestamp": datetime.now(timezone.utc).isoformat(), "reflection": reflection}
            )
            self._save(payload)
            return reflection

        recent = recent[-3:]
        outcomes = []
        for item in recent:
            evaluation = item.get("evaluation", {})
            outcomes.append(
                f"{item.get('signal', {}).get('signal', {}).get('final_call', 'NEUTRAL')} -> "
                f"{evaluation.get('actual_return_pct', 'n/a')}% ({'correct' if evaluation.get('correct') else 'wrong'})"
            )

        system_prompt = (
            "You are a research reflection assistant. Summarize what AlphaHive learned "
            "from recent signal outcomes in 2-4 concise sentences. Respond in plain English only."
        )
        user_prompt = (
            f"Ticker: {ticker}\n"
            f"Recent evaluated outcomes:\n- " + "\n- ".join(outcomes)
        )
        llm_text = await self._call_llm(system_prompt, user_prompt)
        reflection = llm_text.strip() if llm_text.strip() else self._fallback_reflection(outcomes)

        payload.setdefault("reflections", {}).setdefault(ticker, []).append(
            {"timestamp": datetime.now(timezone.utc).isoformat(), "reflection": reflection}
        )
        self._save(payload)
        return reflection

    def _fallback_reflection(self, outcomes: list[str]) -> str:
        if not outcomes:
            return "No evaluated signals yet for this ticker."
        wins = sum("correct" in item for item in outcomes)
        losses = len(outcomes) - wins
        if wins >= losses:
            return (
                f"Recent signals have been more accurate than not, which suggests the current research stack is usable. "
                f"The main improvement area is reducing false positives when momentum is noisy."
            )
        return (
            f"Recent signals have missed too often, so the next debate should be more skeptical and specific. "
            f"The model should especially question weak conviction when the market tape is choppy."
        )

    def get_past_context(self, ticker: str) -> str:
        """Return the last three reflections for prompt injection."""
        payload = self._load()
        reflections = payload.get("reflections", {}).get(ticker, [])
        if not reflections:
            return ""
        recent = reflections[-3:]
        return "\n".join(
            f"- {item.get('reflection', '')}" for item in recent if item.get("reflection")
        )
