# AlphaHive — Week 4 Copilot Prompt Sequence
# Building the Debate Engine, Scorer, and Explainability Layer
# Run these prompts IN ORDER. One prompt = one Copilot session.
# Always tell Copilot to read AGENTS.md first in every session.

---

## What You're Building This Week

```
engine/
├── debate.py       ← PROMPT 1 (LangGraph: bull vs bear using BOTH layers)
├── scorer.py       ← PROMPT 2 (final signal: bullish%, risk, confidence)
└── explainer.py    ← PROMPT 3 (3-line plain English — the product soul)

engine/
└── orchestrator.py ← PROMPT 4 (wire debate + scorer + explainer in)

api/
└── main.py         ← PROMPT 4 (update /analyze to return full signal)

tests/
└── test_week4.py   ← PROMPT 5 (end-to-end signal verification)

BONUS:
└── PROMPT 6        (Redis caching — cache swarm results for 6 hours)
```

By end of Week 4:
- Bull and bear researchers read BOTH swarm signal AND specialist reports
- LangGraph orchestrates a structured 2-round debate
- Scorer converts debate output into Bullish%, Risk level, Confidence
- Explainer generates the 3-line plain English signal card
- Full AlphaHiveSignal from AGENTS.md is complete and returned by /analyze
- Redis caches swarm results so you don't re-run 80 agents on every request

---

## Why This Week Is The Most Important

```
Weeks 1-3 built the INPUTS.
Week 4 builds the OUTPUT — the thing users actually see.

The explainer.py is AlphaHive's soul.
"Reliance is 71% bullish. Strong fundamentals confirmed by volume breakout.
 Crowd simulation shows institutional accumulation with low retail panic."

That 3-line card is what nobody else has built.
Get this right and AlphaHive is a real product.
```

---

## The LangGraph Debate Flow

```
INPUT: orchestrator unified analysis dict (from Week 3)
       Contains: swarm signal + 4 specialist reports

       ┌─────────────────────────────────────┐
       │         DEBATE GRAPH STATE          │
       │  ticker, swarm_signal,              │
       │  specialist_reports,                │
       │  bull_case (filled by bull node)    │
       │  bear_case (filled by bear node)    │
       │  debate_round (1 or 2)              │
       │  final_verdict (filled by risk mgr) │
       └─────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
    [bull_researcher]         [bear_researcher]
    reads ALL inputs          reads ALL inputs
    builds bull case          builds bear case
    (runs in parallel)        (runs in parallel)
            │                         │
            └────────────┬────────────┘
                         ▼
                  [risk_manager]
                  reads both cases
                  makes final call
                  outputs verdict dict
                         │
                         ▼
                    OUTPUT DICT
```

---

## PROMPT 1 — Debate Engine (LangGraph)

