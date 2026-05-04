# AlphaHive — Master Agent Build Context
# Feed this file to Copilot at the start of EVERY session.
# This is the single source of truth for the entire project.

---

## What AlphaHive Is

AlphaHive is a multi-agent market intelligence platform for Indian retail
investors. It combines two layers of AI intelligence:

1. A swarm of 80+ personality agents that simulate real market participant
   behavior (inspired by MiroFish architecture)
2. A specialist analyst debate team that analyzes the facts (inspired by
   TradingAgents architecture)

Together they produce explainable, plain-English signals for NSE and S&P 500
stocks — built for retail investors who cannot access a research desk.

**This is a research intelligence tool. NOT a trade executor.**
Every single output MUST carry this disclaimer:
"For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own."

---

## The Two-Layer Architecture

```
SAME MARKET DATA + NEWS fed into BOTH layers simultaneously

LAYER 1: SWARM ENGINE (80 personality agents)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Simulates what different market participants would actually do.

ROUND 1 — Independent decisions (all 80 run in parallel via asyncio)
  Each agent reads: price data, volume, indicators, news headlines
  Each agent returns: { action, confidence, reasoning }

ROUND 2 — Social influence (agents see Round 1 aggregate)
  Each agent sees: "67% buying, panic agents selling, algos holding"
  Each agent can revise their decision based on crowd behavior
  This is where EMERGENT behavior happens

AGGREGATE OUTPUT:
  bullish_pct    → % weighted buy decisions
  bearish_pct    → % weighted sell decisions
  panic_index    → % of panic-type agents selling
  fomo_index     → % of momentum agents who upgraded after Round 2
  conviction     → how little agents changed Round 1 → Round 2
                   (low change = high conviction in the signal)


LAYER 2: SPECIALIST TEAM (6 analyst agents, run parallel to Layer 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analyzes the actual facts behind the stock.

  fundamental_analyst  → P/E vs sector, EPS delta, promoter holding change
  technical_analyst    → RSI, EMA cross, volume breakout, ATR, Bollinger
  sentiment_analyst    → FinBERT on Indian news headlines (free, local)
  news_analyst         → Exchange announcements, earnings calendar, filings

  OUTPUT: structured report per analyst with score + key findings


SYNTHESIS LAYER (runs after both layers complete)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  bull_researcher  → reads ALL analyst reports + swarm output, builds bull case
  bear_researcher  → reads ALL analyst reports + swarm output, builds bear case

  risk_manager     → reads bull + bear debate, outputs final signal:
                     { bullish_pct, risk_level, confidence, final_call }

  explainer        → converts everything into 3-line plain English:
                     Line 1: Signal + score
                     Line 2: Top reasons (facts from specialist team)
                     Line 3: Crowd behavior narrative (from swarm)
```

---

## The 80 Personality Agents

### RETAIL ARCHETYPES — 25 agents
```python
RETAIL_AGENTS = [
    # name, count, behavior_description, sell_trigger, buy_trigger, weight
    ("Panic_Seller",        8, "sells on any negative move or bad headline",
     "price_change < -2% OR negative_headline", "never buys in panic", 0.6),

    ("FOMO_Buyer",          7, "buys when sees crowd buying, chases green candles",
     "stops out quickly", "crowd_bullish_pct > 60%", 0.7),

    ("Zerodha_Newbie",      5, "emotional, overreacts to everything, random behavior",
     "any red day", "any positive headline", 0.4),

    ("SIP_Investor",        3, "ignores noise, only cares about 200 DMA",
     "price < 200_DMA by 20%", "price at 200_DMA support", 0.9),

    ("Moneycontrol_Reader", 2, "reacts specifically to Moneycontrol headlines",
     "negative_analyst_rating", "positive_analyst_upgrade", 0.75),
]
```

