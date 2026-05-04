"""
AlphaHive — Swarm Runner
==========================
The asyncio parallel engine that runs all 80 personality agents through
two rounds of decision-making.

Round 1: Independent decisions — all 80 agents run in parallel.
Round 2: Social influence — agents see Round 1 aggregate and can revise.

This is the most technically critical file in the swarm layer.
Target: full 80-agent run in under 60 seconds with Ollama.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import asyncio
import logging
import time
from typing import Optional

from agents.swarm.personalities.retail import get_all_retail_agents
from agents.swarm.personalities.institutional import get_all_institutional_agents
from agents.swarm.personalities.algo import get_all_algo_agents
from agents.swarm.personalities.news_reactor import get_all_news_reactor_agents

from data.loader import data_loader
from data.news import get_news_for_ticker
from data.nse import get_fii_dii_flow
from engine.audit import log_swarm_decision

logger = logging.getLogger("alphahive.agents.swarm.runner")


class SwarmRunner:
    """
    Runs the 80-agent swarm through two rounds of parallel decisions.

    Usage:
        runner = SwarmRunner()
        result = await runner.run("RELIANCE.NS")

    The result contains:
        - ticker, market_data
        - round1_results: 80 decision dicts (independent)
        - round2_results: 80 decision dicts (after social influence)
        - crowd_summary: human-readable summary of Round 1
        - timing: performance metrics
    """

    def __init__(self) -> None:
        """Load all 80 agents from the four personality categories."""
        self.agents = []
        self.agents.extend(get_all_retail_agents())          # 25
        self.agents.extend(get_all_institutional_agents())   # 20
        self.agents.extend(get_all_algo_agents())            # 20
        self.agents.extend(get_all_news_reactor_agents())    # 15

        logger.info(f"SwarmRunner initialized with {len(self.agents)} agents")

        # Agent timeout per LLM call (seconds)
        self._agent_timeout = 25.0

    def get_agent_by_name(self, name: str) -> Optional["BaseAgent"]:
        """Find an agent in the swarm by its unique name."""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    # -------------------------------------------------------------------
    # Prepare market data for all agents
    # -------------------------------------------------------------------
    async def prepare_market_data(self, ticker: str) -> dict:
        """
        Fetch everything the agents need to make a decision.

        Runs data fetching in parallel: price, indicators, news, FII/DII.

        Args:
            ticker: NSE ticker (e.g. RELIANCE.NS)

        Returns:
            Market data dict ready for agent consumption
        """
        start = time.time()

        # Fetch all data sources in parallel
        price_task = data_loader.get_current_price(ticker)
        indicators_task = data_loader.get_indicators(ticker)
        news_task = get_news_for_ticker(ticker, max_items=10)
        fii_dii_task = get_fii_dii_flow()

        price_data, indicators, news_items, fii_dii = await asyncio.gather(
            price_task, indicators_task, news_task, fii_dii_task,
            return_exceptions=True,
        )

        # Handle exceptions — never crash, always provide something
        if isinstance(price_data, Exception):
            logger.warning(f"Price fetch failed for {ticker}: {price_data}")
            price_data = {"ticker": ticker, "price": None, "change_pct": 0.0, "volume": 0}

        if isinstance(indicators, Exception):
            logger.warning(f"Indicators failed for {ticker}: {indicators}")
            indicators = {"rsi_14": None, "ema_50": None, "ema_200": None, "atr_14": None}

        if isinstance(news_items, Exception):
            logger.warning(f"News fetch failed for {ticker}: {news_items}")
            news_items = []

        if isinstance(fii_dii, Exception):
            logger.warning(f"FII/DII fetch failed: {fii_dii}")
            fii_dii = {"fii_net_buy_crores": None, "dii_net_buy_crores": None, "fii_sentiment": "UNKNOWN"}

        # Build the market data dict
        price = price_data.get("price") if isinstance(price_data, dict) else None
        change_pct = price_data.get("change_pct", 0.0) if isinstance(price_data, dict) else 0.0

        # Volume ratio
        volume_ratio = None
        if isinstance(indicators, dict):
            volume_ratio = indicators.get("volume_ratio")

        # Price vs 200 EMA
        price_vs_200ema = "unknown"
        if isinstance(indicators, dict) and indicators.get("ema_200") and price:
            ema_200 = indicators["ema_200"]
            if price > ema_200 * 1.01:
                price_vs_200ema = "above"
            elif price < ema_200 * 0.99:
                price_vs_200ema = "below"
            else:
                price_vs_200ema = "at"

        # Extract headline strings from NewsItem objects
        headlines = []
        if isinstance(news_items, list):
            for item in news_items:
                if hasattr(item, "headline"):
                    headlines.append(item.headline)
                elif isinstance(item, str):
                    headlines.append(item)

        # FII/DII flow summary
        fii_net = fii_dii.get("fii_net_buy_crores") if isinstance(fii_dii, dict) else None
        dii_net = fii_dii.get("dii_net_buy_crores") if isinstance(fii_dii, dict) else None
        fii_sentiment = fii_dii.get("fii_sentiment", "UNKNOWN") if isinstance(fii_dii, dict) else "UNKNOWN"

        market_data = {
            "ticker": ticker,
            "price": price,
            "price_change_pct": change_pct,
            "volume_ratio": volume_ratio,
            "indicators": indicators if isinstance(indicators, dict) else {},
            "news_headlines": headlines,
            "fii_dii": {
                "fii_net": fii_net,
                "dii_net": dii_net,
                "fii_sentiment": fii_sentiment,
            },
            "price_vs_200ema": price_vs_200ema,
        }

        elapsed = time.time() - start
        logger.info(
            f"Market data prepared for {ticker} in {elapsed:.1f}s "
            f"(price={price}, RSI={indicators.get('rsi_14') if isinstance(indicators, dict) else 'N/A'}, "
            f"headlines={len(headlines)})"
        )
        return market_data

    # -------------------------------------------------------------------
    # Round 1 — Independent parallel decisions
    # -------------------------------------------------------------------
    async def run_round1(self, market_data: dict, on_decision: Optional[callable] = None) -> list[dict]:
        """
        Run ALL 80 agents in parallel via asyncio.gather (Round 1).

        Each agent makes an independent decision — no crowd knowledge.
        If an agent errors, it returns a neutral hold (never crashes the round).

        Returns:
            List of 80 decision dicts
        """
        start = time.time()
        ticker = market_data.get("ticker", "UNKNOWN")

        logger.info(f"Round 1 starting for {ticker} — {len(self.agents)} agents")

        # Create timeout-wrapped tasks for each agent
        tasks = [
            self._run_agent_with_timeout(
                agent.decide_round1(market_data, on_action=on_decision), agent
            )
            for agent in self.agents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results — replace exceptions with neutral holds
        decisions = []
        errors = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors += 1
                agent = self.agents[i]
                decisions.append({
                    "agent_name": agent.name,
                    "agent_type": agent.agent_type,
                    "weight": agent.weight,
                    "round": 1,
                    "action": "hold",
                    "confidence": 0.1,
                    "reasoning": f"agent error — defaulting to hold ({type(result).__name__})",
                })
                log_swarm_decision(
                    ticker=ticker,
                    agent_name=agent.name,
                    agent_type=agent.agent_type,
                    round_num=1,
                    action="hold",
                    confidence=0.1,
                    reasoning=f"error: {type(result).__name__}",
                )
                if on_decision:
                    on_decision(decisions[-1])
            else:
                decisions.append(result)
                log_swarm_decision(
                    ticker=ticker,
                    agent_name=result["agent_name"],
                    agent_type=result["agent_type"],
                    round_num=1,
                    action=result["action"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                )
                if on_decision:
                    on_decision(result)

        # Log summary
        n_buy = sum(1 for d in decisions if d["action"] == "buy")
        n_sell = sum(1 for d in decisions if d["action"] == "sell")
        n_hold = sum(1 for d in decisions if d["action"] == "hold")
        elapsed = time.time() - start

        logger.info(
            f"Round 1 complete for {ticker}: "
            f"{n_buy} buy, {n_sell} sell, {n_hold} hold "
            f"({errors} errors) in {elapsed:.1f}s"
        )

        return decisions

    # -------------------------------------------------------------------
    # Build crowd summary from Round 1 results
    # -------------------------------------------------------------------
    def build_crowd_summary(self, round1_results: list[dict]) -> str:
        """
        Compute summary statistics from Round 1 and format as a
        human-readable string for Round 2 agent prompts.

        Uses weighted percentages for accuracy.

        Args:
            round1_results: List of 80 decision dicts from Round 1

        Returns:
            Multi-line string describing the crowd behavior
        """
        # Overall weighted percentages
        total_weight = sum(d["weight"] for d in round1_results)
        if total_weight == 0:
            total_weight = 1.0

        buy_weight = sum(d["weight"] for d in round1_results if d["action"] == "buy")
        sell_weight = sum(d["weight"] for d in round1_results if d["action"] == "sell")
        hold_weight = sum(d["weight"] for d in round1_results if d["action"] == "hold")

        buy_pct = (buy_weight / total_weight) * 100
        sell_pct = (sell_weight / total_weight) * 100
        hold_pct = (hold_weight / total_weight) * 100

        # Breakdown by agent type
        types = ["retail", "institutional", "algo", "news_reactor"]
        type_stats = {}
        for agent_type in types:
            type_decisions = [d for d in round1_results if d["agent_type"] == agent_type]
            if not type_decisions:
                type_stats[agent_type] = {"buy": 0, "sell": 0, "hold": 0}
                continue

            tw = sum(d["weight"] for d in type_decisions)
            if tw == 0:
                tw = 1.0
            type_stats[agent_type] = {
                "buy": round((sum(d["weight"] for d in type_decisions if d["action"] == "buy") / tw) * 100, 1),
                "sell": round((sum(d["weight"] for d in type_decisions if d["action"] == "sell") / tw) * 100, 1),
                "hold": round((sum(d["weight"] for d in type_decisions if d["action"] == "hold") / tw) * 100, 1),
            }

        # Find the highest conviction type
        type_max_buy = max(types, key=lambda t: type_stats[t]["buy"])
        type_max_sell = max(types, key=lambda t: type_stats[t]["sell"])

        # Panic-specific: PanicSeller + BadNewsOverreactor sell %
        panic_agents = [
            d for d in round1_results
            if d["agent_name"].startswith(("Panic_Seller", "Bad_News_Overreactor"))
        ]
        panic_sell_count = sum(1 for d in panic_agents if d["action"] == "sell")
        panic_sell_pct = (panic_sell_count / max(len(panic_agents), 1)) * 100

        # Institutional buy %
        inst_decisions = [d for d in round1_results if d["agent_type"] == "institutional"]
        inst_buy_count = sum(1 for d in inst_decisions if d["action"] == "buy")
        inst_buy_pct = (inst_buy_count / max(len(inst_decisions), 1)) * 100

        # Build the summary string
        ticker = round1_results[0].get("ticker", "") if round1_results else ""

        summary = (
            f"Round 1 results:\n"
            f"Overall: {buy_pct:.0f}% BUY, {sell_pct:.0f}% SELL, {hold_pct:.0f}% HOLD\n"
            f"By type:\n"
            f"  Retail agents: {type_stats['retail']['buy']}% buying, "
            f"{type_stats['retail']['sell']}% selling\n"
            f"  Institutional: {type_stats['institutional']['buy']}% buying, "
            f"{type_stats['institutional']['sell']}% selling\n"
            f"  Algo agents: {type_stats['algo']['buy']}% buying, "
            f"{type_stats['algo']['sell']}% selling\n"
            f"  News reactors: {type_stats['news_reactor']['buy']}% buying, "
            f"{type_stats['news_reactor']['sell']}% selling\n"
            f"\n"
            f"Notable: {type_max_buy} showing strongest BUY signal.\n"
            f"Panic agents: {panic_sell_pct:.0f}% selling.\n"
            f"Institutional agents: {inst_buy_pct:.0f}% buying."
        )

        return summary

    # -------------------------------------------------------------------
    # Round 2 — Social influence (agents see crowd summary)
    # -------------------------------------------------------------------
    async def run_round2(
        self,
        market_data: dict,
        crowd_summary: str,
        round1_results: list[dict],
        on_decision: Optional[callable] = None
    ) -> list[dict]:
        """
        Run ALL 80 agents in parallel (Round 2) — now they see the crowd.

        Some agents ignore crowd_summary (SIPInvestor, NoiseIgnorer, RSIBot,
        etc.) — this is handled inside their personality classes.

        Returns:
            List of 80 final decision dicts
        """
        start = time.time()
        ticker = market_data.get("ticker", "UNKNOWN")

        logger.info(f"Round 2 starting for {ticker} — {len(self.agents)} agents")

        tasks = [
            self._run_agent_with_timeout(
                agent.decide_round2(market_data, crowd_summary, on_action=on_decision), agent
            )
            for agent in self.agents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        decisions = []
        errors = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors += 1
                agent = self.agents[i]
                decisions.append({
                    "agent_name": agent.name,
                    "agent_type": agent.agent_type,
                    "weight": agent.weight,
                    "round": 2,
                    "action": "hold",
                    "confidence": 0.1,
                    "reasoning": f"agent error — defaulting to hold ({type(result).__name__})",
                })
                log_swarm_decision(
                    ticker=ticker,
                    agent_name=agent.name,
                    agent_type=agent.agent_type,
                    round_num=2,
                    action="hold",
                    confidence=0.1,
                    reasoning=f"error: {type(result).__name__}",
                )
                if on_decision:
                    on_decision(decisions[-1])
            else:
                decisions.append(result)
                log_swarm_decision(
                    ticker=ticker,
                    agent_name=result["agent_name"],
                    agent_type=result["agent_type"],
                    round_num=2,
                    action=result["action"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                )
                if on_decision:
                    on_decision(result)

        # Log summary and conviction shift
        n_buy = sum(1 for d in decisions if d["action"] == "buy")
        n_sell = sum(1 for d in decisions if d["action"] == "sell")
        n_hold = sum(1 for d in decisions if d["action"] == "hold")
        elapsed = time.time() - start

        r1_buy = sum(1 for d in round1_results if d["action"] == "buy")

        logger.info(
            f"Round 2 complete for {ticker}: "
            f"{n_buy} buy, {n_sell} sell, {n_hold} hold "
            f"({errors} errors) in {elapsed:.1f}s"
        )
        logger.info(
            f"Conviction shift: Round1={r1_buy} buy → Round2={n_buy} buy "
            f"(shift: {n_buy - r1_buy:+d})"
        )

        return decisions

    # -------------------------------------------------------------------
    # Main public method — runs the complete swarm analysis
    # -------------------------------------------------------------------
    async def run(self, ticker: str, on_decision: Optional[callable] = None) -> dict:
        """
        Run the complete 2-round swarm analysis for a stock.

        Steps:
          1. Prepare market data (price, indicators, news, FII/DII)
          2. Round 1: all 80 agents decide independently in parallel
          3. Build crowd summary from Round 1
          4. Round 2: agents see crowd and can revise
          5. Return complete results

        Args:
            ticker: NSE ticker (e.g. RELIANCE.NS)

        Returns:
            Dict with ticker, market_data, round1/round2 results,
            crowd_summary, and timing info
        """
        overall_start = time.time()

        logger.info(f"{'='*60}")
        logger.info(f"SWARM RUN: {ticker}")
        logger.info(f"{'='*60}")

        # Step 1: Prepare market data
        market_data = await self.prepare_market_data(ticker)

        # Step 2: Round 1 — independent decisions
        round1_results = await self.run_round1(market_data, on_decision=on_decision)

        # Step 3: Build crowd summary
        crowd_summary = self.build_crowd_summary(round1_results)

        # Step 4: Round 2 — social influence
        round2_results = await self.run_round2(
            market_data, crowd_summary, round1_results, on_decision=on_decision
        )

        # Step 4.5: Calculate actual influence edges
        import random
        influence_edges = []
        r1_map = {r.get("agent_name"): r for r in round1_results if r.get("agent_name")}
        r2_map = {r.get("agent_name"): r for r in round2_results if r.get("agent_name")}
        
        influencers_buy = [name for name, r in r2_map.items() if r.get("action") == "buy" and r.get("confidence", 0) > 0.7 and r.get("agent_type") in ("institutional", "algo") and r1_map.get(name, {}).get("action") == "buy"]
        influencers_sell = [name for name, r in r2_map.items() if r.get("action") == "sell" and r.get("confidence", 0) > 0.7 and r.get("agent_type") in ("institutional", "algo") and r1_map.get(name, {}).get("action") == "sell"]

        for name, r2 in r2_map.items():
            r1 = r1_map.get(name)
            if not r1: continue
            if r1.get("action") != r2.get("action"):
                # Agent changed their mind
                influencer = None
                if r2.get("action") == "buy" and influencers_buy:
                    influencer = random.choice(influencers_buy)
                elif r2.get("action") == "sell" and influencers_sell:
                    influencer = random.choice(influencers_sell)
                
                if influencer:
                    influence_edges.append({
                        "source": influencer,
                        "target": name,
                        "direction": r2.get("action")
                    })

        # Step 5: Compile results
        total_time = time.time() - overall_start

        logger.info(f"SWARM RUN COMPLETE for {ticker} in {total_time:.1f}s")
        logger.info(f"{'='*60}")

        return {
            "ticker": ticker,
            "market_data": market_data,
            "round1_results": round1_results,
            "round2_results": round2_results,
            "influence_edges": influence_edges,
            "crowd_summary": crowd_summary,
            "timing": {
                "total_seconds": round(total_time, 2),
                "agent_count": len(self.agents),
            },
        }

    # -------------------------------------------------------------------
    # Helper: Run a single agent with timeout
    # -------------------------------------------------------------------
    async def _run_agent_with_timeout(
        self, coro, agent
    ) -> dict:
        """Wrap an agent coroutine with a timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=self._agent_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Agent {agent.name} timed out after {self._agent_timeout}s"
            )
            return {
                "agent_name": agent.name,
                "agent_type": agent.agent_type,
                "weight": agent.weight,
                "round": 0,
                "action": "hold",
                "confidence": 0.1,
                "reasoning": "agent timed out — defaulting to hold",
            }