```
Read AGENTS.md in the project root first. Focus on:
- The SYNTHESIS LAYER description in the architecture
- The AlphaHiveSignal format — specifically the "signal" section
- The LangGraph reference in the TradingAgents section

Create engine/debate.py

The DebateEngine class using LangGraph for structured state management.

This is the most architecturally important file in AlphaHive.
Bull and bear researchers each read the COMBINED output from
Week 3's orchestrator — both the swarm crowd signal AND the
4 specialist reports. They build opposing cases, then a risk manager
synthesizes a final verdict.

---

STEP 1: Define the debate state.

from typing import TypedDict, Optional

class DebateState(TypedDict):
    # Input (set before graph runs)
    ticker: str
    company: str
    sector: str
    swarm_signal: dict          # from SwarmAggregator
    specialist_reports: dict    # fundamental, technical, sentiment, news
    market_data: dict           # raw price/indicator data
    
    # Set by bull_researcher node
    bull_case: Optional[str]
    bull_score: Optional[float]  # 0-100, how strong is the bull case
    
    # Set by bear_researcher node
    bear_case: Optional[str]
    bear_score: Optional[float]  # 0-100, how strong is the bear case
    
    # Set by risk_manager node
    final_verdict: Optional[dict]

---

STEP 2: Define the three node functions.

async def bull_researcher_node(state: DebateState) -> DebateState:
  """
  Reads all available data and builds the strongest possible bull case.
  Does NOT cherry-pick — must acknowledge key risks even in bull case.
  """
  
  # Build a comprehensive data summary for the prompt
  data_summary = _build_data_summary(state)
  
  system_prompt = """You are a bullish equity research analyst covering Indian markets.
Your job is to build the strongest possible bull case for a stock using 
all available data — crowd behavior simulation AND fundamental/technical analysis.
You must be specific and data-driven. Reference actual numbers.
You must acknowledge the top 1-2 risks even in your bull case (this makes it credible).
Respond in valid JSON only."""

  user_prompt = f"""Build the bull case for {state['ticker']} ({state['company']}, {state['sector']} sector).

CROWD SIMULATION RESULTS:
- Swarm bullish: {state['swarm_signal']['bullish_pct']:.1f}%
- Panic index: {state['swarm_signal']['panic_index']:.1f} (low=calm, high=panic)
- FOMO index: {state['swarm_signal']['fomo_index']:.1f}
- Conviction: {state['swarm_signal']['conviction']:.1f}%
- Crowd narrative: {state['swarm_signal'].get('crowd_narrative', 'N/A')}
- Institutional agents: {state['swarm_signal'].get('institutional_bullish_pct', 'N/A')}% bullish

FUNDAMENTAL ANALYSIS:
- Score: {state['specialist_reports']['fundamental']['score']}/100
- Verdict: {state['specialist_reports']['fundamental']['verdict']}
- Summary: {state['specialist_reports']['fundamental']['summary']}
- Key positives: {state['specialist_reports']['fundamental'].get('key_positives', [])}

TECHNICAL ANALYSIS:
- Score: {state['specialist_reports']['technical']['score']}/100
- Verdict: {state['specialist_reports']['technical']['verdict']}
- Summary: {state['specialist_reports']['technical']['summary']}
- Key signals: {state['specialist_reports']['technical'].get('key_signals', [])}

SENTIMENT ANALYSIS:
- Score: {state['specialist_reports']['sentiment']['score']}/100
- Verdict: {state['specialist_reports']['sentiment']['verdict']}
- Summary: {state['specialist_reports']['sentiment']['summary']}

NEWS ANALYSIS:
- Score: {state['specialist_reports']['news']['score']}/100
- Alert: {state['specialist_reports']['news'].get('alert', 'None')}
- Summary: {state['specialist_reports']['news']['summary']}

Return JSON:
{{
  "bull_case": "3-4 sentence bull argument using specific data points above",
  "bull_score": integer 0-100 (how strong is this bull case given the data),
  "top_bull_reasons": ["reason 1", "reason 2", "reason 3"],
  "acknowledged_risks": ["risk 1", "risk 2"]
}}"""

  response = await _call_ollama_specialist(system_prompt, user_prompt)
  parsed = _parse_json_response(response)
  
  state["bull_case"] = parsed.get("bull_case", "Bull case unavailable")
  state["bull_score"] = float(parsed.get("bull_score", 50))
  state["bull_reasons"] = parsed.get("top_bull_reasons", [])
  state["bull_acknowledged_risks"] = parsed.get("acknowledged_risks", [])
  return state


async def bear_researcher_node(state: DebateState) -> DebateState:
  """
  Builds the strongest possible bear case from the same data.
  Must acknowledge bull signals even in bear case.
  """
  
  system_prompt = """You are a bearish equity research analyst and short-seller covering Indian markets.
Your job is to find all the reasons why a stock could underperform or decline.
You are skeptical, risk-aware, and look for what the bulls are missing.
You must reference actual numbers from the data provided.
You must acknowledge the top 1-2 bull signals even in your bear case.
Respond in valid JSON only."""

  user_prompt = f"""Build the bear case for {state['ticker']} ({state['company']}, {state['sector']} sector).

[SAME DATA BLOCK AS BULL RESEARCHER — copy same format]
{_build_data_summary(state)}

Return JSON:
{{
  "bear_case": "3-4 sentence bear argument using specific data points",
  "bear_score": integer 0-100 (how strong is this bear case given the data),
  "top_bear_reasons": ["reason 1", "reason 2", "reason 3"],
  "acknowledged_bull_signals": ["signal 1", "signal 2"]
}}"""

  response = await _call_ollama_specialist(system_prompt, user_prompt)
  parsed = _parse_json_response(response)
  
  state["bear_case"] = parsed.get("bear_case", "Bear case unavailable")
  state["bear_score"] = float(parsed.get("bear_score", 50))
  state["bear_reasons"] = parsed.get("top_bear_reasons", [])
  state["bear_acknowledged_bull"] = parsed.get("acknowledged_bull_signals", [])
  return state


async def risk_manager_node(state: DebateState) -> DebateState:
  """
  Reads both cases and makes the final risk-adjusted call.
  This is the most important node — it synthesizes everything.
  """
  
  system_prompt = """You are a senior risk manager at an equity research firm.
You have read both the bull and bear cases for a stock.
Your job is to make a final, balanced, risk-adjusted verdict.
You weight evidence by quality, not by whoever argued louder.
You are especially attuned to downside risks — protecting capital matters.
Respond in valid JSON only. Be decisive."""

  user_prompt = f"""Make the final verdict for {state['ticker']}.

BULL CASE (score: {state.get('bull_score', 50)}/100):
{state.get('bull_case', 'N/A')}
Top bull reasons: {state.get('bull_reasons', [])}

BEAR CASE (score: {state.get('bear_score', 50)}/100):
{state.get('bear_case', 'N/A')}
Top bear reasons: {state.get('bear_reasons', [])}

CROWD SIGNAL: {state['swarm_signal']['dominant_signal']} 
(conviction: {state['swarm_signal']['conviction']:.0f}%, 
panic: {state['swarm_signal']['panic_index']:.0f})

HIGH PRIORITY ALERT: {state['specialist_reports']['news'].get('alert', 'None')}

Return JSON:
{{
  "final_call": "BULLISH" | "BEARISH" | "NEUTRAL",
  "bullish_probability": integer 0-100,
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "deciding_factor": "one sentence — what tipped the verdict this way",
  "key_risk": "the single most important risk to monitor",
  "verdict_reasoning": "2-3 sentences explaining the final call"
}}

Risk level rules you must follow:
- HIGH if: panic_index > 60 OR bear_case_score > 70 OR high priority alert present
- LOW if: conviction > 80 AND bull_score > 70 AND panic_index < 20
- MEDIUM: everything else

Confidence rules:
- HIGH if: swarm and specialists AGREE on direction AND conviction > 75
- LOW if: swarm and specialists DIVERGE OR conviction < 50
- MEDIUM: everything else"""

  response = await _call_ollama_specialist(system_prompt, user_prompt)
  parsed = _parse_json_response(response)
  
  state["final_verdict"] = {
    "final_call": parsed.get("final_call", "NEUTRAL"),
    "bullish_probability": int(parsed.get("bullish_probability", 50)),
    "risk_level": parsed.get("risk_level", "MEDIUM"),
    "confidence": parsed.get("confidence", "MEDIUM"),
    "deciding_factor": parsed.get("deciding_factor", ""),
    "key_risk": parsed.get("key_risk", ""),
    "verdict_reasoning": parsed.get("verdict_reasoning", ""),
    "bull_score": state.get("bull_score", 50),
    "bear_score": state.get("bear_score", 50),
  }
  return state

---

STEP 3: Build the LangGraph graph.

from langgraph.graph import StateGraph, END

def build_debate_graph():
  graph = StateGraph(DebateState)
  
  # Add nodes
  graph.add_node("bull_researcher", bull_researcher_node)
  graph.add_node("bear_researcher", bear_researcher_node)
  graph.add_node("risk_manager", risk_manager_node)
  
  # Bull and bear run in parallel from START
  graph.set_entry_point("bull_researcher")  
  # NOTE: LangGraph doesn't natively parallelize two entry nodes.
  # Solution: run bull and bear as asyncio tasks BEFORE the graph,
  # then pass results into a single risk_manager call.
  # See DebateEngine.run() below for the correct implementation.
  
  graph.add_edge("bull_researcher", "risk_manager")
  graph.add_edge("risk_manager", END)
  
  return graph.compile()

---

STEP 4: The DebateEngine class.

class DebateEngine:

  def __init__(self):
    self.graph = build_debate_graph()

  async def run(self, orchestrator_output: dict) -> dict:
    """
    Main entry point. Takes Week 3 orchestrator output,
    runs the debate, returns complete debate results.
    """
    
    # Build initial state from orchestrator output
    state = DebateState(
      ticker=orchestrator_output["ticker"],
      company=orchestrator_output.get("company", ""),
      sector=orchestrator_output.get("sector", ""),
      swarm_signal=orchestrator_output["swarm"],
      specialist_reports=orchestrator_output["specialists"],
      market_data=orchestrator_output.get("market_data", {}),
      bull_case=None,
      bull_score=None,
      bear_case=None,
      bear_score=None,
      final_verdict=None,
    )
    
    # Run bull and bear IN PARALLEL (asyncio, not LangGraph parallel)
    # This is faster than sequential and both only need the same input
    import asyncio
    bull_task = asyncio.create_task(bull_researcher_node(state.copy()))
    bear_task = asyncio.create_task(bear_researcher_node(state.copy()))
    
    bull_result, bear_result = await asyncio.gather(
      bull_task, bear_task, return_exceptions=True
    )
    
    # Merge results into state
    if not isinstance(bull_result, Exception):
      state.update({
        "bull_case": bull_result.get("bull_case"),
        "bull_score": bull_result.get("bull_score"),
        "bull_reasons": bull_result.get("bull_reasons", []),
        "bull_acknowledged_risks": bull_result.get("bull_acknowledged_risks", []),
      })
    else:
      state["bull_case"] = "Bull case failed"
      state["bull_score"] = 50.0

    if not isinstance(bear_result, Exception):
      state.update({
        "bear_case": bear_result.get("bear_case"),
        "bear_score": bear_result.get("bear_score"),
        "bear_reasons": bear_result.get("bear_reasons", []),
        "bear_acknowledged_bull": bear_result.get("bear_acknowledged_bull", []),
      })
    else:
      state["bear_case"] = "Bear case failed"
      state["bear_score"] = 50.0
    
    # Run risk manager (needs both cases complete)
    final_state = await risk_manager_node(state)
    
    return {
      "ticker": state["ticker"],
      "bull_case": state.get("bull_case"),
      "bull_score": state.get("bull_score"),
      "bull_reasons": state.get("bull_reasons", []),
      "bull_acknowledged_risks": state.get("bull_acknowledged_risks", []),
      "bear_case": state.get("bear_case"),
      "bear_score": state.get("bear_score"),
      "bear_reasons": state.get("bear_reasons", []),
      "bear_acknowledged_bull": state.get("bear_acknowledged_bull", []),
      "final_verdict": final_state.get("final_verdict"),
    }

---

HELPER FUNCTIONS (add at module level):

def _build_data_summary(state: DebateState) -> str:
  """Formats all data into a clean readable block for prompts."""
  # Format swarm signal + all 4 specialist summaries into one string
  # Keep it under 600 words — LLM context efficiency

async def _call_ollama_specialist(system: str, user: str) -> str:
  """Calls Ollama with llama3.1:8b. 60s timeout. Returns response text."""
  # Same pattern as BaseAgent._call_ollama but uses SPECIALIST model
  # temperature=0.4 for debate agents (more focused than personality agents)

def _parse_json_response(text: str) -> dict:
  """
  Safely parse LLM JSON response.
  Strip markdown fences if present: ```json ... ```
  Try json.loads first.
  If fails: return empty dict (caller handles fallback).
  Never crash.
  """
```