### INSTITUTIONAL ARCHETYPES — 20 agents
```python
INSTITUTIONAL_AGENTS = [
    ("FII_Momentum",    6, "follows global risk-on/off, tracks DXY and US futures",
     "risk_off_signal OR DXY_rising", "risk_on AND emerging_market_inflows", 1.5),

    ("DII_Value",       5, "buys dips only on strong fundamentals, long horizon",
     "fundamental_breakdown", "price_dip AND PE_below_sector_avg", 1.8),

    ("Hedge_Fund_Short",4, "looks for overbought + weak fundamentals to short",
     "never sells at loss quickly", "RSI > 75 AND poor_fundamentals", 1.2),

    ("MF_SIP_Machine",  3, "consistent buyer regardless of price, ignores noise",
     "never", "always accumulates", 2.0),

    ("Insurance_LIC",   2, "very long horizon, accumulates on large drops only",
     "never short term", "price_drop > 10% from peak", 2.5),
]
```

### ALGO ARCHETYPES — 20 agents
```python
ALGO_AGENTS = [
    ("RSI_Bot",             5, "pure RSI signal only, no other input considered",
     "RSI > 70", "RSI < 30", 1.0),

    ("EMA_Crossover_Bot",   5, "50/200 EMA crossover only, golden/death cross",
     "death_cross (50 EMA < 200 EMA)", "golden_cross (50 EMA > 200 EMA)", 1.0),

    ("Volume_Breakout_Bot", 4, "only acts on volume greater than 2x average",
     "volume_spike WITH price_drop", "volume_spike WITH price_breakout", 1.0),

    ("Mean_Reversion_Bot",  4, "bets against momentum after extreme moves",
     "price_up > 5% in 1 day", "price_down > 5% in 1 day", 0.9),

    ("Arbitrage_Bot",       2, "sector rotation, relative strength plays",
     "sector_underperforming", "sector_momentum_shift", 1.1),
]
```

### NEWS REACTOR ARCHETYPES — 15 agents
```python
NEWS_AGENTS = [
    ("Bad_News_Overreactor", 5, "massively sells on any negative headline, panics",
     "any_negative_news", "only after full recovery", 0.5),

    ("Good_News_Chaser",     5, "buys aggressively on positive earnings/guidance",
     "disappointing_followthrough", "positive_earnings OR upgrade", 0.7),

    ("Noise_Ignorer",        3, "ignores news entirely, only price action matters",
     "pure_technical_sell", "pure_technical_buy", 1.0),

    ("Analyst_Follower",     2, "mirrors analyst upgrades and downgrades exactly",
     "analyst_downgrade", "analyst_upgrade", 1.3),
]
```

---

## Project Folder Structure

Build exactly this structure. Do not deviate.

```
alphahive/
│
├── AGENTS.md                    ← THIS FILE. Always in root.
│
├── data/
│   ├── __init__.py
│   ├── loader.py                ← yfinance primary + AKShare fallback
│   ├── nse.py                   ← NSE-specific: Nifty50 list, FII/DII flows,
│   │                               promoter holding, exchange announcements
│   └── news.py                  ← RSS parser for ET, Moneycontrol, NSE filings
│
├── agents/
│   ├── __init__.py
│   ├── base.py                  ← BaseAgent class all agents inherit from
│   │
│   ├── swarm/
│   │   ├── __init__.py
│   │   ├── runner.py            ← asyncio runner for all 80 agents, 2 rounds
│   │   ├── aggregator.py        ← computes panic_index, fomo_index, conviction
│   │   └── personalities/
│   │       ├── __init__.py
│   │       ├── retail.py        ← 25 retail archetype agents
│   │       ├── institutional.py ← 20 institutional archetype agents
│   │       ├── algo.py          ← 20 algo archetype agents
│   │       └── news_reactor.py  ← 15 news reactor archetype agents
│   │
│   └── specialists/
│       ├── __init__.py
│       ├── fundamental.py       ← P/E, EPS, promoter holding, sector compare
│       ├── technical.py         ← RSI, EMA, volume, ATR, Bollinger
│       ├── sentiment.py         ← FinBERT on Indian headlines (free, local)
│       └── news.py              ← Exchange filings, earnings events
│
├── engine/
│   ├── __init__.py
│   ├── orchestrator.py          ← runs Layer 1 + Layer 2 in parallel
│   ├── debate.py                ← LangGraph: bull researcher vs bear researcher
│   ├── scorer.py                ← debate output → bullish%, risk, confidence
│   └── explainer.py             ← everything → 3-line plain English signal
│
├── backtest/
│   ├── __init__.py
│   ├── engine.py                ← walk-forward backtest on NSE historical data
│   └── compare.py               ← AlphaHive vs Buy&Hold vs RSI vs EMA
│
├── api/
│   ├── __init__.py
│   └── main.py                  ← FastAPI: /analyze, /watchlist,
│                                   /sectors, /backtest, /health
│
├── frontend/                    ← Next.js + Tailwind + Recharts
│   ├── pages/
│   │   ├── index.tsx            ← Watchlist dashboard with signal cards
│   │   ├── stock/[ticker].tsx   ← Full debate + swarm visualization
│   │   └── backtest.tsx         ← Performance comparison charts
│   └── components/
│       ├── SignalCard.tsx        ← Stock card: bullish%, risk, crowd bar
│       ├── DebateViewer.tsx      ← Bull case vs bear case side by side
│       └── SwarmViz.tsx          ← Visual crowd behavior (V2 feature)
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Tech Stack — Fixed Decisions

```
LLM (swarm agents):     Ollama + llama3.2:3b (fast, free, local)
                        OR DeepSeek free tier API
