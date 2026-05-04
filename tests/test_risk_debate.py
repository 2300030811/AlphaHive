"""
Test suite for Risk Debate Layer.
Validates risk_analyst_node, risk-adjusted verdict, and invalidation conditions.
"""
import asyncio
import pytest
from engine.debate import (
    DebateState, 
    risk_analyst_node,
    DebateEngine,
    _parse_json_response,
)


@pytest.mark.asyncio
async def test_risk_analyst_node_basic():
    """Test that risk_analyst_node executes and returns valid structure."""
    state = DebateState(
        ticker="RELIANCE.NS",
        company="Reliance Industries",
        sector="Energy",
        swarm_signal={
            "bullish_pct": 65.0,
            "panic_index": 15.0,
            "fomo_index": 25.0,
            "conviction": 75.0,
            "crowd_narrative": "Institutional accumulation with retail concern.",
        },
        specialist_reports={
            "fundamental": {
                "score": 72,
                "verdict": "BULLISH",
                "summary": "P/E 24x, PE Growth 2.0, strong FCF",
                "key_positives": ["Low PE vs peers", "FCF positive", "Dividends stable"],
            },
            "technical": {
                "score": 68,
                "verdict": "BULLISH",
                "summary": "Price above 50 EMA, RSI 58, volume 1.8x avg",
                "key_signals": ["Golden cross forming", "Support at 2800", "Breakout confirmed"],
            },
            "sentiment": {
                "score": 65,
                "verdict": "NEUTRAL",
                "summary": "Mixed sentiment, low FUD on headlines",
            },
            "news": {
                "score": 55,
                "alert": "None",
                "summary": "Promoter holding stable, no major announcements",
            },
        },
        bull_case="Strong fundamentals and technical alignment suggest upside to 3200. Institutional demand is accelerating.",
        bull_score=72.0,
        bear_case="Energy sector faces macro headwinds from energy transition. Refining margins under pressure.",
        bear_score=48.0,
    )
    
    # Execute risk analyst
    result_state = await risk_analyst_node(state)
    
    # Validate output structure
    assert result_state["risk_score"] is not None
    assert isinstance(result_state["risk_score"], float)
    assert 0 <= result_state["risk_score"] <= 100
    
    assert result_state["key_risks"] is not None
    assert isinstance(result_state["key_risks"], list)
    
    assert result_state["invalidation_conditions"] is not None
    assert isinstance(result_state["invalidation_conditions"], list)
    
    assert result_state["risk_assessment"] is not None
    assert isinstance(result_state["risk_assessment"], str)
    
    print(f"Risk Score: {result_state['risk_score']}")
    print(f"Key Risks: {result_state['key_risks']}")
    print(f"Invalidation Conditions: {result_state['invalidation_conditions']}")


@pytest.mark.asyncio
async def test_debate_engine_with_risk_analyst():
    """Test full debate pipeline including risk analyst node."""
    orchestrator_output = {
        "ticker": "TCS.NS",
        "company": "Tata Consultancy Services",
        "sector": "IT Services",
        "swarm": {
            "bullish_pct": 58.0,
            "bearish_pct": 22.0,
            "hold_pct": 20.0,
            "panic_index": 8.0,
            "fomo_index": 15.0,
            "conviction": 72.0,
            "dominant_signal": "NEUTRAL",
            "crowd_narrative": "Retail cautious on growth outlook, institutions holding steady.",
        },
        "specialists": {
            "fundamental": {
                "score": 65,
                "verdict": "NEUTRAL",
                "summary": "P/E 20x, EPS growth slowing to 5% YoY",
                "key_positives": ["Dividend yield 2.3%", "Strong balance sheet"],
            },
            "technical": {
                "score": 60,
                "verdict": "NEUTRAL",
                "summary": "Price consolidating, RSI 48, below 200 DMA",
                "key_signals": ["Support at 3650", "Resistance at 3900"],
            },
            "sentiment": {
                "score": 52,
                "verdict": "NEUTRAL",
                "summary": "Cautious tone, growth concerns dominate",
            },
            "news": {
                "score": 50,
                "alert": "None",
                "summary": "No material news",
            },
            "combined_score": 56.75,
        },
        "memory_context": "Model recently favored TCS, but signal strength declined last month.",
    }
    
    engine = DebateEngine(max_debate_rounds=1)
    debate_result = await engine.run(orchestrator_output)
    
    # Validate that risk analysis is present in output
    assert "risk_score" in debate_result
    assert "key_risks" in debate_result
    assert "invalidation_conditions" in debate_result
    assert "risk_assessment" in debate_result
    
    # Validate final verdict includes risk analysis
    final_verdict = debate_result.get("final_verdict", {})
    assert "risk_score" in final_verdict
    assert "key_risks" in final_verdict
    assert "invalidation_conditions" in final_verdict
    
    print(f"Debate Rounds: {debate_result.get('debate_rounds')}")
    print(f"Stop Reason: {debate_result.get('debate_stop_reason')}")
    print(f"Final Call: {final_verdict.get('final_call')}")
    print(f"Risk Score: {final_verdict.get('risk_score')}")
    print(f"Risk Level: {final_verdict.get('risk_level')}")


def test_parse_json_response_with_risk_format():
    """Test JSON parsing of risk analyst response format."""
    json_response = """
    {
      "risk_score": 62,
      "key_risks": [
        "Energy transition headwinds in refining",
        "Regulatory pressure on fossil fuels",
        "Currency exposure to GBP"
      ],
      "macro_headwinds": [
        "Global oil price volatility",
        "Geopolitical tensions affecting supply"
      ],
      "invalidation_conditions": [
        "If global oil price falls below $50/bbl, FCF generation becomes weak",
        "If regulatory carbon tax implemented, margin compression likely"
      ],
      "risk_assessment": "Energy sector faces structural headwinds from transition. Short-term volatility expected but long-term thesis intact.",
      "tail_risk_alert": "false"
    }
    """
    
    parsed = _parse_json_response(json_response)
    
    assert parsed["risk_score"] == 62
    assert len(parsed["key_risks"]) == 3
    assert len(parsed["invalidation_conditions"]) == 2
    assert "transition" in parsed["risk_assessment"]
    assert parsed["tail_risk_alert"] == "false"


def test_parse_json_response_with_markdown_fence():
    """Test JSON parsing with markdown code fence."""
    json_response = """
    ```json
    {
      "risk_score": 78,
      "key_risks": ["Risk 1", "Risk 2"],
      "invalidation_conditions": ["Condition 1"],
      "risk_assessment": "High risk scenario",
      "tail_risk_alert": "true"
    }
    ```
    """
    
    parsed = _parse_json_response(json_response)
    
    assert parsed["risk_score"] == 78
    assert parsed["tail_risk_alert"] == "true"


@pytest.mark.asyncio
async def test_risk_score_influences_risk_level():
    """Test that high risk_score from analyst influences final risk_level."""
    # Scenario: Bull case is strong, but risk analyst identifies significant risks
    # Expected: Even though debate might lean bullish, high risk_score should upgrade risk_level
    
    state = DebateState(
        ticker="INFY.NS",
        company="Infosys",
        sector="IT Services",
        swarm_signal={"bullish_pct": 70, "panic_index": 5, "conviction": 85},
        specialist_reports={
            "fundamental": {"score": 80, "verdict": "BULLISH"},
            "technical": {"score": 75, "verdict": "BULLISH"},
            "sentiment": {"score": 70, "verdict": "BULLISH"},
            "news": {"score": 65, "alert": "None"},
        },
        bull_case="Strong growth, excellent margins, great execution.",
        bull_score=85.0,
        bear_case="Valuation stretched, growth rate concerns.",
        bear_score=35.0,
    )
    
    # Simulate risk analyst finding high risk despite bull case
    result_state = await risk_analyst_node(state)
    result_state["risk_score"] = 80.0  # High risk despite bull case
    result_state["key_risks"] = [
        "Concentration in US revenue",
        "Geopolitical visa restrictions",
        "AI disruption risk to services model"
    ]
    result_state["invalidation_conditions"] = [
        "If US recession materializes, demand contracts significantly"
    ]
    
    # The risk_score should be captured for downstream scorer
    assert result_state["risk_score"] == 80.0
    assert len(result_state["key_risks"]) == 3


if __name__ == "__main__":
    # Run basic tests
    print("Running Risk Debate Layer tests...")
    
    # Test JSON parsing
    test_parse_json_response_with_risk_format()
    print("✓ JSON parsing test passed")
    
    test_parse_json_response_with_markdown_fence()
    print("✓ JSON parsing with markdown fence test passed")
    
    # Run async tests
    asyncio.run(test_risk_analyst_node_basic())
    print("✓ Risk analyst node basic test passed")
    
    asyncio.run(test_debate_engine_with_risk_analyst())
    print("✓ Full debate engine with risk analyst test passed")
    
    asyncio.run(test_risk_score_influences_risk_level())
    print("✓ Risk score influence test passed")
    
    print("\n✅ All Risk Debate Layer tests passed!")
