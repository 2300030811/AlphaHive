# AlphaHive — Week 1 Copilot Prompt Sequence
# Run these prompts IN ORDER. One prompt = one Copilot session.
# Always start each session by telling Copilot to read AGENTS.md first.

---

## Before You Start — Setup Commands

Run these in terminal before any coding:

```bash
# Create project structure
mkdir alphahive
cd alphahive
mkdir -p data agents/swarm/personalities agents/specialists engine backtest api frontend

# Create empty __init__.py files
touch data/__init__.py
touch agents/__init__.py
touch agents/swarm/__init__.py
touch agents/swarm/personalities/__init__.py
touch agents/specialists/__init__.py
touch engine/__init__.py
touch backtest/__init__.py
touch api/__init__.py

# Create .env file
touch .env
touch .env.example

# Initialize git
git init
echo ".env" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "node_modules/" >> .gitignore

# Copy AGENTS.md to root
cp /path/to/AGENTS.md ./AGENTS.md
```

---

## PROMPT 1 — requirements.txt + .env setup

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root. It contains the full architecture.

Create requirements.txt for the AlphaHive project with these exact packages:

Backend/API:
- fastapi
- uvicorn[standard]
- python-dotenv
- pydantic
- httpx

Data layer:
- yfinance
- akshare
- pandas
- numpy
- feedparser        (for RSS news parsing)

AI/ML:
- langchain
- langchain-core
- langgraph
- transformers      (for FinBERT sentiment)
- torch             (for FinBERT, CPU only)
- ollama            (for local LLM)

Database:
- sqlalchemy
- asyncpg           (async PostgreSQL)
- redis
- alembic           (database migrations)

Also create .env.example with these fields (empty values):
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_SWARM_MODEL=llama3.2:3b
OLLAMA_SPECIALIST_MODEL=llama3.1:8b
DATABASE_URL=postgresql+asyncpg://user:password@localhost/alphahive
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO

Do not add any API key fields. AlphaHive runs free with Ollama + yfinance + AKShare.
```

---

## PROMPT 2 — Database Schema

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root first.

Create api/database.py with SQLAlchemy async setup and these tables:

Table 1: signals
  - id (UUID primary key)
  - ticker (string, indexed)
  - company (string)
  - sector (string)
  - timestamp (datetime with timezone, indexed)
  - final_call (string: BULLISH/BEARISH/NEUTRAL)
  - bullish_probability (float)
  - risk_level (string: LOW/MEDIUM/HIGH)
  - confidence (string: LOW/MEDIUM/HIGH)
  - explanation_line1 (text)
  - explanation_line2 (text)
  - explanation_line3 (text)
  - raw_signal_json (JSON, stores the complete AlphaHiveSignal dict from AGENTS.md)
  - created_at (datetime, auto)

Table 2: swarm_decisions
  - id (UUID primary key)
  - signal_id (foreign key → signals.id)
  - agent_name (string)
  - agent_type (string: retail/institutional/algo/news_reactor)
  - round_number (integer: 1 or 2)
  - action (string: buy/sell/hold)
  - confidence (float 0.0-1.0)
  - reasoning (text)
  - created_at (datetime, auto)

Table 3: watchlist_stocks
  - id (UUID primary key)
  - ticker (string, unique)
  - company (string)
  - sector (string)
  - is_active (boolean, default true)
  - added_at (datetime, auto)

Use async SQLAlchemy. Include create_all() function.
Use the DATABASE_URL from .env file.
Add a get_db() dependency for FastAPI.

Do not pre-populate any data. We will add the Nifty 50 list separately.
```

---

## PROMPT 3 — Data Loader (Most Important File)

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root. Pay special attention to:
- The NSE Data Conventions section (ticker format, required fields)
- The reference section for /Vibe-Trading loaders (for pattern inspiration)

Create data/loader.py with a DataLoader class.

What it does:
Fetches OHLCV price history and current price for any stock ticker.
Primary source: yfinance (handles .NS format for NSE stocks)
Fallback source: AKShare (when yfinance fails or returns empty data)

The class must have these methods:

1. async get_price_history(ticker: str, days: int = 60) -> pd.DataFrame
   Returns DataFrame with columns: date, open, high, low, close, volume
   NSE tickers use format RELIANCE.NS — pass directly to yfinance
   If yfinance returns empty or raises error, try AKShare automatically
   Log which source was actually used

2. async get_current_price(ticker: str) -> dict
   Returns: { ticker, price, change_pct, volume, timestamp }
   Same fallback logic as above

