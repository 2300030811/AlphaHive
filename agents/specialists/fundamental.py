import os
import json
import logging
from datetime import datetime, timezone
import asyncio
import httpx
from typing import Optional

from data.loader import data_loader
from data.nse import get_sector_for_ticker, get_promoter_holding

logger = logging.getLogger(__name__)

class FundamentalAnalyst:
    """
    Fundamental Analyst agent.
    Analyzes facts: P/E vs sector, EPS growth, debt health, promoter holding.
    Uses llama3.1:8b for final assessment based on computed metrics.
    """

    # Hardcoded sector average PEs for Nifty 50 sectors
    SECTOR_AVG_PE = {
        "Banking": 18.0, 
        "IT": 28.0, 
        "Energy": 12.0,
        "FMCG": 55.0, 
        "Auto": 22.0, 
        "Pharma": 35.0,
        "Metals": 10.0, 
        "Telecom": 40.0, 
        "Infrastructure": 20.0,
        "Default": 25.0
    }

    def __init__(self):
        self.model = os.getenv("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = 45.0
        # shared httpx client for the lifetime of this analyst instance
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def analyze(self, ticker: str, market_data: dict) -> dict:
        """
        Gather fundamental data, compute deterministic signals, and query LLM for a verdict.
        """
        start_time = datetime.now(timezone.utc)

        # 1. Gather fundamental data
        info = market_data.get("info", {})
        
        # If market_data didn't pre-fetch info, we can try to get it. 
        # But we'll rely on the orchestrator to provide it if possible, 
        # or we fetch via data_loader if it exposes a raw yfinance info method.
        # Assuming data_loader provides a way to get raw info or we just fetch it.
        # Wait, the prompt says: "Pull these from DataLoader and data/nse.py". 
        # We need to make sure we get the data safely.
        try:
            import yfinance as yf
            loop = asyncio.get_running_loop()
            stock = yf.Ticker(ticker)
            raw_info = await loop.run_in_executor(None, lambda: stock.info)
        except Exception as e:
            logger.warning(f"Failed to fetch fundamentals for {ticker}: {e}")
            raw_info = {}

        pe_ratio = raw_info.get("trailingPE")
        forward_pe = raw_info.get("forwardPE")
        eps_ttm = raw_info.get("trailingEps")
        eps_growth_yoy = raw_info.get("earningsQuarterlyGrowth") # Closest proxy in standard yf
        revenue_growth_yoy = raw_info.get("revenueGrowth")
        profit_margin = raw_info.get("profitMargins")
        debt_to_equity = raw_info.get("debtToEquity")
        roe = raw_info.get("returnOnEquity")
        book_value = raw_info.get("bookValue")
        price_to_book = raw_info.get("priceToBook")

        promoter_holding_pct = await get_promoter_holding(ticker)
        sector = get_sector_for_ticker(ticker)

        # 2. Compute derived signals (deterministic)
        derived = {}
        
        sector_avg = self.SECTOR_AVG_PE.get(sector, self.SECTOR_AVG_PE["Default"])
        if pe_ratio is not None:
            if pe_ratio < sector_avg * 0.85:
                derived["pe_vs_sector"] = "cheap"
            elif pe_ratio > sector_avg * 1.15:
                derived["pe_vs_sector"] = "expensive"
            else:
                derived["pe_vs_sector"] = "fair"
        else:
            derived["pe_vs_sector"] = "unknown"

        if eps_growth_yoy is not None:
            if eps_growth_yoy > 0.1:
                derived["earnings_trend"] = "improving"
            elif eps_growth_yoy < -0.1:
                derived["earnings_trend"] = "declining"
            else:
                derived["earnings_trend"] = "stable"
        else:
            derived["earnings_trend"] = "unknown"

        if debt_to_equity is not None:
            # yfinance sometimes returns D/E as percentage (e.g. 150 instead of 1.5)
            # Let's assume standard format where > 1.5 is high, or > 150 is high.
            # We'll normalize if it's > 10, assuming it's a percentage.
            de_val = debt_to_equity / 100 if debt_to_equity > 10 else debt_to_equity
            if de_val < 0.5:
                derived["debt_health"] = "low"
            elif 0.5 <= de_val <= 1.5:
                derived["debt_health"] = "medium"
            else:
                derived["debt_health"] = "high"
        else:
            derived["debt_health"] = "unknown"

        if promoter_holding_pct is not None:
            if promoter_holding_pct > 50:
                derived["promoter_confidence"] = "high"
            elif 35 <= promoter_holding_pct <= 50:
                derived["promoter_confidence"] = "medium"
            else:
                derived["promoter_confidence"] = "low"
        else:
            derived["promoter_confidence"] = "unknown"

        # 3. Build a concise data summary string and call Ollama
        def fmt(val):
            return str(round(val, 2)) if val is not None else "unavailable"

        def fmt_pct(val):
            return f"{round(val * 100, 2)}%" if val is not None else "unavailable"

        formatted_fundamentals_string = f"""
        P/E Ratio: {fmt(pe_ratio)} (Sector Avg: {sector_avg})
        Forward P/E: {fmt(forward_pe)}
        EPS (TTM): {fmt(eps_ttm)}
        EPS Growth (YoY): {fmt_pct(eps_growth_yoy)}
        Revenue Growth (YoY): {fmt_pct(revenue_growth_yoy)}
        Profit Margin: {fmt_pct(profit_margin)}
        Debt to Equity: {fmt(debt_to_equity)}
        ROE: {fmt_pct(roe)}
        Promoter Holding: {fmt(promoter_holding_pct)}%
        P/B Ratio: {fmt(price_to_book)}

        Derived Signals:
        Valuation vs Sector: {derived["pe_vs_sector"]}
        Earnings Trend: {derived["earnings_trend"]}
        Debt Risk: {derived["debt_health"]}
        Promoter Confidence: {derived["promoter_confidence"]}
        """

        system_prompt = (
            "You are a fundamental equity analyst for Indian stocks.\n"
            "You analyze financial metrics and return a concise assessment.\n"
            "Always respond in valid JSON only. No preamble. No explanation outside JSON."
        )

        user_prompt = (
            f"Analyze these fundamentals for {ticker} ({sector} sector):\n"
            f"{formatted_fundamentals_string}\n\n"
            "Return JSON with exactly these fields:\n"
            "{\n"
            "  \"score\": integer 0-100 (overall fundamental strength),\n"
            "  \"verdict\": \"STRONG\" | \"MODERATE\" | \"WEAK\",\n"
            "  \"key_positives\": [list of max 3 short strings],\n"
            "  \"key_negatives\": [list of max 3 short strings],\n"
            "  \"summary\": \"one sentence summary of fundamentals\"\n"
            "}"
        )

        llm_response = await self._call_llm(system_prompt, user_prompt)

        # 4. Parse response. If parse fails, use deterministic fallback
        score = 50
        verdict = "MODERATE"
        key_positives = []
        key_negatives = []
        summary = f"Fundamental analysis completed with {derived['pe_vs_sector']} valuation and {derived['earnings_trend']} earnings."

        if llm_response:
            try:
                # Extract JSON if surrounded by markdown blocks
                text = llm_response.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                
                parsed = json.loads(text.strip())
                score = parsed.get("score", 50)
                verdict = parsed.get("verdict", "MODERATE")
                key_positives = parsed.get("key_positives", [])
                key_negatives = parsed.get("key_negatives", [])
                summary = parsed.get("summary", summary)
            except Exception as e:
                logger.error(f"Failed to parse LLM response for {ticker}: {e}\nResponse: {llm_response}")

        return {
            "analyst": "fundamental",
            "ticker": ticker,
            "raw_data": {
                "pe_ratio": pe_ratio,
                "forward_pe": forward_pe,
                "eps_ttm": eps_ttm,
                "eps_growth_yoy": eps_growth_yoy,
                "revenue_growth_yoy": revenue_growth_yoy,
                "profit_margin": profit_margin,
                "debt_to_equity": debt_to_equity,
                "roe": roe,
                "promoter_holding_pct": promoter_holding_pct,
                "book_value": book_value,
                "price_to_book": price_to_book,
                "sector": sector,
                "sector_avg_pe": sector_avg
            },
            "derived": derived,
            "score": score,
            "verdict": verdict,
            "key_positives": key_positives,
            "key_negatives": key_negatives,
            "summary": summary,
            "timestamp": start_time.isoformat()
        }

    async def _call_llm(self, system: str, user: str) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "format": "json",
            "stream": False,
            "temperature": 0.2
        }

        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"FundamentalAnalyst LLM call failed: {e}")
            return None

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass
