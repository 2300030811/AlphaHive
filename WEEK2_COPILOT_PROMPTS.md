# AlphaHive — Week 2 Copilot Prompt Sequence
# Building the Swarm Engine — 80 Personality Agents
# Run these prompts IN ORDER. One prompt = one Copilot session.
# Always tell Copilot to read AGENTS.md first in every session.

---

## What You're Building This Week

```
agents/
├── base.py                        ← PROMPT 1
├── swarm/
│   ├── personalities/
│   │   ├── retail.py              ← PROMPT 2
│   │   ├── institutional.py       ← PROMPT 3
│   │   ├── algo.py                ← PROMPT 4
│   │   └── news_reactor.py        ← PROMPT 5
│   ├── runner.py                  ← PROMPT 6
│   └── aggregator.py              ← PROMPT 7
└── verification                   ← PROMPT 8
```

By end of Week 2:
- 80 agents exist with distinct personalities
- All 80 run in parallel via asyncio (Round 1)
- Agents see crowd summary and revise (Round 2)
- Aggregator produces panic_index, fomo_index, conviction score
- Full swarm output for RELIANCE.NS in under 60 seconds

---

## PROMPT 1 — BaseAgent Class

```
Read AGENTS.md in the project root first. Focus on:
- The 80 agent roster section
- The AlphaHiveSignal output format
- The tech stack section (Ollama models)

Create agents/base.py — the BaseAgent class that all 80 swarm agents inherit from.

This class handles everything that is common across all agents so the
personality files stay clean and focused on behavior only.

The BaseAgent class needs:

__init__(self, name: str, agent_type: str, weight: float, personality_prompt: str)
  - name: e.g. "Panic_Seller_03"
  - agent_type: "retail" | "institutional" | "algo" | "news_reactor"
  - weight: float (how much this agent's vote counts — from AGENTS.md roster)
  - personality_prompt: the system prompt that defines who this agent is

async decide_round1(self, market_data: dict) -> dict
  Runs the agent's Round 1 decision (no knowledge of other agents).
  market_data contains: ticker, price, indicators, news_headlines, fii_dii_flow
  
  Calls Ollama with:
    - system: self.personality_prompt + round1 instructions
    - user: formatted market_data as readable text
  
  Returns:
  {
    "agent_name": self.name,
    "agent_type": self.agent_type,
    "weight": self.weight,
    "round": 1,
    "action": "buy" | "sell" | "hold",
    "confidence": 0.0 to 1.0,
    "reasoning": "one sentence max — why this agent made this choice"
  }
  
  If LLM fails or returns unparseable JSON: return a neutral hold with
  confidence 0.1 and reasoning "agent error — defaulting to hold"
  Never crash. Always return something.

async decide_round2(self, market_data: dict, crowd_summary: str) -> dict
  Same as Round 1 but receives a crowd_summary string.
  crowd_summary example:
  "Round 1 results: 67% of agents chose BUY, 21% SELL, 12% HOLD.
   Panic agents: mostly SELLING (73%). Institutional agents: mostly BUYING (80%).
   Algo agents: split (52% buy). News reactors: mostly BUYING (65%)."
  
  Agent must decide: do I stick with my Round 1 choice or revise?
  Some personalities always ignore crowd (Noise_Ignorer, SIP_Investor).
  Some personalities strongly follow crowd (FOMO_Buyer, Panic_Seller).
  This is handled by each subclass — base class just passes crowd_summary in.
  
  Returns same structure as Round 1 with "round": 2.

_call_ollama(self, system_prompt: str, user_prompt: str) -> str
  Private method. Calls Ollama HTTP API directly using httpx.
  URL: http://localhost:11434/api/chat
  Model: read from env OLLAMA_SWARM_MODEL (default: llama3.2:3b)
  
  Request body:
  {
    "model": model_name,
    "messages": [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": user_prompt}
    ],
    "stream": false,
    "options": {
      "temperature": 0.7,
      "num_predict": 150    ← keep responses SHORT for speed
    }
  }
  
  Returns the response text string.
  Timeout: 30 seconds per call.
  On failure: raises AgentError with clear message.

_parse_decision(self, response_text: str) -> dict
  Parse the LLM response into { action, confidence, reasoning }.
  The LLM is instructed to respond ONLY in JSON.
  If JSON parse fails: try to extract "buy"/"sell"/"hold" from raw text.
  If that fails too: return { action: "hold", confidence: 0.1, reasoning: "parse error" }

Also create a custom AgentError exception class in this file.

Add a __repr__ that shows: AgentName(type=retail, weight=0.6)
Use type hints throughout. Add clear docstrings.
```

