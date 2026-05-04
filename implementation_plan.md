# AlphaHive — Final Refinement & Reference Adaptation

Deep audit of all AlphaHive modules against the three reference repos (TradingAgents, Vibe-Trading, MiroFish). This plan addresses bugs, missing features, performance gaps, and architectural improvements that can be adapted from the references.

## User Review Required

> [!IMPORTANT]
> This is a large plan with **8 work items across backend and frontend**. Some items are independent and can be done in parallel. Please review the priorities and let me know if you'd like to focus on specific items first, or if I should execute all of them.

> [!WARNING]
> Items 6 (Reflection/Memory) and 7 (Risk Debate) are new features adapted from TradingAgents that add new files. The rest are fixes/improvements to existing code.

## Proposed Changes

### 1. Backtest Engine — Add Statistical Validation (Adapted from Vibe-Trading)

**Problem**: AlphaHive's backtest engine computes basic metrics (Sharpe, drawdown, win rate) but has **no statistical validation**. Vibe-Trading's `validation.py` provides three rigorous tools: Monte Carlo permutation testing, Bootstrap Sharpe CI, and Walk-Forward consistency analysis. Without these, backtest results have zero statistical significance.

**What to do**: Write an original `backtest/validation.py` module inspired by Vibe-Trading's approach (Monte Carlo test, Bootstrap CI, Walk-Forward analysis). Wire it into the existing `/backtest` API endpoint.

#### [NEW] [validation.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/backtest/validation.py)
- Monte Carlo permutation test: shuffles trade P&L sequence to test if Sharpe is significantly better than random (p-value)
- Bootstrap Sharpe CI: resamples daily returns to estimate 95% confidence interval on Sharpe
- Walk-Forward consistency: splits backtest into 5 sequential windows, checks if returns are consistent
- All three called from `run_validation()` and wired to the compare endpoint

#### [MODIFY] [compare.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/backtest/compare.py)
- Add validation results to the comparison output when enough trades exist
- Add Calmar ratio and Sortino ratio to metrics (inspired by Vibe-Trading `calc_metrics`)

#### [MODIFY] [engine.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/backtest/engine.py)
- Add Calmar and Sortino to `_metrics()` method
- Add profit_factor calculation

---

### 2. Cache Layer — Graceful Redis Fallback (Bug Fix)

**Problem**: `engine/cache.py` crashes at import time if Redis is unavailable because `aioredis.from_url()` is called in `__init__`. This is a **hard crash** — every orchestrator run fails if Redis is down, even though Redis is meant to be optional.

**What to do**: Convert to lazy initialization with an in-memory fallback when Redis is unavailable.

#### [MODIFY] [cache.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/cache.py)
- Move Redis connection to lazy `_get_redis()` method
- Add try/except around all Redis operations with in-memory dict fallback
- Add `_memory_cache: dict` as fallback storage
- Log warning when falling back to in-memory cache

---

### 3. Specialist Analysts — Fix Async/httpx Issues

**Problem**: All three LLM-calling specialists (Fundamental, Technical, News) create a **new httpx.AsyncClient per call**, which is expensive and can leak connections. Also, `fundamental.py` directly calls `asyncio.get_event_loop()` which is deprecated and will break in Python 3.12+.

**What to do**: Use a shared `httpx.AsyncClient` instance per analyst with proper lifecycle. Fix the deprecated event loop call.

