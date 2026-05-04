# AlphaHive — Week 3 Copilot Prompt Sequence
# Building the Specialist Analyst Team + Orchestrator
# Run these prompts IN ORDER. One prompt = one Copilot session.
# Always tell Copilot to read AGENTS.md first in every session.

---

## What You're Building This Week

```
agents/
└── specialists/
    ├── fundamental.py     ← PROMPT 1 (P/E, EPS, promoter holding)
    ├── technical.py       ← PROMPT 2 (RSI, EMA, volume, ATR)
    ├── sentiment.py       ← PROMPT 3 (FinBERT — different from Ollama)
    └── news.py            ← PROMPT 4 (exchange filings, earnings events)

engine/
└── orchestrator.py        ← PROMPT 5 (runs swarm + specialists in parallel)

tests/
└── test_week3.py          ← PROMPT 6 (full pipeline verification)
```

By end of Week 3:
- 4 specialist agents each produce a structured report for any stock
- Swarm engine (Week 2) + all 4 specialists run simultaneously via asyncio
- Orchestrator combines both outputs into a single unified analysis object
- Full pipeline: ticker in → swarm signal + 4 specialist reports out
- Total time target: under 90 seconds end-to-end

---

## Key Difference From Swarm Agents

```
Swarm agents (Week 2):          Specialist agents (Week 3):
─────────────────────────────   ──────────────────────────────
Simulate BEHAVIOR               Analyze FACTS
"What would I do?"              "What does the data show?"
Personality-driven              Data-driven
80 agents, fast model           4 agents, smarter model
Output: crowd signal            Output: structured report
Uses: llama3.2:3b               Uses: llama3.1:8b (or FinBERT)
```

Both run in PARALLEL inside the orchestrator. Neither waits for the other.

---

## PROMPT 1 — Fundamental Analyst

```
Read AGENTS.md in the project root first. Focus on:
- The specialist agents section in the architecture
- The "specialists" section of AlphaHiveSignal output format
- The tech stack section (llama3.1:8b for specialists)

Create agents/specialists/fundamental.py

The FundamentalAnalyst class. This is NOT a subclass of BaseAgent
from the swarm layer. Specialists are a different, cleaner pattern.
They receive data, call Ollama once with a smarter model, and return
a structured report. No personality. No rounds. Pure analysis.

class FundamentalAnalyst:

async analyze(self, ticker: str, market_data: dict) -> dict
  
  Step 1: Gather fundamental data for the ticker.
  Pull these from DataLoader and data/nse.py:
    - pe_ratio (from yfinance .info["trailingPE"])
    - forward_pe (from yfinance .info["forwardPE"])
    - eps_ttm (trailing twelve months EPS)
    - eps_growth_yoy (year over year, if available)
    - revenue_growth_yoy (if available)
    - profit_margin (from yfinance .info["profitMargins"])
    - debt_to_equity (from yfinance .info["debtToEquity"])
    - roe (return on equity, from yfinance .info["returnOnEquity"])
    - promoter_holding_pct (from data/nse.get_promoter_holding)
    - book_value (from yfinance .info["bookValue"])
    - price_to_book (from yfinance .info["priceToBook"])
    
    For NSE sector context:
    - sector (from data/nse.get_sector_for_ticker)
    - Build a HARDCODED sector average PE dict for Nifty 50 sectors:
      SECTOR_AVG_PE = {
        "Banking": 18.0, "IT": 28.0, "Energy": 12.0,
        "FMCG": 55.0, "Auto": 22.0, "Pharma": 35.0,
        "Metals": 10.0, "Telecom": 40.0, "Infrastructure": 20.0,
        "Default": 25.0
      }
  
  Step 2: Compute derived signals (deterministic — no LLM needed):
    - pe_vs_sector: pe_ratio vs sector average
      "cheap" if PE < sector_avg * 0.85
      "fair" if 0.85 <= PE/sector_avg <= 1.15
      "expensive" if PE > sector_avg * 1.15
    - earnings_trend: "improving" | "declining" | "stable"
      based on eps_growth_yoy
    - debt_health: "low" if D/E < 0.5, "medium" if 0.5-1.5, "high" if >1.5
    - promoter_confidence: "high" if promoter_pct > 50, "medium" 35-50, "low" <35

  Step 3: Build a concise data summary string and call Ollama (llama3.1:8b).
  System prompt:
    "You are a fundamental equity analyst for Indian stocks.
     You analyze financial metrics and return a concise assessment.
     Always respond in valid JSON only. No preamble. No explanation outside JSON."
  
  User prompt:
    "Analyze these fundamentals for {ticker} ({sector} sector):
     {formatted_fundamentals_string}
     
     Return JSON with exactly these fields:
     {
       'score': integer 0-100 (overall fundamental strength),
       'verdict': 'STRONG' | 'MODERATE' | 'WEAK',
       'key_positives': [list of max 3 short strings],
       'key_negatives': [list of max 3 short strings],
       'summary': 'one sentence summary of fundamentals'
     }"
  
  Step 4: Parse response. If parse fails, use deterministic fallback:
    score = 50 (neutral), verdict = "MODERATE", use computed signals as summary.
  
  Return the complete report:
  {
    "analyst": "fundamental",
    "ticker": ticker,
    "raw_data": { all fetched metrics },
    "derived": { pe_vs_sector, earnings_trend, debt_health, promoter_confidence },
    "score": int,
    "verdict": str,
    "key_positives": list,
    "key_negatives": list,
    "summary": str,
    "timestamp": ISO timestamp
  }

Handle missing data gracefully — many NSE stocks won't have all fields.
If yfinance returns None for a field: skip it, note "unavailable" in raw_data.
Never crash. Always return a report.
Use OLLAMA_SPECIALIST_MODEL from .env (default: llama3.1:8b).
Timeout: 45 seconds for the LLM call.
```