---

## PROMPT 2 — Retail Personality Agents (25 agents)

```
Read AGENTS.md in the project root first. Focus on the RETAIL ARCHETYPES
section in the "The 80 Personality Agents" list.

Create agents/swarm/personalities/retail.py

Import BaseAgent from agents/base.py.

Build these 5 retail agent classes, each a subclass of BaseAgent.
Each class overrides __init__ to set its own personality_prompt.
The personality_prompt is the SYSTEM PROMPT that shapes how this agent
thinks — it defines their psychology, what they care about, what scares them.

Each class also has a class method: create_instances(n: int) -> list
That returns n instances of itself with names like "Panic_Seller_01", etc.

---

CLASS 1: PanicSellerAgent (creates 8 instances, weight=0.6)
Personality prompt to write:
"You are a retail investor in India who panics easily. You check Zerodha
every 10 minutes. Any price drop of 2% or more makes you want to sell
immediately. Bad news headlines terrify you. You have lost money before
by holding through drops and you will not do it again. You prioritize
protecting capital over making gains. You often sell at the worst time.
When the crowd is also selling, you feel validated and sell harder.
When you see institutional investors buying, you feel slightly reassured
but still nervous."

Decision rules to encode in the prompt:
- SELL if: price_change_today < -2% OR any negative headline detected
- SELL if: crowd is selling AND you are uncertain
- HOLD only if: everything looks calm and green
- BUY almost never — only if RSI very oversold (<25) AND crowd strongly buying

---

CLASS 2: FOMOBuyerAgent (creates 7 instances, weight=0.7)
Personality prompt to write:
"You are a retail investor who suffers from extreme FOMO (Fear Of Missing
Out). When you see a stock going up, you need to buy it immediately or
you feel sick. You chase green candles. You buy breakouts. You do not
care about fundamentals — only momentum and what other people are doing.
When 60% or more of people are buying, you upgrade your conviction
immediately. You have bought at the top many times. You ignore bad news
as long as the price is going up."

Decision rules to encode:
- BUY if: price_change_today > 1% OR volume_ratio > 1.5
- STRONG BUY if: crowd_bullish_pct > 60% (Round 2 especially)
- SELL only if: price drops sharply — stop loss mentality
- HOLD if: price flat and crowd is mixed

---

CLASS 3: ZerodhaNewbieAgent (creates 5 instances, weight=0.4)
Personality prompt to write:
"You are a new retail investor who opened a Zerodha account 6 months ago.
You are emotional and inconsistent. You watch CNBC and react to whatever
the anchors say. You do not understand RSI or EMA but you know what green
and red means. You make impulsive decisions. Sometimes you buy because
your friend told you to. Sometimes you sell because a headline scared you.
Your decisions are somewhat random but biased toward buying anything
trending and selling anything red."

Decision rules: intentionally more random — use higher temperature,
shorter reasoning. This adds realistic noise to the swarm.

---

CLASS 4: SIPInvestorAgent (creates 3 instances, weight=0.9)
Personality prompt to write:
"You are a disciplined SIP (Systematic Investment Plan) investor in India.
You invest every month regardless of market conditions. You think in
5-10 year horizons. Short term price moves do not affect you. You only
care about one thing: is the stock's price near or below its 200-day
moving average? If yes, you accumulate. If significantly above 200 DMA,
you hold but do not add. You never panic sell. You ignore news noise.
You are the most rational retail investor in the market."

Decision rules:
- BUY if: price is at or below 200 EMA support
- HOLD if: price is above 200 EMA (still invested, just not adding)
- SELL almost never — only on fundamental breakdown
- IGNORE crowd_summary entirely in Round 2 (true to personality)

---

CLASS 5: MoneycontrolReaderAgent (creates 2 instances, weight=0.75)
Personality prompt to write:
"You are a retail investor who reads Moneycontrol religiously every morning.
You trust analyst upgrades and downgrades completely. If a brokerage
upgrades a stock with a higher target price, you buy. If they downgrade,
you sell. You are also influenced by Moneycontrol's sentiment indicators.
You check what FII and DII are doing because you read it on Moneycontrol
and believe that FII behavior predicts stock direction."

Decision rules:
- BUY if: positive analyst mention in news OR FII net buying
- SELL if: analyst downgrade mentioned OR FII net selling
- HOLD if: no clear signal from news

---

At the bottom of the file, add:

def get_all_retail_agents() -> list[BaseAgent]:
    """Returns all 25 retail agents ready for the swarm runner."""
    agents = []
    agents.extend(PanicSellerAgent.create_instances(8))
    agents.extend(FOMOBuyerAgent.create_instances(7))
    agents.extend(ZerodhaNewbieAgent.create_instances(5))
    agents.extend(SIPInvestorAgent.create_instances(3))
    agents.extend(MoneycontrolReaderAgent.create_instances(2))
    return agents  # 25 total

Use type hints. Add docstrings. Keep personality prompts tight — max 100 words each.
Shorter prompts = faster LLM responses = faster swarm.
```