LLM (specialist team):  Ollama + llama3.1:8b OR deepseek-v3
Agent orchestration:    LangGraph (for debate engine)
Swarm runner:           Python asyncio (for 80 parallel agents)
Primary data:           yfinance (NSE format: RELIANCE.NS, TCS.NS)
Fallback data:          AKShare (when yfinance fails for NSE)
Sentiment model:        FinBERT (huggingface, free, local inference)
News data:              RSS feeds (no API key needed)
Backend:                FastAPI
Database:               PostgreSQL (signal history, agent decisions)
Cache:                  Redis (current prices, today's signals)
Frontend:               Next.js + Tailwind + Recharts
Deploy:                 Vercel (frontend) + Render (backend)
```

---

## NSE Data Conventions

```python
# Always use Yahoo Finance format for NSE tickers
NSE_FORMAT = "{SYMBOL}.NS"   # e.g. RELIANCE.NS, TCS.NS, INFY.NS
BSE_FORMAT = "{SYMBOL}.BO"   # e.g. RELIANCE.BO

# Nifty 50 universe (MVP watchlist)
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "ITC.NS", "ASIANPAINT.NS", "AXISBANK.NS", "LT.NS", "DMART.NS",
    "SUNPHARMA.NS", "ULTRACEMCO.NS", "TITAN.NS", "WIPRO.NS", "NESTLEIND.NS",
    "HCLTECH.NS", "MARUTI.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
    "TECHM.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS",
]

# Data fields needed per stock per day
REQUIRED_FIELDS = [
    "open", "high", "low", "close", "volume",  # OHLCV
    "rsi_14",                                   # RSI
    "ema_50", "ema_200",                        # EMAs
    "atr_14",                                   # ATR for volatility
    "volume_avg_30",                            # 30-day avg volume
    "pe_ratio",                                 # Fundamental
    "eps_growth_yoy",                           # Fundamental
]
```

---

## The 3 Reference Repos — How to Use Them

You have these folders extracted locally. They are REFERENCE ONLY.
Do not copy code. Read them to understand patterns.
Write original AlphaHive code inspired by what you learn.

### /TradingAgents — Apache 2.0 (credit in README required)
```
READ THESE FILES to understand the patterns:

tradingagents/agents/analysts/fundamentals_analyst.py
→ How to structure an analyst agent with LLM prompting
→ How agent receives data and returns structured report
→ Adapt: change prompts to NSE context, remove FinnHub dependency

tradingagents/agents/researchers/bull_researcher.py
tradingagents/agents/researchers/bear_researcher.py
→ How bull vs bear debate is structured
→ How each researcher reads analyst reports and builds a case
→ Adapt: add swarm output as additional input to both researchers

tradingagents/graph/trading_graph.py
→ How LangGraph connects agents into a stateful graph
→ How state flows from analysts → researchers → risk manager
→ Adapt: add swarm layer as parallel input, remove trade execution node

tradingagents/llm_clients/
→ How to abstract LLM providers (Ollama, OpenAI, DeepSeek)
→ Copy the pattern, write your own clean version

