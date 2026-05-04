import asyncio
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Callable
from fastapi import HTTPException

from agents.swarm.runner import SwarmRunner
from agents.swarm.aggregator import SwarmAggregator
from agents.specialists.fundamental import FundamentalAnalyst
from agents.specialists.technical import TechnicalAnalyst
from agents.specialists.sentiment import SentimentAnalyst
from agents.specialists.news import NewsAnalyst

from engine.debate import DebateEngine
from engine.scorer import Scorer
from engine.explainer import Explainer
from engine.cache import SignalCache
from engine.memory import SignalMemory
from engine.research_quality import ResearchQualityAnalyzer
from engine.audit import log_specialist, log_debate, log_signal

logger = logging.getLogger(__name__)

class AlphaHiveOrchestrator:
    """
    The Engine Orchestrator.
    Runs the Swarm engine and all 4 specialist analysts SIMULTANEOUSLY.
    Combines their outputs into a single unified analysis object.
    """

    # Circuit breaker settings
    _consecutive_failures: int = 0
    _circuit_open: bool = False
    _circuit_open_since: float | None = None
    FAILURE_THRESHOLD: int = 3
    RECOVERY_TIMEOUT_SECONDS: float = 60.0

    def __init__(self):
        logger.info("Initializing AlphaHiveOrchestrator components...")
        self.swarm_runner = SwarmRunner()
        self.swarm_aggregator = SwarmAggregator()
        self.fundamental = FundamentalAnalyst()
        self.technical = TechnicalAnalyst()
        self.sentiment = SentimentAnalyst()
        self.news = NewsAnalyst()
        self.debate_engine = DebateEngine()
        self.scorer = Scorer()
        self.explainer = Explainer()
        self.quality_analyzer = ResearchQualityAnalyzer()
        self.cache = SignalCache()
        self.signal_memory = SignalMemory()
        logger.info("AlphaHiveOrchestrator initialized. Ready to analyze.")

    async def analyze(self, ticker: str, stream_queue: asyncio.Queue = None) -> dict:
        import time

        # Circuit breaker: check if we've had repeated failures
        if AlphaHiveOrchestrator._circuit_open:
            if AlphaHiveOrchestrator._circuit_open_since is not None:
                elapsed = time.time() - AlphaHiveOrchestrator._circuit_open_since
                if elapsed < AlphaHiveOrchestrator.RECOVERY_TIMEOUT_SECONDS:
                    logger.warning("Circuit breaker is OPEN — returning safe fallback signal")
                    raise HTTPException(
                        status_code=503,
                        detail="Analysis temporarily unavailable (circuit breaker open). Please try again later."
                    )
                else:
                    # Try to close the circuit after timeout
                    AlphaHiveOrchestrator._circuit_open = False
                    AlphaHiveOrchestrator._consecutive_failures = 0
                    AlphaHiveOrchestrator._circuit_open_since = None
                    logger.info("Circuit breaker: attempting to close (recovery timeout elapsed)")

        # Check full signal cache first (fastest path)
        cached_signal = await self.cache.get_signal(ticker)
        if cached_signal:
            logger.info(f"Signal cache HIT for {ticker}")
            return cached_signal
        
        # STEP 1: Run swarm + specialists (Week 3 code, unchanged)
        orchestrator_output = await self._run_parallel_analysis(ticker, stream_queue=stream_queue)
        orchestrator_output["memory_context"] = self.signal_memory.get_past_context(ticker)
        
        # STEP 2: Run debate engine on the combined output
        debate_output = await self.debate_engine.run(orchestrator_output)

        # Audit log the debate output
        log_debate(
            ticker=ticker,
            bull_score=debate_output.get("bull_score", 50),
            bear_score=debate_output.get("bear_score", 50),
            final_call=debate_output.get("final_verdict", {}).get("final_call", "NEUTRAL"),
        )

        # STEP 3: Score the debate output
        signal = self.scorer.compute(debate_output, orchestrator_output)

        # STEP 4: Add deterministic quality, evidence, and risk audit layer
        quality_result = self.quality_analyzer.evaluate(
            ticker=ticker,
            orchestrator_output=orchestrator_output,
            debate_output=debate_output,
            signal=signal,
        )
        signal = self._apply_quality_adjustments(signal, quality_result)
        orchestrator_output["quality"] = quality_result
        
        # STEP 5: Generate plain English explanation
        explanation = self.explainer.generate(
            ticker=ticker,
            scorer_output=signal,
            debate_output=debate_output,
            orchestrator_output=orchestrator_output
        )

        if stream_queue:
            await stream_queue.put({"event": "stage_update", "data": {"stage": "complete"}})
        
        # STEP 6: Build complete AlphaHiveSignal (format from AGENTS.md plus audit metadata)
        from datetime import datetime, timezone
        swarm_section = orchestrator_output.get("swarm", {}) or {}
        # Ensure hold_pct exists in swarm output
        if "hold_pct" not in swarm_section:
            try:
                b = float(swarm_section.get("bullish_pct", 0))
                r = float(swarm_section.get("bearish_pct", 0))
                swarm_section["hold_pct"] = max(0.0, 100.0 - (b + r))
            except Exception:
                swarm_section["hold_pct"] = swarm_section.get("hold_pct", 0)

        complete_signal = {
            # Identity
            "ticker": ticker,
            "company": orchestrator_output.get("company", ticker),
            "sector": orchestrator_output.get("sector", "Unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": orchestrator_output.get("elapsed_seconds", 0),
            "market_data": orchestrator_output.get("market_data", {}),
            
            # Layer 1: Swarm
            "swarm": swarm_section,
            
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
                "bull_case": debate_output.get("bull_case", ""),
                "bear_case": debate_output.get("bear_case", ""),
                "bull_score": debate_output.get("bull_score", 50.0),
                "bear_score": debate_output.get("bear_score", 50.0),
                "bull_reasons": debate_output.get("bull_reasons", []),
                "bear_reasons": debate_output.get("bear_reasons", []),
            },
            
            # Final Signal
            "signal": signal,

            # Research quality and auditability
            "research_quality": quality_result["research_quality"],
            "conflicts": quality_result["conflicts"],
            "evidence": quality_result["evidence"],
            "risk_notes": quality_result["risk_notes"],
            
            # Plain English Explanation
            "explanation": explanation,
            
            # MANDATORY disclaimer
            "disclaimer": (
                "For educational purposes only. Not investment advice. "
                "AlphaHive is not SEBI-registered. "
                "All trading decisions are entirely your own."
            ),
        }
        
        # Store complete signal in cache after computing
        await self.cache.set_signal(ticker, complete_signal)

        # Persist signal outcomes for future reflection passes.
        self.signal_memory.store_signal(ticker, complete_signal)
        asyncio.create_task(self.signal_memory.reflect(ticker))
        
        # STEP 6: Store in PostgreSQL (async, don't await — fire and forget)
        asyncio.create_task(self._store_signal(complete_signal))

        # Audit log the final signal
        log_signal(ticker, complete_signal)

        return complete_signal

    async def _store_signal(self, signal: dict):
        """Persist complete signal to PostgreSQL signals table."""
        from api.database import Signal, async_session
        from datetime import datetime, timezone

        try:
            async with async_session() as session:
                sig = Signal(
                    ticker=signal["ticker"],
                    company=signal.get("company", signal["ticker"]),
                    sector=signal.get("sector", "Unknown"),
                    timestamp=datetime.fromisoformat(signal["timestamp"].replace("Z", "+00:00"))
                        if signal.get("timestamp")
                        else datetime.now(timezone.utc),
                    final_call=signal["signal"]["final_call"],
                    bullish_probability=signal["signal"]["bullish_probability"],
                    risk_level=signal["signal"]["risk_level"],
                    confidence=signal["signal"].get("confidence", "MEDIUM"),
                    explanation_line1=signal.get("explanation", {}).get("line1"),
                    explanation_line2=signal.get("explanation", {}).get("line2"),
                    explanation_line3=signal.get("explanation", {}).get("line3"),
                    raw_signal_json=signal,
                )
                session.add(sig)
                await session.commit()
                logger.info(f"Signal persisted to PostgreSQL for {signal['ticker']}")
        except Exception as e:
            logger.warning(f"Failed to persist signal to PostgreSQL: {e}")

    async def interview_agent(self, ticker: str, agent_name: str, query: str) -> str:
        """
        Routes a user interview question to a specific swarm agent.
        
        Args:
            ticker: The stock ticker being discussed.
            agent_name: The unique name of the agent (e.g. "Panic_Seller_03").
            query: The user's question.
            
        Returns:
            The agent's response as a string.
        """
        logger.info(f"Interviewing agent {agent_name} about {ticker}: '{query}'")
        
        # 1. Get the agent instance
        agent = self.swarm_runner.get_agent_by_name(agent_name)
        if not agent:
            return f"I couldn't find an agent named {agent_name} in the current swarm."

        # 2. Get the context (cached signal or fresh data)
        # We prefer the cached signal because it contains the exact decisions made.
        cached_signal = await self.cache.get_signal(ticker)
        if not cached_signal:
            # Fallback: check swarm cache
            cached_swarm = await self.cache.get_swarm(ticker)
            if cached_swarm:
                cached_signal = {"swarm": cached_swarm, "market_data": cached_swarm.get("market_data")}
        
        if not cached_signal:
            return f"I have no recent memory of analyzing {ticker}. Please run an analysis first."

        # 3. Extract agent-specific context
        swarm_data = cached_signal.get("swarm", {})
        r1_results = swarm_data.get("round1_results", [])
        r2_results = swarm_data.get("round2_results", [])
        
        decision_history = []
        for d in r1_results:
            if d.get("agent_name") == agent_name:
                decision_history.append(d)
        for d in r2_results:
            if d.get("agent_name") == agent_name:
                decision_history.append(d)

        context = {
            "market_data": cached_signal.get("market_data") or swarm_data.get("market_data") or {},
            "decision_history": decision_history
        }

        # 4. Call the agent's interview method
        try:
            return await agent.interview(query, context)
        except Exception as e:
            logger.error(f"Error during agent interview: {e}")
            return f"The agent is currently unavailable. Error: {e}"

    async def _run_parallel_analysis(self, ticker: str, stream_queue: asyncio.Queue = None) -> dict:
        start_time = time.time()
        
        # 1. Prepare shared market data (used by both layers)
        if stream_queue:
            await stream_queue.put({"event": "stage_update", "data": {"stage": "data"}})
        try:
            market_data = await self.swarm_runner.prepare_market_data(ticker)
        except Exception as e:
            logger.error(f"Failed to prepare market data for {ticker}: {e}")
            market_data = {"ticker": ticker}

        # 2. Launch SWARM and ALL 4 SPECIALISTS simultaneously.
        if stream_queue:
            await stream_queue.put({"event": "stage_update", "data": {"stage": "round1"}})
            
        def on_swarm_event(data, micro_action=None):
            if stream_queue:
                if micro_action:
                    # Micro-action telemetry: 'data' is the agent object (BaseAgent)
                    agent = data
                    agent_name = agent.name if hasattr(agent, 'name') else str(agent)
                    agent_type = agent.agent_type if hasattr(agent, 'agent_type') else "system"
                    
                    asyncio.create_task(stream_queue.put({
                        "event": "agent_action",
                        "data": {
                            "id": f"{agent_name}_{datetime.now().timestamp()}",
                            "agentName": agent_name,
                            "agentType": agent_type,
                            "message": micro_action,
                            "timestamp": datetime.now(timezone.utc).strftime("%M:%S")
                        }
                    }))
                else:
                    # Full decision telemetry
                    decision = data
                    agent_event = {
                        "id": decision.get("agent_name"),
                        "agentType": decision.get("agent_type"),
                        "agentName": decision.get("agent_name"),
                        "message": decision.get("reasoning", ""),
                        "decision": decision.get("action", "hold").upper(),
                        "round": decision.get("round", 1),
                        "timestamp": datetime.now(timezone.utc).strftime("%M:%S")
                    }
                    asyncio.create_task(stream_queue.put({"event": "agent_decision", "data": agent_event}))

        swarm_task = asyncio.create_task(self._run_swarm(ticker, on_decision=on_swarm_event))
        fundamental_task = asyncio.create_task(self.fundamental.analyze(ticker, market_data))
        technical_task = asyncio.create_task(self.technical.analyze(ticker, market_data))
        sentiment_task = asyncio.create_task(self.sentiment.analyze(ticker, market_data))
        news_task = asyncio.create_task(self.news.analyze(ticker, market_data))

        # Wait for ALL to complete (or fail gracefully)
        results = await asyncio.gather(
            swarm_task, 
            fundamental_task, 
            technical_task,
            sentiment_task, 
            news_task,
            return_exceptions=True
        )

        swarm_result, fund_result, tech_result, sent_result, news_result = results

        # Handle any failed tasks gracefully
        swarm_signal = self._safe_swarm(swarm_result)
        fund_report = self._safe_specialist(fund_result, "fundamental")
        tech_report = self._safe_specialist(tech_result, "technical")
        sent_report = self._safe_specialist(sent_result, "sentiment")
        news_report = self._safe_specialist(news_result, "news")

        if stream_queue:
            await stream_queue.put({"event": "stage_update", "data": {"stage": "specialists"}})
            # We could push specific specialist reports here if the frontend supports it
            # For now, we push aggregate updates via stage_update

        # Audit log each specialist result
        for report, name in [(fund_report, "fundamental"), (tech_report, "technical"),
                              (sent_report, "sentiment"), (news_report, "news")]:
            if report and "score" in report:
                log_specialist(
                    ticker=ticker,
                    analyst=name,
                    score=report["score"],
                    verdict=report.get("verdict", "NEUTRAL"),
                    summary=report.get("summary", ""),
                )

        # Track consecutive failures for circuit breaker
        has_failure = isinstance(fund_result, Exception) or isinstance(tech_result, Exception) \
            or isinstance(sent_result, Exception) or isinstance(news_result, Exception) \
            or isinstance(swarm_result, Exception)
        if has_failure:
            AlphaHiveOrchestrator._consecutive_failures += 1
            if AlphaHiveOrchestrator._consecutive_failures >= AlphaHiveOrchestrator.FAILURE_THRESHOLD:
                AlphaHiveOrchestrator._circuit_open = True
                AlphaHiveOrchestrator._circuit_open_since = time.time()
                logger.error(
                    f"Circuit breaker OPENED after {AlphaHiveOrchestrator._consecutive_failures} "
                    "consecutive failures. Analysis requests will return 503 for the next "
                    f"{AlphaHiveOrchestrator.RECOVERY_TIMEOUT_SECONDS}s."
                )
        else:
            AlphaHiveOrchestrator._consecutive_failures = 0

        elapsed = time.time() - start_time

        # 3. Build the unified analysis object.
        specialist_scores = [
            r["score"] for r in [fund_report, tech_report, sent_report, news_report]
            if r and "score" in r and r["score"] is not None
        ]
        combined_specialist_score = sum(specialist_scores) / len(specialist_scores) if specialist_scores else 50.0

        company_name = market_data.get("company", ticker)
        sector_name = market_data.get("sector", "Unknown")

        return {
            "ticker": ticker,
            "company": company_name,
            "sector": sector_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            
            # Layer 1: Swarm output
            "swarm": swarm_signal,
            
            # Layer 2: Specialist outputs  
            "specialists": {
                "fundamental": fund_report,
                "technical": tech_report,
                "sentiment": sent_report,
                "news": news_report,
                "combined_score": round(combined_specialist_score, 1)
            },

            # Raw shared data for downstream evidence and future audit views
            "market_data": market_data,
            
            # Preview of final signal
            "signal_preview": {
                "swarm_call": swarm_signal.get("dominant_signal", "NEUTRAL"),
                "specialist_score": round(combined_specialist_score, 1),
                "agreement": self._check_agreement(swarm_signal, combined_specialist_score),
                "alert": news_report.get("alert") if news_report else None
            },
            
            # Mandatory disclaimer
            "disclaimer": (
                "For educational purposes only. Not investment advice. "
                "AlphaHive is not SEBI-registered. "
                "All trading decisions are entirely your own."
            )
        }

    async def _run_swarm(self, ticker: str, on_decision: Optional[callable] = None) -> dict:
        """
        Runs swarm runner + aggregator.
        """
        # Check cache first
        cached = await self.cache.get_swarm(ticker)
        if cached:
            logger.info(f"Swarm cache HIT for {ticker}")
            return cached
        
        runner_output = await self.swarm_runner.run(ticker, on_decision=on_decision)
        swarm_signal = self.swarm_aggregator.compute(runner_output)
        enriched_signal = {
            **swarm_signal,
            "round1_results": runner_output.get("round1_results", []),
            "round2_results": runner_output.get("round2_results", []),
            "crowd_summary": runner_output.get("crowd_summary", ""),
            "market_data": runner_output.get("market_data", {}),
            "timing": runner_output.get("timing", {}),
        }
        
        # Store enriched data so live views keep round-level trace detail on cache hits.
        await self.cache.set_swarm(ticker, enriched_signal)
        return enriched_signal

    def _safe_swarm(self, result) -> dict:
        if isinstance(result, Exception):
            logger.error(f"Swarm task failed: {result}")
            return {
                "bullish_pct": 50, 
                "bearish_pct": 30, 
                "hold_pct": 20,
                "panic_index": 0, 
                "fomo_index": 0, 
                "conviction": 50,
                "round1_bullish": 50,
                "round2_bullish": 50,
                "crowd_amplification": 0,
                "dominant_signal": "NEUTRAL", 
                "signal_strength": "WEAK",
                "crowd_narrative": "Swarm analysis unavailable; using neutral fallback.",
                "error": str(result)
            }
        defaults = {
            "bullish_pct": 50,
            "bearish_pct": 30,
            "hold_pct": 20,
            "panic_index": 0,
            "fomo_index": 0,
            "conviction": 50,
            "round1_bullish": result.get("bullish_pct", 50) if isinstance(result, dict) else 50,
            "round2_bullish": result.get("bullish_pct", 50) if isinstance(result, dict) else 50,
            "crowd_amplification": 0,
            "dominant_signal": "NEUTRAL",
            "signal_strength": "WEAK",
            "crowd_narrative": "Mixed signals across the swarm.",
        }
        normalized = {**defaults, **result}
        if not normalized.get("crowd_narrative"):
            normalized["crowd_narrative"] = "Mixed signals across the swarm."
        return normalized

    def _safe_specialist(self, result, analyst_name: str) -> dict:
        if isinstance(result, Exception):
            logger.error(f"{analyst_name.capitalize()} task failed: {result}")
            return {
                "analyst": analyst_name, 
                "score": 50, 
                "verdict": "NEUTRAL",
                "summary": "Analysis unavailable", 
                "error": str(result)
            }
        return result

    def _check_agreement(self, swarm_signal: dict, specialist_score: float) -> str:
        """
        Check if swarm and specialists agree on direction.
        DIVERGENCE is the most interesting signal.
        """
        swarm_bullish = swarm_signal.get("bullish_pct", 50) > 55
        swarm_bearish = swarm_signal.get("bullish_pct", 50) < 45
        specialist_bullish = specialist_score > 55
        specialist_bearish = specialist_score < 45
        
        if swarm_bullish and specialist_bullish:
            return "STRONG_AGREEMENT_BULLISH"
        if swarm_bearish and specialist_bearish:
            return "STRONG_AGREEMENT_BEARISH"
        if swarm_bullish and not specialist_bullish:
            return "DIVERGENCE_SWARM_BULLISH"
        if not swarm_bullish and specialist_bullish:
            return "DIVERGENCE_SPECIALIST_BULLISH"
            
        return "NEUTRAL"

    def _apply_quality_adjustments(self, signal: dict, quality_result: dict) -> dict:
        """
        Attach audit metadata to the final signal and downgrade confidence
        when the research-quality layer says the evidence is weak.
        """
        adjusted = dict(signal)
        research_quality = quality_result.get("research_quality", {})
        conflicts = quality_result.get("conflicts", [])
        risk_notes = quality_result.get("risk_notes", {})

        trust_score = research_quality.get("trust_score", 50)
        trust_label = research_quality.get("trust_label", "MEDIUM")

        adjusted["trust_score"] = trust_score
        adjusted["trust_label"] = trust_label

        if conflicts:
            adjusted["primary_conflict"] = conflicts[0]["title"]

        invalidation_conditions = risk_notes.get("invalidation_conditions", [])
        if invalidation_conditions:
            adjusted["invalidation_condition"] = invalidation_conditions[0]

        if trust_score < 45:
            adjusted["confidence"] = "LOW"
        elif trust_score < 65 and adjusted.get("confidence") == "HIGH":
            adjusted["confidence"] = "MEDIUM"

        if any(item.get("severity") == "HIGH" for item in conflicts):
            if adjusted.get("risk_level") == "LOW":
                adjusted["risk_level"] = "MEDIUM"

        return adjusted

    async def close(self):
        """Close any long-lived resources held by the orchestrator (HTTP clients, etc.)."""
        try:
            if hasattr(self.fundamental, "close"):
                await self.fundamental.close()
        except Exception:
            logger.warning("Failed to close FundamentalAnalyst client")
        try:
            if hasattr(self.technical, "close"):
                await self.technical.close()
        except Exception:
            logger.warning("Failed to close TechnicalAnalyst client")
        try:
            if hasattr(self.news, "close"):
                await self.news.close()
        except Exception:
            logger.warning("Failed to close NewsAnalyst client")