---

## PROMPT 3 — Institutional Personality Agents (20 agents)

```
Read AGENTS.md in the project root first. Focus on INSTITUTIONAL ARCHETYPES.

Create agents/swarm/personalities/institutional.py

Same structure as retail.py — subclasses of BaseAgent, create_instances(), etc.

---

CLASS 1: FIIAgent — Foreign Institutional Investor (6 instances, weight=1.5)
Personality prompt:
"You are a Foreign Institutional Investor (FII) managing a large emerging
markets fund. Your decisions are driven by: global risk appetite (risk-on vs
risk-off), US Federal Reserve policy, dollar index (DXY) direction, and India's
macro fundamentals. When global risk is ON and DXY is falling, you buy Indian
equities aggressively. When risk is OFF or DXY is rising, you sell. You have
very large position sizes, so you think about liquidity. You follow momentum
at a macro level. You DO NOT panic on single stock news — only macro matters."

Decision rules:
- BUY if: fii_flow is net positive today (from nse.py data)
- BUY if: strong sector momentum + global risk-on
- SELL if: fii_flow is net negative
- Weight=1.5 — their votes count more (represent large capital)

---

CLASS 2: DIIValueAgent — Domestic Institutional Investor (5 instances, weight=1.8)
Personality prompt:
"You are a Domestic Institutional Investor (DII) — a mutual fund or insurance
company managing Indian retail savings. You are value-oriented. You buy on
dips when fundamentals are strong. You are contrarian to FIIs — when FIIs sell
and price drops, you often step in and buy if you believe in the business.
You look at P/E vs sector average, earnings growth, and promoter holding.
You are patient. You do not react to single day moves. You are the stabilizing
force in Indian markets."

Decision rules:
- BUY if: dii_flow net positive AND fundamental_score high
- BUY if: FII selling has caused price drop but fundamentals intact
- HOLD otherwise — rarely sell unless fundamental breakdown
- Contrarian signal: if 70% of agents selling, you might buy

---

CLASS 3: HedgeFundShortAgent (4 instances, weight=1.2)
Personality prompt:
"You are a hedge fund analyst looking for short opportunities in Indian markets.
You look for stocks that are technically overbought (RSI > 75) combined with
weak or deteriorating fundamentals. You also watch for stocks with high
promoter pledging (a red flag in India), recent insider selling, or poor
earnings quality. You are not emotional. You are analytical and cold.
When you find a short opportunity, you have high conviction. You ignore
the crowd — in fact, when everyone is bullish, you get more suspicious."

Decision rules:
- SELL (short signal) if: RSI > 75 AND fundamental issues detected
- SELL if: crowd is extremely bullish (contrarian indicator for you)
- HOLD if: no clear short thesis
- Never BUY — you only look for shorts or stay flat

---

CLASS 4: MFSIPMachineAgent — Mutual Fund (3 instances, weight=2.0)
Personality prompt:
"You represent systematic SIP flows into equity mutual funds. Every month,
crores of rupees from retail SIP investors flow into you automatically.
You must deploy this capital regardless of market conditions. You are
not emotional. You buy consistently. You slightly favor large-cap Nifty 50
stocks that are liquid. You are the most consistent buyer in Indian markets.
You represent the backbone of domestic institutional buying."

Decision rules:
- BUY almost always — SIP flows are automatic
- HOLD only if stock is truly illiquid or suspended
- NEVER SELL on short term moves
- Weight=2.0 — represents large consistent capital

---

CLASS 5: LICInsuranceAgent (2 instances, weight=2.5)
Personality prompt:
"You are LIC (Life Insurance Corporation of India) — the largest domestic
institutional investor. You manage the savings of crores of Indians. Your
horizon is 10-20 years. You buy massive dips. A 10% correction in a quality
Nifty 50 stock is an opportunity for you. You do not care about quarterly
earnings noise. You care about India's long-term growth story. When markets
are panicking and everyone is selling, you are often buying.
Your weight is the highest because you represent the most capital."

Decision rules:
- BUY on large drops (>10% from recent high)
- HOLD in normal conditions
- NEVER sell Nifty 50 quality stocks short term
- Weight=2.5 — highest weight in the entire swarm

---

At the bottom:

def get_all_institutional_agents() -> list[BaseAgent]:
    agents = []
    agents.extend(FIIAgent.create_instances(6))
    agents.extend(DIIValueAgent.create_instances(5))
    agents.extend(HedgeFundShortAgent.create_instances(4))
    agents.extend(MFSIPMachineAgent.create_instances(3))
    agents.extend(LICInsuranceAgent.create_instances(2))
    return agents  # 20 total
```