---

## PROMPT 2 — Scorer

```
Read AGENTS.md in the project root first. Focus on the "signal" section
of the AlphaHiveSignal output format.

Create engine/scorer.py

The Scorer class. Takes the complete debate output + orchestrator output
and computes the final numerical signal. This is DETERMINISTIC — no LLM.
All logic is rule-based so the output is consistent and explainable.

class Scorer:

  def compute(self, debate_output: dict, orchestrator_output: dict) -> dict:
    """
    Computes the final AlphaHive signal from debate + orchestrator outputs.
    Returns the "signal" section of AlphaHiveSignal.
    """
    
    verdict = debate_output.get("final_verdict", {})
    swarm = orchestrator_output.get("swarm", {})
    specialists = orchestrator_output.get("specialists", {})
    
    # --- BULLISH PROBABILITY ---
    # Start with the risk manager's stated probability
    base_prob = verdict.get("bullish_probability", 50)
    
    # Adjust based on agreement between layers
    agreement = orchestrator_output.get("signal_preview", {}).get("agreement", "NEUTRAL")
    
    if "STRONG_AGREEMENT_BULLISH" in agreement:
      base_prob = min(95, base_prob + 8)
    elif "STRONG_AGREEMENT_BEARISH" in agreement:
      base_prob = max(5, base_prob - 8)
    elif "DIVERGENCE" in agreement:
      # Pull toward 50 when layers disagree
      base_prob = base_prob * 0.85 + 50 * 0.15
    
    # Cap extremes — never say 100% or 0% (markets are uncertain)
    bullish_probability = round(max(5, min(95, base_prob)))
    
    # --- RISK LEVEL ---
    # Start with risk manager verdict, validate against metrics
    risk_level = verdict.get("risk_level", "MEDIUM")
    
    # Override rules (hard rules that always apply)
    if orchestrator_output.get("signal_preview", {}).get("alert"):
      # Any high-priority alert = at least MEDIUM risk
      if risk_level == "LOW":
        risk_level = "MEDIUM"
    
    if swarm.get("panic_index", 0) > 70:
      risk_level = "HIGH"  # Widespread panic = always high risk
    
    if swarm.get("conviction", 100) < 40:
      # Low conviction swarm = uncertain = at least MEDIUM
      if risk_level == "LOW":
        risk_level = "MEDIUM"
    
    # --- CONFIDENCE ---
    confidence = verdict.get("confidence", "MEDIUM")
    
    # Downgrade confidence if specialist data was missing
    specialist_errors = sum(
      1 for name in ["fundamental", "technical", "sentiment", "news"]
      if "error" in specialists.get(name, {})
    )
    if specialist_errors >= 2:
      confidence = "LOW"  # Too much data missing to be confident
    
    # --- FINAL CALL ---
    # Derive from bullish_probability (not from LLM verdict directly)
    # This ensures consistency: the call always matches the probability
    if bullish_probability >= 60:
      final_call = "BULLISH"
    elif bullish_probability <= 40:
      final_call = "BEARISH"
    else:
      final_call = "NEUTRAL"
    
    # --- SCORES BREAKDOWN ---
    scores = {
      "swarm_bullish_pct": round(swarm.get("bullish_pct", 50), 1),
      "fundamental_score": specialists.get("fundamental", {}).get("score", 50),
      "technical_score": specialists.get("technical", {}).get("score", 50),
      "sentiment_score": specialists.get("sentiment", {}).get("score", 50),
      "news_score": specialists.get("news", {}).get("score", 50),
      "combined_specialist_score": round(specialists.get("combined_score", 50), 1),
      "bull_case_score": round(debate_output.get("bull_score", 50), 1),
      "bear_case_score": round(debate_output.get("bear_score", 50), 1),
    }
    
    return {
      "final_call": final_call,
      "bullish_probability": bullish_probability,
      "risk_level": risk_level,
      "confidence": confidence,
      "deciding_factor": verdict.get("deciding_factor", ""),
      "key_risk": verdict.get("key_risk", ""),
      "scores": scores,
      "agreement_type": agreement,
    }
```