3. async get_batch_prices(tickers: list[str]) -> dict[str, dict]
   Fetches current price for multiple tickers using asyncio.gather
   Returns dict mapping ticker → price dict
   Never fails entirely — if one ticker fails, include error in result

4. async get_indicators(ticker: str, days: int = 60) -> dict
   Fetches price history then computes:
   - rsi_14 (RSI with 14 period)
   - ema_50 (50-day EMA)
   - ema_200 (200-day EMA)
   - atr_14 (Average True Range 14 period)
   - volume_avg_30 (30-day average volume)
   - volume_ratio (today's volume / volume_avg_30)
   Returns all as a dict

Design pattern to follow (inspired by Vibe-Trading registry pattern):
- Primary loader tries first
- If it raises any exception OR returns empty DataFrame → try fallback
- Log: "yfinance succeeded for RELIANCE.NS" or "yfinance failed, using AKShare"
- Never crash — always return something or raise a clear custom exception

For AKShare NSE data: use ak.stock_us_daily() as a starting point.
Note: AKShare India coverage is limited — handle gracefully if not available.

Add proper type hints. Add docstrings. Handle timezone: NSE is UTC+5:30.
```

---

## PROMPT 4 — NSE-Specific Data Module

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root.

Create data/nse.py for NSE-specific data that no reference repo has.

This is original work — there is nothing to reference. Build from scratch.

The module needs these functions:

1. get_nifty50_universe() -> list[dict]
   Returns the Nifty 50 stock list from AGENTS.md NSE Data Conventions section.
   Each item: { ticker, company, sector }
   Hardcode this list — it rarely changes.

2. async get_fii_dii_flow(date: str = None) -> dict
   Fetch FII and DII buying/selling data.
   Source: NSE website RSS or public endpoint
   URL to try: https://www.nseindia.com/api/fiidiiTradeReact
   Returns: {
     date, fii_net_buy (crores), dii_net_buy (crores),
     fii_sentiment (BUYING/SELLING/NEUTRAL),
     dii_sentiment (BUYING/SELLING/NEUTRAL)
   }
   If fetch fails: return None with logged warning (not a crash)

3. async get_promoter_holding(ticker: str) -> dict
   Attempt to get promoter holding % for an NSE stock.
   Try yfinance major_holders first.
   Returns: { ticker, promoter_pct, institution_pct, public_pct }
   If unavailable: return None (many stocks won't have this)

4. get_sector_for_ticker(ticker: str) -> str
   Returns sector string for a Nifty 50 ticker.
   Build a hardcoded mapping from the Nifty 50 list.
   Returns "Unknown" for tickers not in the list.

5. async get_nifty50_sector_performance() -> dict
   Group Nifty 50 stocks by sector, compute average daily change per sector.
   Returns: { "Banking": +1.2, "IT": -0.4, "Energy": +0.8, ... }
   Uses get_batch_prices from data/loader.py

Import DataLoader from data/loader.py for price data.
All network calls must have a 10-second timeout.
Add SEBI disclaimer as a module-level constant string.
```

---

## PROMPT 5 — News RSS Parser

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root.

Create data/news.py for Indian financial news RSS parsing.

This is completely original — no reference repo does Indian news. Build fresh.

The module needs:

1. A NewsItem dataclass:
   { headline, source, url, published_at, ticker_mentions, sentiment_score }
   sentiment_score is None here (FinBERT runs in agents/specialists/sentiment.py)
   ticker_mentions is a list of NSE tickers found in the headline

2. async get_latest_news(max_items: int = 50) -> list[NewsItem]
   Fetch from these FREE RSS feeds (no API key):
   - Economic Times Markets: https://economictimes.indiatimes.com/markets/rss.cms
   - Moneycontrol: https://www.moneycontrol.com/rss/marketreports.xml
   - NSE press releases: https://www.nseindia.com/api/rss/pressreleases
   
   Use feedparser library (already in requirements.txt)
   Combine all sources, deduplicate by headline, sort by date
   Return max_items most recent

3. async get_news_for_ticker(ticker: str, max_items: int = 10) -> list[NewsItem]
   Filter news where ticker_mentions contains the given ticker
   Also search for company name (e.g. "Reliance" for RELIANCE.NS)
   Build a company name mapping from the Nifty 50 list in data/nse.py

4. extract_ticker_mentions(headline: str) -> list[str]
   Scan a headline for any Nifty 50 company names or ticker symbols
   Return list of .NS format tickers found
   Example: "Reliance Industries Q4 results" → ["RELIANCE.NS"]

Use asyncio for parallel RSS fetching.
Cache results for 30 minutes in memory (simple dict cache with timestamp).
All fetches have 10-second timeout.
Handle malformed RSS gracefully — skip bad items, log warning.
```

---

## PROMPT 6 — FastAPI Skeleton

Paste this into Copilot Chat:

```
Read AGENTS.md in the project root.

Create api/main.py with a FastAPI application skeleton.

This is the web API wrapper around AlphaHive's analysis engine.
The engine doesn't exist yet — create placeholder functions that return
mock data in the exact AlphaHiveSignal format defined in AGENTS.md.

Endpoints to create:

GET /health
  Returns: { status: "ok", version: "0.1.0", timestamp }

GET /watchlist
  Returns list of Nifty 50 stocks from data/nse.py
  With their latest cached signal if available in Redis
  If no cached signal: return stock info with signal: null

POST /analyze
  Body: { ticker: str }
  For now: returns a MOCK AlphaHiveSignal for that ticker
  (real engine replaces mock in Week 4)
  Mock should use correct format from AGENTS.md
  Include SEBI disclaimer in every response

GET /stock/{ticker}
  Returns latest signal for a ticker from PostgreSQL
  If no signal exists: return 404 with helpful message

GET /sectors
  Returns sector performance from data/nse.get_nifty50_sector_performance()

GET /news/{ticker}
  Returns latest 10 news items for a ticker from data/news.py

Include:
- CORS middleware (allow all origins for development)
- Lifespan event to connect database on startup
- Global exception handler that never exposes stack traces
- Request logging middleware
- All responses include SEBI disclaimer in headers:
  X-AlphaHive-Disclaimer: "Educational purposes only. Not investment advice."

Use async everywhere. Use the database from api/database.py.
Use environment variables from .env via python-dotenv.
```

---

## PROMPT 7 — Verify Everything Works

After running all 6 prompts, paste this final verification prompt:

```
Read AGENTS.md in the project root.

Now help me verify the Week 1 build works correctly.

Run through these checks and tell me what to fix if any fail:

CHECK 1: Data loader works for NSE stocks
Write a test script tests/test_loader.py that:
- Imports DataLoader from data/loader.py
- Calls get_price_history("RELIANCE.NS", days=30)
- Prints the first 5 rows of the DataFrame
- Calls get_current_price("TCS.NS")
- Prints the result
- Calls get_indicators("INFY.NS")
- Prints RSI, EMA_50, volume_ratio

CHECK 2: News parser returns Indian headlines
Add to test script:
- Imports get_latest_news from data/news.py
- Prints the 5 most recent headlines with source and date

CHECK 3: Nifty 50 list loads correctly
Add to test script:
- Imports get_nifty50_universe from data/nse.py
- Prints count and first 5 entries

CHECK 4: FastAPI starts without errors
Command to run: uvicorn api.main:app --reload --port 8000
Expected: "Application startup complete" in logs

CHECK 5: Health endpoint responds
Command: curl http://localhost:8000/health
Expected: { "status": "ok", ... }

CHECK 6: Mock analyze works
Command: curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"ticker": "RELIANCE.NS"}'
Expected: Full AlphaHiveSignal format with SEBI disclaimer