---

## PROMPT 4 — Algo Personality Agents (20 agents)

```
Read AGENTS.md in the project root first. Focus on ALGO ARCHETYPES.

Create agents/swarm/personalities/algo.py

Same structure as previous files.

Important note for algo agents: these agents are MORE deterministic.
Their decisions should follow rules strictly with less randomness.
Use temperature=0.3 for algo agents (lower than retail's 0.7).
Override _call_ollama options in each algo agent class to set temperature.

---

CLASS 1: RSIBotAgent (5 instances, weight=1.0)
Personality prompt:
"You are a pure RSI trading algorithm. You have ONE rule: buy when RSI
is below 30 (oversold), sell when RSI is above 70 (overbought), hold
otherwise. You do not care about news, fundamentals, or what other agents
think. You are mechanical. You never deviate from your RSI rule.
You represent the thousands of simple momentum algos running in markets."

Decision: purely RSI_14 value. No crowd influence in Round 2.

---

CLASS 2: EMACrossoverBotAgent (5 instances, weight=1.0)
Personality prompt:
"You are an EMA crossover algorithm. Golden Cross (50 EMA above 200 EMA)
means BUY. Death Cross (50 EMA below 200 EMA) means SELL. If neither
cross has occurred recently, you HOLD. You are purely technical.
You ignore all other inputs."

Decision: purely EMA_50 vs EMA_200 relationship.

---

CLASS 3: VolumeBreakoutBotAgent (4 instances, weight=1.0)
Personality prompt:
"You are a volume breakout algorithm. You only act when volume is greater
than 2x the 30-day average. High volume with price UP = BUY signal.
High volume with price DOWN = SELL signal. Normal volume = HOLD always.
Volume confirms institutional intent — that is all you care about."

Decision: volume_ratio > 2.0 is the trigger. Direction = price_change sign.

---

CLASS 4: MeanReversionBotAgent (4 instances, weight=0.9)
Personality prompt:
"You are a mean reversion algorithm. You believe that extreme price moves
revert to average. If a stock is up more than 5% today, you SELL (expect
reversion down). If it is down more than 5% today, you BUY (expect bounce).
You are contrarian to momentum. You bet against extreme single-day moves."

Decision: abs(price_change_today) > 5% is the trigger. Action = opposite direction.

---

CLASS 5: ArbitrageBotAgent (2 instances, weight=1.1)
Personality prompt:
"You are a sector rotation and relative strength algorithm. You compare
the target stock's performance to its sector average. If the stock is
significantly outperforming its sector peers, you BUY (relative strength).
If it is significantly underperforming its peers, you SELL (relative weakness).
You represent funds that rotate capital toward sector leaders."

Decision: compare stock performance vs sector average from nse.py sector data.

---

def get_all_algo_agents() -> list[BaseAgent]:
    agents = []
    agents.extend(RSIBotAgent.create_instances(5))
    agents.extend(EMACrossoverBotAgent.create_instances(5))
    agents.extend(VolumeBreakoutBotAgent.create_instances(4))
    agents.extend(MeanReversionBotAgent.create_instances(4))
    agents.extend(ArbitrageBotAgent.create_instances(2))
    return agents  # 20 total
```

