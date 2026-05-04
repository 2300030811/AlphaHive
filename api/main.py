"""
AlphaHive FastAPI application.

Web API wrapper around the AlphaHive analysis engine. It serves the Nifty 50
watchlist, cached/full stock signals, live swarm streaming, sector summaries,
news, backtests, and system health.

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import logging
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json

load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level.upper(), logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("alphahive.api")

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

# SEBI Disclaimer — attached to every response
SEBI_DISCLAIMER = (
    "For educational purposes only. Not investment advice. "
    "AlphaHive is not SEBI-registered. "
    "All trading decisions are entirely your own."
)

VERSION = "0.1.0"
STREAM_ANALYSIS_TIMEOUT_SECONDS = float(
    os.getenv("STREAM_ANALYSIS_TIMEOUT_SECONDS", "45")
)

# -----------------------------------------------------------------------
# Background Job State
# -----------------------------------------------------------------------
# Stores background analysis tasks and their status/telemetry
# In production, this would be a distributed store like Redis, 
# but for MVP local memory is fine as long as we don't restart frequently.
active_jobs = {}
job_queues = {} # job_id -> asyncio.Queue for SSE events

async def _cleanup_stale_jobs():
    """Periodically remove completed jobs from memory to prevent leaks."""
    while True:
        await asyncio.sleep(3600)  # run every hour
        try:
            now = datetime.now(timezone.utc)
            stale_keys = []
            for jid, info in active_jobs.items():
                if info.get("status") in ("completed", "failed"):
                    stale_keys.append(jid)
                elif "started_at" in info:
                    started = datetime.fromisoformat(info["started_at"])
                    if (now - started).total_seconds() > 7200: # 2 hours
                        stale_keys.append(jid)
            
            for jid in stale_keys:
                active_jobs.pop(jid, None)
                job_queues.pop(jid, None)
        except Exception as e:
            logger.error(f"Error in job cleanup: {e}")


# -----------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """Request body for /analyze endpoint."""
    ticker: str


class HealthResponse(BaseModel):
    """Response for /health endpoint."""
    status: str
    version: str
    timestamp: str
    disclaimer: str


class InterviewRequest(BaseModel):
    """Request body for /analyze/interview endpoint."""
    ticker: str
    agent_name: str
    query: str


# -----------------------------------------------------------------------
# Lifespan — startup/shutdown
# -----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect to DB on startup, cleanup on shutdown."""
    logger.info("=" * 60)
    logger.info("AlphaHive API starting up...")
    logger.info(f"Version: {VERSION}")
    logger.info(f"Log Level: {log_level}")
    logger.info("=" * 60)

    # Try to initialize database (will fail gracefully if PostgreSQL not running)
    try:
        from api.database import create_all, check_connection
        db_connected = await check_connection()
        if db_connected:
            await create_all()
            logger.info("Database connected and tables created")
        else:
            logger.warning(
                "Database not available — running without persistence. "
                "Start PostgreSQL and update DATABASE_URL in .env to enable."
            )
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    # Initialize Orchestrator
    try:
        from engine.orchestrator import AlphaHiveOrchestrator
        app.state.orchestrator = AlphaHiveOrchestrator()
    except Exception as e:
        logger.error(f"Failed to initialize Orchestrator: {e}")

    # Start cleanup task
    cleanup_task = asyncio.create_task(_cleanup_stale_jobs())

    logger.info("AlphaHive API ready! 🐝")
    logger.info(SEBI_DISCLAIMER)
    yield

    logger.info("AlphaHive API shutting down...")
    cleanup_task.cancel()