---

## PROMPT 3 — Explainer (The Product Soul)

```
Read AGENTS.md in the project root first. Focus on:
- The explainability layer description in the architecture
- The "explanation" section of AlphaHiveSignal format
- This file is what users actually read. Every word matters.

Create engine/explainer.py

The Explainer class. Converts the complete analysis into the 3-line
plain English signal card that is AlphaHive's product differentiator.

THIS FILE DOES NOT CALL OLLAMA.
The explainer is 100% deterministic string templates.
Reason: LLM-generated explanations can hallucinate specific numbers.
The template approach guarantees every number in the explanation
is real and traceable to an actual data source.

class Explainer:

  def generate(self,
               ticker: str,
               scorer_output: dict,
               debate_output: dict,
               orchestrator_output: dict) -> dict:
    """
    Generates the 3-line explanation for any AlphaHive signal.
    Returns the "explanation" section of AlphaHiveSignal.
    """
    
    signal = scorer_output
    swarm = orchestrator_output["swarm"]
    specs = orchestrator_output["specialists"]
    
    line1 = self._generate_line1(ticker, signal, orchestrator_output)
    line2 = self._generate_line2(signal, specs, debate_output)
    line3 = self._generate_line3(swarm, signal)
    
    return {
      "line1": line1,
      "line2": line2,
      "line3": line3,
      "full_text": f"{line1} {line2} {line3}",
      "bull_case": debate_output.get("bull_case", ""),
      "bear_case": debate_output.get("bear_case", ""),
      "deciding_factor": signal.get("deciding_factor", ""),
    }

  def _generate_line1(self, ticker: str, signal: dict,
                       orchestrator_output: dict) -> str:
    """
    Line 1: The headline — what is the verdict and how strong.
    Format: "{Company} is {prob}% bullish with {confidence} conviction."
    OR: "{Company} shows bearish signals at {prob}% with {risk} risk."
    """
    company = orchestrator_output.get("company", ticker.replace(".NS", ""))
    prob = signal["bullish_probability"]
    call = signal["final_call"]
    conf = signal["confidence"]
    risk = signal["risk_level"]
    
    if call == "BULLISH":
      conf_phrase = {
        "HIGH": "high conviction",
        "MEDIUM": "moderate conviction",
        "LOW": "low conviction — use caution"
      }[conf]
      return f"{company} is {prob}% bullish with {conf_phrase}."
    
    elif call == "BEARISH":
      bear_prob = 100 - prob
      risk_phrase = {
        "HIGH": "elevated risk",
        "MEDIUM": "moderate risk",
        "LOW": "manageable risk"
      }[risk]
      return f"{company} shows bearish signals at {bear_prob}% with {risk_phrase}."
    
    else:  # NEUTRAL
      return (f"{company} shows mixed signals at {prob}% bullish. "
              f"No clear directional edge currently.")

  def _generate_line2(self, signal: dict, specs: dict,
                       debate_output: dict) -> str:
    """
    Line 2: The facts — what the specialist data shows.
    References actual numbers from fundamental and technical reports.
    """
    fund = specs.get("fundamental", {})
    tech = specs.get("technical", {})
    sent = specs.get("sentiment", {})
    
    # Collect the strongest signals to mention
    mentions = []
    
    # Fundamental signals
    derived = fund.get("derived", {})
    if derived.get("pe_vs_sector") == "cheap":
      mentions.append("PE below sector average")
    elif derived.get("pe_vs_sector") == "expensive":
      mentions.append("PE above sector average")
    
    if derived.get("earnings_trend") == "improving":
      eps_growth = fund.get("raw_data", {}).get("eps_growth_yoy")
      if eps_growth:
        mentions.append(f"EPS +{eps_growth:.0f}% YoY")
      else:
        mentions.append("improving earnings trend")
    elif derived.get("earnings_trend") == "declining":
      mentions.append("declining earnings trend")
    
    # Technical signals
    indicators = tech.get("indicators", {})
    rsi = indicators.get("rsi_14")
    if rsi:
      if rsi < 30:
        mentions.append(f"RSI {rsi:.0f} (oversold territory)")
      elif rsi > 70:
        mentions.append(f"RSI {rsi:.0f} (overbought — watch carefully)")
      elif 45 <= rsi <= 65:
        mentions.append(f"RSI {rsi:.0f} (healthy momentum zone)")
    
    trend = indicators.get("trend_structure")
    if trend == "uptrend":
      mentions.append("price in confirmed uptrend")
    elif trend == "downtrend":
      mentions.append("price in downtrend structure")
    
    vol_ratio = indicators.get("volume_ratio")
    if vol_ratio and vol_ratio > 1.5:
      mentions.append(f"volume {vol_ratio:.1f}x above average")
    
    golden = indicators.get("golden_cross")
    death = indicators.get("death_cross")
    if golden:
      mentions.append("golden cross recently formed")
    elif death:
      mentions.append("death cross recently formed — bearish signal")
    
    # Sentiment
    sent_verdict = sent.get("verdict")
    if sent_verdict == "POSITIVE":
      mentions.append("positive news sentiment")
    elif sent_verdict == "NEGATIVE":
      mentions.append("negative news sentiment")
    
    # Also include the deciding factor from debate
    deciding = signal.get("deciding_factor")
    
    # Build the line
    if mentions:
      # Take top 3 most relevant
      top_mentions = mentions[:3]
      facts_str = ", ".join(top_mentions) + "."
      if deciding:
        return f"Key factors: {facts_str} {deciding}"
      return f"Key factors: {facts_str}"
    else:
      # Fallback to specialist summaries
      if fund.get("summary"):
        return f"Fundamentals: {fund['summary']}"
      return "Specialist analysis completed. See full report for details."

  def _generate_line3(self, swarm: dict, signal: dict) -> str:
    """
    Line 3: The crowd — what the swarm simulation shows.
    This is AlphaHive's unique differentiator. Always reference specific numbers.
    """
    bullish_pct = swarm.get("bullish_pct", 50)
    panic = swarm.get("panic_index", 0)
    fomo = swarm.get("fomo_index", 0)
    conviction = swarm.get("conviction", 50)
    crowd_narrative = swarm.get("crowd_narrative", "")
    
    # Build crowd description from metrics
    
    # Panic description
    if panic > 60:
      panic_phrase = f"Retail panic elevated at {panic:.0f}% — crowd fear is high."
    elif panic > 35:
      panic_phrase = f"Moderate retail panic at {panic:.0f}%."
    else:
      panic_phrase = f"Retail panic low at {panic:.0f}% — crowd is calm."
    
    # FOMO description  
    if fomo > 60:
      fomo_phrase = f"FOMO buying strong at {fomo:.0f}% — momentum chasers active."
    elif fomo > 35:
      fomo_phrase = ""  # medium FOMO isn't noteworthy
    else:
      fomo_phrase = ""
    
    # Conviction description
    if conviction > 80:
      conv_phrase = f"High crowd conviction ({conviction:.0f}%)."
    elif conviction < 40:
      conv_phrase = f"Low crowd conviction ({conviction:.0f}%) — uncertain signal."
    else:
      conv_phrase = ""
    
    # Divergence check — most interesting case
    agreement = signal.get("agreement_type", "")
    if "DIVERGENCE" in agreement:
      if "SWARM_BULLISH" in agreement:
        return (f"Crowd simulation shows {bullish_pct:.0f}% bullish "
                f"but specialist data is cautious — divergence detected. "
                f"{panic_phrase} Verify before acting.")
      else:
        return (f"Crowd simulation cautious at {bullish_pct:.0f}% bullish "
                f"but specialist data is positive — divergence detected. "
                f"Fundamentals may not yet be reflected in crowd behavior.")
    
    # Standard crowd narrative
    parts = [
      f"Crowd simulation: {bullish_pct:.0f}% of market participants bullish.",
      panic_phrase,
      fomo_phrase,
      conv_phrase,
    ]
    
    # Use the swarm aggregator's narrative if it's good
    if crowd_narrative and len(crowd_narrative) > 20:
      parts.append(crowd_narrative)
    
    return " ".join(p for p in parts if p).strip()
```