DO NOT USE:
tradingagents/dataflows/   ← their FinnHub data layer, not needed
Any CLI code              ← you are building a web product
Trade execution logic     ← AlphaHive does not execute trades
```

### /Vibe-Trading — MIT (free to use)
```
READ THESE FILES to understand the patterns:

agent/backtest/loaders/yfinance.py
→ How to correctly fetch NSE data using yfinance
→ How to handle OHLCV, handle weekend gaps, handle corporate actions
→ Adapt: write your own cleaner version with NSE-specific logic

agent/backtest/loaders/akshare.py
→ How AKShare is used as India data source
→ How to map AKShare field names to standard format
→ Adapt: write your own version for your data schema

agent/backtest/loaders/registry.py
→ The auto-fallback chain pattern — most important concept here
→ Try source 1, if fails try source 2, log which was used
→ Adapt: write your own DataRegistry class with same pattern

agent/backtest/engines/
→ How walk-forward backtest is structured
→ How to avoid look-ahead bias in signal testing
→ Adapt: simplify for NSE equities only (no crypto/futures needed)

DO NOT USE:
agent/src/agent/loop.py        ← their ReAct loop, not your architecture
agent/src/skills/              ← their 69-skill system, not needed
frontend/                      ← their frontend is built for CLI streaming
```

### /MiroFish — AGPL-3.0 — ZERO CODE. READ ONLY.
```
READ THESE FILES for visual and architectural inspiration ONLY:

Look at how they structure agent personalities
Look at how they do multi-round agent interaction
Look at their frontend visualization of agent movement

WRITE: your own swarm runner from scratch using asyncio
WRITE: your own personality system from the agent roster above
ZERO code from MiroFish. AGPL license = if you use even one function,
your entire project must be released under AGPL.
```

---

## Signal Output Format

Every stock analysis must return this exact structure:

```python
AlphaHiveSignal = {
    # Identity
    "ticker": "RELIANCE.NS",
    "company": "Reliance Industries",
    "sector": "Energy",
    "timestamp": "2026-04-27T09:15:00+05:30",

    # Swarm Layer outputs
    "swarm": {
        "bullish_pct": 71.4,
        "bearish_pct": 18.6,
        "hold_pct": 10.0,
        "panic_index": 12.3,      # low = calm, high = panic
        "fomo_index": 34.7,       # high = momentum chasing
        "conviction": 87.2,       # high = agents barely changed R1→R2
        "round1_bullish": 65.0,   # before social influence
        "round2_bullish": 71.4,   # after social influence
    },

    # Specialist Layer outputs
    "specialists": {
        "fundamental_score": 72.0,
        "technical_score": 68.0,
        "sentiment_score": 61.0,
        "news_score": 55.0,
        "fundamental_summary": "PE 24x vs sector 28x. EPS +12% YoY.",
        "technical_summary": "RSI 58. Price above 50 EMA. Volume 1.8x avg.",
        "sentiment_summary": "Positive earnings coverage. Low fear words.",
        "news_summary": "No negative filings. Promoter holding stable.",
    },

    # Final synthesized signal
    "signal": {
        "final_call": "BULLISH",          # BULLISH / BEARISH / NEUTRAL
        "bullish_probability": 71.0,
        "risk_level": "MEDIUM",           # LOW / MEDIUM / HIGH
        "confidence": "HIGH",             # LOW / MEDIUM / HIGH
    },

    # Plain English explainability (the product soul)
    "explanation": {
        "line1": "Reliance Industries is 71% bullish with high conviction.",
        "line2": "Strong fundamentals: PE below sector avg, EPS +12% YoY, "
                 "volume breakout on 1.8x average confirmed by EMA alignment.",
        "line3": "Crowd simulation shows institutional accumulation dominating. "
                 "Retail panic low at 12%. Positive momentum building.",
    },

    # SEBI disclaimer — MANDATORY on every signal
    "disclaimer": "For educational purposes only. Not investment advice. "
                  "AlphaHive is not SEBI-registered. "
                  "All trading decisions are entirely your own.",
}
```

---

## Build Order — Week by Week

```
WEEK 1: Data Foundation
  data/loader.py       → yfinance + AKShare auto-fallback
  data/nse.py          → Nifty 50 universe, FII/DII ingestion
  data/news.py         → RSS parser for Indian financial news
  api/main.py          → FastAPI skeleton with /health endpoint
  DATABASE SCHEMA      → PostgreSQL tables for signals + decisions