For any check that fails, show me the exact error and fix it.
Do not move to Week 2 until all 6 checks pass.
```

---

## End of Week 1 Checklist

Before starting Week 2, confirm ALL of these:

```
[ ] requirements.txt exists with all packages
[ ] .env.example exists with all keys documented
[ ] data/loader.py fetches RELIANCE.NS price history successfully
[ ] data/loader.py falls back to AKShare when yfinance fails
[ ] data/nse.py returns Nifty 50 universe (30 stocks minimum)
[ ] data/news.py fetches at least 10 Indian financial headlines
[ ] api/database.py has all 3 tables defined
[ ] api/main.py starts with uvicorn successfully
[ ] GET /health returns 200
[ ] POST /analyze returns mock signal in correct format
[ ] SEBI disclaimer appears in every signal response
[ ] git commit with message "Week 1: Data foundation complete"
```

---

## Week 2 Preview

Next week you build the swarm engine — the 80 personality agents.
The prompts will reference:
- agents/base.py (BaseAgent class)
- agents/swarm/personalities/retail.py (25 retail agents)
- agents/swarm/runner.py (asyncio parallel runner)

Make sure Ollama is installed and running before Week 2:
```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull the swarm model (fast, small, free)
ollama pull llama3.2:3b

# Pull the specialist model (smarter, still free)
ollama pull llama3.1:8b

# Verify
ollama list
```