---

## PROMPT 4 — Wire Everything Into Orchestrator + API

```
Read AGENTS.md in the project root first.

Update two files: engine/orchestrator.py and api/main.py

PART A: Update engine/orchestrator.py

Import the new engines:
  from engine.debate import DebateEngine
  from engine.scorer import Scorer
  from engine.explainer import Explainer

Add to AlphaHiveOrchestrator.__init__:
  self.debate_engine = DebateEngine()
  self.scorer = Scorer()
  self.explainer = Explainer()

Update the analyze() method to run the full pipeline:

async def analyze(self, ticker: str) -> dict:
  
  # STEP 1: Run swarm + specialists (Week 3 code, unchanged)
  orchestrator_output = await self._run_parallel_analysis(ticker)
  # (rename old analyze body to _run_parallel_analysis)
  
  # STEP 2: Run debate engine on the combined output
  debate_output = await self.debate_engine.run(orchestrator_output)
  
  # STEP 3: Score the debate output
  signal = self.scorer.compute(debate_output, orchestrator_output)
  
  # STEP 4: Generate plain English explanation
  explanation = self.explainer.generate(
    ticker=ticker,
    scorer_output=signal,
    debate_output=debate_output,
    orchestrator_output=orchestrator_output
  )
  
  # STEP 5: Build complete AlphaHiveSignal (exact format from AGENTS.md)
  from datetime import datetime, timezone
  
  complete_signal = {
    # Identity
    "ticker": ticker,
    "company": orchestrator_output.get("company", ticker),
    "sector": orchestrator_output.get("sector", "Unknown"),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "elapsed_seconds": orchestrator_output.get("elapsed_seconds", 0),
    
    # Layer 1: Swarm
    "swarm": orchestrator_output["swarm"],
    
    # Layer 2: Specialists
    "specialists": {
      "fundamental_score": orchestrator_output["specialists"]["fundamental"]["score"],
      "technical_score": orchestrator_output["specialists"]["technical"]["score"],
      "sentiment_score": orchestrator_output["specialists"]["sentiment"]["score"],
      "news_score": orchestrator_output["specialists"]["news"]["score"],
      "fundamental_summary": orchestrator_output["specialists"]["fundamental"]["summary"],
      "technical_summary": orchestrator_output["specialists"]["technical"]["summary"],
      "sentiment_summary": orchestrator_output["specialists"]["sentiment"]["summary"],
      "news_summary": orchestrator_output["specialists"]["news"]["summary"],
    },
    
    # Debate
    "debate": {
      "bull_case": debate_output["bull_case"],
      "bear_case": debate_output["bear_case"],
      "bull_score": debate_output["bull_score"],
      "bear_score": debate_output["bear_score"],
      "bull_reasons": debate_output.get("bull_reasons", []),
      "bear_reasons": debate_output.get("bear_reasons", []),
    },
    
    # Final Signal
    "signal": signal,
    
    # Plain English Explanation
    "explanation": explanation,
    
    # MANDATORY disclaimer
    "disclaimer": (
      "For educational purposes only. Not investment advice. "
      "AlphaHive is not SEBI-registered. "
      "All trading decisions are entirely your own."
    ),
  }
  
  # STEP 6: Store in PostgreSQL (async, don't await — fire and forget)
  asyncio.create_task(self._store_signal(complete_signal))
  
  return complete_signal

async def _store_signal(self, signal: dict):
  """Persist complete signal to PostgreSQL signals table."""
  # Use api/database.py session
  # Store raw_signal_json as the full dict
  # Handle DB errors silently — storage failure should never crash analysis
  pass  # implement using SQLAlchemy async session

PART B: Update api/main.py

The /analyze endpoint already calls orchestrator.analyze(ticker).
Now it returns the complete AlphaHiveSignal — no changes needed there.

Add one new endpoint:

GET /stock/{ticker}/debate
  Returns the bull case and bear case for a stock's latest signal.
  Fetches from PostgreSQL signals table (raw_signal_json → debate section).
  Used by the frontend DebateViewer component.
  
  Response:
  {
    "ticker": ticker,
    "bull_case": str,
    "bear_case": str,
    "bull_score": float,
    "bear_score": float,
    "bull_reasons": list,
    "bear_reasons": list,
    "timestamp": str
  }
```

