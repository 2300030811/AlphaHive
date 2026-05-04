import logging
import asyncio
from datetime import datetime, timezone
from transformers import pipeline
from data.news import get_news_for_ticker

logger = logging.getLogger(__name__)

class SentimentAnalyst:
    """
    Sentiment Analyst agent.
    Uses FinBERT (ProsusAI/finbert) to analyze Indian financial news headlines.
    This model is synchronous and CPU-bound, so it runs in an executor.
    Does not use Ollama.
    """

    def __init__(self):
        logger.info("Initializing FinBERT pipeline for SentimentAnalyst...")
        self.finbert = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1  # CPU
        )
        logger.info("FinBERT pipeline loaded successfully.")

    async def analyze(self, ticker: str, market_data: dict) -> dict:
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch recent news
        try:
            headlines = await get_news_for_ticker(ticker, max_items=15)
        except Exception as e:
            logger.warning(f"Failed to fetch news for {ticker} sentiment analysis: {e}")
            headlines = []

        if not headlines:
            return self._fallback_report(ticker, start_time)

        # Extract texts
        headline_texts = []
        for h in headlines:
            if hasattr(h, "headline"):
                headline_texts.append(h.headline)
            elif isinstance(h, str):
                headline_texts.append(h)
                
        if not headline_texts:
            return self._fallback_report(ticker, start_time)

        # 2. Run FinBERT on each headline using an executor
        loop = asyncio.get_event_loop()
        
        def run_finbert_batch(texts):
            return self.finbert(texts, truncation=True, max_length=512)
            
        try:
            results = await loop.run_in_executor(None, run_finbert_batch, headline_texts)
        except Exception as e:
            logger.error(f"FinBERT execution failed for {ticker}: {e}")
            return self._fallback_report(ticker, start_time)

        # 3. Compute aggregate sentiment metrics
        scored_headlines = []
        for i, (item, result) in enumerate(zip(headlines, results)):
            hl_text = headline_texts[i]
            source = getattr(item, "source", "Unknown") if hasattr(item, "source") else "Unknown"
            published_at = getattr(item, "published_at", None) if hasattr(item, "published_at") else None
            
            scored_headlines.append({
                "headline": hl_text,
                "source": source,
                "label": result["label"],
                "confidence": result["score"],
                "published_at": published_at
            })

        positive_count = sum(1 for h in scored_headlines if h["label"] == "positive")
        negative_count = sum(1 for h in scored_headlines if h["label"] == "negative")
        neutral_count = sum(1 for h in scored_headlines if h["label"] == "neutral")
        total = len(scored_headlines)

        positive_score = sum(h["confidence"] for h in scored_headlines if h["label"] == "positive")
        negative_score = sum(h["confidence"] for h in scored_headlines if h["label"] == "negative")

        net_sentiment = (positive_score - negative_score) / total if total > 0 else 0.0
        sentiment_score = int((net_sentiment + 1) / 2 * 100)
        
        if sentiment_score > 60:
            verdict = "POSITIVE"
        elif sentiment_score < 40:
            verdict = "NEGATIVE"
        else:
            verdict = "NEUTRAL"

        fear_index = (negative_count / total) * 100 if total > 0 else 0.0
        greed_index = (positive_count / total) * 100 if total > 0 else 0.0

        # 4. Extract top 3 most impactful headlines
        top_headlines = sorted(scored_headlines, key=lambda x: x["confidence"], reverse=True)[:3]

        # 5. Summary template
        if verdict == "POSITIVE":
            summary = f"News sentiment strongly positive. {positive_count}/{total} headlines bullish. Fear index low at {fear_index:.0f}%."
        elif verdict == "NEGATIVE":
            summary = f"News sentiment negative. {negative_count}/{total} headlines bearish. Elevated fear at {fear_index:.0f}%."
        else:
            summary = f"Mixed news sentiment. No clear directional bias from {total} recent headlines."

        return {
            "analyst": "sentiment",
            "ticker": ticker,
            "headlines_analyzed": total,
            "scored_headlines": scored_headlines,
            "top_headlines": top_headlines,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "net_sentiment": net_sentiment,
            "score": sentiment_score,
            "verdict": verdict,
            "fear_index": fear_index,
            "greed_index": greed_index,
            "summary": summary,
            "timestamp": start_time.isoformat()
        }

    def _fallback_report(self, ticker: str, start_time: datetime) -> dict:
        return {
            "analyst": "sentiment",
            "ticker": ticker,
            "headlines_analyzed": 0,
            "scored_headlines": [],
            "top_headlines": [],
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "net_sentiment": 0.0,
            "score": 50,
            "verdict": "NEUTRAL",
            "fear_index": 0.0,
            "greed_index": 0.0,
            "summary": "No recent news found. Sentiment is neutral.",
            "timestamp": start_time.isoformat()
        }