---

## PROMPT 5 — News Reactor Agents (15 agents)

```
Read AGENTS.md in the project root first. Focus on NEWS REACTOR ARCHETYPES.

Create agents/swarm/personalities/news_reactor.py

Same structure as previous files.

---

CLASS 1: BadNewsOverreactorAgent (5 instances, weight=0.5)
Personality prompt:
"You overreact to negative news. If any headline mentions: loss, decline,
cut, downgrade, miss, warning, fraud, investigation, or fall — you panic
sell immediately. You assume the worst interpretation of every negative
word. You represent retail investors who read scary headlines and sell
without thinking. Your weight is low because your overreaction is often
wrong."

Decision: scan news_headlines for negative keywords → SELL with high confidence.
If no negative headlines → HOLD (you wait for bad news, not good news).

---

CLASS 2: GoodNewsChaserAgent (5 instances, weight=0.7)
Personality prompt:
"You chase positive news aggressively. If any headline mentions: beat,
record, growth, upgrade, expansion, profit, win, new contract, or strong
— you buy immediately. You assume positive headlines mean the stock will
go up. You represent retail investors who buy on good news momentum.
You often buy after the price has already moved."

Decision: scan news_headlines for positive keywords → BUY with high confidence.
If no positive headlines → HOLD.

---

CLASS 3: NoiseIgnorerAgent (3 instances, weight=1.0)
Personality prompt:
"You completely ignore news. You believe news is already priced in by the
time you read it. You only look at price action and volume. News is noise.
You are a pure price action trader. In Round 2, you also ignore what other
agents decided — you only trust what the chart is telling you."

Decision: use only price_change and volume_ratio. Full ignore of headlines.
Also ignore crowd_summary in Round 2.

---

CLASS 4: AnalystFollowerAgent (2 instances, weight=1.3)
Personality prompt:
"You follow analyst recommendations exactly. If news mentions a brokerage
upgrading this stock with a higher target price, you buy immediately.
If a downgrade or target price cut is mentioned, you sell immediately.
You trust analysts completely. You represent retail investors who rely on
brokerage research. When no analyst news is available, you hold."

Decision: scan for "upgrade", "target price", "buy rating" → BUY.
Scan for "downgrade", "sell rating", "cut" → SELL.
No analyst news → HOLD.

---

def get_all_news_reactor_agents() -> list[BaseAgent]:
    agents = []
    agents.extend(BadNewsOverreactorAgent.create_instances(5))
    agents.extend(GoodNewsChaserAgent.create_instances(5))
    agents.extend(NoiseIgnorerAgent.create_instances(3))
    agents.extend(AnalystFollowerAgent.create_instances(2))
    return agents  # 15 total
```

---

## PROMPT 6 — Swarm Runner (The Engine)