---

## PROMPT 2 — Technical Analyst

```
Read AGENTS.md in the project root first.

Create agents/specialists/technical.py

The TechnicalAnalyst class. Same pattern as FundamentalAnalyst —
clean, data-driven, no personality, one Ollama call.

class TechnicalAnalyst:

async analyze(self, ticker: str, market_data: dict) -> dict

  Step 1: Compute ALL indicators from price history.
  Import DataLoader. Fetch 90 days of OHLCV history.
  Compute these — use pandas/numpy directly, no external TA library needed:

  TREND INDICATORS:
    - ema_20: 20-day EMA
    - ema_50: 50-day EMA  
    - ema_200: 200-day EMA
    - trend_structure: "uptrend" | "downtrend" | "ranging"
      uptrend: ema_20 > ema_50 > ema_200
      downtrend: ema_20 < ema_50 < ema_200
      ranging: anything else
    - golden_cross: bool (ema_50 recently crossed above ema_200, last 10 days)
    - death_cross: bool (ema_50 recently crossed below ema_200, last 10 days)

  MOMENTUM INDICATORS:
    - rsi_14: standard RSI formula (use pandas, compute from scratch)
      rsi_signal: "oversold" if <30, "overbought" if >70, "neutral" 30-70
    - macd_line: EMA_12 - EMA_26
    - macd_signal: 9-day EMA of macd_line
    - macd_histogram: macd_line - macd_signal
    - macd_signal_type: "bullish_crossover" | "bearish_crossover" | "neutral"

  VOLUME INDICATORS:
    - volume_avg_20: 20-day average volume
    - volume_ratio: today's volume / volume_avg_20
    - volume_trend: "expanding" | "contracting" | "neutral"
      expanding: last 5 days avg > volume_avg_20
    - breakout_confirmed: bool
      True if: price at 52-week high AND volume_ratio > 1.5

  VOLATILITY INDICATORS:
    - atr_14: Average True Range (standard formula)
    - atr_pct: atr_14 / current_price * 100 (volatility as % of price)
    - bb_upper, bb_lower, bb_middle: Bollinger Bands (20-day, 2 std dev)
    - bb_position: "above_upper" | "below_lower" | "inside"
    - bb_squeeze: bool (bands are narrowing — volatility compression)

  SUPPORT/RESISTANCE (simple):
    - week_52_high: 52-week high price
    - week_52_low: 52-week low price
    - pct_from_52w_high: ((current - 52w_high) / 52w_high) * 100
    - support_level: lowest price in last 20 days
    - resistance_level: highest price in last 20 days

  Step 2: Derive a composite technical score (0-100) deterministically:
    score = 50 (start neutral)
    
    Trend signals (±20 max):
      +10 if uptrend_structure
      +5 if golden_cross (recent)
      -10 if downtrend_structure
      -5 if death_cross (recent)
    
    Momentum signals (±20 max):
      +10 if rsi 40-65 (healthy momentum zone)
      +5 if macd bullish crossover
      -10 if rsi > 75 (overbought)
      -5 if rsi < 25 (severely oversold — recovery possible but risky)
      -5 if macd bearish crossover
    
    Volume signals (±10 max):
      +10 if breakout_confirmed
      +5 if volume_ratio > 1.5 with price up
      -5 if volume_ratio > 1.5 with price down
    
    Clamp final score to 0-100.

  Step 3: Call Ollama (llama3.1:8b) with concise indicator summary.
  System prompt:
    "You are a technical analyst for Indian equity markets.
     Analyze the provided indicators and return a concise technical verdict.
     Respond in valid JSON only. No preamble."
  
  User prompt:
    "Technical analysis for {ticker}:
     {formatted_indicators_summary}
     
     Return JSON:
     {
       'verdict': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
       'key_signals': [list of max 3 most important signals],
       'watch_levels': { 'support': price, 'resistance': price },
       'summary': 'one sentence technical assessment'
     }"

  Return full report:
  {
    "analyst": "technical",
    "ticker": ticker,
    "indicators": { all computed indicator values },
    "score": int (deterministic composite score),
    "verdict": str (from LLM),
    "key_signals": list,
    "watch_levels": dict,
    "summary": str,
    "timestamp": ISO timestamp
  }

Important: compute RSI from scratch using pandas — do not use ta-lib or
any external TA library. This keeps requirements.txt clean.
RSI formula:
  delta = close.diff()
  gain = delta.clip(lower=0).rolling(14).mean()
  loss = (-delta.clip(upper=0)).rolling(14).mean()
  rs = gain / loss
  rsi = 100 - (100 / (1 + rs))
```

