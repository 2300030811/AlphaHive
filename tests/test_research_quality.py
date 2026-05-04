from datetime import datetime, timezone

from engine.research_quality import ResearchQualityAnalyzer


def _mock_orchestrator_output(
    *,
    swarm_bullish=72.0,
    combined_score=68.0,
    fundamental_score=70,
    technical_score=66,
    sentiment_score=62,
    news_score=58,
    news_alert=None,
):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "ticker": "RELIANCE.NS",
        "company": "Reliance Industries",
        "sector": "Energy",
        "swarm": {
            "bullish_pct": swarm_bullish,
            "bearish_pct": 18.0,
            "hold_pct": 10.0,
            "panic_index": 16.0,
            "fomo_index": 32.0,
            "conviction": 84.0,
        },
        "specialists": {
            "fundamental": {
                "score": fundamental_score,
                "summary": "PE below sector average and EPS improving.",
                "timestamp": now,
                "raw_data": {
                    "pe_ratio": 22.0,
                    "sector_avg_pe": 28.0,
                    "eps_growth_yoy": 0.12,
                    "promoter_holding_pct": 50.1,
                },
                "derived": {
                    "pe_vs_sector": "cheap",
                    "earnings_trend": "improving",
                    "promoter_confidence": "high",
                },
            },
            "technical": {
                "score": technical_score,
                "summary": "Price above key moving averages.",
                "timestamp": now,
                "watch_levels": {"support": 2400.0, "resistance": 2650.0},
                "indicators": {
                    "rsi_14": 58.0,
                    "rsi_signal": "neutral",
                    "ema_50": 2480.0,
                    "ema_200": 2350.0,
                    "trend_structure": "uptrend",
                    "volume_ratio": 1.8,
                    "volume_trend": "expanding",
                },
            },
            "sentiment": {
                "score": sentiment_score,
                "summary": "Positive coverage.",
                "timestamp": now,
                "headlines_analyzed": 3,
                "verdict": "POSITIVE",
                "top_headlines": [
                    {
                        "headline": "Reliance profit rises on telecom strength",
                        "source": "Example RSS",
                        "label": "positive",
                        "confidence": 0.92,
                        "published_at": now,
                    }
                ],
            },
            "news": {
                "score": news_score,
                "summary": "No material negative events.",
                "timestamp": now,
                "headlines_analyzed": 4,
                "bullish_events": 1,
                "bearish_events": 0,
                "alert": news_alert,
                "top_events": [
                    {
                        "headline": "Reliance announces expansion plan",
                        "event_type": "bullish_event",
                        "impact": 0.7,
                    }
                ],
            },
            "combined_score": combined_score,
        },
        "signal_preview": {
            "agreement": "STRONG_AGREEMENT_BULLISH",
        },
    }


def _mock_debate_output(bull_score=74, bear_score=48):
    return {
        "bull_score": bull_score,
        "bear_score": bear_score,
        "bull_case": "Constructive setup.",
        "bear_case": "Risks are manageable.",
    }


def _mock_signal(final_call="BULLISH"):
    return {
        "final_call": final_call,
        "bullish_probability": 72,
        "risk_level": "LOW",
        "confidence": "HIGH",
        "agreement_type": "STRONG_AGREEMENT_BULLISH",
        "key_risk": "",
    }


def test_research_quality_adds_trust_evidence_and_risk_notes():
    analyzer = ResearchQualityAnalyzer()
    result = analyzer.evaluate(
        ticker="RELIANCE.NS",
        orchestrator_output=_mock_orchestrator_output(),
        debate_output=_mock_debate_output(),
        signal=_mock_signal(),
    )

    assert result["research_quality"]["trust_label"] in {"HIGH", "MEDIUM"}
    assert result["research_quality"]["trust_score"] >= 55
    assert result["evidence"]["facts"]
    assert any(fact["source"] for fact in result["evidence"]["facts"])
    assert result["risk_notes"]["invalidation_conditions"]
    assert result["conflicts"] == []


def test_research_quality_flags_cross_layer_conflicts():
    analyzer = ResearchQualityAnalyzer()
    output = _mock_orchestrator_output(
        swarm_bullish=74.0,
        combined_score=42.0,
        fundamental_score=35,
        technical_score=78,
        news_score=35,
        news_alert="HIGH RISK: Material negative event detected. Review manually.",
    )
    signal = _mock_signal()
    signal["agreement_type"] = "DIVERGENCE_SWARM_BULLISH"

    result = analyzer.evaluate(
        ticker="RELIANCE.NS",
        orchestrator_output=output,
        debate_output=_mock_debate_output(bull_score=64, bear_score=60),
        signal=signal,
    )

    titles = {conflict["title"] for conflict in result["conflicts"]}
    assert "Crowd bullish, specialists cautious" in titles
    assert "Bullish signal with news alert" in titles
    assert result["research_quality"]["trust_score"] < 75
    assert result["risk_notes"]["primary_risk"]


if __name__ == "__main__":
    test_research_quality_adds_trust_evidence_and_risk_notes()
    test_research_quality_flags_cross_layer_conflicts()
    print("research quality tests passed")