```
Read AGENTS.md in the project root first. Focus on:
- The two-layer architecture section
- Round 1 and Round 2 descriptions
- The complete list of imports from all 4 personality files

Create agents/swarm/runner.py — the asyncio parallel swarm runner.

This is the most technically important file in the swarm layer.

Import all 4 get_all_*_agents() functions from personalities/.
Also import DataLoader from data/loader.py and get_news_for_ticker from data/news.py.

The SwarmRunner class:

__init__(self)
  Loads all 80 agents by calling all 4 get_all_*_agents() functions.
  Combines into self.agents (list of 80 BaseAgent instances).
  Logs: "SwarmRunner initialized with {len(agents)} agents"

async prepare_market_data(self, ticker: str) -> dict
  Fetches everything the agents need:
  {
    "ticker": ticker,
    "price": current price (from DataLoader.get_current_price),
    "price_change_pct": daily change %,
    "volume_ratio": today vs 30-day avg,
    "indicators": { rsi_14, ema_50, ema_200, atr_14 },
    "news_headlines": list of headline strings (from get_news_for_ticker),
    "fii_dii": { fii_net, dii_net, fii_sentiment } (from nse.py),
    "price_vs_200ema": "above" | "below" | "at"
  }
  
  Format this as a clear, readable text block too:
  self._format_market_data(data) -> str
  Returns a human-readable market summary for agent prompts.

async run_round1(self, market_data: dict) -> list[dict]
  Runs ALL 80 agents in parallel using asyncio.gather.
  
  tasks = [agent.decide_round1(market_data) for agent in self.agents]
  results = await asyncio.gather(*tasks, return_exceptions=True)
  
  Handle exceptions: if an agent raises an error, replace with a neutral
  hold decision (do not crash the entire round).
  
  Returns list of 80 decision dicts.
  Log: "Round 1 complete: {n_buy} buy, {n_sell} sell, {n_hold} hold"

build_crowd_summary(self, round1_results: list[dict]) -> str
  Computes summary statistics from Round 1 results.
  Returns a human-readable string for Round 2 agent prompts:
  
  "Round 1 results for {ticker}:
  Overall: {buy_pct}% BUY, {sell_pct}% SELL, {hold_pct}% HOLD
  By type:
    Retail agents: {retail_buy}% buying, {retail_sell}% selling
    Institutional: {inst_buy}% buying, {inst_sell}% selling  
    Algo agents: {algo_buy}% buying, {algo_sell}% selling
    News reactors: {news_buy}% buying, {news_sell}% selling
  
  Notable: {highest_conviction_type} showing strongest signal.
  Panic agents: {panic_sell_pct}% selling.
  Institutional agents: {inst_buy_pct}% buying."
  
  Use weighted percentages (multiply by agent weight, then normalize).

async run_round2(self, market_data: dict, crowd_summary: str,
                 round1_results: list[dict]) -> list[dict]
  Same as run_round1 but calls agent.decide_round2(market_data, crowd_summary).
  
  IMPORTANT: Some agents ignore crowd in Round 2 (SIPInvestor, NoiseIgnorer,
  RSIBot, etc.) — this is handled inside their personality classes,
  the runner just passes crowd_summary to everyone.
  
  Returns list of 80 final decision dicts.
  Log: "Round 2 complete: {n_buy} buy, {n_sell} sell, {n_hold} hold"
  Log: "Conviction shift: Round1={r1_buy}% → Round2={r2_buy}% buy"

async run(self, ticker: str) -> dict
  The main public method. Runs the complete swarm analysis.
  
  1. market_data = await self.prepare_market_data(ticker)
  2. round1 = await self.run_round1(market_data)
  3. crowd_summary = self.build_crowd_summary(round1)
  4. round2 = await self.run_round2(market_data, crowd_summary, round1)
  5. Returns { ticker, market_data, round1_results, round2_results, crowd_summary }
  
  Log total time taken.
  Target: under 60 seconds for 80 agents.

Add timing logs throughout so we can see if any agent is slow.
Use asyncio.timeout (Python 3.11+) or asyncio.wait_for for per-agent timeouts of 25s.
```

---

## PROMPT 7 — Swarm Aggregator