---

## PROMPT 3 — Sentiment Analyst (FinBERT)

```
Read AGENTS.md in the project root first.

Create agents/specialists/sentiment.py

The SentimentAnalyst class. This is the ONLY specialist that does NOT
use Ollama. It uses FinBERT — a BERT model fine-tuned on financial text.
FinBERT is free, runs locally, already downloaded last week.

Model: ProsusAI/finbert
Labels: "positive", "negative", "neutral" (finance-specific)
This is FAR better than general sentiment models for Indian financial news.

class SentimentAnalyst:

__init__(self)
  Load FinBERT pipeline ONCE at initialization (not on every analyze call):
  
  from transformers import pipeline
  self.finbert = pipeline(
    "text-classification",
    model="ProsusAI/finbert",
    tokenizer="ProsusAI/finbert",
    device=-1            # CPU — do not require GPU
  )
  
  Also load the news fetcher:
  from data.news import get_news_for_ticker

async analyze(self, ticker: str, market_data: dict) -> dict
  
  Step 1: Fetch recent news for this ticker.
  headlines = await get_news_for_ticker(ticker, max_items=15)
  If no headlines: return neutral report with note "no recent news found"
  
  Step 2: Run FinBERT on each headline.
  FinBERT is synchronous. Run in a thread executor to avoid blocking asyncio:
  
  import asyncio
  loop = asyncio.get_event_loop()
  
  def run_finbert_batch(texts):
    return self.finbert(texts, truncation=True, max_length=512)
  
  headline_texts = [h.headline for h in headlines]
  results = await loop.run_in_executor(None, run_finbert_batch, headline_texts)
  
  Step 3: Compute aggregate sentiment metrics.
  For each result: { label, score } where score = confidence of that label.
  
  scored_headlines = []
  for headline, result in zip(headlines, results):
    scored_headlines.append({
      "headline": headline.headline,
      "source": headline.source,
      "label": result["label"],           # "positive"/"negative"/"neutral"
      "confidence": result["score"],       # 0.0-1.0
      "published_at": headline.published_at
    })
  
  Compute aggregates:
    positive_count = count where label == "positive"
    negative_count = count where label == "negative"
    neutral_count = count where label == "neutral"
    total = len(scored_headlines)
    
    # Weighted by confidence
    positive_score = sum(h["confidence"] for h if h["label"]=="positive")
    negative_score = sum(h["confidence"] for h if h["label"]=="negative")
    
    # Net sentiment: positive dominance vs negative
    net_sentiment = (positive_score - negative_score) / total
    # Range: -1.0 (all negative) to +1.0 (all positive)
    
    # Overall score 0-100
    sentiment_score = int((net_sentiment + 1) / 2 * 100)
    # net=-1.0 → score=0, net=0 → score=50, net=+1.0 → score=100
    
    # Verdict
    if sentiment_score > 60: verdict = "POSITIVE"
    elif sentiment_score < 40: verdict = "NEGATIVE"
    else: verdict = "NEUTRAL"
    
    # Fear/greed proxy
    fear_index = (negative_count / total) * 100
    greed_index = (positive_count / total) * 100

  Step 4: Extract top 3 most impactful headlines (highest confidence, any label):
    top_headlines = sorted by confidence desc, take first 3.

  Return:
  {
    "analyst": "sentiment",
    "ticker": ticker,
    "headlines_analyzed": total,
    "scored_headlines": scored_headlines,    # full list
    "top_headlines": top_headlines,          # top 3
    "positive_count": int,
    "negative_count": int,
    "neutral_count": int,
    "net_sentiment": float,                  # -1.0 to +1.0
    "score": int,                            # 0-100
    "verdict": str,
    "fear_index": float,
    "greed_index": float,
    "summary": str,                          # generated by string template, not LLM
    "timestamp": ISO timestamp
  }

  Summary template (no LLM — purely from metrics):
    if verdict == "POSITIVE":
      f"News sentiment strongly positive. {positive_count}/{total} headlines bullish. Fear index low at {fear_index:.0f}%."
    elif verdict == "NEGATIVE":
      f"News sentiment negative. {negative_count}/{total} headlines bearish. Elevated fear at {fear_index:.0f}%."
    else:
      f"Mixed news sentiment. No clear directional bias from {total} recent headlines."

NOTE: FinBERT is synchronous and CPU-only. It is slower than Ollama for
single calls but MUCH more accurate for financial sentiment than a general LLM.
Do not try to make it async natively — the run_in_executor pattern is correct.
Do not cache the pipeline — load once in __init__ and reuse.
```

