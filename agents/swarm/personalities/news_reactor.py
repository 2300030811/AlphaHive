"""
AlphaHive — News Reactor Personality Agents (15 agents)
========================================================
Simulates agents who primarily react to news headlines:
  - Bad News Overreactor (5)  — panic sells on negative keywords, weight 0.5
  - Good News Chaser (5)      — buys on positive keywords, weight 0.7
  - Noise Ignorer (3)         — ignores news entirely, weight 1.0
  - Analyst Follower (2)      — mirrors analyst ratings exactly, weight 1.3

These agents show how news sentiment flows through the market and
how different participants interpret the same information differently.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

from typing import Optional, Callable
from agents.base import BaseAgent


# ---------------------------------------------------------------------------
# 1. Bad News Overreactor — panic sells on any negative headline
# ---------------------------------------------------------------------------
class BadNewsOverreactorAgent(BaseAgent):
    """
    Overreacts to negative news. If any headline contains loss, decline,
    cut, downgrade, miss, warning, fraud, investigation, or fall — panic
    sells immediately. Assumes the worst interpretation of every negative
    word. Weight is low (0.5) because overreaction is often wrong.
    """

    PERSONALITY_PROMPT = (
        "You overreact to negative news. If any headline mentions: loss, "
        "decline, cut, downgrade, miss, warning, fraud, investigation, "
        "fall, or concern — you panic sell immediately. You assume the "
        "worst interpretation of every negative word. You represent retail "
        "investors who read scary headlines and sell without thinking.\n\n"
        "RULES:\n"
        "- SELL with high confidence if ANY negative keyword in headlines\n"
        "- HOLD if no negative headlines (you wait for bad news)\n"
        "- BUY almost never — only after full recovery from bad news\n"
        "- In Round 2, if crowd is also selling, you sell even harder"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="news_reactor",
            weight=0.5,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 5) -> list["BadNewsOverreactorAgent"]:
        """Create n BadNewsOverreactor agents (default 5)."""
        return [cls(f"Bad_News_Overreactor_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 2. Good News Chaser — buys aggressively on positive headlines
# ---------------------------------------------------------------------------
class GoodNewsChaserAgent(BaseAgent):
    """
    Chases positive news aggressively. If headlines mention beat, record,
    growth, upgrade, expansion, profit, win, new contract, or strong —
    buys immediately. Assumes positive headlines = stock goes up.
    Often buys after the price has already moved. Weight 0.7.
    """

    PERSONALITY_PROMPT = (
        "You chase positive news aggressively. If any headline mentions: "
        "beat, record, growth, upgrade, expansion, profit, win, new "
        "contract, strong, or outperform — you buy immediately. You "
        "assume positive headlines mean the stock will go up. You "
        "represent retail investors who buy on good news momentum. "
        "You often buy after the price has already moved.\n\n"
        "RULES:\n"
        "- BUY with high confidence if ANY positive keyword in headlines\n"
        "- HOLD if no positive headlines (you wait for good news)\n"
        "- SELL only on disappointing follow-through after good news\n"
        "- In Round 2, crowd buying amplifies your conviction"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="news_reactor",
            weight=0.7,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 5) -> list["GoodNewsChaserAgent"]:
        """Create n GoodNewsChaser agents (default 5)."""
        return [cls(f"Good_News_Chaser_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 3. Noise Ignorer — ignores news entirely, pure price action
# ---------------------------------------------------------------------------
class NoiseIgnorerAgent(BaseAgent):
    """
    Completely ignores news — believes news is already priced in.
    Only looks at price action and volume. In Round 2, also ignores
    what other agents decided. Pure price action trader. Weight 1.0 —
    balanced and rational approach.
    """

    PERSONALITY_PROMPT = (
        "You completely ignore news. You believe news is already priced in "
        "by the time you read it. You only look at price action and volume. "
        "News is noise. You are a pure price action trader. You also ignore "
        "what other agents decided — you only trust the chart.\n\n"
        "RULES:\n"
        "- BUY if price_change > 0 AND volume_ratio > 1.0 (price action)\n"
        "- SELL if price_change < -1% AND volume_ratio > 1.0\n"
        "- HOLD if no clear price action signal\n"
        "- IGNORE all news headlines completely\n"
        "- IGNORE crowd_summary in Round 2"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="news_reactor",
            weight=1.0,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    async def decide_round2(
        self, market_data: dict, crowd_summary: str, on_action: Optional[Callable] = None
    ) -> dict:
        """Noise Ignorer ignores crowd — pure price action, no influence."""
        return await self.decide_round1(market_data, on_action=on_action)

    @classmethod
    def create_instances(cls, n: int = 3) -> list["NoiseIgnorerAgent"]:
        """Create n NoiseIgnorer agents (default 3)."""
        return [cls(f"Noise_Ignorer_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# 4. Analyst Follower — mirrors analyst upgrades/downgrades exactly
# ---------------------------------------------------------------------------
class AnalystFollowerAgent(BaseAgent):
    """
    Follows analyst recommendations exactly. If news mentions a brokerage
    upgrade or higher target price, buys immediately. If downgrade or
    target cut, sells immediately. Trusts analysts completely. Represents
    retail investors relying on brokerage research. Weight 1.3 — analyst
    signals can be informative.
    """

    PERSONALITY_PROMPT = (
        "You follow analyst recommendations exactly. If news mentions a "
        "brokerage upgrading this stock with a higher target price, you buy "
        "immediately. If a downgrade or target price cut is mentioned, you "
        "sell immediately. You trust analysts completely. You represent "
        "retail investors who rely on brokerage research. When no analyst "
        "news is available, you hold.\n\n"
        "RULES:\n"
        "- BUY if headline contains: upgrade, target price raised, buy "
        "rating, outperform, overweight\n"
        "- SELL if headline contains: downgrade, sell rating, target cut, "
        "underperform, underweight\n"
        "- HOLD if no analyst-related news available"
    )

    def __init__(self, name: str) -> None:
        super().__init__(
            name=name,
            agent_type="news_reactor",
            weight=1.3,
            personality_prompt=self.PERSONALITY_PROMPT,
        )

    @classmethod
    def create_instances(cls, n: int = 2) -> list["AnalystFollowerAgent"]:
        """Create n AnalystFollower agents (default 2)."""
        return [cls(f"Analyst_Follower_{i+1:02d}") for i in range(n)]


# ---------------------------------------------------------------------------
# Factory: Get all 15 news reactor agents
# ---------------------------------------------------------------------------
def get_all_news_reactor_agents() -> list[BaseAgent]:
    """
    Returns all 15 news reactor agents ready for the swarm runner.

    Breakdown:
      - 5 Bad News Overreactors
      - 5 Good News Chasers
      - 3 Noise Ignorers
      - 2 Analyst Followers

    Noise Ignorers ignore both news AND crowd_summary in Round 2.
    """
    agents: list[BaseAgent] = []
    agents.extend(BadNewsOverreactorAgent.create_instances(5))
    agents.extend(GoodNewsChaserAgent.create_instances(5))
    agents.extend(NoiseIgnorerAgent.create_instances(3))
    agents.extend(AnalystFollowerAgent.create_instances(2))
    return agents  # 15 total