#### [MODIFY] [fundamental.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/agents/specialists/fundamental.py)
- Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()`
- Create a shared `httpx.AsyncClient` in `__init__` with proper timeout config
- Add `close()` method for cleanup

#### [MODIFY] [technical.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/agents/specialists/technical.py)
- Same shared client pattern
- Add `close()` method

#### [MODIFY] [news.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/agents/specialists/news.py)
- Same shared client pattern
- Add `close()` method

---

### 4. Orchestrator — Cleanup Specialist Lifecycle & Signal Timestamp

**Problem**: The orchestrator instantiates specialist analysts on every `analyze()` call, and never closes their httpx clients. Also, the final signal output is missing the `timestamp` field required by AGENTS.md.

#### [MODIFY] [orchestrator.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/orchestrator.py)
- Move specialist instantiation to `__init__` (they're stateless, no need to recreate)
- Add `close()` method that closes all specialist httpx clients
- Ensure `timestamp` is always set in the final signal output
- Add missing `hold_pct` to swarm section of final signal

---

### 5. Debate Engine — Add Multi-Round Support (Adapted from TradingAgents)

**Problem**: AlphaHive's debate engine runs a single pass: Bull → Bear → Risk Manager. TradingAgents uses a **multi-round debate loop** where Bull and Bear go back and forth for N rounds, with a judge deciding when to stop. This produces much richer analysis.

**What to do**: Add configurable multi-round debate with a round counter and early-termination condition (when a researcher repeats themselves or round limit is reached). This is inspired by TradingAgents' `conditional_logic.should_continue_debate` pattern.

#### [MODIFY] [debate.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/debate.py)
- Add `max_debate_rounds` config (default: 2, max: 4)
- Add round counter to the LangGraph state
- Add conditional edge that checks round count before looping Bull ↔ Bear
- Accumulate debate history across rounds (inspired by TradingAgents `investment_debate_state.history`)
- Pass accumulated history to Risk Manager for final judgment

---

### 6. Signal Memory & Reflection (Adapted from TradingAgents)

**Problem**: AlphaHive generates signals but never looks back to see if they were right. TradingAgents has a **reflection system** where past decisions are compared against actual returns, generating lessons that improve future analysis. This is a key differentiator.

**What to do**: Create a lightweight signal outcome tracker that stores past signals and, on the next run for the same ticker, checks if the signal was correct. Generate a 2-4 sentence reflection.

#### [NEW] [memory.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/memory.py)
- `SignalMemory` class with file-based JSON storage (no extra DB dependency)
- `store_signal(ticker, signal)` — saves signal with timestamp
- `get_pending_signals(ticker)` — finds signals that haven't been evaluated
- `evaluate_signal(ticker, signal_date)` — fetches actual return from yfinance, computes if signal was correct
- `reflect(ticker)` — generates 2-4 sentence plain-text reflection using Ollama
- `get_past_context(ticker)` — returns last 3 reflections for injection into debate prompts

#### [MODIFY] [orchestrator.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/orchestrator.py)
- After generating a signal, store it via `SignalMemory.store_signal()`
- Before debate, inject past reflections into the debate prompts via `get_past_context()`

---

### 7. Risk Debate Layer (Adapted from TradingAgents)

**Problem**: AlphaHive has a single Risk Manager node in the debate engine. TradingAgents has a **3-way risk debate** between Aggressive, Conservative, and Neutral analysts, followed by a Portfolio Manager who makes the final call. This produces more nuanced risk assessment.

**What to do**: Add a risk debate step after the Bull/Bear investment debate, with three risk perspectives feeding into the final scorer.

#### [MODIFY] [debate.py](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/engine/debate.py)
- Add three risk perspective nodes: `aggressive_risk`, `conservative_risk`, `neutral_risk`
- Each node receives the Bull/Bear debate summary + specialist reports
- Add edges: Risk Manager → Aggressive → Conservative → Neutral → Risk Manager (conditional loop)
- Risk Manager node reads all three perspectives before making final call
- Add `max_risk_rounds` config (default: 1)

---

### 8. Frontend — Fix SSE Integration & Add Missing Metrics

**Problem**: The watchlist page sorts by `trust_score` but accesses it inconsistently (`research_quality?.trust_score ?? signal.trust_score`). The stock detail page may crash when signal fields are undefined.

#### [MODIFY] [page.tsx (watchlist)](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/frontend/src/app/watchlist/page.tsx)
- Fix trust score access to use consistent path
- Add null-safe access for all signal fields in sorting

#### [MODIFY] [AppContext.tsx](file:///c:/Users/bhima/OneDrive/Desktop/AlphaHive/frontend/src/context/AppContext.tsx)
- Add error boundary for API failures
- Add retry logic for failed watchlist fetches

---

## Execution Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 P0 | 2. Cache Redis Fallback | Small | Critical — prevents crashes |
| 🔴 P0 | 3. Fix Specialist async/httpx | Small | Prevents leaks + crashes on Py 3.12 |
| 🟡 P1 | 4. Orchestrator cleanup | Small | Quality + signal compliance |
| 🟡 P1 | 5. Multi-round debate | Medium | Major analysis quality improvement |
| 🟡 P1 | 1. Backtest validation | Medium | Adds statistical rigor |
| 🟢 P2 | 6. Signal memory/reflection | Medium | Differentiator from TradingAgents |
| 🟢 P2 | 7. Risk debate layer | Large | Advanced debate architecture |
| 🟢 P2 | 8. Frontend fixes | Small | UI stability |

## Open Questions

> [!IMPORTANT]
> **Multi-round debate performance**: Each debate round is an Ollama LLM call (~5-10s). With 2 rounds × 2 researchers = 4 extra calls. Are you comfortable with adding ~20-40s to analysis time for richer debate? Default would be 2 rounds.

> [!NOTE]
> **Risk debate layer**: This is the largest new feature. It adds 3 new LLM calls per analysis. Should I implement it as an optional mode (enabled via env var) so it doesn't slow down the default path?

## Verification Plan

### Automated Tests
- Run existing test suite: `pytest tests/` — ensure no regressions
- New test file `tests/test_validation.py` for backtest validation
- New test file `tests/test_memory.py` for signal memory

### Manual Verification
- Start backend with `python -m api.main` and verify `/health`, `/analyze`, `/backtest` endpoints
- Test with Redis down → verify graceful fallback to in-memory cache
- Test with Ollama down → verify graceful degradation in specialists
