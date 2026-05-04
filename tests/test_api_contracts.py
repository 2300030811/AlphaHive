import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import _stream_agent_events, get_stock_signal, get_watchlist


def test_stream_agent_events_maps_swarm_actions_to_ui_decisions():
    result = {
        "swarm": {
            "round1_results": [
                {
                    "agent_type": "retail",
                    "agent_name": "Panic_Seller_1",
                    "action": "sell",
                    "confidence": 0.8,
                    "reasoning": "Negative move triggered panic.",
                },
                {
                    "agent_type": "institutional",
                    "agent_name": "DII_Value_1",
                    "action": "buy",
                    "confidence": 0.7,
                    "reasoning": "Valuation support.",
                },
            ],
            "round2_results": [
                {
                    "agent_type": "algo",
                    "agent_name": "RSI_Bot_1",
                    "action": "hold",
                    "confidence": 0.6,
                    "reasoning": "RSI neutral.",
                }
            ],
        },
        "specialists": {},
    }

    events = _stream_agent_events(result)
    decisions = {event["decision"] for event in events}

    assert "BUY" not in decisions
    assert "SELL" not in decisions
    assert {"BULLISH", "BEARISH", "HOLD"}.issuperset(decisions)


def test_watchlist_exposes_cached_signal_contract():
    cached_signal = {
        "ticker": "RELIANCE.NS",
        "company": "Reliance Industries",
        "sector": "Energy",
        "signal": {"final_call": "BULLISH", "bullish_probability": 64},
        "swarm": {"conviction": 77},
        "disclaimer": "For educational purposes only. Not investment advice. "
        "AlphaHive is not SEBI-registered. All trading decisions are entirely your own.",
    }

    class DummyCache:
        async def get_signal(self, ticker):
            return cached_signal if ticker == "RELIANCE.NS" else None

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(orchestrator=SimpleNamespace(cache=DummyCache())))
    )

    payload = asyncio.run(get_watchlist(request))
    first = payload["stocks"][0]

    assert "cached_signal" in first
    assert first["cached_signal"] == cached_signal
    assert payload["cached_count"] >= 1
    assert payload["disclaimer"]


def test_stock_signal_reads_cache_before_database():
    cached_signal = {
        "ticker": "TCS.NS",
        "signal": {"final_call": "NEUTRAL", "bullish_probability": 52},
    }

    class DummyCache:
        async def get_signal(self, ticker):
            return cached_signal if ticker == "TCS.NS" else None

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(orchestrator=SimpleNamespace(cache=DummyCache())))
    )

    payload = asyncio.run(get_stock_signal("TCS", request))

    assert payload["ticker"] == "TCS.NS"
    assert payload["signal"]["final_call"] == "NEUTRAL"
    assert payload["disclaimer"]
