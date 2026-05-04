"""
AlphaHive — BaseAgent Class
=============================
The foundation class that all 80 swarm personality agents inherit from.
Handles everything common across agents so personality files stay clean.

Responsibilities:
  - Ollama LLM calls via httpx (async)
  - JSON response parsing with graceful fallbacks
  - Round 1 (independent decision) and Round 2 (social influence) methods
  - Agent identity (name, type, weight, personality prompt)

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import json
import logging
import os
import re
from typing import Optional, Callable

import httpx

logger = logging.getLogger("alphahive.agents.base")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class AgentError(Exception):
    """Raised when an agent encounters an unrecoverable error."""
    pass


# ---------------------------------------------------------------------------
# BaseAgent — All 80 swarm agents inherit from this
# ---------------------------------------------------------------------------
class BaseAgent:
    """
    Base class for all AlphaHive swarm agents.

    Each personality subclass overrides __init__ to set its own
    personality_prompt — the system prompt that shapes how the agent thinks.

    Attributes:
        name:             Unique identifier (e.g. "Panic_Seller_03")
        agent_type:       Category — "retail" | "institutional" | "algo" | "news_reactor"
        weight:           How much this agent's vote counts in aggregation
        personality_prompt: System prompt defining the agent's psychology
    """

    # Default Ollama settings — subclasses can override
    OLLAMA_URL: str = "http://localhost:11434/api/chat"
    TEMPERATURE: float = 0.7
    NUM_PREDICT: int = 150
    TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        name: str,
        agent_type: str,
        weight: float,
        personality_prompt: str,
    ) -> None:
        self.name = name
        self.agent_type = agent_type
        self.weight = weight
        self.personality_prompt = personality_prompt

    def __repr__(self) -> str:
        return f"{self.name}(type={self.agent_type}, weight={self.weight})"

    # -------------------------------------------------------------------
    # Round 1 — Independent decision (no crowd knowledge)
    # -------------------------------------------------------------------
    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        """
        Run the agent's Round 1 decision — no knowledge of other agents.

        Args:
            market_data: Dict with ticker, price, indicators, news_headlines,
                         fii_dii_flow, etc.
            on_action: Optional callback for granular telemetry

        Returns:
            Decision dict: {agent_name, agent_type, weight, round, action,
                           confidence, reasoning}
        """
        if on_action:
            on_action(self, "Analyzing technical indicators and price action...")
        
        system_prompt = self._build_round1_system_prompt()
        user_prompt = self._format_market_data(market_data)

        try:
            if on_action:
                on_action(self, "Running independent reasoning via LLM...")
            response_text = await self._call_ollama(system_prompt, user_prompt)
            decision = self._parse_decision(response_text)
        except (AgentError, Exception) as e:
            logger.warning(f"Agent {self.name} Round 1 error: {e}")
            decision = {
                "action": "hold",
                "confidence": 0.1,
                "reasoning": "agent error — defaulting to hold",
            }

        return {
            "agent_name": self.name,
            "agent_type": self.agent_type,
            "weight": self.weight,
            "round": 1,
            "action": decision["action"],
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
        }

    # -------------------------------------------------------------------
    # Round 2 — Social influence (sees crowd summary)
    # -------------------------------------------------------------------
    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """
        Round 2 decision — agent now sees what the crowd decided in Round 1.

        Some personalities ignore crowd_summary entirely (SIP_Investor,
        Noise_Ignorer, RSI_Bot, etc.) — this is handled inside each
        personality subclass by overriding this method.

        Args:
            market_data:   Same market data dict from Round 1
            crowd_summary: Human-readable summary of Round 1 aggregate results
            on_action:     Optional callback for granular telemetry

        Returns:
            Decision dict: same structure as Round 1, with "round": 2
        """
        if on_action:
            on_action(self, "Reviewing Round 1 crowd behavior summary...")
            
        system_prompt = self._build_round2_system_prompt()
        user_prompt = self._format_market_data_with_crowd(
            market_data, crowd_summary
        )

        try:
            if on_action:
                on_action(self, "Synthesizing social influence vs own bias...")
            response_text = await self._call_ollama(system_prompt, user_prompt)
            decision = self._parse_decision(response_text)
        except (AgentError, Exception) as e:
            logger.warning(f"Agent {self.name} Round 2 error: {e}")
            decision = {
                "action": "hold",
                "confidence": 0.1,
                "reasoning": "agent error — defaulting to hold",
            }

        return {
            "agent_name": self.name,
            "agent_type": self.agent_type,
            "weight": self.weight,
            "round": 2,
            "action": decision["action"],
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
        }

    # -------------------------------------------------------------------
    # Interview — Direct interaction with user
    # -------------------------------------------------------------------
    async def interview(self, query: str, context: dict) -> str:
        """
        Allows a user to "chat" with this agent about its decisions.

        Args:
            query:   The user's question (e.g. "Why did you buy?")
            context: The data the agent had during the simulation
                     (market_data, its own previous decisions, etc.)

        Returns:
            The agent's response in its personality.
        """
        system_prompt = (
            f"{self.personality_prompt}\n\n"
            "INSTRUCTIONS:\n"
            "A retail investor is interviewing you about your recent market behavior.\n"
            "Stay in character. Explain your reasoning based on the data provided.\n"
            "Be concise (2-3 sentences max). Do NOT provide investment advice.\n"
            "Mandatory closing: 'All trading decisions are your own.'"
        )

        # Build a context-rich user prompt
        decision_history = context.get("decision_history", [])
        history_text = "\n".join([
            f"Round {d['round']}: {d['action'].upper()} (Confidence: {d['confidence']:.1f}, Reasoning: {d['reasoning']})"
            for d in decision_history
        ])

        market_data = context.get("market_data", {})
        market_text = self._format_market_data(market_data)

        user_prompt = (
            f"INTERVIEW QUESTION: {query}\n\n"
            f"YOUR DECISION HISTORY:\n{history_text}\n\n"
            f"MARKET CONTEXT AT TIME OF DECISION:\n{market_text}\n"
        )

        try:
            response = await self._call_ollama(system_prompt, user_prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Interview failed for {self.name}: {e}")
            return (
                f"As a {self.agent_type} participant, my logic is currently "
                f"re-calibrating. {e}. All trading decisions are your own."
            )

    # -------------------------------------------------------------------
    # Ollama LLM call
    # -------------------------------------------------------------------
    async def _call_ollama(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """
        Call Ollama HTTP API with the given prompts.

        Uses httpx async for non-blocking requests.
        Model defaults to llama3.2:3b (fast for swarm).

        Returns:
            The raw response text from the LLM.

        Raises:
            AgentError: If the call fails or times out.
        """
        model = os.getenv("OLLAMA_SWARM_MODEL", "llama3.2:3b")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self.TEMPERATURE,
                "num_predict": self.NUM_PREDICT,
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.TIMEOUT_SECONDS
            ) as client:
                response = await client.post(self.OLLAMA_URL, json=payload)
                response.raise_for_status()

                data = response.json()
                content = data.get("message", {}).get("content", "")
                if not content:
                    raise AgentError(
                        f"Empty response from Ollama for agent {self.name}"
                    )
                return content

        except httpx.TimeoutException:
            raise AgentError(
                f"Ollama timed out ({self.TIMEOUT_SECONDS}s) for {self.name}"
            )
        except httpx.HTTPStatusError as e:
            raise AgentError(
                f"Ollama HTTP error {e.response.status_code} for {self.name}"
            )
        except Exception as e:
            raise AgentError(f"Ollama call failed for {self.name}: {e}")

    # -------------------------------------------------------------------
    # Parse the LLM's decision response
    # -------------------------------------------------------------------
    def _parse_decision(self, response_text: str) -> dict:
        """
        Parse the LLM response into {action, confidence, reasoning}.

        Strategy:
          1. Try to parse as JSON directly
          2. Try to extract JSON from markdown code blocks
          3. Fallback: regex extract action/confidence from raw text
          4. Last resort: return neutral hold

        Returns:
            Dict with action (buy/sell/hold), confidence (0.0-1.0), reasoning
        """
        # Strategy 1: Direct JSON parse
        try:
            parsed = json.loads(response_text.strip())
            return self._validate_decision(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Extract JSON from markdown code blocks
        json_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
        )
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                return self._validate_decision(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 2b: Find any JSON-like object in the text
        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                return self._validate_decision(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: Regex extraction from raw text
        text_lower = response_text.lower()
        action = "hold"  # default
        if "buy" in text_lower and "sell" not in text_lower:
            action = "buy"
        elif "sell" in text_lower and "buy" not in text_lower:
            action = "sell"
        elif "buy" in text_lower and "sell" in text_lower:
            # Both mentioned — pick whichever appears first
            buy_pos = text_lower.index("buy")
            sell_pos = text_lower.index("sell")
            action = "buy" if buy_pos < sell_pos else "sell"

        # Try to extract confidence
        confidence = 0.5
        conf_match = re.search(r"confidence[\":\s]*([0-9.]+)", text_lower)
        if conf_match:
            try:
                confidence = float(conf_match.group(1))
                if confidence > 1.0:
                    confidence = confidence / 100.0
            except ValueError:
                confidence = 0.5

        logger.debug(
            f"Agent {self.name}: JSON parse failed, extracted from text: "
            f"action={action}, confidence={confidence}"
        )

        return {
            "action": action,
            "confidence": max(0.0, min(1.0, confidence)),
            "reasoning": response_text[:100].strip(),
        }

    def _validate_decision(self, parsed: dict) -> dict:
        """Validate and normalize a parsed decision dict."""
        action = str(parsed.get("action", "hold")).lower().strip()
        if action not in ("buy", "sell", "hold"):
            action = "hold"

        confidence = float(parsed.get("confidence", 0.5))
        if confidence > 1.0:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))

        reasoning = str(parsed.get("reasoning", "no reasoning provided"))
        # Truncate long reasoning
        if len(reasoning) > 200:
            reasoning = reasoning[:197] + "..."

        return {
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    # -------------------------------------------------------------------
    # Prompt builders
    # -------------------------------------------------------------------
    def _build_round1_system_prompt(self) -> str:
        """Build the system prompt for Round 1 (independent decision)."""
        return (
            f"{self.personality_prompt}\n\n"
            "INSTRUCTIONS:\n"
            "You are making an INDEPENDENT market decision. No one else's "
            "opinion matters in this round.\n"
            "Analyze the market data provided and decide: buy, sell, or hold.\n"
            "Respond ONLY with a JSON object, nothing else:\n"
            '{"action": "buy"|"sell"|"hold", '
            '"confidence": 0.0 to 1.0, '
            '"reasoning": "one sentence max"}'
        )

    def _build_round2_system_prompt(self) -> str:
        """Build the system prompt for Round 2 (social influence)."""
        return (
            f"{self.personality_prompt}\n\n"
            "INSTRUCTIONS:\n"
            "You have now seen what other market participants decided in "
            "Round 1. Their crowd summary is included in the data below.\n"
            "Based on your personality, decide if you want to:\n"
            "  - STICK with your previous view\n"
            "  - CHANGE your action based on crowd behavior\n"
            "Respond ONLY with a JSON object, nothing else:\n"
            '{"action": "buy"|"sell"|"hold", '
            '"confidence": 0.0 to 1.0, '
            '"reasoning": "one sentence max"}'
        )

    # -------------------------------------------------------------------
    # Data formatters
    # -------------------------------------------------------------------
    def _format_market_data(self, market_data: dict) -> str:
        """Format market data as a readable text block for agent prompts."""
        ticker = market_data.get("ticker", "UNKNOWN")
        price = market_data.get("price", "N/A")
        change_pct = market_data.get("price_change_pct", "N/A")
        volume_ratio = market_data.get("volume_ratio", "N/A")

        indicators = market_data.get("indicators", {})
        rsi = indicators.get("rsi_14", "N/A")
        ema_50 = indicators.get("ema_50", "N/A")
        ema_200 = indicators.get("ema_200", "N/A")
        atr = indicators.get("atr_14", "N/A")

        headlines = market_data.get("news_headlines", [])
        news_text = "\n".join(f"  - {h}" for h in headlines[:5]) if headlines else "  No recent news"

        fii_dii = market_data.get("fii_dii", {})
        fii_net = fii_dii.get("fii_net", "N/A")
        dii_net = fii_dii.get("dii_net", "N/A")
        fii_sentiment = fii_dii.get("fii_sentiment", "UNKNOWN")

        price_vs_200 = market_data.get("price_vs_200ema", "N/A")

        return (
            f"STOCK: {ticker}\n"
            f"PRICE: ₹{price} (Change: {change_pct}%)\n"
            f"VOLUME RATIO: {volume_ratio}x vs 30-day avg\n"
            f"\nTECHNICAL INDICATORS:\n"
            f"  RSI(14): {rsi}\n"
            f"  EMA(50): {ema_50}\n"
            f"  EMA(200): {ema_200}\n"
            f"  ATR(14): {atr}\n"
            f"  Price vs 200 EMA: {price_vs_200}\n"
            f"\nNEWS HEADLINES:\n{news_text}\n"
            f"\nINSTITUTIONAL FLOWS:\n"
            f"  FII Net: {fii_net} crores ({fii_sentiment})\n"
            f"  DII Net: {dii_net} crores\n"
        )

    def _format_market_data_with_crowd(
        self, market_data: dict, crowd_summary: str
    ) -> str:
        """Format market data + crowd summary for Round 2 prompts."""
        base = self._format_market_data(market_data)
        return (
            f"{base}\n"
            f"{'='*50}\n"
            f"CROWD BEHAVIOR (Round 1 Results):\n"
            f"{crowd_summary}\n"
            f"{'='*50}\n"
        )

    # -------------------------------------------------------------------
    # Class method for creating multiple instances
    # -------------------------------------------------------------------
    @classmethod
    def create_instances(cls, n: int) -> list["BaseAgent"]:
        """
        Create n instances of this agent class with numbered names.

        Override in subclasses to set the correct personality_prompt,
        weight, and agent_type.

        Args:
            n: Number of instances to create

        Returns:
            List of n agent instances
        """
        raise NotImplementedError(
            "Subclasses must implement create_instances()"
        )