---

## PROMPT 5 — Week 4 Verification

```
Read AGENTS.md in the project root first.

Create tests/test_week4.py

CHECK 1: Debate engine produces bull and bear cases
  from engine.debate import DebateEngine
  
  # Create mock orchestrator output (use structure from AGENTS.md)
  mock_output = {
    "ticker": "RELIANCE.NS",
    "company": "Reliance Industries",
    "sector": "Energy",
    "swarm": {
      "bullish_pct": 68.5,
      "bearish_pct": 21.0,
      "hold_pct": 10.5,
      "panic_index": 18.3,
      "fomo_index": 31.7,
      "conviction": 82.4,
      "dominant_signal": "BULLISH",
      "signal_strength": "STRONG",
      "crowd_narrative": "Institutional accumulation dominating retail behavior."
    },
    "specialists": {
      "fundamental": {"score": 72, "verdict": "STRONG",
                       "summary": "PE below sector, EPS +12% YoY",
                       "key_positives": ["PE 22x vs sector 28x", "EPS growth"],
                       "derived": {"pe_vs_sector": "cheap",
                                   "earnings_trend": "improving",
                                   "debt_health": "low",
                                   "promoter_confidence": "high"},
                       "raw_data": {"eps_growth_yoy": 12.3}},
      "technical": {"score": 68, "verdict": "BULLISH",
                     "summary": "Price above all EMAs, volume breakout",
                     "key_signals": ["golden cross", "volume 1.8x avg"],
                     "indicators": {"rsi_14": 58.2, "ema_50": 2800,
                                    "ema_200": 2650, "trend_structure": "uptrend",
                                    "volume_ratio": 1.82, "golden_cross": True,
                                    "death_cross": False}},
      "sentiment": {"score": 63, "verdict": "POSITIVE",
                     "summary": "Positive earnings coverage, low fear words",
                     "net_sentiment": 0.26, "fear_index": 18.5},
      "news": {"score": 58, "verdict": "NEUTRAL",
                "summary": "No material negative events",
                "alert": None,
                "bullish_events": 2, "bearish_events": 0},
      "combined_score": 65.25
    },
    "signal_preview": {
      "swarm_call": "BULLISH",
      "specialist_score": 65.25,
      "agreement": "STRONG_AGREEMENT_BULLISH",
      "alert": None
    }
  }
  
  engine = DebateEngine()
  result = await engine.run(mock_output)
  
  assert result["bull_case"] is not None
  assert result["bear_case"] is not None
  assert result["final_verdict"] is not None
  assert result["final_verdict"]["final_call"] in ["BULLISH", "BEARISH", "NEUTRAL"]
  assert 0 <= result["final_verdict"]["bullish_probability"] <= 100
  assert result["final_verdict"]["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
  
  print(f"✓ CHECK 1 PASSED")
  print(f"  Bull score: {result['bull_score']}")
  print(f"  Bear score: {result['bear_score']}")
  print(f"  Final call: {result['final_verdict']['final_call']}")
  print(f"  Bullish probability: {result['final_verdict']['bullish_probability']}%")
  print(f"  Deciding factor: {result['final_verdict']['deciding_factor']}")

CHECK 2: Scorer produces valid signal
  from engine.scorer import Scorer
  scorer = Scorer()
  signal = scorer.compute(result, mock_output)
  
  assert signal["final_call"] in ["BULLISH", "BEARISH", "NEUTRAL"]
  assert 5 <= signal["bullish_probability"] <= 95
  assert signal["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
  assert signal["confidence"] in ["LOW", "MEDIUM", "HIGH"]
  assert "scores" in signal
  
  print(f"✓ CHECK 2 PASSED")
  print(f"  Final call: {signal['final_call']}")
  print(f"  Bullish probability: {signal['bullish_probability']}%")
  print(f"  Risk: {signal['risk_level']}, Confidence: {signal['confidence']}")
  print(f"  Agreement: {signal['agreement_type']}")

CHECK 3: Explainer generates 3-line human-readable output
  from engine.explainer import Explainer
  explainer = Explainer()
  explanation = explainer.generate(
    ticker="RELIANCE.NS",
    scorer_output=signal,
    debate_output=result,
    orchestrator_output=mock_output
  )
  
  assert explanation["line1"] and len(explanation["line1"]) > 20
  assert explanation["line2"] and len(explanation["line2"]) > 20
  assert explanation["line3"] and len(explanation["line3"]) > 20
  assert "%" in explanation["line1"]  # Must reference actual numbers
  
  print(f"✓ CHECK 3 PASSED — Explanation generated")
  print(f"\n  LINE 1: {explanation['line1']}")
  print(f"  LINE 2: {explanation['line2']}")
  print(f"  LINE 3: {explanation['line3']}")

CHECK 4: Full live pipeline returns complete AlphaHiveSignal
  import httpx
  async with httpx.AsyncClient() as client:
    resp = await client.post(
      "http://localhost:8000/analyze",
      json={"ticker": "RELIANCE.NS"},
      timeout=180.0   # full pipeline needs more time
    )
  
  assert resp.status_code == 200
  data = resp.json()
  
  # Verify complete AlphaHiveSignal structure
  required_keys = ["ticker", "swarm", "specialists", "debate",
                   "signal", "explanation", "disclaimer"]
  for key in required_keys:
    assert key in data, f"Missing key: {key}"
  
  assert data["signal"]["final_call"] in ["BULLISH", "BEARISH", "NEUTRAL"]
  assert data["explanation"]["line1"] != ""
  assert data["disclaimer"] != ""
  
  print(f"✓ CHECK 4 PASSED — Complete AlphaHiveSignal from API")
  print(f"\n  SIGNAL CARD FOR {data['ticker']}:")
  print(f"  ─────────────────────────────────────")
  print(f"  {data['explanation']['line1']}")
  print(f"  {data['explanation']['line2']}")
  print(f"  {data['explanation']['line3']}")
  print(f"  ─────────────────────────────────────")
  print(f"  Call: {data['signal']['final_call']} | "
        f"Risk: {data['signal']['risk_level']} | "
        f"Confidence: {data['signal']['confidence']}")

Print final summary:
  print("\n=== WEEK 4 COMPLETE ===")
  print("Bull vs Bear debate engine (LangGraph): ✓")
  print("Scorer (deterministic signal): ✓")
  print("Explainer (3-line plain English): ✓")
  print("Complete AlphaHiveSignal from API: ✓")
  print("\nAlphaHive is now a working intelligence product.")
  print("Ready for Week 5: Frontend Dashboard")
```

