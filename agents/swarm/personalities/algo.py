"""
AlphaHive — Algo Personality Agents (20 agents)
=================================================
Simulates algorithmic trading bots — more deterministic than retail:
  - RSI Bot (5)              — pure RSI signal, weight 1.0
  - EMA Crossover Bot (5)    — 50/200 EMA cross, weight 1.0
  - Volume Breakout Bot (4)  — volume > 2x avg trigger, weight 1.0
  - Mean Reversion Bot (4)   — bets against extreme moves, weight 0.9
  - Arbitrage Bot (2)        — sector rotation, weight 1.1

Algo agents use LOWER temperature (0.3) for more deterministic output.
They ignore crowd in Round 2 — pure rules, no social influence.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

from typing import Optional, Callable
from agents.base import BaseAgent


def _indicator_value(market_data: dict, key: str) -> float | None:
    indicators = market_data.get("indicators", {}) if isinstance(market_data, dict) else {}
    value = indicators.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _make_decision(
    agent: BaseAgent,
    action: str,
    confidence: float,
    reasoning: str,
    round_number: int,
) -> dict:
    return {
        "agent_name": agent.name,
        "agent_type": agent.agent_type,
        "weight": agent.weight,
        "round": round_number,
        "action": action,
        "confidence": max(0.0, min(1.0, round(confidence, 2))),
        "reasoning": reasoning[:200],
    }


# ---------------------------------------------------------------------------
# 1. RSI Bot — pure RSI signal, nothing else
# ---------------------------------------------------------------------------
class RSIBotAgent(BaseAgent):
    """
    Pure RSI trading algorithm. One rule: buy < 30, sell > 70, hold otherwise.
    Ignores news, fundamentals, and crowd. Mechanical and deterministic.
    Represents thousands of simple momentum algos running in markets.
    """

    TEMPERATURE = 0.3  # More deterministic for algo agents

    PERSONALITY_PROMPT = (
        "You are a pure RSI trading algorithm. You have ONE rule: buy when "
        "RSI is below 30 (oversold), sell when RSI is above 70 (overbought), "
        "hold otherwise. You do not care about news, fundamentals, or what "
        "other agents think. You are mechanical and never deviate from your "
        "RSI rule. Look at the RSI(14) value in the data and decide.\n\n"
        "RULES:\n"
        "- BUY if RSI < 30\n"
        "- SELL if RSI > 70\n"
        "- HOLD if RSI between 30 and 70\n"
        "- Confidence scales with how extreme the RSI is"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="algo",
            weight=1.0,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        if on_action:
            on_action(self, "Calculating RSI(14) from historical OHLCV...")
        rsi = _indicator_value(market_data, "rsi_14")
        if rsi is None:
            return _make_decision(
                self,
                action="hold",
                confidence=0.25,
                reasoning="RSI unavailable, so the bot waits for a valid reading.",
                round_number=1,
            )

        if rsi < 30:
            confidence = min(0.95, 0.55 + (30 - rsi) / 60)
            return _make_decision(
                self,
                action="buy",
                confidence=confidence,
                reasoning=f"RSI {rsi:.1f} is oversold, so the bot buys.",
                round_number=1,
            )

        if rsi > 70:
            confidence = min(0.95, 0.55 + (rsi - 70) / 60)
            return _make_decision(
                self,
                action="sell",
                confidence=confidence,
                reasoning=f"RSI {rsi:.1f} is overbought, so the bot sells.",
                round_number=1,
            )

        confidence = max(0.25, 0.6 - abs(rsi - 50) / 100)
        return _make_decision(
            self,
            action="hold",
            confidence=confidence,
            reasoning=f"RSI {rsi:.1f} sits in the neutral zone, so the bot holds.",
            round_number=1,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """RSI Bot ignores crowd — purely mechanical, no social influence."""
        if on_action:
            on_action(self, "Mechanical check: ignoring crowd consensus...")
        return await self._decision_round(market_data, round_number=2, on_action=on_action)

    async def _decision_round(self, market_data: dict, round_number: int, on_action: Optional[Callable] = None) -> dict:
        decision = await self.decide_round1(market_data, on_action=on_action)
        decision["round"] = round_number
        return decision

    @classmethod
    def create_instances(cls, n: int = 5) -> list["RSIBotAgent"]:
        """Create n RSI Bot agents (default 5)."""
        return [cls(f"RSI_Bot_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 2. EMA Crossover Bot — 50/200 EMA golden/death cross
# ---------------------------------------------------------------------------
class EMACrossoverBotAgent(BaseAgent):
    """
    EMA crossover algorithm. Golden Cross (50 EMA > 200 EMA) = BUY.
    Death Cross (50 EMA < 200 EMA) = SELL. Purely technical.
    Ignores all other inputs and crowd behavior.
    """

    TEMPERATURE = 0.3

    PERSONALITY_PROMPT = (
        "You are an EMA crossover algorithm. Golden Cross (50 EMA above "
        "200 EMA) means BUY. Death Cross (50 EMA below 200 EMA) means SELL. "
        "If neither cross has occurred recently, you HOLD. You are purely "
        "technical. You ignore all other inputs including news and crowd.\n\n"
        "RULES:\n"
        "- BUY if EMA(50) > EMA(200) — golden cross\n"
        "- SELL if EMA(50) < EMA(200) — death cross\n"
        "- HOLD if EMAs are very close (no clear cross)\n"
        "- Confidence based on how wide the EMA gap is"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="algo",
            weight=1.0,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        if on_action:
            on_action(self, "Checking 50/200 EMA crossover status...")
        ema_50 = _indicator_value(market_data, "ema_50")
        ema_200 = _indicator_value(market_data, "ema_200")
        if ema_50 is None or ema_200 is None:
            return _make_decision(
                self,
                action="hold",
                confidence=0.25,
                reasoning="EMA data is incomplete, so the bot waits.",
                round_number=1,
            )

        gap_pct = ((ema_50 - ema_200) / ema_200) * 100 if ema_200 else 0.0
        if ema_50 > ema_200 * 1.01:
            confidence = min(0.95, 0.55 + abs(gap_pct) / 20)
            return _make_decision(
                self,
                action="buy",
                confidence=confidence,
                reasoning=f"EMA(50) {ema_50:.2f} is above EMA(200) {ema_200:.2f}, so the bot buys.",
                round_number=1,
            )

        if ema_50 < ema_200 * 0.99:
            confidence = min(0.95, 0.55 + abs(gap_pct) / 20)
            return _make_decision(
                self,
                action="sell",
                confidence=confidence,
                reasoning=f"EMA(50) {ema_50:.2f} is below EMA(200) {ema_200:.2f}, so the bot sells.",
                round_number=1,
            )

        confidence = max(0.25, 0.55 - abs(gap_pct) / 50)
        return _make_decision(
            self,
            action="hold",
            confidence=confidence,
            reasoning=f"EMA gap is narrow ({gap_pct:.2f}%), so the bot holds.",
            round_number=1,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """EMA Bot ignores crowd — purely technical, no social influence."""
        if on_action:
            on_action(self, "Technical rule: ignoring crowd behavior...")
        decision = await self.decide_round1(market_data, on_action=on_action)
        decision["round"] = 2
        return decision

    @classmethod
    def create_instances(cls, n: int = 5) -> list["EMACrossoverBotAgent"]:
        """Create n EMA Crossover Bot agents (default 5)."""
        return [cls(f"EMA_Crossover_Bot_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 3. Volume Breakout Bot — volume > 2x average trigger
# ---------------------------------------------------------------------------
class VolumeBreakoutBotAgent(BaseAgent):
    """
    Volume breakout algorithm. Acts only when volume > 2x 30-day average.
    High volume + price UP = BUY. High volume + price DOWN = SELL.
    Normal volume = HOLD. Volume confirms institutional intent.
    """

    TEMPERATURE = 0.3

    PERSONALITY_PROMPT = (
        "You are a volume breakout algorithm. You only act when volume is "
        "greater than 2x the 30-day average. High volume with price UP is "
        "a BUY signal. High volume with price DOWN is a SELL signal. Normal "
        "volume means HOLD always. Volume confirms institutional intent — "
        "that is all you care about.\n\n"
        "RULES:\n"
        "- BUY if volume_ratio > 2.0 AND price_change > 0\n"
        "- SELL if volume_ratio > 2.0 AND price_change < 0\n"
        "- HOLD if volume_ratio < 2.0 (wait for volume confirmation)\n"
        "- Confidence scales with how extreme the volume spike is"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="algo",
            weight=1.0,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        if on_action:
            on_action(self, "Scanning for 2x volume breakout threshold...")
        volume_ratio = market_data.get("volume_ratio")
        price_change = market_data.get("price_change_pct")

        try:
            volume_ratio_value = float(volume_ratio) if volume_ratio is not None else None
        except (TypeError, ValueError):
            volume_ratio_value = None
        try:
            price_change_value = float(price_change) if price_change is not None else None
        except (TypeError, ValueError):
            price_change_value = None

        if volume_ratio_value is None or price_change_value is None:
            return _make_decision(
                self,
                action="hold",
                confidence=0.25,
                reasoning="Volume or price change is missing, so the bot waits.",
                round_number=1,
            )

        if volume_ratio_value > 2.0 and price_change_value > 0:
            confidence = min(0.95, 0.55 + (volume_ratio_value - 2.0) / 2 + min(price_change_value, 5) / 20)
            return _make_decision(
                self,
                action="buy",
                confidence=confidence,
                reasoning=f"Volume is {volume_ratio_value:.2f}x average and price is rising, so the bot buys.",
                round_number=1,
            )

        if volume_ratio_value > 2.0 and price_change_value < 0:
            confidence = min(0.95, 0.55 + (volume_ratio_value - 2.0) / 2 + min(abs(price_change_value), 5) / 20)
            return _make_decision(
                self,
                action="sell",
                confidence=confidence,
                reasoning=f"Volume is {volume_ratio_value:.2f}x average and price is falling, so the bot sells.",
                round_number=1,
            )

        confidence = max(0.25, 0.5 - abs(volume_ratio_value - 1.0) / 5)
        return _make_decision(
            self,
            action="hold",
            confidence=confidence,
            reasoning=f"Volume is only {volume_ratio_value:.2f}x average, so the bot waits for confirmation.",
            round_number=1,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """Volume Bot ignores crowd — purely volume-driven."""
        if on_action:
            on_action(self, "Ignoring social layer (pure volume algo)...")
        decision = await self.decide_round1(market_data, on_action=on_action)
        decision["round"] = 2
        return decision

    @classmethod
    def create_instances(cls, n: int = 4) -> list["VolumeBreakoutBotAgent"]:
        """Create n VolumeBreakout Bot agents (default 4)."""
        return [cls(f"Volume_Breakout_Bot_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 4. Mean Reversion Bot — contrarian to extreme moves
# ---------------------------------------------------------------------------
class MeanReversionBotAgent(BaseAgent):
    """
    Mean reversion algorithm. Believes extreme price moves revert to average.
    If stock up > 5% today, SELL (expect reversion). If down > 5%, BUY
    (expect bounce). Contrarian to momentum. Weight 0.9.
    """

    TEMPERATURE = 0.3

    PERSONALITY_PROMPT = (
        "You are a mean reversion algorithm. You believe extreme price moves "
        "revert to average. If a stock is up more than 5% today, you SELL "
        "(expect reversion down). If it is down more than 5% today, you BUY "
        "(expect bounce). You are contrarian to momentum. You bet against "
        "extreme single-day moves.\n\n"
        "RULES:\n"
        "- SELL if price_change > +5% today (overbought short-term)\n"
        "- BUY if price_change < -5% today (oversold short-term)\n"
        "- HOLD if price_change between -5% and +5%\n"
        "- Confidence scales with how extreme the move is"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="algo",
            weight=0.9,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        if on_action:
            on_action(self, "Calculating mean reversion deviation (5% threshold)...")
        price_change = market_data.get("price_change_pct")
        try:
            price_change_value = float(price_change) if price_change is not None else None
        except (TypeError, ValueError):
            price_change_value = None

        if price_change_value is None:
            return _make_decision(
                self,
                action="hold",
                confidence=0.25,
                reasoning="Price change is missing, so the bot waits.",
                round_number=1,
            )

        if price_change_value > 5.0:
            confidence = min(0.95, 0.55 + price_change_value / 20)
            return _make_decision(
                self,
                action="sell",
                confidence=confidence,
                reasoning=f"Price is up {price_change_value:.2f}% today, so the bot expects reversion and sells.",
                round_number=1,
            )

        if price_change_value < -5.0:
            confidence = min(0.95, 0.55 + abs(price_change_value) / 20)
            return _make_decision(
                self,
                action="buy",
                confidence=confidence,
                reasoning=f"Price is down {price_change_value:.2f}% today, so the bot expects a bounce and buys.",
                round_number=1,
            )

        confidence = max(0.25, 0.5 - abs(price_change_value) / 20)
        return _make_decision(
            self,
            action="hold",
            confidence=confidence,
            reasoning=f"Price change of {price_change_value:.2f}% is not extreme enough, so the bot holds.",
            round_number=1,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """Mean Reversion Bot ignores crowd — pure contrarian algo."""
        if on_action:
            on_action(self, "Applying contrarian logic to crowd consensus...")
        decision = await self.decide_round1(market_data, on_action=on_action)
        decision["round"] = 2
        return decision

    @classmethod
    def create_instances(cls, n: int = 4) -> list["MeanReversionBotAgent"]:
        """Create n MeanReversion Bot agents (default 4)."""
        return [cls(f"Mean_Reversion_Bot_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 5. Arbitrage Bot — sector rotation and relative strength
# ---------------------------------------------------------------------------
class ArbitrageBotAgent(BaseAgent):
    """
    Sector rotation and relative strength algorithm. Compares stock
    performance to its sector average. Outperforming sector = BUY (relative
    strength). Underperforming = SELL (relative weakness). Represents funds
    that rotate capital toward sector leaders. Weight 1.1.
    """

    TEMPERATURE = 0.3

    PERSONALITY_PROMPT = (
        "You are a sector rotation and relative strength algorithm. You "
        "compare the target stock's performance to its sector average. If "
        "the stock is outperforming its sector peers, you BUY (relative "
        "strength). If it is underperforming its peers, you SELL (relative "
        "weakness). You represent funds that rotate capital toward sector "
        "leaders.\n\n"
        "RULES:\n"
        "- BUY if stock outperforming sector average\n"
        "- SELL if stock underperforming sector average\n"
        "- HOLD if performance is near sector average\n"
        "- Use price_change relative to sector context"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="algo",
            weight=1.1,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round1(self, market_data: dict, on_action: Optional[Callable] = None) -> dict:
        if on_action:
            on_action(self, "Benchmarking stock against sector average...")
        price_change = market_data.get("price_change_pct")
        volume_ratio = market_data.get("volume_ratio")
        sector_context = market_data.get("sector_change_pct")

        try:
            price_change_value = float(price_change) if price_change is not None else None
        except (TypeError, ValueError):
            price_change_value = None
        try:
            volume_ratio_value = float(volume_ratio) if volume_ratio is not None else None
        except (TypeError, ValueError):
            volume_ratio_value = None
        try:
            sector_change_value = float(sector_context) if sector_context is not None else None
        except (TypeError, ValueError):
            sector_change_value = None

        if price_change_value is None:
            return _make_decision(
                self,
                action="hold",
                confidence=0.25,
                reasoning="Sector rotation context is incomplete, so the bot waits.",
                round_number=1,
            )

        relative_strength = price_change_value - (sector_change_value or 0.0)

        if sector_change_value is not None:
            if relative_strength > 1.0 and (volume_ratio_value or 1.0) >= 1.0:
                confidence = min(0.95, 0.55 + abs(relative_strength) / 10)
                return _make_decision(
                    self,
                    action="buy",
                    confidence=confidence,
                    reasoning=f"Stock is outperforming its sector by {relative_strength:.2f}%, so the bot buys.",
                    round_number=1,
                )
            if relative_strength < -1.0:
                confidence = min(0.95, 0.55 + abs(relative_strength) / 10)
                return _make_decision(
                    self,
                    action="sell",
                    confidence=confidence,
                    reasoning=f"Stock is underperforming its sector by {abs(relative_strength):.2f}%, so the bot sells.",
                    round_number=1,
                )

        if price_change_value > 1.5 and (volume_ratio_value or 1.0) > 1.2:
            confidence = min(0.9, 0.5 + price_change_value / 15)
            return _make_decision(
                self,
                action="buy",
                confidence=confidence,
                reasoning="No sector benchmark is available, but price and volume show relative strength.",
                round_number=1,
            )

        if price_change_value < -1.5:
            confidence = min(0.9, 0.5 + abs(price_change_value) / 15)
            return _make_decision(
                self,
                action="sell",
                confidence=confidence,
                reasoning="No sector benchmark is available, but the stock is weak on its own tape.",
                round_number=1,
            )

        confidence = max(0.25, 0.45 - abs(price_change_value) / 20)
        return _make_decision(
            self,
            action="hold",
            confidence=confidence,
            reasoning="Relative strength is inconclusive, so the bot holds.",
            round_number=1,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """Arbitrage Bot ignores crowd — purely algorithmic."""
        if on_action:
            on_action(self, "Ignoring crowd: executing sector rotation logic...")
        decision = await self.decide_round1(market_data, on_action=on_action)
        decision["round"] = 2
        return decision

    @classmethod
    def create_instances(cls, n: int = 2) -> list["ArbitrageBotAgent"]:
        """Create n Arbitrage Bot agents (default 2)."""
        return [cls(f"Arbitrage_Bot_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# Factory: Get all 20 algo agents
# ---------------------------------------------------------------------------
def get_all_algo_agents() -> list[BaseAgent]:
    """
    Returns all 20 algo agents ready for the swarm runner.

    Breakdown:
      - 5 RSI Bots
      - 5 EMA Crossover Bots
      - 4 Volume Breakout Bots
      - 4 Mean Reversion Bots
      - 2 Arbitrage Bots

    All algo agents ignore crowd_summary in Round 2 — purely rule-based.
    """
    agents: list[BaseAgent] = []
    agents.extend(RSIBotAgent.create_instances(5))
    agents.extend(EMACrossoverBotAgent.create_instances(5))
    agents.extend(VolumeBreakoutBotAgent.create_instances(4))
    agents.extend(MeanReversionBotAgent.create_instances(4))
    agents.extend(ArbitrageBotAgent.create_instances(2))
    return agents  # 20 total
