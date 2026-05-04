import asyncio
import json
import sys
import types
from pathlib import Path

from engine.memory import SignalMemory


class _FakeHistory:
    empty = False
    columns = ["Close"]

    def reset_index(self):
        return self

    def __getitem__(self, key):
        if key == "Close":
            return [100.0, 105.0, 106.0]
        raise KeyError(key)


class _FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, start=None, end=None, auto_adjust=True):
        return _FakeHistory()


def test_signal_memory_store_evaluate_and_reflect(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))

    storage_path = tmp_path / "signal_memory.json"
    memory = SignalMemory(storage_path=str(storage_path))

    signal = {
        "ticker": "RELIANCE.NS",
        "timestamp": "2026-05-01T09:15:00+00:00",
        "signal": {"final_call": "BULLISH"},
    }

    memory.store_signal("RELIANCE.NS", signal)
    assert len(memory.get_pending_signals("RELIANCE.NS")) == 1

    evaluation = memory.evaluate_signal("RELIANCE.NS", "2026-05-01T09:15:00+00:00")
    assert evaluation["status"] == "evaluated"
    assert evaluation["signal_call"] == "BULLISH"

    reflection = asyncio.run(memory.reflect("RELIANCE.NS"))
    assert reflection
    assert memory.get_past_context("RELIANCE.NS")


def test_debate_engine_stops_on_repetition(monkeypatch):
    import engine.debate as debate

    async def fake_call(system, user):
        if "Make the final verdict" in user:
            return json.dumps(
                {
                    "final_call": "BULLISH",
                    "bullish_probability": 66,
                    "risk_level": "MEDIUM",
                    "confidence": "HIGH",
                    "deciding_factor": "Momentum and fundamentals align.",
                    "key_risk": "Macro volatility",
                    "verdict_reasoning": "The balance of evidence is supportive.",
                }
            )
        if "Build the bull case" in user:
            return json.dumps(
                {
                    "bull_case": "Bull case text",
                    "bull_score": 71,
                    "top_bull_reasons": ["reason1"],
                    "acknowledged_risks": ["risk1"],
                }
            )
        return json.dumps(
            {
                "bear_case": "Bear case text",
                "bear_score": 61,
                "top_bear_reasons": ["reason2"],
                "acknowledged_bull_signals": ["signal1"],
            }
        )

    monkeypatch.setattr(debate, "_call_ollama_specialist", fake_call)

    engine = debate.DebateEngine(max_debate_rounds=3)
    mock_output = {
        "ticker": "RELIANCE.NS",
        "company": "Reliance Industries",
        "sector": "Energy",
        "swarm": {
            "bullish_pct": 60,
            "panic_index": 20,
            "fomo_index": 10,
            "conviction": 80,
            "dominant_signal": "BULLISH",
        },
        "specialists": {
            "fundamental": {"score": 70, "verdict": "STRONG", "summary": "ok"},
            "technical": {"score": 65, "verdict": "BULLISH", "summary": "ok"},
            "sentiment": {"score": 55, "verdict": "NEUTRAL", "summary": "ok"},
            "news": {"score": 50, "verdict": "NEUTRAL", "summary": "ok", "alert": None},
        },
        "market_data": {},
    }

    result = asyncio.run(engine.run(mock_output))
    assert result["final_verdict"]["final_call"] == "BULLISH"
    assert result["debate_rounds"] == 2
    assert result["debate_stop_reason"] == "Repeated debate content"
    assert len(result["debate_history"]) == 2
