"""
AlphaHive — Swarm Personality Agents
======================================
80 unique personality agents across 4 categories:
  - retail.py:          25 agents (Panic, FOMO, Newbie, SIP, Moneycontrol)
  - institutional.py:   20 agents (FII, DII, Hedge Fund, MF SIP, LIC)
  - algo.py:            20 agents (RSI, EMA, Volume, MeanRev, Arbitrage)
  - news_reactor.py:    15 agents (BadNews, GoodNews, NoiseIgnorer, Analyst)
"""

from agents.swarm.personalities.retail import get_all_retail_agents
from agents.swarm.personalities.institutional import get_all_institutional_agents
from agents.swarm.personalities.algo import get_all_algo_agents
from agents.swarm.personalities.news_reactor import get_all_news_reactor_agents


def get_all_agents():
    """Returns all 80 swarm agents."""
    agents = []
    agents.extend(get_all_retail_agents())          # 25
    agents.extend(get_all_institutional_agents())   # 20
    agents.extend(get_all_algo_agents())            # 20
    agents.extend(get_all_news_reactor_agents())    # 15
    return agents  # 80 total


__all__ = [
    "get_all_retail_agents",
    "get_all_institutional_agents",
    "get_all_algo_agents",
    "get_all_news_reactor_agents",
    "get_all_agents",
]
