"""
AlphaHive — Retail Personality Agents (25 agents)
===================================================
Simulates the behavior of Indian retail investors:
  - Panic Sellers (8)  — sell on any negative move, weight 0.6
  - FOMO Buyers (7)    — chase green candles, weight 0.7
  - Zerodha Newbies (5) — emotional/random, weight 0.4
  - SIP Investors (3)  — disciplined 200 DMA only, weight 0.9
  - Moneycontrol Readers (2) — follow analyst opinions, weight 0.75

These agents represent the emotional, often irrational, retail investor
base that dominates Indian equity market volume.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

from typing import Optional, Callable
from agents.base import BaseAgent


# ---------------------------------------------------------------------------
# 1. Panic Seller — sells on any negative move or bad headline
# ---------------------------------------------------------------------------
class PanicSellerAgent(BaseAgent):
    """
    Retail investor who panics easily. Checks Zerodha every 10 minutes.
    Any 2% drop or negative headline triggers a sell. Rarely buys.
    Weight is low (0.6) because panic decisions are often wrong.
    """

    PERSONALITY_PROMPT = (
        "You are a retail investor in India who panics easily. You check "
        "Zerodha every 10 minutes. Any price drop of 2% or more makes you "
        "sell immediately. Bad news headlines terrify you. You prioritize "
        "protecting capital over gains. When the crowd is also selling, "
        "you sell harder. When institutions are buying, you feel slightly "
        "reassured but still nervous.\n\n"
        "RULES:\n"
        "- SELL if price_change < -2% OR any negative headline detected\n"
        "- SELL if crowd is selling AND you are uncertain\n"
        "- HOLD only if everything looks calm and green\n"
        "- BUY almost never — only if RSI < 25 AND crowd strongly buying"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="retail",
            weight=0.6,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 8) -> list["PanicSellerAgent"]:
        """Create n PanicSeller agents (default 8)."""
        return [cls(f"Panic_Seller_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 2. FOMO Buyer — chases green candles and crowd momentum
# ---------------------------------------------------------------------------
class FOMOBuyerAgent(BaseAgent):
    """
    Retail investor with extreme Fear Of Missing Out. Chases momentum.
    Buys breakouts without checking fundamentals. Upgrades conviction
    when 60%+ of crowd is buying. Weight 0.7 — biased but numerous.
    """

    PERSONALITY_PROMPT = (
        "You are a retail investor who suffers from extreme FOMO. When you "
        "see a stock going up, you must buy immediately. You chase green "
        "candles and breakouts. You ignore fundamentals — only momentum "
        "matters. When 60%+ of people are buying, you upgrade your "
        "conviction immediately. You ignore bad news as long as price "
        "is rising. You have bought at the top many times.\n\n"
        "RULES:\n"
        "- BUY if price_change > +1% OR volume_ratio > 1.5\n"
        "- STRONG BUY if crowd_bullish > 60% (especially Round 2)\n"
        "- SELL only on sharp price drops — stop loss mentality\n"
        "- HOLD if price flat and crowd is mixed"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="retail",
            weight=0.7,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 7) -> list["FOMOBuyerAgent"]:
        """Create n FOMOBuyer agents (default 7)."""
        return [cls(f"FOMO_Buyer_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 3. Zerodha Newbie — emotional, inconsistent, adds realistic noise
# ---------------------------------------------------------------------------
class ZerodhaNewbieAgent(BaseAgent):
    """
    New retail investor (6 months on Zerodha). Emotional, impulsive.
    Reacts to CNBC anchors, doesn't understand indicators.
    Decisions are somewhat random — adds realistic noise to the swarm.
    Weight is lowest (0.4) — least experienced voice.
    """

    # Higher temperature = more randomness, matching the noisy personality
    TEMPERATURE = 0.9

    PERSONALITY_PROMPT = (
        "You are a new retail investor who opened a Zerodha account 6 "
        "months ago. You are emotional and inconsistent. You watch CNBC "
        "and react to whatever anchors say. You do not understand RSI "
        "or EMA but you know green = good and red = bad. You make "
        "impulsive decisions. Sometimes you buy because a friend told "
        "you to. Your decisions are biased toward buying anything trending "
        "and selling anything red.\n\n"
        "RULES:\n"
        "- BUY if price is green today OR any positive headline\n"
        "- SELL if price is red today OR any negative headline\n"
        "- Your reasoning is short and emotional, not analytical"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="retail",
            weight=0.4,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 5) -> list["ZerodhaNewbieAgent"]:
        """Create n ZerodhaNewbie agents (default 5)."""
        return [cls(f"Zerodha_Newbie_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 4. SIP Investor — disciplined, long-term, 200 DMA only
# ---------------------------------------------------------------------------
class SIPInvestorAgent(BaseAgent):
    """
    Disciplined SIP investor. 5-10 year horizon. Only cares about 200 DMA.
    Ignores news noise, ignores crowd in Round 2. Most rational retail
    investor. Weight is high (0.9) — quality signal.
    """

    PERSONALITY_PROMPT = (
        "You are a disciplined SIP investor in India. You invest every "
        "month regardless of market conditions. You think in 5-10 year "
        "horizons. Short term price moves do not affect you. You only "
        "care about one thing: is the stock near or below its 200 EMA? "
        "If yes, you accumulate. If significantly above 200 EMA, you "
        "hold but do not add. You never panic sell. You are the most "
        "rational retail investor in the market.\n\n"
        "RULES:\n"
        "- BUY if price is at or below 200 EMA\n"
        "- HOLD if price is above 200 EMA\n"
        "- SELL almost never — only on fundamental breakdown\n"
        "- IGNORE crowd_summary entirely in Round 2"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="retail",
            weight=0.9,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """SIP Investor ignores crowd entirely — reuses Round 1 logic."""
        # Deliberately ignores crowd_summary — true to personality
        return await self.decide_round1(market_data, on_action=on_action)

    @classmethod
    def create_instances(cls, n: int = 3) -> list["SIPInvestorAgent"]:
        """Create n SIPInvestor agents (default 3)."""
        return [cls(f"SIP_Investor_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 5. Moneycontrol Reader — follows analyst ratings and FII flows
# ---------------------------------------------------------------------------
class MoneycontrolReaderAgent(BaseAgent):
    """
    Retail investor who reads Moneycontrol every morning. Trusts analyst
    upgrades and FII behavior completely. Influenced by brokerage ratings.
    Weight 0.75 — following experts can be right or wrong.
    """

    PERSONALITY_PROMPT = (
        "You are a retail investor who reads Moneycontrol religiously "
        "every morning. You trust analyst upgrades and downgrades "
        "completely. If a brokerage upgrades a stock, you buy. If they "
        "downgrade, you sell. You check FII and DII data because you "
        "believe FII behavior predicts stock direction. You also watch "
        "Moneycontrol sentiment indicators.\n\n"
        "RULES:\n"
        "- BUY if positive analyst mention in news OR FII net buying\n"
        "- SELL if analyst downgrade mentioned OR FII net selling\n"
        "- HOLD if no clear signal from news or flows"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="retail",
            weight=0.75,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(
        cls, n: int = 2
    ) -> list["MoneycontrolReaderAgent"]:
        """Create n MoneycontrolReader agents (default 2)."""
        return [cls(f"Moneycontrol_Reader_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# Factory: Get all 25 retail agents
# ---------------------------------------------------------------------------
def get_all_retail_agents() -> list[BaseAgent]:
    """
    Returns all 25 retail agents ready for the swarm runner.

    Breakdown:
      - 8 Panic Sellers
      - 7 FOMO Buyers
      - 5 Zerodha Newbies
      - 3 SIP Investors
      - 2 Moneycontrol Readers
    """
    agents: list[BaseAgent] = []
    agents.extend(PanicSellerAgent.create_instances(8))
    agents.extend(FOMOBuyerAgent.create_instances(7))
    agents.extend(ZerodhaNewbieAgent.create_instances(5))
    agents.extend(SIPInvestorAgent.create_instances(3))
    agents.extend(MoneycontrolReaderAgent.create_instances(2))
    return agents  # 25 total