---

## PROMPT 4 — News Analyst

```
Read AGENTS.md in the project root first.

Create agents/specialists/news.py

The NewsAnalyst class. Different from SentimentAnalyst — sentiment
measures the TONE of news. News analyst measures the EVENTS and their
market significance.

Specifically: what happened, is it a material event, what's the likely
impact on the stock price directionally?

class NewsAnalyst:

  # Material event keywords by category
  BULLISH_EVENTS = [
    "earnings beat", "profit up", "revenue growth", "new contract",
    "acquisition", "buyback", "dividend", "upgrade", "stake increase",
    "expansion", "partnership", "order win", "capacity", "q4 beat",
    "record profit", "guidance raised", "promoter buying"
  ]
  
  BEARISH_EVENTS = [
    "earnings miss", "profit down", "revenue decline", "loss", "write-off",
    "downgrade", "investigation", "fraud", "debt", "default",
    "margin squeeze", "guidance cut", "promoter selling", "sebi notice",
    "it raid", "npa", "resignation", "lawsuit"
  ]
  
  NEUTRAL_EVENTS = [
    "board meeting", "agm", "quarterly results", "management change",
    "name change", "new appointment", "rbi", "government policy"
  ]

async analyze(self, ticker: str, market_data: dict) -> dict

  Step 1: Fetch news and exchange-specific data.
  headlines = await get_news_for_ticker(ticker, max_items=20)
  
  Step 2: Event detection — scan each headline for material events.
  For each headline:
    event_type = detect_event_type(headline.headline)  # see below
    impact = score_impact(headline.headline, event_type)
    
  def detect_event_type(headline_text: str) -> str:
    text_lower = headline_text.lower()
    for keyword in BULLISH_EVENTS:
      if keyword in text_lower: return "bullish_event"
    for keyword in BEARISH_EVENTS:
      if keyword in text_lower: return "bearish_event"
    for keyword in NEUTRAL_EVENTS:
      if keyword in text_lower: return "neutral_event"
    return "no_event"
  
  def score_impact(headline_text: str, event_type: str) -> float:
    # Base impact by type
    base = {"bullish_event": 0.7, "bearish_event": 0.7,
            "neutral_event": 0.3, "no_event": 0.1}[event_type]
    
    # Amplifiers
    if any(w in headline_text.lower() for w in
           ["record", "historic", "all-time", "massive", "surge", "crash"]):
      base = min(1.0, base + 0.2)
    
    return base

  Step 3: Aggregate event scores.
  bullish_events = [h for h if event_type == "bullish_event"]
  bearish_events = [h for h if event_type == "bearish_event"]
  
  bullish_impact = sum(e["impact"] for e in bullish_events)
  bearish_impact = sum(e["impact"] for e in bearish_events)
  
  net_event_score = bullish_impact - bearish_impact
  
  # Normalize to 0-100 score
  # net_event_score ranges roughly -5 to +5 in practice
  news_score = int(max(0, min(100, (net_event_score + 5) / 10 * 100)))
  
  if news_score > 60: verdict = "POSITIVE"
  elif news_score < 40: verdict = "NEGATIVE"
  else: verdict = "NEUTRAL"

  Step 4: Check for high-priority events (these override the score logic):
  HIGH_PRIORITY_BULLISH = ["earnings beat", "buyback", "dividend", "upgrade"]
  HIGH_PRIORITY_BEARISH = ["fraud", "investigation", "it raid", "sebi notice",
                            "promoter selling", "default"]
  
  high_priority_bullish_found = any keyword in any headline
  high_priority_bearish_found = any keyword in any headline
  
  # Flag these in the report — they are significant regardless of score
  alert = None
  if high_priority_bearish_found:
    alert = "HIGH RISK: Material negative event detected. Review manually."
  elif high_priority_bullish_found:
    alert = "NOTABLE: Material positive event detected."

  Step 5: Call Ollama for natural language event summary.
  Only call if there are material events (bullish or bearish events found).
  If no material events: skip LLM call, return "No material events detected."
  
  If calling: pass the top 5 most impactful headlines and ask for a
  2-sentence summary of the most important development and its likely impact.
  Use OLLAMA_SPECIALIST_MODEL.

  Return:
  {
    "analyst": "news",
    "ticker": ticker,
    "headlines_analyzed": len(headlines),
    "bullish_events": len(bullish_events),
    "bearish_events": len(bearish_events),
    "high_priority_bullish": high_priority_bullish_found,
    "high_priority_bearish": high_priority_bearish_found,
    "alert": alert,           # None or string
    "score": int,
    "verdict": str,
    "top_events": top 5 events with event_type and impact,
    "summary": str,
    "timestamp": ISO timestamp
  }
```