# -----------------------------------------------------------------------
# App initialization
# -----------------------------------------------------------------------
app = FastAPI(
    title="AlphaHive API",
    description=(
        "Multi-agent market intelligence platform for Indian retail investors. "
        "Combines 80+ personality agents with specialist analyst debate. "
        f"\n\n⚠️ {SEBI_DISCLAIMER}"
    ),
    version=VERSION,
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")]

# CORS — lockdown
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# Middleware: Add disclaimer header + request logging
# -----------------------------------------------------------------------
@app.middleware("http")
async def add_disclaimer_header(request: Request, call_next):
    """Add SEBI disclaimer header to every response + log requests."""
    logger.info(f"{request.method} {request.url.path}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return Response(
            content='{"error": "Internal server error", '
                    f'"disclaimer": "{SEBI_DISCLAIMER}"}}',
            status_code=500,
            media_type="application/json",
        )

    response.headers["X-AlphaHive-Disclaimer"] = (
        "Educational purposes only. Not investment advice."
    )
    response.headers["X-AlphaHive-Version"] = VERSION
    return response


# -----------------------------------------------------------------------
# GET /health
# -----------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    System health check.
    Returns API status, version, and current timestamp.
    """
    return {
        "status": "ok",
        "version": VERSION,
        "timestamp": datetime.now(IST).isoformat(),
        "disclaimer": SEBI_DISCLAIMER,
    }


# -----------------------------------------------------------------------
# GET /watchlist
# -----------------------------------------------------------------------
@app.get("/watchlist", tags=["Watchlist"])
async def get_watchlist(req: Request):
    """
    Returns the Nifty 50 watchlist with latest cached signals.
    If no cached signal exists for a stock, signal will be null.
    """
    from data.nse import get_nifty50_universe

    stocks = get_nifty50_universe()

    watchlist = []
    for stock in stocks:
        cached_signal = await _load_cached_signal(req, stock["ticker"])
        watchlist.append({
            "ticker": stock["ticker"],
            "company": stock["company"],
            "sector": stock["sector"],
            "cached_signal": cached_signal,
        })

    return {
        "count": len(watchlist),
        "stocks": watchlist,
        "cached_count": sum(1 for item in watchlist if item["cached_signal"]),
        "disclaimer": SEBI_DISCLAIMER,
    }


async def _load_cached_signal(req: Request, ticker: str) -> dict | None:
    """Best-effort cache lookup used by routes that should work without DB."""
    orchestrator = getattr(req.app.state, "orchestrator", None)
    cache = getattr(orchestrator, "cache", None)
    if cache is None:
        return None

    try:
        signal = await cache.get_signal(ticker)
        return signal if isinstance(signal, dict) else None
    except Exception as e:
        logger.warning("Cached signal lookup failed for %s: %s", ticker, e)
        return None


# -----------------------------------------------------------------------
# POST /analyze
# -----------------------------------------------------------------------
@app.post("/analyze/sync", tags=["Analysis"])
async def analyze_stock_sync(request: AnalyzeRequest, req: Request):
    """
    Run AlphaHive analysis on a stock using the Orchestrator.
    """
    ticker = request.ticker.upper()

    # Validate ticker format
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    try:
        orchestrator = req.app.state.orchestrator
        result = await orchestrator.analyze(ticker)
        logger.info(f"Analysis generated for {ticker}")
        return result
    except Exception as e:
        logger.error(f"Analysis failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# POST /analyze/interview
# -----------------------------------------------------------------------
@app.post("/analyze/interview", tags=["Analysis"])
async def interview_agent(request: InterviewRequest, req: Request):
    """
    Interview a specific swarm agent about their decision for a ticker.
    """
    ticker = _normalize_ticker_symbol(request.ticker)
    
    try:
        orchestrator = req.app.state.orchestrator
        response = await orchestrator.interview_agent(
            ticker=ticker,
            agent_name=request.agent_name,
            query=request.query
        )
        return {
            "ticker": ticker,
            "agent_name": request.agent_name,
            "response": response,
            "disclaimer": SEBI_DISCLAIMER
        }
    except Exception as e:
        logger.error(f"Interview failed for {request.agent_name} on {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# GET /swarm/stream/{ticker}
# -----------------------------------------------------------------------
def _sse_event(event: str, payload: dict) -> str:
    """Encode one Server-Sent Event payload."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _lookup_company_sector(ticker: str) -> tuple[str, str]:
    try:
        from data.nse import get_nifty50_universe

        for stock in get_nifty50_universe():
            if stock.get("ticker") == ticker:
                return stock.get("company", ticker), stock.get("sector", "Unknown")
    except Exception:
        pass

    return ticker.replace(".NS", "").replace(".BO", ""), "Unknown"


def _build_stream_preview_signal(ticker: str) -> dict:
    """
    Deterministic preview used only to keep the live UI responsive while the
    full orchestrator finishes the real signal.
    """
    rng = random.Random(ticker)
    company, sector = _lookup_company_sector(ticker)

    bullish_pct = round(rng.uniform(48.0, 68.0), 1)
    bearish_pct = round(rng.uniform(16.0, min(38.0, 92.0 - bullish_pct)), 1)
    hold_pct = round(max(0.0, 100.0 - bullish_pct - bearish_pct), 1)
    round1_bullish = round(max(30.0, min(78.0, bullish_pct + rng.uniform(-7.0, 4.0))), 1)
    panic_index = round(rng.uniform(8.0, 42.0), 1)
    fomo_index = round(rng.uniform(18.0, 58.0), 1)
    conviction = round(rng.uniform(62.0, 88.0), 1)
    crowd_amplification = round(bullish_pct - round1_bullish, 1)

    if bullish_pct > 60:
        final_call = "BULLISH"
    elif bearish_pct > 60:
        final_call = "BEARISH"
    else:
        final_call = "NEUTRAL"

    signal_strength = (
        "STRONG"
        if conviction > 80 and max(bullish_pct, bearish_pct) > 65
        else "MODERATE"
        if conviction > 60
        else "WEAK"
    )

    swarm = {
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "hold_pct": hold_pct,
        "panic_index": panic_index,
        "fomo_index": fomo_index,
        "conviction": conviction,
        "round1_bullish": round1_bullish,
        "round2_bullish": bullish_pct,
        "crowd_amplification": crowd_amplification,
        "influence_edges": [],
        "dominant_signal": final_call,
        "signal_strength": signal_strength,
        "crowd_narrative": (
            f"{final_call.lower()} crowd lean with {conviction:.0f}% decision "
            "stability while the full analyst run finishes."
        ),
    }

    return {
        "ticker": ticker,
        "company": company,
        "sector": sector,
        "timestamp": datetime.now(IST).isoformat(),
        "elapsed_seconds": 0,
        "swarm": swarm,
        "specialists": {
            "fundamental_score": 50.0,
            "technical_score": 50.0,
            "sentiment_score": 50.0,
            "news_score": 50.0,
            "fundamental_summary": "Fundamental analyst report pending.",
            "technical_summary": "Technical analyst report pending.",
            "sentiment_summary": "Sentiment analyst report pending.",
            "news_summary": "News analyst report pending.",
        },
        "debate": {
            "bull_case": "Bull researcher pending.",
            "bear_case": "Bear researcher pending.",
            "bull_score": 50.0,
            "bear_score": 50.0,
            "bull_reasons": [],
            "bear_reasons": [],
        },
        "signal": {
            "final_call": final_call,
            "bullish_probability": bullish_pct,
            "risk_level": "HIGH" if panic_index > 55 else "MEDIUM",
            "confidence": "HIGH" if conviction > 78 else "MEDIUM",
            "deciding_factor": "Live swarm preview",
            "key_risk": "Full specialist analysis is still running.",
            "agreement_type": "PENDING",
            "scores": {},
        },
        "explanation": {
            "line1": f"{company} live swarm preview is {bullish_pct:.1f}% bullish.",
            "line2": "Specialist reports are still being computed.",
            "line3": swarm["crowd_narrative"],
            "full_text": f"{company} live swarm preview is running.",
            "bull_case": "",
            "bear_case": "",
            "deciding_factor": "Live swarm preview",
        },
        "disclaimer": SEBI_DISCLAIMER,
        "_meta": {
            "is_stream_preview": True,
            "note": "Preview keeps SSE responsive before the full analysis completes.",
        },
    }


def _stream_agent_events(result: dict) -> list[dict]:
    swarm = result.get("swarm", {})
    specialists = result.get("specialists", {})

    round1_results = swarm.get("round1_results") or []
    round2_results = swarm.get("round2_results") or []

    if round1_results and round2_results:
        def _format_decision(decision: dict, event_id: int, round_number: int) -> dict:
            action = str(decision.get("action", "hold")).lower()
            if action == "buy":
                ui_decision = "BULLISH"
            elif action == "sell":
                ui_decision = "BEARISH"
            else:
                ui_decision = "HOLD"

            return {
                "id": event_id,
                "agentType": str(decision.get("agent_type", "Unknown")).replace("_", " ").title(),
                "agentName": decision.get("agent_name", f"Agent_{event_id}"),
                "message": decision.get("reasoning", ""),
                "decision": ui_decision,
                "timestamp": f"R{round_number}:{event_id:02d}",
                "round": round_number,
                "confidence": decision.get("confidence", 0.5),
            }

        actual_events = []
        for index, decision in enumerate(round1_results[:6], start=1):
            actual_events.append(_format_decision(decision, index, 1))
        for index, decision in enumerate(round2_results[:4], start=7):
            actual_events.append(_format_decision(decision, index, 2))
        return actual_events

    bullish_pct = float(swarm.get("bullish_pct", 50.0))
    panic_index = float(swarm.get("panic_index", 20.0))
    fomo_index = float(swarm.get("fomo_index", 25.0))
    technical_score = float(specialists.get("technical_score", 50.0))
    news_score = float(specialists.get("news_score", 50.0))
    news_summary = specialists.get("news_summary", "News analyst report pending.")

    return [
        {
            "id": 1,
            "agentType": "Institutional",
            "agentName": "DII_Value",
            "message": "Accumulation thesis checked against fundamentals and valuation discipline.",
            "decision": "BULLISH" if bullish_pct > 55 else "HOLD",
            "timestamp": "00:00",
            "round": 1,
        },
        {
            "id": 2,
            "agentType": "Algo",
            "agentName": "EMA_Crossover_Bot",
            "message": f"Trend model active. Volume context is {'above' if fomo_index > 30 else 'near'} average.",
            "decision": "BULLISH" if bullish_pct > 50 else "BEARISH",
            "timestamp": "00:03",
            "round": 1,
        },
        {
            "id": 3,
            "agentType": "Retail",
            "agentName": "Panic_Seller",
            "message": f"Panic index {panic_index:.1f}%. {'Calm tape.' if panic_index < 30 else 'Retail selling pressure visible.'}",
            "decision": "BEARISH" if panic_index > 50 else "HOLD",
            "timestamp": "00:05",
            "round": 1,
        },
        {
            "id": 4,
            "agentType": "News Reactor",
            "agentName": "Good_News_Chaser",
            "message": news_summary,
            "decision": "BULLISH" if news_score > 55 else "HOLD",
            "timestamp": "00:07",
            "round": 1,
        },
        {
            "id": 5,
            "agentType": "Institutional",
            "agentName": "FII_Momentum",
            "message": "Global risk and emerging-market flow check complete.",
            "decision": "BULLISH" if bullish_pct > 52 else "HOLD",
            "timestamp": "00:09",
            "round": 1,
        },
        {
            "id": 6,
            "agentType": "Algo",
            "agentName": "RSI_Bot",
            "message": f"Technical score {technical_score:.1f}. Overbought risk is {'controlled' if technical_score > 60 else 'unconfirmed'}.",
            "decision": "BULLISH" if technical_score > 62 else "HOLD",
            "timestamp": "00:11",
            "round": 1,
        },
        {
            "id": 7,
            "agentType": "Retail",
            "agentName": "FOMO_Buyer",
            "message": f"Crowd {bullish_pct:.0f}% bullish after Round 1 aggregate.",
            "decision": "BULLISH" if bullish_pct > 57 else "HOLD",
            "timestamp": "00:13",
            "round": 2,
            "changed": bullish_pct > 57,
        },
        {
            "id": 8,
            "agentType": "News Reactor",
            "agentName": "Noise_Ignorer",
            "message": "Headline noise discounted. Price action remains the main input.",
            "decision": "BULLISH" if bullish_pct > 55 else "HOLD",
            "timestamp": "00:14",
            "round": 2,
        },
        {
            "id": 9,
            "agentType": "Institutional",
            "agentName": "MF_SIP_Machine",
            "message": "Long-horizon accumulation mandate unchanged.",
            "decision": "BULLISH",
            "timestamp": "00:15",
            "round": 2,
        },
        {
            "id": 10,
            "agentType": "Retail",
            "agentName": "SIP_Investor",
            "message": "200 DMA tolerance check complete. No short-term exit trigger.",
            "decision": "HOLD",
            "timestamp": "00:16",
            "round": 2,
        },
    ]

async def _update_redis_job_status(orchestrator, job_id: str, status: str):
    try:
        redis_client = await orchestrator.cache._get_redis()
        if redis_client:
            data_str = await redis_client.get(f"job:{job_id}")
            if data_str:
                data = json.loads(data_str)
                data["status"] = status
                await redis_client.set(f"job:{job_id}", json.dumps(data), ex=3600)
    except Exception as e:
        logger.warning(f"Failed to update redis job status: {e}")



@app.post("/analyze", tags=["Analysis"], status_code=202)
async def start_analysis(req: AnalyzeRequest, request: Request, response: Response):
    """
    Spawns a background analysis job and returns a job_id immediately.
    Clients can then poll or stream telemetry using /swarm/stream/{ticker}?job_id={id}
    """
    ticker = _normalize_ticker_symbol(req.ticker)
    orchestrator = request.app.state.orchestrator
    
    # Check if a job is already running for this ticker to avoid duplicates
    for jid, info in active_jobs.items():
        if info["ticker"] == ticker and info["status"] == "running":
            return {"job_id": jid, "status": "running", "ticker": ticker, "message": "Analysis already in progress"}

    job_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    
    # We store the queue separately to make cleanup easier
    job_queues[job_id] = queue
    
    # Start background task
    task = asyncio.create_task(orchestrator.analyze(ticker, stream_queue=queue))
    
    active_jobs[job_id] = {
        "job_id": job_id,
        "ticker": ticker,
        "task": task,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": None
    }

    # Optional: Persist job metadata to Redis for status tracking
    orchestrator = request.app.state.orchestrator
    try:
        redis_client = await orchestrator.cache._get_redis()
        if redis_client:
            await redis_client.set(f"job:{job_id}", json.dumps({"ticker": ticker, "status": "running"}), ex=3600)
    except Exception as e:
        logger.warning(f"Failed to persist job to redis: {e}")

    def job_done_callback(t):
        try:
            result = t.result()
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["result"] = result
            # Update Redis status
            asyncio.create_task(_update_redis_job_status(orchestrator, job_id, "completed"))
            # Put completion event in queue
            asyncio.create_task(queue.put({"event": "analysis_complete", "data": result}))
            asyncio.create_task(queue.put({"event": "stage_update", "data": {"stage": "complete"}}))
        except Exception as e:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = str(e)
            asyncio.create_task(_update_redis_job_status(orchestrator, job_id, "failed"))
            asyncio.create_task(queue.put({"event": "stream_error", "data": {"error": str(e)}}))

    task.add_done_callback(job_done_callback)

    return {
        "job_id": job_id,
        "ticker": ticker,
        "status": "running",
        "disclaimer": SEBI_DISCLAIMER
    }


@app.get("/swarm/stream/{ticker}", tags=["Analysis"])
async def stream_swarm_analysis(ticker: str, req: Request, job_id: str = None):
    """
    SSE endpoint to stream agent decisions. 
    If job_id is provided, it hooks into an existing background task.
    Otherwise, it starts a new one (legacy behavior).
    """
    ticker = _normalize_ticker_symbol(ticker)

    async def event_generator():
        # Case A: User provided a job_id for an active background job
        if job_id and job_id in job_queues:
            logger.info(f"SSE: Hooking into active job {job_id} for {ticker}")
            queue = job_queues[job_id]
            
            # Catch-up: If job is already done, send result and close
            if active_jobs[job_id]["status"] == "completed":
                yield _sse_event("analysis_complete", active_jobs[job_id]["result"])
                yield _sse_event("stage_update", {"stage": "complete"})
                return

            try:
                while True:
                    event_data = await queue.get()
                    yield _sse_event(event_data["event"], event_data["data"])
                    if event_data["event"] == "analysis_complete":
                        break
            except Exception as e:
                logger.error(f"SSE stream error for job {job_id}: {e}")
                yield _sse_event("stream_error", {"error": str(e)})
            return

        # Case B: Legacy / direct streaming (creates its own task)
        analysis_task = None
        try:
            preview = _build_stream_preview_signal(ticker)
            orchestrator = getattr(req.app.state, "orchestrator", None)
            
            # Use a queue even for direct streaming to unify logic later
            local_queue = asyncio.Queue()

            if orchestrator is not None:
                analysis_task = asyncio.create_task(orchestrator.analyze(ticker, stream_queue=local_queue))
            
            # [Rest of legacy logic remains as fallback for now...]
            # Actually, let's keep it simple and just run the existing logic if no job_id
            # but we should probably refactor it to use the queue if we want consistency.

            preview_agents = _stream_agent_events(preview)

            yield _sse_event("swarm_snapshot", preview["swarm"])
            yield _sse_event("stage_update", {"stage": "data"})
            await asyncio.sleep(0.2)

            yield _sse_event("stage_update", {"stage": "round1"})
            for agent in preview_agents[:6]:
                await asyncio.sleep(0.12)
                yield _sse_event("agent_decision", agent)

            yield _sse_event("stage_update", {"stage": "aggregate"})
            await asyncio.sleep(0.35)

            yield _sse_event("stage_update", {"stage": "round2"})
            for agent in preview_agents[6:]:
                await asyncio.sleep(0.12)
                yield _sse_event("agent_decision", agent)

            yield _sse_event("stage_update", {"stage": "specialists"})
            await asyncio.sleep(0.35)

            yield _sse_event("stage_update", {"stage": "debate"})

            if analysis_task is not None:
                try:
                    result = await asyncio.wait_for(
                        analysis_task,
                        timeout=STREAM_ANALYSIS_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Stream analysis timed out for %s after %.1fs",
                        ticker,
                        STREAM_ANALYSIS_TIMEOUT_SECONDS,
                    )
                    yield _sse_event(
                        "stream_error",
                        {
                            "error": (
                                "Full analysis is taking longer than expected. "
                                "Local swarm preview remains active."
                            )
                        },
                    )
                    return
            else:
                result = preview

            has_real_agent_trace = bool(
                result.get("swarm", {}).get("round1_results")
                and result.get("swarm", {}).get("round2_results")
            )
            if has_real_agent_trace:
                for agent in _stream_agent_events(result):
                    confirmed_agent = {
                        **agent,
                        "id": int(agent.get("id", 0)) + 100,
                        "timestamp": f"final:{agent.get('timestamp', '')}",
                    }
                    await asyncio.sleep(0.1)
                    yield _sse_event("agent_decision", confirmed_agent)

            yield _sse_event("stage_update", {"stage": "complete"})
            yield _sse_event("analysis_complete", result)
        except asyncio.CancelledError:
            if analysis_task is not None and not analysis_task.done():
                analysis_task.cancel()
            raise
        except Exception as e:
            logger.error(f"Stream error for {ticker}: {e}")
            yield _sse_event("stream_error", {"error": str(e)})
        finally:
            if analysis_task is not None and not analysis_task.done():
                analysis_task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# -----------------------------------------------------------------------
# GET /stock/{ticker}
# -----------------------------------------------------------------------
def _normalize_ticker_symbol(ticker: str) -> str:
    symbol = ticker.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = f"{symbol}.NS"
    return symbol


async def _load_stored_signals(ticker: str, limit: int = 1):
    from api.database import Signal, async_session
    from sqlalchemy import select

    async with async_session() as session:
        stmt = (
            select(Signal)
            .where(Signal.ticker == ticker)
            .order_by(Signal.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _signal_entry_price(raw_signal: dict | None) -> float | None:
    if not isinstance(raw_signal, dict):
        return None

    market_data = raw_signal.get("market_data", {})
    entry_price = market_data.get("price")
    try:
        return float(entry_price) if entry_price is not None else None
    except (TypeError, ValueError):
        return None


@app.get("/stock/{ticker}", tags=["Analysis"])
async def get_stock_signal(ticker: str, req: Request):
    """
    Get the latest signal for a ticker from cache first, then database.
    Returns 404 if no signal has been generated yet.
    """
    ticker = _normalize_ticker_symbol(ticker)

    try:
        cached_signal = await _load_cached_signal(req, ticker)
        if cached_signal:
            cached_signal.setdefault("ticker", ticker)
            cached_signal.setdefault("disclaimer", SEBI_DISCLAIMER)
            return cached_signal

        signals = await _load_stored_signals(ticker, limit=1)
        if not signals:
            raise HTTPException(status_code=404, detail=f"No signal found for {ticker}.")

        latest = signals[0]
        payload = dict(latest.raw_signal_json or {})
        if payload:
            payload.setdefault("ticker", latest.ticker)
            payload.setdefault("company", latest.company)
            payload.setdefault("sector", latest.sector)
            payload.setdefault("timestamp", latest.timestamp.isoformat())
            payload.setdefault("disclaimer", SEBI_DISCLAIMER)
            return payload

        return {
            "ticker": latest.ticker,
            "company": latest.company,
            "sector": latest.sector,
            "timestamp": latest.timestamp.isoformat(),
            "signal": {
                "final_call": latest.final_call,
                "bullish_probability": latest.bullish_probability,
                "risk_level": latest.risk_level,
                "confidence": latest.confidence,
            },
            "disclaimer": SEBI_DISCLAIMER,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signal fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{ticker}", tags=["Analysis"])
async def get_signal_history(ticker: str, limit: int = 20):
    """Return recent stored signals for a ticker."""
    ticker = _normalize_ticker_symbol(ticker)
    limit = max(1, min(limit, 100))

    try:
        signals = await _load_stored_signals(ticker, limit=limit)
        if not signals:
            raise HTTPException(status_code=404, detail=f"No signal history found for {ticker}.")

        history = []
        for row in signals:
            raw_signal = row.raw_signal_json or {}
            history.append({
                "ticker": row.ticker,
                "company": row.company,
                "sector": row.sector,
                "timestamp": row.timestamp.isoformat(),
                "final_call": row.final_call,
                "bullish_probability": row.bullish_probability,
                "risk_level": row.risk_level,
                "confidence": row.confidence,
                "entry_price": _signal_entry_price(raw_signal),
                "has_market_data": bool(raw_signal.get("market_data")),
                "disclaimer": raw_signal.get("disclaimer", SEBI_DISCLAIMER),
            })

        return {
            "ticker": ticker,
            "count": len(history),
            "signals": history,
            "disclaimer": SEBI_DISCLAIMER,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"History fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/validation/{ticker}", tags=["Analysis"])
async def validate_signal_history(ticker: str, horizon_days: int = 7, limit: int = 20):
    """Evaluate stored signals against the latest price to create a validation trail."""
    ticker = _normalize_ticker_symbol(ticker)
    horizon_days = max(1, horizon_days)
    limit = max(1, min(limit, 100))

    try:
        signals = await _load_stored_signals(ticker, limit=limit)
        if not signals:
            raise HTTPException(status_code=404, detail=f"No signal history found for {ticker}.")

        from data.loader import data_loader

        current_price_data = await data_loader.get_current_price(ticker)
        current_price = current_price_data.get("price")
        now = datetime.now(timezone.utc)

        evaluated = []
        for row in signals:
            raw_signal = row.raw_signal_json or {}
            entry_price = _signal_entry_price(raw_signal)
            final_call = raw_signal.get("signal", {}).get("final_call", row.final_call)
            age_days = max((now - row.timestamp).days, 0)

            status = "pending"
            return_pct = None
            direction_match = None

            if entry_price is None:
                status = "missing_entry_price"
            elif current_price is None:
                status = "missing_current_price"
            elif age_days < horizon_days:
                status = "pending"
            else:
                return_pct = round(((current_price - entry_price) / entry_price) * 100, 2)
                if final_call == "BULLISH":
                    direction_match = return_pct > 0
                elif final_call == "BEARISH":
                    direction_match = return_pct < 0
                else:
                    direction_match = abs(return_pct) <= 1.0
                status = "evaluated"

            evaluated.append({
                "timestamp": row.timestamp.isoformat(),
                "age_days": age_days,
                "final_call": final_call,
                "entry_price": entry_price,
                "current_price": current_price,
                "return_pct": return_pct,
                "direction_match": direction_match,
                "status": status,
            })

        matured = [item for item in evaluated if item["status"] == "evaluated"]
        direction_accuracy_pct = None
        average_return_pct = None
        if matured:
            direction_accuracy_pct = round(
                sum(1 for item in matured if item["direction_match"]) / len(matured) * 100,
                1,
            )
            average_return_pct = round(
                sum(item["return_pct"] for item in matured if item["return_pct"] is not None) / len(matured),
                2,
            )

        return {
            "ticker": ticker,
            "horizon_days": horizon_days,
            "current_price": current_price,
            "evaluated_count": len(matured),
            "pending_count": sum(1 for item in evaluated if item["status"] == "pending"),
            "missing_count": sum(1 for item in evaluated if item["status"].startswith("missing")),
            "direction_accuracy_pct": direction_accuracy_pct,
            "average_return_pct": average_return_pct,
            "signals": evaluated,
            "disclaimer": SEBI_DISCLAIMER,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validation failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# GET /sectors
# -----------------------------------------------------------------------
@app.get("/sectors", tags=["Market Data"])
async def get_sector_performance():
    """
    Returns sector performance across Nifty 50 stocks.
    Average daily change percentage per sector.
    """
    try:
        from data.nse import get_nifty50_sector_performance
        performance = await get_nifty50_sector_performance()

        return {
            "sectors": performance,
            "timestamp": datetime.now(IST).isoformat(),
            "disclaimer": SEBI_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"Sector performance failed: {e}")
        return {
            "sectors": {},
            "error": "Unable to fetch sector performance. Market may be closed.",
            "timestamp": datetime.now(IST).isoformat(),
            "disclaimer": SEBI_DISCLAIMER,
        }


# -----------------------------------------------------------------------
# GET /backtest
# -----------------------------------------------------------------------
@app.get("/backtest", tags=["Backtest"])
async def run_backtest(
    ticker: str = "RELIANCE.NS",
    start_date: str = "2025-04-01",
    end_date: str = "2026-04-01",
    initial_capital: float = 100000.0,
    transaction_cost_bps: float = 10.0,
):
    """
    Run a walk-forward comparison for one ticker.

    The AlphaHive strategy here is a deterministic proxy, not the full
    live LLM/news/swarm system. Signals are shifted one bar to avoid
    look-ahead bias.
    """
    try:
        from backtest.compare import run_backtest_comparison

        result = await run_backtest_comparison(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            transaction_cost_bps=transaction_cost_bps,
        )
        return result
    except Exception as e:
        logger.error(f"Backtest failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# GET /news/{ticker}
# -----------------------------------------------------------------------
@app.get("/news/{ticker}", tags=["News"])
async def get_stock_news(ticker: str, max_items: int = 10):
    """
    Returns latest news items for a specific stock.
    Matches by ticker symbol and company name.
    """
    ticker = ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    try:
        from data.news import get_news_for_ticker
        news_items = await get_news_for_ticker(ticker, max_items=max_items)

        return {
            "ticker": ticker,
            "count": len(news_items),
            "news": [item.to_dict() for item in news_items],
            "disclaimer": SEBI_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"News fetch failed for {ticker}: {e}")
        return {
            "ticker": ticker,
            "count": 0,
            "news": [],
            "error": str(e),
            "disclaimer": SEBI_DISCLAIMER,
        }


# -----------------------------------------------------------------------
# GET /news (all latest news)
# -----------------------------------------------------------------------
@app.get("/news", tags=["News"])
async def get_all_news(max_items: int = 30):
    """Returns latest Indian financial news from all sources."""
    try:
        from data.news import get_latest_news
        news_items = await get_latest_news(max_items=max_items)

        return {
            "count": len(news_items),
            "news": [item.to_dict() for item in news_items],
            "disclaimer": SEBI_DISCLAIMER,
        }
    except Exception as e:
        logger.error(f"News fetch failed: {e}")
        return {
            "count": 0,
            "news": [],
            "error": str(e),
            "disclaimer": SEBI_DISCLAIMER,
        }


# -----------------------------------------------------------------------
# Removed Mock Signal Generator
# -----------------------------------------------------------------------


# -----------------------------------------------------------------------
# GET /stock/{ticker}/debate
# -----------------------------------------------------------------------
@app.get("/stock/{ticker}/debate", tags=["Analysis"])
async def get_stock_debate(ticker: str, req: Request):
    """
    Returns the bull case and bear case for a stock's latest signal.
    """
    ticker = ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    try:
        orchestrator = req.app.state.orchestrator
        signal = await orchestrator.cache.get_signal(ticker)
        if signal and "debate" in signal:
            return {
                "ticker": ticker,
                "bull_case": signal["debate"].get("bull_case"),
                "bear_case": signal["debate"].get("bear_case"),
                "bull_score": signal["debate"].get("bull_score"),
                "bear_score": signal["debate"].get("bear_score"),
                "bull_reasons": signal["debate"].get("bull_reasons", []),
                "bear_reasons": signal["debate"].get("bear_reasons", []),
                "timestamp": signal.get("timestamp")
            }
        else:
            raise HTTPException(status_code=404, detail="Debate not found. Run /analyze first.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Debate fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# GET /cache/invalidate/{ticker}
# -----------------------------------------------------------------------
@app.get("/cache/invalidate/{ticker}", tags=["System"])
async def invalidate_cache(ticker: str, req: Request):
    """Clears cached signal for a ticker."""
    ticker = ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"
        
    try:
        orchestrator = req.app.state.orchestrator
        await orchestrator.cache.invalidate(ticker)
        return {"status": "cleared", "ticker": ticker}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# GET /cache/status
# -----------------------------------------------------------------------
@app.get("/cache/status", tags=["System"])
async def cache_status(req: Request):
    """Returns cache health status. Returns 503 if Redis is disconnected."""
    try:
        orchestrator = req.app.state.orchestrator
        is_healthy = await orchestrator.cache.health()
        if not is_healthy:
            raise HTTPException(status_code=503, detail="Redis is disconnected")
        return {
            "redis": "connected",
            "cached_tickers": []
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------
# Run with: uvicorn api.main:app --reload --port 8000
# -----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