---

## PROMPT 6 — Redis Caching (Performance Layer)

```
Read AGENTS.md in the project root. Focus on:
- Redis in the tech stack section
- The performance notes about re-running 80 agents

The swarm takes 60-90 seconds to run 80 agents.
Running it fresh for every /analyze request is impractical for a dashboard.
Solution: cache swarm results in Redis for 6 hours.
Indian market sessions are 9:15 AM - 3:30 PM IST.
One morning run + one afternoon run covers the full session.

Create engine/cache.py

class SignalCache:

  def __init__(self):
    import redis.asyncio as aioredis
    self.redis = aioredis.from_url(
      os.getenv("REDIS_URL", "redis://localhost:6379"),
      encoding="utf-8",
      decode_responses=True
    )
    self.SWARM_TTL = 6 * 60 * 60      # 6 hours in seconds
    self.SIGNAL_TTL = 1 * 60 * 60     # 1 hour for full signals
  
  async def get_swarm(self, ticker: str) -> dict | None:
    """Get cached swarm result. Returns None if not cached."""
    key = f"swarm:{ticker}"
    data = await self.redis.get(key)
    if data:
      import json
      return json.loads(data)
    return None
  
  async def set_swarm(self, ticker: str, swarm_result: dict):
    """Cache swarm result for 6 hours."""
    import json
    key = f"swarm:{ticker}"
    await self.redis.set(key, json.dumps(swarm_result), ex=self.SWARM_TTL)
  
  async def get_signal(self, ticker: str) -> dict | None:
    """Get full cached AlphaHiveSignal."""
    key = f"signal:{ticker}"
    data = await self.redis.get(key)
    if data:
      import json
      return json.loads(data)
    return None
  
  async def set_signal(self, ticker: str, signal: dict):
    """Cache full signal for 1 hour."""
    import json
    key = f"signal:{ticker}"
    await self.redis.set(key, json.dumps(signal), ex=self.SIGNAL_TTL)
  
  async def invalidate(self, ticker: str):
    """Force refresh — delete both cached values for a ticker."""
    await self.redis.delete(f"swarm:{ticker}")
    await self.redis.delete(f"signal:{ticker}")
  
  async def health(self) -> bool:
    """Check Redis connection."""
    try:
      await self.redis.ping()
      return True
    except:
      return False

Now update engine/orchestrator.py to use the cache:

In AlphaHiveOrchestrator.__init__:
  self.cache = SignalCache()

In AlphaHiveOrchestrator._run_swarm():
  # Check cache first
  cached = await self.cache.get_swarm(ticker)
  if cached:
    log.info(f"Swarm cache HIT for {ticker}")
    return cached
  
  # Cache miss — run the full swarm
  runner_output = await self.swarm_runner.run(ticker)
  swarm_signal = self.swarm_aggregator.compute(runner_output)
  
  # Store in cache
  await self.cache.set_swarm(ticker, swarm_signal)
  return swarm_signal

In AlphaHiveOrchestrator.analyze():
  # Check full signal cache first (fastest path)
  cached_signal = await self.cache.get_signal(ticker)
  if cached_signal:
    log.info(f"Signal cache HIT for {ticker}")
    return cached_signal
  
  # [rest of analysis runs normally]
  
  # Store complete signal in cache after computing
  await self.cache.set_signal(ticker, complete_signal)

Add to api/main.py:
  GET /cache/invalidate/{ticker}
    Clears cached signal for a ticker (force fresh analysis).
    Useful for: after earnings, after major news event.
    Response: { "status": "cleared", "ticker": ticker }
  
  GET /cache/status
    Returns: { "redis": "connected" | "disconnected",
               "cached_tickers": list of currently cached tickers }
```