---

## PROMPT 5 — Engine Orchestrator (The Core Connector)

```
Read AGENTS.md in the project root first. Focus on:
- The two-layer architecture diagram
- The SYNTHESIS LAYER description
- The complete AlphaHiveSignal output format

Create engine/orchestrator.py

The AlphaHiveOrchestrator class.
This is the file that makes AlphaHive's architecture real.
It runs the swarm engine and all 4 specialist analysts SIMULTANEOUSLY
using asyncio, then combines their outputs into a single unified object.

This file does NOT do the debate (Week 4) or explainability (Week 5).
This week it combines raw outputs into a unified analysis dict.

class AlphaHiveOrchestrator:

__init__(self)
  Initialize all components ONCE (not on every analysis call):
  
  from agents.swarm.runner import SwarmRunner
  from agents.swarm.aggregator import SwarmAggregator
  from agents.specialists.fundamental import FundamentalAnalyst
  from agents.specialists.technical import TechnicalAnalyst
  from agents.specialists.sentiment import SentimentAnalyst
  from agents.specialists.news import NewsAnalyst
  
  self.swarm_runner = SwarmRunner()      # loads all 80 agents
  self.swarm_aggregator = SwarmAggregator()
  self.fundamental = FundamentalAnalyst()
  self.technical = TechnicalAnalyst()
  self.sentiment = SentimentAnalyst()   # loads FinBERT in __init__
  self.news = NewsAnalyst()
  
  Log: "AlphaHiveOrchestrator initialized. Ready to analyze."

async analyze(self, ticker: str) -> dict
  The main method. Runs everything in parallel.
  
  Step 1: Prepare shared market data (used by both layers).
  market_data = await self.swarm_runner.prepare_market_data(ticker)
  
  Step 2: Launch SWARM and ALL 4 SPECIALISTS simultaneously.
  This is the architectural core — nothing waits for anything else.
  
  import asyncio
  import time
  
  start_time = time.time()
  
  swarm_task = asyncio.create_task(
    self._run_swarm(ticker, market_data)
  )
  fundamental_task = asyncio.create_task(
    self.fundamental.analyze(ticker, market_data)
  )
  technical_task = asyncio.create_task(
    self.technical.analyze(ticker, market_data)
  )
  sentiment_task = asyncio.create_task(
    self.sentiment.analyze(ticker, market_data)
  )
  news_task = asyncio.create_task(
    self.news.analyze(ticker, market_data)
  )
  
  # Wait for ALL to complete (or fail gracefully)
  results = await asyncio.gather(
    swarm_task, fundamental_task, technical_task,
    sentiment_task, news_task,
    return_exceptions=True
  )
  
  swarm_result, fund_result, tech_result, sent_result, news_result = results
  
  # Handle any failed tasks gracefully
  swarm_signal = self._safe_swarm(swarm_result)
  fund_report = self._safe_specialist(fund_result, "fundamental")
  tech_report = self._safe_specialist(tech_result, "technical")
  sent_report = self._safe_specialist(sent_result, "sentiment")
  news_report = self._safe_specialist(news_result, "news")
  
  elapsed = time.time() - start_time
  
  Step 3: Build the unified analysis object.
  
  # Compute combined specialist score (simple average of available scores)
  specialist_scores = [
    r["score"] for r in [fund_report, tech_report, sent_report, news_report]
    if r and "score" in r and r["score"] is not None
  ]
  combined_specialist_score = sum(specialist_scores) / len(specialist_scores) if specialist_scores else 50
  
  return {
    "ticker": ticker,
    "company": market_data.get("company", ticker),
    "sector": market_data.get("sector", "Unknown"),
    "timestamp": ISO_timestamp_now,
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
    
    # Preview of final signal (debate engine adds full signal in Week 4)
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

async _run_swarm(self, ticker: str, market_data: dict) -> dict
  Runs swarm runner + aggregator.
  runner_output = await self.swarm_runner.run(ticker)
  return self.swarm_aggregator.compute(runner_output)

def _safe_swarm(self, result) -> dict
  If result is an Exception: log the error, return a neutral swarm dict.
  Neutral: { bullish_pct: 50, bearish_pct: 30, hold_pct: 20,
             panic_index: 0, fomo_index: 0, conviction: 50,
             dominant_signal: "NEUTRAL", signal_strength: "WEAK",
             error: str(exception) }

def _safe_specialist(self, result, analyst_name: str) -> dict
  If result is an Exception: log error, return minimal dict:
  { analyst: analyst_name, score: 50, verdict: "NEUTRAL",
    summary: "Analysis unavailable", error: str(exception) }

def _check_agreement(self, swarm_signal: dict, specialist_score: float) -> str
  Check if swarm and specialists agree on direction.
  
  swarm_bullish = swarm_signal.get("bullish_pct", 50) > 55
  specialist_bullish = specialist_score > 55
  
  if swarm_bullish and specialist_bullish: return "STRONG_AGREEMENT_BULLISH"
  if not swarm_bullish and not specialist_bullish: return "STRONG_AGREEMENT_BEARISH"
  if swarm_bullish and not specialist_bullish: return "DIVERGENCE_SWARM_BULLISH"
  if not swarm_bullish and specialist_bullish: return "DIVERGENCE_SPECIALIST_BULLISH"
  return "NEUTRAL"
  
  # DIVERGENCE is actually the most interesting signal —
  # crowd behavior and fundamentals disagree. This becomes
  # a key explainability point in Week 5.

Also wire the orchestrator into api/main.py:
  In the POST /analyze endpoint, replace the mock signal with:
  
  orchestrator = AlphaHiveOrchestrator()  # init once at app startup
  result = await orchestrator.analyze(ticker)
  return result
  
  Store the orchestrator instance in app.state so it's initialized once:
  app.state.orchestrator = AlphaHiveOrchestrator()
  Then in endpoint: orchestrator = request.app.state.orchestrator
```

