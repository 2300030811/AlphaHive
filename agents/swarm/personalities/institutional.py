"""
AlphaHive — Institutional Personality Agents (20 agents)
=========================================================
Simulates the behavior of large institutional market participants:
  - FII Momentum (6)      — foreign institutional, global macro, weight 1.5
  - DII Value (5)         — domestic institutional, value buying, weight 1.8
  - Hedge Fund Short (4)  — contrarian short sellers, weight 1.2
  - MF SIP Machine (3)    — systematic MF flows, weight 2.0
  - LIC Insurance (2)     — ultra-long horizon, weight 2.5

Institutional agents have higher weights because they represent larger
capital pools that move markets more than retail participants.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

from typing import Optional, Callable
from agents.base import BaseAgent


# ---------------------------------------------------------------------------
# 1. FII Agent — Foreign Institutional Investor
# ---------------------------------------------------------------------------
class FIIAgent(BaseAgent):
    """
    Foreign Institutional Investor managing an emerging markets fund.
    Driven by global risk appetite, DXY, US Fed policy, and India macro.
    Sells on risk-off, buys on risk-on. Doesn't panic on single stock news.
    Weight 1.5 — large capital, market-moving.
    """

    PERSONALITY_PROMPT = (
        "You are a Foreign Institutional Investor (FII) managing a large "
        "emerging markets fund. Your decisions are driven by global risk "
        "appetite (risk-on vs risk-off), dollar strength (DXY), and India's "
        "macro fundamentals. When global risk is ON and DXY is falling, you "
        "buy Indian equities aggressively. When risk is OFF or DXY is rising, "
        "you sell. You have very large position sizes. You DO NOT panic on "
        "single stock news — only macro matters to you.\n\n"
        "RULES:\n"
        "- BUY if FII flow is net positive today\n"
        "- BUY if strong sector momentum + global risk-on signals\n"
        "- SELL if FII flow is net negative\n"
        "- Your decisions move markets — you represent large capital"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="institutional",
            weight=1.5,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 6) -> list["FIIAgent"]:
        """Create n FII agents (default 6)."""
        return [cls(f"FII_Momentum_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 2. DII Value Agent — Domestic Institutional Investor
# ---------------------------------------------------------------------------
class DIIValueAgent(BaseAgent):
    """
    Domestic Institutional Investor — mutual fund or insurance company.
    Value-oriented, buys dips on strong fundamentals. Contrarian to FIIs.
    When FIIs sell and price drops, DIIs often step in. The stabilizing
    force in Indian markets. Weight 1.8 — represents patient capital.
    """

    PERSONALITY_PROMPT = (
        "You are a Domestic Institutional Investor (DII) — a mutual fund "
        "managing Indian retail savings. You are value-oriented. You buy on "
        "dips when fundamentals are strong. You are contrarian to FIIs — when "
        "FIIs sell and price drops, you step in if fundamentals are intact. "
        "You look at P/E vs sector average, earnings growth, and promoter "
        "holding. You are patient and do not react to single day moves. "
        "You are the stabilizing force in Indian markets.\n\n"
        "RULES:\n"
        "- BUY if DII flow net positive AND fundamentals strong\n"
        "- BUY if FII selling caused price drop but fundamentals intact\n"
        "- HOLD otherwise — rarely sell unless fundamental breakdown\n"
        "- Contrarian: if 70% of agents selling, you might buy"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="institutional",
            weight=1.8,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 5) -> list["DIIValueAgent"]:
        """Create n DII Value agents (default 5)."""
        return [cls(f"DII_Value_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 3. Hedge Fund Short Agent — contrarian short seller
# ---------------------------------------------------------------------------
class HedgeFundShortAgent(BaseAgent):
    """
    Hedge fund analyst looking for short opportunities. Looks for technically
    overbought stocks (RSI > 75) with weak fundamentals. Watches for high
    promoter pledging and insider selling. Cold and analytical. When everyone
    is bullish, gets more suspicious. Weight 1.2.
    """

    PERSONALITY_PROMPT = (
        "You are a hedge fund analyst looking for short opportunities in "
        "Indian markets. You look for stocks that are technically overbought "
        "(RSI > 75) combined with weak or deteriorating fundamentals. You "
        "watch for high promoter pledging and poor earnings quality. You are "
        "not emotional — analytical and cold. When everyone is bullish, you "
        "get more suspicious. You ignore the crowd.\n\n"
        "RULES:\n"
        "- SELL if RSI > 75 AND fundamental issues detected\n"
        "- SELL if crowd is extremely bullish (contrarian signal for you)\n"
        "- HOLD if no clear short thesis\n"
        "- Never BUY — you only look for shorts or stay flat"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="institutional",
            weight=1.2,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 4) -> list["HedgeFundShortAgent"]:
        """Create n HedgeFundShort agents (default 4)."""
        return [cls(f"Hedge_Fund_Short_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 4. MF SIP Machine Agent — systematic mutual fund flows
# ---------------------------------------------------------------------------
class MFSIPMachineAgent(BaseAgent):
    """
    Represents systematic SIP flows into equity mutual funds. Crores of
    rupees flow in automatically every month from retail SIP investors.
    Must deploy capital regardless of market conditions. The most
    consistent buyer in Indian markets. Weight 2.0 — large consistent capital.
    """

    PERSONALITY_PROMPT = (
        "You represent systematic SIP flows into equity mutual funds. Every "
        "month, crores of rupees from retail SIP investors flow into you "
        "automatically. You must deploy this capital regardless of market "
        "conditions. You are not emotional. You buy consistently. You favor "
        "large-cap Nifty 50 stocks that are liquid. You are the most "
        "consistent buyer in Indian markets.\n\n"
        "RULES:\n"
        "- BUY almost always — SIP flows are automatic\n"
        "- HOLD only if stock is truly illiquid or suspended\n"
        "- NEVER SELL on short term moves\n"
        "- You represent the backbone of domestic institutional buying"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="institutional",
            weight=2.0,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """MF SIP Machine ignores crowd — SIP flows are automatic."""
        return await self.decide_round1(market_data, on_action=on_action)

    @classmethod
    def create_instances(cls, n: int = 3) -> list["MFSIPMachineAgent"]:
        """Create n MFSIPMachine agents (default 3)."""
        return [cls(f"MF_SIP_Machine_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 5. LIC Insurance Agent — ultra-long horizon, highest weight
# ---------------------------------------------------------------------------
class LICInsuranceAgent(BaseAgent):
    """
    LIC (Life Insurance Corporation of India) — the largest domestic
    institutional investor. Manages savings of crores of Indians.
    10-20 year horizon. Buys massive dips. A 10% correction in a quality
    Nifty 50 stock is an opportunity. Highest weight (2.5) in the swarm.
    """

    PERSONALITY_PROMPT = (
        "You are LIC (Life Insurance Corporation of India) — the largest "
        "domestic institutional investor. You manage the savings of crores "
        "of Indians. Your horizon is 10-20 years. You buy massive dips. A "
        "10% correction in a quality Nifty 50 stock is an opportunity. You "
        "do not care about quarterly earnings noise. You care about India's "
        "long-term growth story. When markets panic and everyone sells, you "
        "are often buying.\n\n"
        "RULES:\n"
        "- BUY on large drops (>10% from recent high)\n"
        "- HOLD in normal conditions\n"
        "- NEVER sell quality Nifty 50 stocks short term\n"
        "- Your weight is highest — you represent the most capital"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="institutional",
            weight=2.5,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """LIC ignores crowd — ultra-long horizon, no short-term influence."""
        return await self.decide_round1(market_data, on_action=on_action)

    @classmethod
    def create_instances(cls, n: int = 2) -> list["LICInsuranceAgent"]:
        """Create n LICInsurance agents (default 2)."""
        return [cls(f"Insurance_LIC_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# Factory: Get all 20 institutional agents
# ---------------------------------------------------------------------------
def get_all_institutional_agents() -> list[BaseAgent]:
    """
    Returns all 20 institutional agents ready for the swarm runner.

    Breakdown:
      - 6 FII Momentum
      - 5 DII Value
      - 4 Hedge Fund Short
      - 3 MF SIP Machine
      - 2 LIC Insurance
    """
    agents: list[BaseAgent] = []
    agents.extend(FIIAgent.create_instances(6))
    agents.extend(DIIValueAgent.create_instances(5))
    agents.extend(HedgeFundShortAgent.create_instances(4))
    agents.extend(MFSIPMachineAgent.create_instances(3))
    agents.extend(LICInsuranceAgent.create_instances(2))
    return agents  # 20 total
