"""
AlphaHive — Indian Financial News RSS Parser
=============================================
Fetches and parses free RSS feeds from Indian financial news sources.
No API keys required — uses public RSS endpoints only.

Sources:
  - Economic Times Markets
  - Moneycontrol Market Reports
  - LiveMint Markets
  - Business Standard

Features:
  - Parallel RSS fetching via asyncio
  - Ticker mention extraction from headlines
  - In-memory cache (30 minutes TTL)
  - Graceful handling of malformed feeds

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
import httpx

logger = logging.getLogger("alphahive.data.news")

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))


# -----------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------
@dataclass
class NewsItem:
    """
    A single news headline from an Indian financial source.
    
    sentiment_score is None here — it gets populated later by
    agents/specialists/sentiment.py using FinBERT.
    """
    headline: str
    source: str
    url: str
    published_at: Optional[datetime]
    ticker_mentions: list[str] = field(default_factory=list)
    sentiment_score: Optional[float] = None  # Filled by FinBERT in Week 3

    def to_dict(self) -> dict:
        return {
            "headline": self.headline,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ticker_mentions": self.ticker_mentions,
            "sentiment_score": self.sentiment_score,
        }


# -----------------------------------------------------------------------
# RSS Feed Configuration
# -----------------------------------------------------------------------
RSS_FEEDS = [
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "source_key": "ET",
    },
    {
        "name": "Moneycontrol Markets",
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
        "source_key": "MC",
    },
    {
        "name": "LiveMint Markets",
        "url": "https://www.livemint.com/rss/markets",
        "source_key": "LM",
    },
    {
        "name": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "source_key": "BS",
    },
]

# HTTP headers to avoid being blocked
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# -----------------------------------------------------------------------
# Ticker extraction patterns — built from Nifty 50 list
# -----------------------------------------------------------------------
# Import the Nifty 50 data for ticker matching
from data.nse import NIFTY_50_STOCKS, _COMPANY_NAME_TO_TICKER

# Build regex patterns for company name matching
_COMPANY_PATTERNS: list[tuple[re.Pattern, str]] = []
for stock in NIFTY_50_STOCKS:
    # Match company name (case insensitive)
    company = stock["company"]
    ticker = stock["ticker"]
    symbol = ticker.replace(".NS", "")

    # Full company name pattern
    _COMPANY_PATTERNS.append(
        (re.compile(re.escape(company), re.IGNORECASE), ticker)
    )
    # Short symbol pattern (word boundary to avoid false matches)
    _COMPANY_PATTERNS.append(
        (re.compile(rf"\b{re.escape(symbol)}\b", re.IGNORECASE), ticker)
    )
    # First meaningful word of company name (skip very short/common words)
    words = company.split()
    if words and len(words[0]) > 3:
        _COMPANY_PATTERNS.append(
            (re.compile(rf"\b{re.escape(words[0])}\b", re.IGNORECASE), ticker)
        )


# -----------------------------------------------------------------------
# In-memory cache
# -----------------------------------------------------------------------
_news_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 1800  # 30 minutes


def _get_cached(key: str) -> Optional[list[NewsItem]]:
    """Get cached news items if not expired."""
    if key in _news_cache:
        entry = _news_cache[key]
        age = (datetime.now(timezone.utc) - entry["timestamp"]).total_seconds()
        if age < CACHE_TTL_SECONDS:
            logger.debug(f"Cache hit for '{key}' (age: {int(age)}s)")
            return entry["data"]
        del _news_cache[key]
    return None


def _set_cached(key: str, data: list[NewsItem]) -> None:
    """Store news items in cache."""
    _news_cache[key] = {
        "data": data,
        "timestamp": datetime.now(timezone.utc),
    }


# -----------------------------------------------------------------------
# 1. Fetch all latest news
# -----------------------------------------------------------------------
async def get_latest_news(max_items: int = 50) -> list[NewsItem]:
    """
    Fetch latest financial news from all RSS sources in parallel.
    
    - Combines all sources
    - Deduplicates by headline
    - Extracts ticker mentions from each headline
    - Sorts by publication date (newest first)
    - Caches results for 30 minutes
    
    Args:
        max_items: Maximum number of news items to return
        
    Returns:
        List of NewsItem objects sorted by recency
    """
    # Check cache
    cache_key = "all_latest_news"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached[:max_items]

    # Fetch from all sources in parallel
    tasks = [_fetch_single_feed(feed) for feed in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Combine all items
    all_items: list[NewsItem] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Feed '{RSS_FEEDS[i]['name']}' failed: {result}")
            continue
        if isinstance(result, list):
            all_items.extend(result)
            logger.info(f"Feed '{RSS_FEEDS[i]['name']}': {len(result)} items")

    # Deduplicate by headline (case-insensitive)
    seen_headlines: set[str] = set()
    unique_items: list[NewsItem] = []
    for item in all_items:
        key = item.headline.lower().strip()
        if key not in seen_headlines:
            seen_headlines.add(key)
            unique_items.append(item)

    # Extract ticker mentions for each headline
    for item in unique_items:
        item.ticker_mentions = extract_ticker_mentions(item.headline)

    # Sort by date (newest first), handling None dates
    unique_items.sort(
        key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    # Trim to max_items
    unique_items = unique_items[:max_items]

    # Cache the results
    _set_cached(cache_key, unique_items)

    logger.info(f"Total news fetched: {len(unique_items)} unique items from {len(RSS_FEEDS)} feeds")
    return unique_items


# -----------------------------------------------------------------------
# 2. Get news for a specific ticker
# -----------------------------------------------------------------------
async def get_news_for_ticker(
    ticker: str,
    max_items: int = 10,
) -> list[NewsItem]:
    """
    Filter news for a specific stock ticker.
    
    Matches by:
    - Ticker symbol (e.g. "RELIANCE")
    - Full company name (e.g. "Reliance Industries")
    - Partial company name (e.g. "Reliance")
    
    Args:
        ticker: NSE ticker (e.g. RELIANCE.NS)
        max_items: Maximum items to return
        
    Returns:
        List of matching NewsItem objects
    """
    # Fetch all news first
    all_news = await get_latest_news(max_items=200)

    # Filter for this ticker
    matching = []
    for item in all_news:
        # Check if ticker is in the extracted mentions
        if ticker in item.ticker_mentions:
            matching.append(item)
            continue

        # Also do a direct text search for company name and symbol
        symbol = ticker.replace(".NS", "").replace(".BO", "")
        headline_lower = item.headline.lower()

        if symbol.lower() in headline_lower:
            matching.append(item)
            continue

        # Check company name from NSE data
        from data.nse import get_company_name
        company = get_company_name(ticker)
        if company and company.lower() != ticker.lower():
            # Search for first word of company name (more reliable)
            first_word = company.split()[0].lower()
            if len(first_word) > 3 and first_word in headline_lower:
                matching.append(item)

    return matching[:max_items]


# -----------------------------------------------------------------------
# 3. Extract ticker mentions from a headline
# -----------------------------------------------------------------------
def extract_ticker_mentions(headline: str) -> list[str]:
    """
    Scan a headline for any Nifty 50 company names or ticker symbols.
    
    Uses regex patterns built from the Nifty 50 universe to avoid
    false positives (e.g. "IT" matching ITC).
    
    Args:
        headline: News headline text
        
    Returns:
        List of .NS format tickers found
        Example: "Reliance Industries Q4 results" → ["RELIANCE.NS"]
    """
    found_tickers: set[str] = set()

    for pattern, ticker in _COMPANY_PATTERNS:
        if pattern.search(headline):
            found_tickers.add(ticker)

    return sorted(found_tickers)


# -----------------------------------------------------------------------
# Private: Fetch a single RSS feed
# -----------------------------------------------------------------------
async def _fetch_single_feed(feed_config: dict) -> list[NewsItem]:
    """
    Fetch and parse a single RSS feed.
    
    Uses httpx for async HTTP, then feedparser to parse the XML.
    Handles malformed feeds gracefully — skips bad items, logs warnings.
    """
    name = feed_config["name"]
    url = feed_config["url"]
    source_key = feed_config["source_key"]

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=os.getenv("NEWS_SSL_VERIFY", "true").lower() == "true") as client:
            response = await client.get(url, headers=REQUEST_HEADERS)
            response.raise_for_status()
            raw_xml = response.text

    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching RSS feed: {name} ({url})")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error for {name}: {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"Failed to fetch {name}: {e}")
        return []

    # Parse with feedparser
    try:
        parsed = feedparser.parse(raw_xml)
    except Exception as e:
        logger.warning(f"Failed to parse RSS from {name}: {e}")
        return []

    items: list[NewsItem] = []

    for entry in parsed.entries:
        try:
            # Extract headline
            headline = entry.get("title", "").strip()
            if not headline:
                continue

            # Extract URL
            link = entry.get("link", "")

            # Parse publication date
            pub_date = _parse_feed_date(entry)

            items.append(NewsItem(
                headline=headline,
                source=source_key,
                url=link,
                published_at=pub_date,
            ))

        except Exception as e:
            logger.debug(f"Skipping malformed RSS entry from {name}: {e}")
            continue

    return items


# -----------------------------------------------------------------------
# Private: Parse feed entry dates
# -----------------------------------------------------------------------
def _parse_feed_date(entry: dict) -> Optional[datetime]:
    """
    Parse the publication date from an RSS feed entry.
    
    feedparser normalizes dates into `published_parsed` or `updated_parsed`
    as a time.struct_time — convert that to datetime.
    """
    import time

    # Try feedparser's parsed date fields
    for date_field in ("published_parsed", "updated_parsed"):
        parsed_time = entry.get(date_field)
        if parsed_time:
            try:
                dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue

    # Try raw date strings
    for date_field in ("published", "updated", "pubDate"):
        raw_date = entry.get(date_field)
        if raw_date:
            try:
                # Try common date formats
                for fmt in (
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S GMT",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S",
                ):
                    try:
                        return datetime.strptime(raw_date, fmt).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
            except Exception:
                continue

    return None


# -----------------------------------------------------------------------
# Utility: Clear news cache (for testing)
# -----------------------------------------------------------------------
def clear_cache() -> None:
    """Clear the in-memory news cache."""
    _news_cache.clear()
    logger.info("News cache cleared")