---

## PROMPT 6 — Week 3 Verification

```
Read AGENTS.md in the project root first.

Create tests/test_week3.py — full pipeline verification.

Run these checks in order. Each must pass before the next.

CHECK 1: Fundamental Analyst returns valid report for NSE stock
  from agents.specialists.fundamental import FundamentalAnalyst
  analyst = FundamentalAnalyst()
  report = await analyst.analyze("RELIANCE.NS", {})
  
  assert report["analyst"] == "fundamental"
  assert 0 <= report["score"] <= 100
  assert report["verdict"] in ["STRONG", "MODERATE", "WEAK"]
  assert isinstance(report["key_positives"], list)
  assert isinstance(report["summary"], str) and len(report["summary"]) > 10
  print(f"✓ CHECK 1 PASSED")
  print(f"  Fundamental score: {report['score']}")
  print(f"  Verdict: {report['verdict']}")
  print(f"  Summary: {report['summary']}")
  print(f"  PE vs sector: {report['derived'].get('pe_vs_sector')}")

CHECK 2: Technical Analyst computes all indicators
  from agents.specialists.technical import TechnicalAnalyst
  analyst = TechnicalAnalyst()
  report = await analyst.analyze("TCS.NS", {})
  
  assert "rsi_14" in report["indicators"]
  assert "ema_50" in report["indicators"]
  assert "ema_200" in report["indicators"]
  assert "trend_structure" in report["indicators"]
  assert 0 <= report["score"] <= 100
  assert report["verdict"] in ["BULLISH", "BEARISH", "NEUTRAL"]
  print(f"✓ CHECK 2 PASSED")
  print(f"  RSI-14: {report['indicators']['rsi_14']:.1f}")
  print(f"  Trend: {report['indicators']['trend_structure']}")
  print(f"  Technical score: {report['score']}")
  print(f"  Key signals: {report['key_signals']}")

CHECK 3: FinBERT Sentiment runs without GPU
  from agents.specialists.sentiment import SentimentAnalyst
  analyst = SentimentAnalyst()
  report = await analyst.analyze("INFY.NS", {})
  
  assert report["analyst"] == "sentiment"
  assert -1.0 <= report["net_sentiment"] <= 1.0
  assert 0 <= report["score"] <= 100
  assert report["verdict"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]
  print(f"✓ CHECK 3 PASSED")
  print(f"  Headlines analyzed: {report['headlines_analyzed']}")
  print(f"  Net sentiment: {report['net_sentiment']:.3f}")
  print(f"  Sentiment score: {report['score']}")
  print(f"  Top headline: {report['top_headlines'][0]['headline'] if report['top_headlines'] else 'none'}")

CHECK 4: News Analyst detects material events
  from agents.specialists.news import NewsAnalyst
  analyst = NewsAnalyst()
  report = await analyst.analyze("HDFCBANK.NS", {})
  
  assert report["analyst"] == "news"
  assert 0 <= report["score"] <= 100
  assert report["verdict"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]
  print(f"✓ CHECK 4 PASSED")
  print(f"  Bullish events: {report['bullish_events']}")
  print(f"  Bearish events: {report['bearish_events']}")
  print(f"  Alert: {report['alert']}")
  print(f"  Summary: {report['summary']}")

CHECK 5: Orchestrator runs full parallel pipeline
  from engine.orchestrator import AlphaHiveOrchestrator
  orchestrator = AlphaHiveOrchestrator()
  
  import time
  start = time.time()
  result = await orchestrator.analyze("RELIANCE.NS")
  elapsed = time.time() - start
  
  assert "swarm" in result
  assert "specialists" in result
  assert "signal_preview" in result
  assert "disclaimer" in result
  assert result["disclaimer"] != ""
  
  # Both layers present
  assert result["specialists"]["fundamental"] is not None
  assert result["specialists"]["technical"] is not None
  assert result["specialists"]["sentiment"] is not None
  assert result["specialists"]["news"] is not None
  
  print(f"✓ CHECK 5 PASSED — Full pipeline in {elapsed:.1f}s")
  print(f"  Ticker: {result['ticker']}")
  print(f"  Swarm signal: {result['swarm']['dominant_signal']}")
  print(f"  Swarm bullish: {result['swarm']['bullish_pct']:.1f}%")
  print(f"  Specialist score: {result['specialists']['combined_score']}")
  print(f"  Agreement: {result['signal_preview']['agreement']}")
  print(f"  Alert: {result['signal_preview']['alert']}")

CHECK 6: API endpoint returns live orchestrator output
  import httpx
  async with httpx.AsyncClient() as client:
    resp = await client.post(
      "http://localhost:8000/analyze",
      json={"ticker": "TCS.NS"},
      timeout=120.0
    )
  assert resp.status_code == 200
  data = resp.json()
  assert "swarm" in data
  assert "X-AlphaHive-Disclaimer" in resp.headers
  print(f"✓ CHECK 6 PASSED — API returning live data")
  print(f"  Response time: {resp.elapsed.total_seconds():.1f}s")

Print final:
  print("\n=== WEEK 3 COMPLETE ===")
  print("Fundamental Analyst (Ollama + yfinance): ✓")
  print("Technical Analyst (pure pandas indicators): ✓")
  print("Sentiment Analyst (FinBERT, local CPU): ✓")
  print("News Analyst (event detection): ✓")
  print("Orchestrator (parallel execution): ✓")
  print("API serving live analysis: ✓")
  print("\nReady for Week 4: Bull vs Bear Debate Engine (LangGraph)")
```