```
Read AGENTS.md in the project root first. Focus on:
- The AGGREGATE OUTPUT section in the architecture
- The swarm section of AlphaHiveSignal format

Create agents/swarm/aggregator.py

The SwarmAggregator class takes the runner output and computes
the final swarm signal metrics.

compute(self, runner_output: dict) -> dict
  Input: the full dict from SwarmRunner.run()
  Output: the "swarm" section of AlphaHiveSignal

  Compute these metrics from round2_results:

  1. bullish_pct
     Weighted % of BUY decisions in Round 2.
     weight_buy = sum(agent.weight for agent if action=="buy")
     weight_total = sum(all agent weights)
     bullish_pct = (weight_buy / weight_total) * 100

  2. bearish_pct
     Same but for SELL decisions.

  3. hold_pct
     Same but for HOLD decisions.
     (bullish + bearish + hold should sum to 100)

  4. panic_index
     Focus ONLY on panic-type agents: PanicSeller, BadNewsOverreactor,
     ZerodhaNewbie (partial).
     panic_index = weighted % of these agents choosing SELL in Round 2.
     Scale: 0 (no panic) to 100 (maximum panic).

  5. fomo_index
     Focus on momentum/fomo agents: FOMOBuyer, GoodNewsChaser.
     Also check Round 1→Round 2 upgrades by these agents.
     fomo_index = % of fomo-type agents who are BUYing AND
                  upgraded their confidence from Round 1 to Round 2.

  6. conviction
     Measures how stable the crowd signal is.
     For each agent: did they change their action from Round 1 to Round 2?
     changed = count of agents where round1.action != round2.action
     conviction = ((total_agents - changed) / total_agents) * 100
     High conviction = few agents changed = strong signal.
     Low conviction = many agents changed = uncertain/volatile signal.

  7. round1_bullish
     Weighted bullish_pct from Round 1 results (before social influence).

  8. round2_bullish
     Weighted bullish_pct from Round 2 results (after social influence).
     If round2_bullish > round1_bullish: crowd amplified bullishness (FOMO risk).
     If round2_bullish < round1_bullish: crowd dampened bullishness (panic risk).

Returns:
{
  "bullish_pct": float,
  "bearish_pct": float,
  "hold_pct": float,
  "panic_index": float,
  "fomo_index": float,
  "conviction": float,
  "round1_bullish": float,
  "round2_bullish": float,
  "crowd_amplification": float,  # round2_bullish - round1_bullish
  "dominant_signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "signal_strength": "STRONG" | "MODERATE" | "WEAK"
}

dominant_signal logic:
  if bullish_pct > 60: BULLISH
  elif bearish_pct > 60: BEARISH
  else: NEUTRAL

signal_strength logic:
  if conviction > 80 AND (bullish_pct > 65 OR bearish_pct > 65): STRONG
  elif conviction > 60: MODERATE
  else: WEAK

Also add a generate_crowd_narrative(swarm_output: dict) -> str method:
  Returns a single plain-English sentence describing the crowd behavior.
  Examples:
  "Strong institutional accumulation with low retail panic."
  "Widespread panic selling led by retail, institutions holding firm."
  "Mixed signals — algos buying, retail uncertain, no clear crowd direction."
  Use the metrics to template these narratives (not LLM — pure logic).
```

---

## PROMPT 8 — Week 2 Verification

```
Read AGENTS.md in the project root first.

Create tests/test_week2.py to verify the entire swarm engine works.

Run these checks in order:

CHECK 1: All 80 agents load correctly
  from agents.swarm.personalities.retail import get_all_retail_agents
  from agents.swarm.personalities.institutional import get_all_institutional_agents
  from agents.swarm.personalities.algo import get_all_algo_agents
  from agents.swarm.personalities.news_reactor import get_all_news_reactor_agents
  
  retail = get_all_retail_agents()
  institutional = get_all_institutional_agents()
  algo = get_all_algo_agents()
  news = get_all_news_reactor_agents()
  
  assert len(retail) == 25, f"Expected 25 retail agents, got {len(retail)}"
  assert len(institutional) == 20
  assert len(algo) == 20
  assert len(news) == 15
  total = retail + institutional + algo + news
  assert len(total) == 80, f"Expected 80 total agents, got {len(total)}"
  print(f"✓ CHECK 1 PASSED: {len(total)} agents loaded")

CHECK 2: Single agent decision works
  Take one PanicSellerAgent instance.
  Create mock market_data with RELIANCE.NS data.
  Call decide_round1(market_data).
  Assert result has: agent_name, action (buy/sell/hold), confidence (0-1), reasoning.
  Print the decision.
  print(f"✓ CHECK 2 PASSED: Single agent returns valid decision")

CHECK 3: Full Round 1 parallel run
  runner = SwarmRunner()
  market_data = await runner.prepare_market_data("RELIANCE.NS")
  
  import time
  start = time.time()
  round1 = await runner.run_round1(market_data)
  elapsed = time.time() - start
  
  assert len(round1) == 80
  assert all("action" in d for d in round1)
  assert elapsed < 90, f"Round 1 took {elapsed}s — too slow, check Ollama"
  print(f"✓ CHECK 3 PASSED: 80 agents in {elapsed:.1f}s")

CHECK 4: Crowd summary builds correctly
  crowd_summary = runner.build_crowd_summary(round1)
  assert "BUY" in crowd_summary or "SELL" in crowd_summary
  assert "Retail" in crowd_summary
  assert "Institutional" in crowd_summary
  print("✓ CHECK 4 PASSED: Crowd summary generated")
  print(crowd_summary)

CHECK 5: Round 2 runs and shows movement
  round2 = await runner.run_round2(market_data, crowd_summary, round1)
  assert len(round2) == 80
  
  r1_buy = sum(1 for d in round1 if d["action"] == "buy")
  r2_buy = sum(1 for d in round2 if d["action"] == "buy")
  print(f"✓ CHECK 5 PASSED: Round 1 buy={r1_buy}, Round 2 buy={r2_buy}")
  print(f"  Social influence shifted {abs(r2_buy - r1_buy)} agents")

CHECK 6: Aggregator produces valid swarm output
  from agents.swarm.aggregator import SwarmAggregator
  agg = SwarmAggregator()
  runner_output = {
    "ticker": "RELIANCE.NS",
    "market_data": market_data,
    "round1_results": round1,
    "round2_results": round2,
    "crowd_summary": crowd_summary
  }
  swarm_signal = agg.compute(runner_output)
  
  assert 0 <= swarm_signal["bullish_pct"] <= 100
  assert 0 <= swarm_signal["panic_index"] <= 100
  assert 0 <= swarm_signal["conviction"] <= 100
  assert swarm_signal["dominant_signal"] in ["BULLISH", "BEARISH", "NEUTRAL"]
  
  print(f"✓ CHECK 6 PASSED: Swarm signal computed")
  print(f"  Bullish: {swarm_signal['bullish_pct']:.1f}%")
  print(f"  Panic Index: {swarm_signal['panic_index']:.1f}")
  print(f"  Conviction: {swarm_signal['conviction']:.1f}%")
  print(f"  Signal: {swarm_signal['dominant_signal']} ({swarm_signal['signal_strength']})")
  print(f"  Narrative: {agg.generate_crowd_narrative(swarm_signal)}")

Print final summary:
  print("\n=== WEEK 2 COMPLETE ===")
  print("80 personality agents: ✓")
  print("Parallel Round 1: ✓")  
  print("Social influence Round 2: ✓")
  print("Swarm aggregation: ✓")
  print("Ready for Week 3: Specialist analysts")

If any check fails, show the exact error and which file to fix.
```