---

## Week 4 End Checklist

```
[ ] Bull researcher reads BOTH swarm signal AND specialist reports
[ ] Bear researcher reads BOTH swarm signal AND specialist reports
[ ] Bull and bear run in parallel (asyncio.gather — not sequential)
[ ] Risk manager synthesizes both cases into final verdict
[ ] Scorer converts verdict to bullish_probability (5-95 range)
[ ] Risk level overrides work: panic_index > 70 always = HIGH
[ ] Confidence is downgraded when specialist data is missing
[ ] Explainer Line 1 references the actual bullish probability number
[ ] Explainer Line 2 references actual RSI, PE, or volume figures (real numbers)
[ ] Explainer Line 3 references actual panic_index and fomo_index values
[ ] DIVERGENCE case produces a special explanation (different template)
[ ] Complete AlphaHiveSignal returned by POST /analyze
[ ] Redis caching: second /analyze call for same ticker is < 5 seconds
[ ] SEBI disclaimer present in every response
[ ] git commit: "Week 4: Debate engine + scorer + explainer complete"
```

---

## Week 5 Preview

Next week: the Frontend Dashboard.
```
frontend/
├── pages/
│   ├── index.tsx            ← Watchlist: 50 stocks, signal cards
│   ├── stock/[ticker].tsx   ← Full signal: debate viewer + crowd metrics
│   └── backtest.tsx         ← Performance comparison (Week 7)
└── components/
    ├── SignalCard.tsx        ← The 3-line card + bullish%, risk badge
    ├── DebateViewer.tsx      ← Bull vs bear side by side
    └── SwarmMetrics.tsx      ← Panic index, FOMO index, conviction gauge
```

Before Week 5: make sure you can run the frontend locally.
```bash
cd frontend
npx create-next-app@latest . --typescript --tailwind --app
npm install recharts lucide-react
npm run dev
# Should open at http://localhost:3000
```
