import json
import logging
import os
import asyncio
import re
from difflib import SequenceMatcher
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
import httpx

logger = logging.getLogger("alphahive.engine.debate")

class DebateState(TypedDict, total=False):
    # Input (set before graph runs)
    ticker: str
    company: str
    sector: str
    swarm_signal: dict          # from SwarmAggregator
    specialist_reports: dict    # fundamental, technical, sentiment, news
    market_data: dict           # raw price/indicator data
    memory_context: str
    debate_round: int
    max_debate_rounds: int
    debate_history: list[dict]
    debate_repeat_count: int
    debate_stop_reason: str
    
    # Set by bull_researcher node
    bull_case: Optional[str]
    bull_score: Optional[float]  # 0-100, how strong is the bull case
    bull_reasons: Optional[list]
    bull_acknowledged_risks: Optional[list]
    
    # Set by bear_researcher node
    bear_case: Optional[str]
    bear_score: Optional[float]  # 0-100, how strong is the bear case
    bear_reasons: Optional[list]
    bear_acknowledged_bull: Optional[list]
    
    # Set by risk_analyst node
    risk_score: Optional[float]           # 0-100, how risky is this stock
    key_risks: Optional[list[str]]        # Top 3-4 identified risks
    macro_headwinds: Optional[list[str]]  # Macro/sector/regulatory risks
    invalidation_conditions: Optional[list[str]]  # Conditions that would break the thesis
    risk_assessment: Optional[str]        # Narrative summary of risk analysis
    
    # Set by risk_manager node
    final_verdict: Optional[dict]

def _build_data_summary(state: DebateState) -> str:
    """Formats all data into a clean readable block for prompts."""
    summary = f"""CROWD SIMULATION RESULTS:
- Swarm bullish: {state['swarm_signal'].get('bullish_pct', 50):.1f}%
- Panic index: {state['swarm_signal'].get('panic_index', 0):.1f} (low=calm, high=panic)
- FOMO index: {state['swarm_signal'].get('fomo_index', 0):.1f}
- Conviction: {state['swarm_signal'].get('conviction', 50):.1f}%
- Crowd narrative: {state['swarm_signal'].get('crowd_narrative', 'N/A')}

FUNDAMENTAL ANALYSIS:
- Score: {state['specialist_reports'].get('fundamental', {}).get('score', 50)}/100
- Verdict: {state['specialist_reports'].get('fundamental', {}).get('verdict', 'N/A')}
- Summary: {state['specialist_reports'].get('fundamental', {}).get('summary', 'N/A')}
- Key positives: {state['specialist_reports'].get('fundamental', {}).get('key_positives', [])}

TECHNICAL ANALYSIS:
- Score: {state['specialist_reports'].get('technical', {}).get('score', 50)}/100
- Verdict: {state['specialist_reports'].get('technical', {}).get('verdict', 'N/A')}
- Summary: {state['specialist_reports'].get('technical', {}).get('summary', 'N/A')}
- Key signals: {state['specialist_reports'].get('technical', {}).get('key_signals', [])}

SENTIMENT ANALYSIS:
- Score: {state['specialist_reports'].get('sentiment', {}).get('score', 50)}/100
- Verdict: {state['specialist_reports'].get('sentiment', {}).get('verdict', 'N/A')}
- Summary: {state['specialist_reports'].get('sentiment', {}).get('summary', 'N/A')}

NEWS ANALYSIS:
- Score: {state['specialist_reports'].get('news', {}).get('score', 50)}/100
- Alert: {state['specialist_reports'].get('news', {}).get('alert', 'None')}
- Summary: {state['specialist_reports'].get('news', {}).get('summary', 'N/A')}"""
    memory_context = (state.get("memory_context") or "").strip()
    if memory_context:
        summary += f"\n\nPAST REFLECTIONS:\n{memory_context}"
    return summary


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio()


def _history_summary(state: DebateState) -> str:
    history = state.get("debate_history", []) or []
    if not history:
        return "No prior debate rounds."

    lines = []
    for item in history[-3:]:
        lines.append(
            f"Round {item.get('round', '?')}: bull_score={item.get('bull_score', 50):.0f}, "
            f"bear_score={item.get('bear_score', 50):.0f}, verdict={item.get('verdict', 'N/A')}"
        )
    return "\n".join(lines)