---

## Week 2 End Checklist

Before starting Week 3, confirm ALL of these:

```
[ ] 80 agents load: 25 retail + 20 institutional + 20 algo + 15 news reactor
[ ] Each agent has a distinct personality_prompt (not copy-paste of each other)
[ ] Single agent decision returns: name, type, weight, round, action, confidence, reasoning
[ ] Round 1 completes in under 90 seconds (80 agents parallel)
[ ] Round 2 shows DIFFERENT results from Round 1 (social influence is working)
[ ] Conviction score: agents that ignore crowd (SIP, Noise Ignorer, RSI Bot)
    do NOT change between Round 1 and Round 2
[ ] Aggregator produces bullish_pct + panic_index + fomo_index + conviction
[ ] All values are in valid ranges (0-100)
[ ] Crowd narrative is a readable English sentence
[ ] git commit: "Week 2: 80-agent swarm engine complete"
```

---

## Performance Troubleshooting

If Round 1 is taking longer than 90 seconds:

```bash
# Check Ollama is running
ollama list

# Check which model you are using (should be fast small model for swarm)
echo $OLLAMA_SWARM_MODEL  # should be llama3.2:3b

# If slow: switch to an even faster model
ollama pull tinyllama
# Then in .env: OLLAMA_SWARM_MODEL=tinyllama

# Check if agents are truly running in parallel
# Look at logs — you should see 80 "Starting agent..." lines
# appear almost simultaneously, not one by one

# If sequential: check that asyncio.gather is being used correctly
# The tasks list must be created BEFORE gather is called
```

---

## Week 3 Preview

Next week you build the 4 specialist analysts:
- agents/specialists/fundamental.py
- agents/specialists/technical.py
- agents/specialists/sentiment.py  ← FinBERT setup (different from Ollama)
- agents/specialists/news.py
- engine/orchestrator.py ← runs swarm + specialists in parallel

Make sure FinBERT model downloads before Week 3:
```bash
python -c "from transformers import pipeline; pipeline('text-classification', model='ProsusAI/finbert')"
# This downloads the model (~400MB) — do it now so Week 3 is smooth
```
