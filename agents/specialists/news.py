import os
import json
import logging
from datetime import datetime, timezone
import httpx
from typing import Optional

from data.news import get_news_for_ticker

logger = logging.getLogger(__name__)

class NewsAnalyst:
    """
    News Analyst agent.
    Measures EVENTS and their market significance from headlines.
    Uses Ollama only if material events are found to generate a summary.
    """

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

    HIGH_PRIORITY_BULLISH = ["earnings beat", "buyback", "dividend", "upgrade"]
    HIGH_PRIORITY_BEARISH = ["fraud", "investigation", "it raid", "sebi notice",
                             "promoter selling", "default"]

    def __init__(self):
        self.model = os.getenv("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = 45.0
        # shared httpx client for this analyst instance
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def analyze(self, ticker: str, market_data: dict) -> dict:
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch news
        try:
            headlines_raw = await get_news_for_ticker(ticker, max_items=20)
        except Exception as e:
            logger.warning(f"Failed to fetch news for {ticker}: {e}")
            headlines_raw = []

        headlines = []
        for h in headlines_raw:
            if hasattr(h, "headline"):
                headlines.append(h.headline)
            elif isinstance(h, str):
                headlines.append(h)

        if not headlines:
            return self._fallback_report(ticker, start_time)

        # 2. Event detection
        events = []
        for text in headlines:
            event_type = self._detect_event_type(text)
            impact = self._score_impact(text, event_type)
            events.append({
                "headline": text,
                "event_type": event_type,
                "impact": impact
            })

        # 3. Aggregate event scores
        bullish_events = [e for e in events if e["event_type"] == "bullish_event"]
        bearish_events = [e for e in events if e["event_type"] == "bearish_event"]
        
        bullish_impact = sum(e["impact"] for e in bullish_events)
        bearish_impact = sum(e["impact"] for e in bearish_events)
        
        net_event_score = bullish_impact - bearish_impact
        news_score = int(max(0, min(100, (net_event_score + 5) / 10 * 100)))

        if news_score > 60:
            verdict = "POSITIVE"
        elif news_score < 40:
            verdict = "NEGATIVE"
        else:
            verdict = "NEUTRAL"

        # 4. Check for high-priority events
        high_priority_bullish_found = False
        high_priority_bearish_found = False
        
        for text in headlines:
            text_lower = text.lower()
            if any(k in text_lower for k in self.HIGH_PRIORITY_BULLISH):
                high_priority_bullish_found = True
            if any(k in text_lower for k in self.HIGH_PRIORITY_BEARISH):
                high_priority_bearish_found = True

        alert = None
        if high_priority_bearish_found:
            alert = "HIGH RISK: Material negative event detected. Review manually."
        elif high_priority_bullish_found:
            alert = "NOTABLE: Material positive event detected."

        top_events = sorted([e for e in events if e["event_type"] != "no_event"], 
                            key=lambda x: x["impact"], reverse=True)[:5]

        # 5. Call Ollama for natural language event summary
        summary = "No material events detected."
        if bullish_events or bearish_events:
            top_headlines_text = "\n".join([f"- {e['headline']} (Impact: {e['impact']})" for e in top_events])
            
            system_prompt = (
                "You are a financial news analyst.\n"
                "Provide a concise 2-sentence summary of the most important development and its likely impact on the stock.\n"
                "Respond with ONLY the 2-sentence summary. No preamble, no quotes."
            )
            
            user_prompt = (
                f"Analyze these top material events for {ticker}:\n"
                f"{top_headlines_text}"
            )
            
            llm_response = await self._call_llm(system_prompt, user_prompt)
            if llm_response:
                summary = llm_response.strip()

        return {
            "analyst": "news",
            "ticker": ticker,
            "headlines_analyzed": len(headlines),
            "bullish_events": len(bullish_events),
            "bearish_events": len(bearish_events),
            "high_priority_bullish": high_priority_bullish_found,
            "high_priority_bearish": high_priority_bearish_found,
            "alert": alert,
            "score": news_score,
            "verdict": verdict,
            "top_events": top_events,
            "summary": summary,
            "timestamp": start_time.isoformat()
        }

    def _detect_event_type(self, headline_text: str) -> str:
        text_lower = headline_text.lower()
        for keyword in self.BULLISH_EVENTS:
            if keyword in text_lower: return "bullish_event"
        for keyword in self.BEARISH_EVENTS:
            if keyword in text_lower: return "bearish_event"
        for keyword in self.NEUTRAL_EVENTS:
            if keyword in text_lower: return "neutral_event"
        return "no_event"

    def _score_impact(self, headline_text: str, event_type: str) -> float:
        base = {
            "bullish_event": 0.7, 
            "bearish_event": 0.7,
            "neutral_event": 0.3, 
            "no_event": 0.1
        }[event_type]
        
        amplifiers = ["record", "historic", "all-time", "massive", "surge", "crash"]
        if any(w in headline_text.lower() for w in amplifiers):
            base = min(1.0, base + 0.2)
            
        return base

    def _fallback_report(self, ticker: str, start_time: datetime) -> dict:
        return {
            "analyst": "news",
            "ticker": ticker,
            "headlines_analyzed": 0,
            "bullish_events": 0,
            "bearish_events": 0,
            "high_priority_bullish": False,
            "high_priority_bearish": False,
            "alert": None,
            "score": 50,
            "verdict": "NEUTRAL",
            "top_events": [],
            "summary": "No news available for event detection.",
            "timestamp": start_time.isoformat()
        }

    async def _call_llm(self, system: str, user: str) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "stream": False,
            "temperature": 0.3
        }

        try:
            response = await self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"NewsAnalyst LLM call failed: {e}")
            return None

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass
