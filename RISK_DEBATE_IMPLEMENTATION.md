# Risk Debate Layer — Implementation Summary

**Status:** ✅ Complete and validated  
**Last Updated:** May 1, 2026  
**Integration:** Fully integrated into debate engine and scorer

---

## What Was Implemented

A dedicated **Risk Analyst Node** that runs as the final stage of the debate pipeline, assessing tail risks, black-swan scenarios, macro headwinds, and invalidation conditions before the final risk manager verdict.

### Architecture

```
Debate Pipeline Flow:
  researchers_node (bull + bear in parallel)
    ↓
  _should_continue_debate (loop check)
    ↓
  risk_analyst_node (NEW) ← Dedicated risk assessment
    ↓
  risk_manager_node (Incorporates risk analysis)
    ↓
  END
```

---

## Core Components

### 1. **risk_analyst_node** (engine/debate.py)

**Purpose:** Comprehensive risk assessment independent of bull/bear debate

**Inputs:**
- Swarm signal data (panic_index, FOMO, conviction)
- Bull and bear case scores
- Specialist reports (fundamental, technical, sentiment, news)
- Crowd narrative and alerts

**Outputs:**
- `risk_score` (0-100): Quantitative risk level
- `key_risks` (list): Top 3-4 identified risks
- `macro_headwinds` (list): Macro/sector/regulatory risks
- `invalidation_conditions` (list): Specific events that break the thesis
- `risk_assessment` (str): 2-3 sentence narrative
- `tail_risk_alert` (bool): Flag for elevated black-swan risk

**Risk Analyst Prompting:**
```
"You are a risk analyst specializing in tail risks, black-swan events,
and capital preservation. Think like a short-seller or risk manager.
Identify hidden risks, macro headwinds, regulatory threats.
Specify conditions that would INVALIDATE the current thesis."
```

**Example Output:**
```json
{
  "risk_score": 62,
  "key_risks": [
    "Energy transition headwinds in refining",
    "Regulatory pressure on fossil fuels",
    "Currency exposure to GBP appreciation"
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
  "tail_risk_alert": false
}
```

### 2. **Updated DebateState** (engine/debate.py)

**New TypedDict Fields:**
```python
risk_score: Optional[float]           # 0-100, how risky
key_risks: Optional[list[str]]        # Top 3-4 risks
macro_headwinds: Optional[list[str]]  # Sector/macro/regulatory risks
invalidation_conditions: Optional[list[str]]  # Thesis-breaking conditions
risk_assessment: Optional[str]        # Narrative summary
```

### 3. **Enhanced risk_manager_node** (engine/debate.py)

**Updated Prompt Incorporation:**
```
Risk Analysis (risk score: {risk_score}/100):
- Key risks: {key_risks}
- Macro headwinds: {macro_headwinds}
- Invalidation conditions: {invalidation_conditions}
- {risk_assessment}
```

**Updated Risk Level Rules:**
```
- HIGH if: risk_score > 75 OR panic_index > 60 OR bear_score > 70
- MEDIUM if: risk_score 40-70 OR conviction < 75 OR missing data
- LOW if: risk_score < 40 AND conviction > 80 AND bull_score > 70
```

**Updated Confidence Rules:**
```
- HIGH if: direction agreement AND conviction > 75 AND risk_score < 50
- LOW if: direction divergence OR conviction < 50 OR risk_score > 70
- MEDIUM: everything else
```

### 4. **Enhanced Scorer** (engine/scorer.py)

**New Scoring Logic:**
- `risk_score` from analyst now influences final `risk_level` calculation
- Risk score > 75 forces "HIGH" risk level
- Risk score 40-70 with LOW recommendation upgrades to "MEDIUM"
- Confidence downgraded if risk > 75 AND invalidation conditions exist

**New Output Fields:**
```python
{
    "risk_score": round(risk_score, 1),  # In scores dict
    "key_risks": [...],                   # Top-level signal field
    "invalidation_conditions": [...],     # Top-level signal field
    "risk_assessment": "...",             # Top-level signal field
}
```

---

## Integration with AlphaHiveSignal

The final signal now includes comprehensive risk information:

```python
AlphaHiveSignal = {
    # ... existing fields ...
    "signal": {
        "final_call": "BULLISH",
        "bullish_probability": 71,
        "risk_level": "MEDIUM",  # ← Informed by risk_score
        "confidence": "HIGH",     # ← Adjusted for risk profile
        "key_risks": [
            "Energy transition pressure",
            "Regulatory headwinds",
            "FX exposure"
        ],
        "invalidation_conditions": [
            "If oil < $50/bbl, thesis breaks",
            "If carbon tax enacted, margin compression"
        ],
        "risk_assessment": "Structural sector risks present but thesis intact...",
        "scores": {
            "risk_score": 62.0,  # ← New metric
            # ... other scores ...
        }
    },
    "explanation": {
        "line1": "Signal: 71% bullish, MEDIUM risk",
        "line2": "Key drivers: Strong fundamentals, technical alignment",
        "line3": "Risk: Watch energy transition headwinds and oil price support"
    }
}
```

---

## Key Design Decisions

### 1. **Dedicated Node, Not Integrated into Risk Manager**
- Separates risk identification from verdict synthesis
- Allows risk analyst to operate independently of debate outcome
- Enables rigorous tail-risk assessment without confirmation bias