---

## Week 3 End Checklist

```
[ ] FundamentalAnalyst returns valid report for any Nifty 50 stock
[ ] TechnicalAnalyst computes RSI, EMAs, MACD, ATR, Bollinger from scratch
[ ] SentimentAnalyst uses FinBERT (not Ollama) and runs on CPU correctly
[ ] NewsAnalyst detects bullish/bearish keywords and flags high-priority events
[ ] Orchestrator launches swarm + 4 specialists simultaneously (asyncio.gather)
[ ] _check_agreement correctly identifies DIVERGENCE cases
[ ] API /analyze endpoint now returns live orchestrator output (not mock)
[ ] No specialist failure crashes the orchestrator (graceful fallback confirmed)
[ ] Total pipeline time under 120 seconds (target: under 90s)
[ ] SEBI disclaimer present in every API response
[ ] git commit: "Week 3: Specialist analysts + orchestrator complete"
```

---

## Performance Notes

```
Expected timing breakdown:
  Swarm (80 agents, 2 rounds):      45-75s  ← bottleneck, runs in parallel
  Fundamental (yfinance + Ollama):  10-20s  ← runs parallel with swarm
  Technical (pandas compute only):   2-5s   ← fastest, pure math
  Sentiment (FinBERT, CPU):         5-15s   ← depends on headline count
  News (keyword scan + Ollama):      5-15s  ← fast if no material events

Total wall clock (all parallel):    ~75-90s ← dominated by swarm

If swarm is your bottleneck (it will be), Week 4 will introduce Redis
caching so swarm results from the morning run are reused for the debate
engine without re-running 80 agents.
```

---

## Week 4 Preview

Next week: the debate engine and final scoring.
```
engine/
├── debate.py     ← LangGraph: bull vs bear read BOTH swarm + specialists
├── scorer.py     ← final signal: bullish%, risk level, confidence
└── explainer.py  ← 3-line plain English (the product soul)
```

Before Week 4 starts, verify LangGraph is installed:
```bash
pip show langgraph
# Should show version 0.1.x or higher
# If not: pip install langgraph langchain langchain-core
```