def _is_repeated_round(state: DebateState, current_round: dict[str, Any]) -> bool:
    history = state.get("debate_history", []) or []
    if not history:
        return False

    previous = history[-1]
    bull_sim = _similarity(current_round.get("bull_case", ""), previous.get("bull_case", ""))
    bear_sim = _similarity(current_round.get("bear_case", ""), previous.get("bear_case", ""))
    score_delta = abs(float(current_round.get("bull_score", 50)) - float(previous.get("bull_score", 50)))
    score_delta += abs(float(current_round.get("bear_score", 50)) - float(previous.get("bear_score", 50)))

    return bull_sim >= 0.92 and bear_sim >= 0.92 and score_delta <= 5.0

async def _call_ollama_specialist(system: str, user: str) -> str:
    """Calls Ollama with llama3.1:8b. 60s timeout. Returns response text."""
    model = os.getenv("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "format": "json",
        "stream": False,
        "temperature": 0.4
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
    except Exception as e:
        logger.error(f"Debate LLM call failed: {e}")
        return ""

def _parse_json_response(text: str) -> dict:
    """
    Safely parse LLM JSON response.
    Strip markdown fences if present: ```json ... ```
    Try json.loads first.
    If fails: return empty dict (caller handles fallback).
    Never crash.
    """
    if not text:
        return {}
        
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    try:
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Failed to parse debate JSON response: {e}")
        return {}


async def bull_researcher_node(state: DebateState) -> DebateState:
    """
    Reads all available data and builds the strongest possible bull case.
    Does NOT cherry-pick — must acknowledge key risks even in bull case.
    """
    data_summary = _build_data_summary(state)
    
    system_prompt = """You are a bullish equity research analyst covering Indian markets.
Your job is to build the strongest possible bull case for a stock using 
all available data — crowd behavior simulation AND fundamental/technical analysis.
You must be specific and data-driven. Reference actual numbers.
You must acknowledge the top 1-2 risks even in your bull case (this makes it credible).
Respond in valid JSON only."""
    history_context = _history_summary(state)

    user_prompt = f"""Build the bull case for {state['ticker']} ({state['company']}, {state['sector']} sector).

Current debate round: {state.get('debate_round', 1)} of {state.get('max_debate_rounds', 2)}

Prior debate context:
{history_context}

{data_summary}

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
    history_context = _history_summary(state)

    user_prompt = f"""Build the bear case for {state['ticker']} ({state['company']}, {state['sector']} sector).

Current debate round: {state.get('debate_round', 1)} of {state.get('max_debate_rounds', 2)}

Prior debate context:
{history_context}

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


async def risk_analyst_node(state: DebateState) -> DebateState:
    """
    Dedicated risk analyst that assesses tail risks, macro headwinds,
    regulatory/sector risks, and invalidation conditions.
    Runs after bull/bear debate to inform the final risk manager verdict.
    """
    system_prompt = """You are a risk analyst specializing in tail risks, black-swan events,
and capital preservation. You have read a bull and bear case for an Indian equity.
Your job is to identify the hidden risks, macro headwinds, regulatory threats,
and the specific conditions that would INVALIDATE the current thesis.
Think like a short-seller or risk manager — assume something could go very wrong.
Be specific and data-driven. Reference sector dynamics, macro trends, regulatory environment.
Respond in valid JSON only."""
    
    swarm_sig = state.get("swarm_signal", {})
    spec_reports = state.get("specialist_reports", {})
    
    user_prompt = f"""Perform deep risk analysis for {state['ticker']} ({state['company']}, {state['sector']} sector).

BULL CASE (score {state.get('bull_score', 50)}/100):
{state.get('bull_case', 'N/A')}

BEAR CASE (score {state.get('bear_score', 50)}/100):
{state.get('bear_case', 'N/A')}

CROWD SENTIMENT: {swarm_sig.get('dominant_signal', 'UNKNOWN')}
(Panic index: {swarm_sig.get('panic_index', 0):.0f}, FOMO: {swarm_sig.get('fomo_index', 0):.0f})

NEWS ALERT: {spec_reports.get('news', {}).get('alert', 'None')}

SECTOR CONTEXT: {state['sector']} sector equities

Your analysis:
1. What tail risks / black-swan events could emerge? (Macro, regulatory, sector-specific)
2. What are the 3-4 most important risks to monitor?
3. What specific conditions or events would BREAK the investment thesis?
4. How sensitive is the thesis to macro changes (inflation, rates, FX, FII flows)?

Return JSON:
{{
  "risk_score": integer 0-100 (0=safe, 100=extremely risky),
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "macro_headwinds": ["headwind 1", "headwind 2"],
  "invalidation_conditions": [
    "If [specific condition], the thesis breaks",
    "If [specific condition], the thesis breaks"
  ],
  "risk_assessment": "2-3 sentence narrative on biggest risk vectors",
  "tail_risk_alert": "true" | "false"  (true if black-swan risk seems elevated)
}}"""
    
    response = await _call_ollama_specialist(system_prompt, user_prompt)
    parsed = _parse_json_response(response)
    
    state["risk_score"] = float(parsed.get("risk_score", 50))
    state["key_risks"] = parsed.get("key_risks", [])
    state["macro_headwinds"] = parsed.get("macro_headwinds", [])
    state["invalidation_conditions"] = parsed.get("invalidation_conditions", [])
    state["risk_assessment"] = parsed.get("risk_assessment", "Risk assessment unavailable")
    
    # Flag if tail risk elevated
    tail_risk_flag = parsed.get("tail_risk_alert", "").lower() == "true"
    if tail_risk_flag or state["risk_score"] > 75:
        logger.warning(f"[{state['ticker']}] Elevated tail risk detected: score={state['risk_score']:.0f}")
    
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

    swarm_sig = state.get("swarm_signal", {})
    spec_reports = state.get("specialist_reports", {})
    
    user_prompt = f"""Make the final verdict for {state['ticker']}.

Debate rounds completed: {state.get('debate_round', 1)}

Round history summary:
{_history_summary(state)}

BULL CASE (score: {state.get('bull_score', 50)}/100):
{state.get('bull_case', 'N/A')}
Top bull reasons: {state.get('bull_reasons', [])}

BEAR CASE (score: {state.get('bear_score', 50)}/100):
{state.get('bear_case', 'N/A')}
Top bear reasons: {state.get('bear_reasons', [])}

RISK ANALYSIS (risk score: {state.get('risk_score', 50)}/100):
Key risks: {state.get('key_risks', [])}
Macro headwinds: {state.get('macro_headwinds', [])}
Invalidation conditions: {state.get('invalidation_conditions', [])}
{state.get('risk_assessment', 'N/A')}

CROWD SIGNAL: {swarm_sig.get('dominant_signal', 'UNKNOWN')} 
(conviction: {swarm_sig.get('conviction', 50):.0f}%, 
panic: {swarm_sig.get('panic_index', 0):.0f})

HIGH PRIORITY ALERT: {spec_reports.get('news', {}).get('alert', 'None')}

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
- HIGH if: risk_score > 70 OR panic_index > 60 OR bear_score > 70 OR high priority alert
- MEDIUM if: risk_score 40-70 OR conviction < 75 OR some data missing
- LOW if: risk_score < 40 AND conviction > 80 AND bull_score > 70 AND panic_index < 20

Confidence rules:
- HIGH if: swarm and specialists AGREE on direction AND conviction > 75 AND risk_score < 50
- LOW if: swarm and specialists DIVERGE OR conviction < 50 OR risk_score > 70
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
        "risk_score": state.get("risk_score", 50),
        "key_risks": state.get("key_risks", []),
        "invalidation_conditions": state.get("invalidation_conditions", []),
        "debate_rounds": state.get("debate_round", 1),
    }
    return state


async def researchers_node(state: DebateState) -> DebateState:
    """Run bull and bear researchers in parallel inside the graph."""
    bull_task = asyncio.create_task(bull_researcher_node(state.copy()))
    bear_task = asyncio.create_task(bear_researcher_node(state.copy()))

    bull_result, bear_result = await asyncio.gather(
        bull_task, bear_task, return_exceptions=True
    )

    if not isinstance(bull_result, Exception):
        state.update({
            "bull_case": bull_result.get("bull_case"),
            "bull_score": bull_result.get("bull_score"),
            "bull_reasons": bull_result.get("bull_reasons", []),
            "bull_acknowledged_risks": bull_result.get("bull_acknowledged_risks", []),
        })
    else:
        logger.error(f"Bull researcher failed: {bull_result}")
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
        logger.error(f"Bear researcher failed: {bear_result}")
        state["bear_case"] = "Bear case failed"
        state["bear_score"] = 50.0

    current_round = {
        "round": state.get("debate_round", 0) + 1,
        "bull_case": state.get("bull_case"),
        "bull_score": state.get("bull_score", 50),
        "bull_reasons": state.get("bull_reasons", []),
        "bear_case": state.get("bear_case"),
        "bear_score": state.get("bear_score", 50),
        "bear_reasons": state.get("bear_reasons", []),
    }

    history = list(state.get("debate_history", []) or [])
    is_repeated = _is_repeated_round(state, current_round)
    history.append(current_round)
    state["debate_history"] = history
    state["debate_round"] = current_round["round"]
    state["debate_repeat_count"] = state.get("debate_repeat_count", 0) + (1 if is_repeated else 0)
    if state["debate_repeat_count"]:
        state["debate_stop_reason"] = "Repeated debate content"
    return state


def _should_continue_debate(state: DebateState) -> str:
    max_rounds = int(state.get("max_debate_rounds", 2) or 2)
    current_round = int(state.get("debate_round", 0) or 0)
    repeat_count = int(state.get("debate_repeat_count", 0) or 0)

    if current_round >= max_rounds:
        state["debate_stop_reason"] = state.get("debate_stop_reason") or "Reached max debate rounds"
        return "risk_analyst"
    if repeat_count >= 1:
        state["debate_stop_reason"] = state.get("debate_stop_reason") or "Researchers repeated themselves"
        return "risk_analyst"
    return "researchers"

def build_debate_graph():
    graph = StateGraph(DebateState)
    
    # Add nodes
    graph.add_node("researchers", researchers_node)
    graph.add_node("risk_analyst", risk_analyst_node)
    graph.add_node("risk_manager", risk_manager_node)

    graph.set_entry_point("researchers")
    graph.add_conditional_edges("researchers", _should_continue_debate, {
        "researchers": "researchers",
        "risk_analyst": "risk_analyst",
    })
    graph.add_edge("risk_analyst", "risk_manager")
    graph.add_edge("risk_manager", END)
    
    return graph.compile()


class DebateEngine:
    def __init__(self, max_debate_rounds: int = 2):
        self.max_debate_rounds = max(1, min(int(max_debate_rounds), 4))
        self.graph = build_debate_graph()

    async def run(self, orchestrator_output: dict) -> dict:
        """
        Main entry point. Takes Week 3 orchestrator output,
        runs the debate, returns complete debate results.
        """
        state = DebateState(
            ticker=orchestrator_output["ticker"],
            company=orchestrator_output.get("company", ""),
            sector=orchestrator_output.get("sector", ""),
            swarm_signal=orchestrator_output.get("swarm", {}),
            specialist_reports=orchestrator_output.get("specialists", {}),
            market_data=orchestrator_output.get("market_data", {}),
            memory_context=orchestrator_output.get("memory_context", ""),
            debate_round=0,
            max_debate_rounds=self.max_debate_rounds,
            debate_history=[],
            debate_repeat_count=0,
            debate_stop_reason="",
            bull_case=None,
            bull_score=None,
            bear_case=None,
            bear_score=None,
            bull_reasons=None,
            bull_acknowledged_risks=None,
            bear_reasons=None,
            bear_acknowledged_bull=None,
            risk_score=None,
            key_risks=None,
            macro_headwinds=None,
            invalidation_conditions=None,
            risk_assessment=None,
            final_verdict=None,
        )
        final_state = await self.graph.ainvoke(state)
        
        return {
            "ticker": final_state["ticker"],
            "bull_case": final_state.get("bull_case"),
            "bull_score": final_state.get("bull_score"),
            "bull_reasons": final_state.get("bull_reasons", []),
            "bull_acknowledged_risks": final_state.get("bull_acknowledged_risks", []),
            "bear_case": final_state.get("bear_case"),
            "bear_score": final_state.get("bear_score"),
            "bear_reasons": final_state.get("bear_reasons", []),
            "bear_acknowledged_bull": final_state.get("bear_acknowledged_bull", []),
            "risk_score": final_state.get("risk_score"),
            "key_risks": final_state.get("key_risks", []),
            "macro_headwinds": final_state.get("macro_headwinds", []),
            "invalidation_conditions": final_state.get("invalidation_conditions", []),
            "risk_assessment": final_state.get("risk_assessment"),
            "final_verdict": final_state.get("final_verdict"),
            "debate_history": final_state.get("debate_history", []),
            "debate_rounds": final_state.get("debate_round", 0),
            "debate_stop_reason": final_state.get("debate_stop_reason", ""),
        }