### 2. **Risk Score as Primary Override**
- If risk_score > 75, final risk_level is always "HIGH"
- Prevents overconfident BULLISH signals from masking real risks
- Respects capital preservation principle

### 3. **Invalidation Conditions Over Generic Risks**
- Forces analyst to specify *exact* conditions that break the thesis
- Enables users to set up monitoring/alerts
- Reduces vague risk statements

### 4. **Tail Risk Alert Flag**
- Separate boolean flag for elevated black-swan risk
- Can trigger different trading logic (smaller position sizes, wider stops)
- Not directly used in risk_level (too subjective) but surfaced for user awareness

### 5. **Graph Routing**
- risk_analyst always runs (after debate convergence)
- Ensures every signal includes comprehensive risk assessment
- No early-exit before risk analysis is complete

---

## Testing

### Unit Tests (tests/test_risk_debate.py)

1. **test_risk_analyst_node_basic()** — Verifies node executes and returns valid structure
2. **test_debate_engine_with_risk_analyst()** — Full pipeline including risk analysis
3. **test_parse_json_response_with_risk_format()** — JSON parsing for risk analyst output
4. **test_parse_json_response_with_markdown_fence()** — Robust markdown handling
5. **test_risk_score_influences_risk_level()** — Risk score overrides verdict risk level

### Validation Results

```
✓ DebateState includes all risk fields
✓ risk_analyst_node creates valid output structure
✓ JSON parsing handles risk analyst response format
✓ Scorer incorporates risk_score into final signal
✓ DebateEngine routes through risk_analyst node
✓ Risk_score > 75 forces risk_level "HIGH"
✓ Confidence downgraded when risk elevated
✓ Invalidation conditions surfaced in final signal
```

---

## Integration Examples

### Example 1: Strong Bull Case with Elevated Risk
```python
debate_output = {
    "bull_score": 85,
    "bear_score": 25,
    "risk_score": 78,  # HIGH RISK despite bull case
    "invalidation_conditions": [
        "If geopolitical tension escalates, supply disruption possible",
        "If regulatory restrictions tighten, growth stalls"
    ]
}

final_signal = {
    "final_call": "BULLISH",
    "bullish_probability": 80,
    "risk_level": "HIGH",  # Upgraded from MEDIUM due to risk_score
    "confidence": "MEDIUM",  # Downgraded due to high risk
    "key_risks": [...],
    "invalidation_conditions": [...]  # User can set alerts
}
```

### Example 2: Neutral Sentiment with Macro Risks
```python
debate_output = {
    "bull_score": 55,
    "bear_score": 52,
    "risk_score": 72,
    "macro_headwinds": ["Potential interest rate hike", "FII outflow risk"],
    "invalidation_conditions": ["If Nifty50 breaks 22000 support"]
}

final_signal = {
    "final_call": "NEUTRAL",
    "bullish_probability": 50,
    "risk_level": "MEDIUM",  # Reflects elevated macro risk
    "confidence": "LOW",  # Mixed debate + significant risks
    "explanation_line3": "Risk: Monitor macro headwinds and index support levels"
}
```

---

## Limitations & Future Work

### Known Limitations
1. **LLM-dependent:** Risk assessment quality depends on Ollama model choice
2. **Latency:** Adds ~2-3 seconds per analysis (one more LLM call)
3. **Subjectivity:** Some risks require domain expertise beyond pattern matching

### Potential Enhancements (V2+)
1. **Quantitative Risk Metrics:** Add VaR, expected shortfall, correlation risk
2. **Historical Risk Tracking:** Learn which invalidation conditions actually trigger
3. **Risk Dashboard:** Visual display of key_risks and invalidation_conditions
4. **Alert System:** Automatically trigger when invalidation conditions are detected
5. **Tail-Risk Premium:** Adjust bullish_probability down if tail_risk_alert is true
6. **Scenario Analysis:** Run debate with "what-if" invalidation conditions as context

---

## Code Files Modified

| File | Changes |
|------|---------|
| `engine/debate.py` | Added risk_analyst_node, updated DebateState, updated risk_manager_node, integrated into graph routing |
| `engine/scorer.py` | Updated risk_level calculation to incorporate risk_score, added risk fields to output |
| `tests/test_risk_debate.py` | Created with 5 test cases validating risk layer |

---

## Backward Compatibility

✅ **Fully backward compatible**
- risk_score defaults to 50 if analyst unavailable
- Old debate code still works (risk fields optional in TypedDict)
- Scorer gracefully handles missing risk fields
- Frontend can ignore risk fields if not implemented yet

---

## Implementation Status

```
[x] risk_analyst_node created with comprehensive prompting
[x] DebateState updated with risk fields
[x] Debate graph integrated with risk_analyst routing
[x] risk_manager_node updated to incorporate risk analysis
[x] Scorer updated to reflect risk in final verdict
[x] DebateEngine updated to return risk fields
[x] Test suite created (5 tests, all passing)
[x] Syntax validation (no errors)
[x] Integration validation (end-to-end flow verified)
```

---

## SEBI Disclaimer

**For educational purposes only. Not investment advice.**  
AlphaHive is not SEBI-registered. All trading decisions are entirely your own.  
Risk analysis is provided for informational purposes. Always conduct your own due diligence.

---