WEEK 2: Swarm Engine — The Core
  agents/base.py                  → BaseAgent with LLM abstraction
  agents/swarm/personalities/     → All 80 personality agents
  agents/swarm/runner.py          → asyncio parallel runner, 2 rounds
  agents/swarm/aggregator.py      → panic/fomo/conviction calculation
  TEST: Run swarm on RELIANCE.NS, verify 80 agents return decisions

WEEK 3: Specialist Analysts
  agents/specialists/fundamental.py
  agents/specialists/technical.py
  agents/specialists/sentiment.py  ← FinBERT setup here
  agents/specialists/news.py
  TEST: All 4 analysts return structured report for any Nifty 50 stock

WEEK 4: Debate + Synthesis Engine
  engine/orchestrator.py  → runs Layer 1 + Layer 2 in parallel
  engine/debate.py        → LangGraph bull vs bear with both inputs
  engine/scorer.py        → final signal computation
  engine/explainer.py     → 3-line plain English output
  TEST: Full signal JSON for RELIANCE.NS matches output format above

WEEK 5: API Layer
  api/main.py complete   → /analyze, /watchlist, /sectors, /backtest
  Redis caching          → cache signals for 6 hours
  PostgreSQL storage     → persist all signals for history
  TEST: curl /analyze?ticker=TCS.NS returns full signal in <60 seconds

WEEK 6: Frontend Dashboard
  pages/index.tsx          → watchlist with signal cards
  pages/stock/[ticker].tsx → full debate transcript viewer
  components/SignalCard.tsx → clean card with bullish%, risk, crowd bar
  components/DebateViewer.tsx → bull vs bear side by side
  TEST: Can see 20 Nifty 50 stocks with live signals in browser

WEEK 7: Backtest Arena
  backtest/engine.py    → walk-forward on NSE historical data
  backtest/compare.py   → vs Buy&Hold, RSI, EMA crossover
  frontend backtest page → cumulative return chart, Sharpe ratio
  TEST: 6-month backtest runs and shows honest performance comparison

WEEK 8: Deploy + Polish
  docker-compose.yml    → one command local run
  Vercel deploy         → frontend
  Render deploy         → backend + PostgreSQL
  README.md             → architecture diagram, demo video, disclaimer
  GitHub Actions        → daily signal refresh at 9:15 AM IST
```

---

## Copilot Prompt Pattern

Use this pattern for every module. Never deviate.

```
Context: Read /AGENTS.md in project root for full architecture context.

Now build: [EXACT FILE PATH]

Reference for inspiration (do not copy code):
- [REPO FILE PATH] → [what pattern to learn from it]

What to write:
[Specific description of what this file does]
[Input it receives]
[Output it must return]
[Any specific constraints or edge cases]

Use the output format defined in AGENTS.md.
Add SEBI disclaimer to any function that returns a signal.
Write clean, commented, original code.
```

---

## Attribution (put this in README.md)

```
AlphaHive is an independent implementation inspired by:
- TradingAgents (Apache 2.0) by TauricResearch — specialist agent architecture
- Vibe-Trading (MIT) by HKUDS — data loader patterns
- MiroFish (AGPL-3.0) by 666ghj — swarm visualization concept

All AlphaHive code is original. No code was copied from any reference repo.
```

---

## Common Mistakes to Avoid

```
1. DO NOT use FinnHub API — it is paid and US-only
2. DO NOT hardcode API keys — use .env file
3. DO NOT output "BUY" or "SELL" signals — SEBI compliance
   Always output "BULLISH signal" or "research indicates bullish"
4. DO NOT run all 80 agents sequentially — always asyncio parallel
5. DO NOT use MiroFish code — AGPL license
6. DO NOT build SwarmViz in Week 1 — it is a V2 feature
7. DO NOT use WidthType.PERCENTAGE in any table — DXA only (if docx)
8. DO add SEBI disclaimer to every single signal output
9. DO use .NS suffix for all NSE tickers
10. DO cache signals in Redis — do not re-run full analysis on every request
```
