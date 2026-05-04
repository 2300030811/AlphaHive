"""
AlphaHive — NSE-Specific Data Module
=====================================
India-specific market data that no reference repo provides.
This is original AlphaHive code built from scratch.

Features:
  - Nifty 50 universe (hardcoded, rarely changes)
  - FII/DII flow data from NSE
  - Promoter holding via yfinance
  - Sector classification and performance

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger("alphahive.data.nse")

# SEBI Disclaimer — mandatory on every signal
SEBI_DISCLAIMER = (
    "For educational purposes only. Not investment advice. "
    "AlphaHive is not SEBI-registered. "
    "All trading decisions are entirely your own."
)

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

# -----------------------------------------------------------------------
# Nifty 50 Universe — Hardcoded (changes only during index reconstitution)
# -----------------------------------------------------------------------
NIFTY_50_STOCKS = [
    {"ticker": "RELIANCE.NS",   "company": "Reliance Industries",         "sector": "Energy"},
    {"ticker": "TCS.NS",        "company": "Tata Consultancy Services",   "sector": "IT"},
    {"ticker": "INFY.NS",       "company": "Infosys",                     "sector": "IT"},
    {"ticker": "HDFCBANK.NS",   "company": "HDFC Bank",                   "sector": "Banking"},
    {"ticker": "ICICIBANK.NS",  "company": "ICICI Bank",                  "sector": "Banking"},
    {"ticker": "HINDUNILVR.NS", "company": "Hindustan Unilever",          "sector": "FMCG"},
    {"ticker": "SBIN.NS",       "company": "State Bank of India",         "sector": "Banking"},
    {"ticker": "BAJFINANCE.NS", "company": "Bajaj Finance",               "sector": "Financial Services"},
    {"ticker": "BHARTIARTL.NS", "company": "Bharti Airtel",               "sector": "Telecom"},
    {"ticker": "KOTAKBANK.NS",  "company": "Kotak Mahindra Bank",         "sector": "Banking"},
    {"ticker": "ITC.NS",        "company": "ITC Limited",                 "sector": "FMCG"},
    {"ticker": "ASIANPAINT.NS", "company": "Asian Paints",                "sector": "Consumer Goods"},
    {"ticker": "AXISBANK.NS",   "company": "Axis Bank",                   "sector": "Banking"},
    {"ticker": "LT.NS",         "company": "Larsen & Toubro",             "sector": "Infrastructure"},
    {"ticker": "DMART.NS",      "company": "Avenue Supermarts (DMart)",    "sector": "Retail"},
    {"ticker": "SUNPHARMA.NS",  "company": "Sun Pharmaceutical",          "sector": "Pharma"},
    {"ticker": "ULTRACEMCO.NS", "company": "UltraTech Cement",            "sector": "Cement"},
    {"ticker": "TITAN.NS",      "company": "Titan Company",               "sector": "Consumer Goods"},
    {"ticker": "WIPRO.NS",      "company": "Wipro",                       "sector": "IT"},
    {"ticker": "NESTLEIND.NS",  "company": "Nestle India",                "sector": "FMCG"},
    {"ticker": "HCLTECH.NS",    "company": "HCL Technologies",            "sector": "IT"},
    {"ticker": "MARUTI.NS",     "company": "Maruti Suzuki India",         "sector": "Automobile"},
    {"ticker": "POWERGRID.NS",  "company": "Power Grid Corporation",      "sector": "Power"},
    {"ticker": "NTPC.NS",       "company": "NTPC Limited",                "sector": "Power"},
    {"ticker": "ONGC.NS",       "company": "Oil & Natural Gas Corp",      "sector": "Energy"},
    {"ticker": "TECHM.NS",      "company": "Tech Mahindra",               "sector": "IT"},
    {"ticker": "JSWSTEEL.NS",   "company": "JSW Steel",                   "sector": "Metals"},
    {"ticker": "TATASTEEL.NS",  "company": "Tata Steel",                  "sector": "Metals"},
    {"ticker": "ADANIENT.NS",   "company": "Adani Enterprises",           "sector": "Diversified"},
    {"ticker": "ADANIPORTS.NS", "company": "Adani Ports & SEZ",           "sector": "Infrastructure"},
]

# Pre-built lookup maps for fast access
_TICKER_TO_STOCK = {s["ticker"]: s for s in NIFTY_50_STOCKS}
_TICKER_TO_SECTOR = {s["ticker"]: s["sector"] for s in NIFTY_50_STOCKS}
_TICKER_TO_COMPANY = {s["ticker"]: s["company"] for s in NIFTY_50_STOCKS}

# Company name → ticker reverse mapping (for news matching)
_COMPANY_NAME_TO_TICKER = {}
for stock in NIFTY_50_STOCKS:
    # Map full name and short keywords
    _COMPANY_NAME_TO_TICKER[stock["company"].lower()] = stock["ticker"]
    # Also map the first word of company name
    first_word = stock["company"].split()[0].lower()
    _COMPANY_NAME_TO_TICKER[first_word] = stock["ticker"]
    # And the ticker symbol without .NS
    symbol = stock["ticker"].replace(".NS", "").lower()
    _COMPANY_NAME_TO_TICKER[symbol] = stock["ticker"]

# NSE website headers (they block plain requests)
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


# -----------------------------------------------------------------------
# 1. Nifty 50 Universe
# -----------------------------------------------------------------------
def get_nifty50_universe() -> list[dict]:
    """
    Returns the Nifty 50 stock list with ticker, company name, and sector.
    
    This is hardcoded because:
    - The Nifty 50 composition changes only twice a year
    - NSE doesn't provide a reliable free API for index composition
    - Hardcoding ensures zero network failures for the watchlist
    
    Returns:
        List of dicts: [{"ticker": "RELIANCE.NS", "company": "...", "sector": "..."}]
    """
    return NIFTY_50_STOCKS.copy()


# -----------------------------------------------------------------------
# 2. FII / DII Flow Data
# -----------------------------------------------------------------------
async def get_fii_dii_flow(date: str = None) -> Optional[dict]:
    """
    Fetch FII and DII buying/selling data from NSE Bhav Copy (public, no auth).

    Bhav Copy CSV at:
    https://www.nseindia.com/archives/equity/mkt/MAKDDMMYYYY.csv

    Delivery percentage is used as a proxy for institutional vs retail activity:
    - High delivery % (~25-40%) = institutional (FII/DII) activity
    - Low delivery % (<15%) = retail dominated

    FII/DII net flow is estimated from the delivery percentage trend.

    Args:
        date: Date string in YYYY-MM-DD format (default: today IST)

    Returns:
        Dict with fii/dii sentiment estimate and delivery metrics
    """
    if date is None:
        date_str = datetime.now(IST).strftime("%d-%m-%Y")
        date_yyyy = datetime.now(IST).strftime("%Y%m%d")
    else:
        d = datetime.fromisoformat(date)
        date_str = d.strftime("%d-%m-%Y")
        date_yyyy = d.strftime("%Y%m%d")

    ssl_verify = os.getenv("NSE_SSL_VERIFY", "true").lower() == "true"

    # Primary: NSE public JSON feed for FII/DII flows.
    api_url = "https://www.nseindia.com/api/fiidiiTradeReact"
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=ssl_verify) as client:
            response = await client.get(api_url, headers=NSE_HEADERS)
            if response.status_code == 200:
                parsed = _parse_fii_dii_response(response.json(), date_str)
                if parsed:
                    parsed["source"] = "nse_api"
                    return parsed
    except Exception as e:
        logger.warning(f"NSE FII/DII API fetch failed: {e}")

    # Secondary: NSE Bhav Copy CSV (public, no session cookies needed)
    bhav_url = f"https://www.nseindia.com/archives/equity/mkt/MAK{date_yyyy}.csv"

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=ssl_verify) as client:
            response = await client.get(bhav_url, headers=NSE_HEADERS)
            if response.status_code == 200:
                parsed = _parse_bhav_copy_csv(response.text, date_str)
                if parsed:
                    return parsed
    except Exception as e:
        logger.warning(f"NSE Bhav Copy fetch failed for {date_yyyy}: {e}")

    # Secondary: NSE equity archives (varied URL format)
    archive_url = f"https://www.nseindia.com/archives/equity/mkt/{date_yyyy}.csv"
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=ssl_verify) as client:
            response = await client.get(archive_url, headers=NSE_HEADERS)
            if response.status_code == 200:
                parsed = _parse_bhav_copy_csv(response.text, date_str)
                if parsed:
                    return parsed
    except Exception as e:
        logger.warning(f"NSE archive fetch failed: {e}")

    # Fallback: derive from Nifty 50 index volume anomalies via yfinance
    logger.info("Using yfinance volume proxy for FII/DII estimate")
    return await _get_fii_dii_from_yfinance(date_str)


async def _parse_bhav_copy_csv(raw_csv: str, date: str) -> Optional[dict]:
    """
    Parse NSE Bhav Copy CSV to estimate institutional vs retail activity.

    Delivery percentage is the primary signal:
    - High delivery = institutional (FII/DII) accumulation
    """
    try:
        import io
        import csv

        reader = csv.DictReader(io.StringIO(raw_csv))
        delivery_pcts = []
        total_quantity = 0

        for row in reader:
            try:
                qty = int(row.get("TOTTRDQTY", 0) or 0)
                delv = int(row.get("TOTTRDVAL", 0) or 0)
                if qty > 0 and delv > 0:
                    # Delivery percentage = delivered qty / total traded qty
                    del_pct = (delv / qty) * 100 if qty else 0
                    delivery_pcts.append(del_pct)
                    total_quantity += qty
            except (ValueError, KeyError):
                continue

        if not delivery_pcts:
            return None

        # Market-wide average delivery percentage
        avg_delivery = sum(delivery_pcts) / len(delivery_pcts)

        # Classify sentiment based on delivery percentage
        if avg_delivery >= 25:
            fii_sentiment = "ACCUMULATING"  # High delivery = institutional
            dii_sentiment = "ACCUMULATING"
        elif avg_delivery >= 18:
            fii_sentiment = "MODERATE"
            dii_sentiment = "MODERATE"
        else:
            fii_sentiment = "RETAIL_DOMINATED"
            dii_sentiment = "RETAIL_DOMINATED"

        return {
            "date": date,
            "fii_net_buy_crores": None,  # Bhav copy doesn't distinguish FII vs DII
            "dii_net_buy_crores": None,
            "fii_sentiment": fii_sentiment,
            "dii_sentiment": dii_sentiment,
            "delivery_pct": round(avg_delivery, 1),
            "source": "nse_bhav_copy",
            "note": "Institutional activity estimated from market-wide delivery percentage",
        }
    except Exception as e:
        logger.warning(f"Bhav copy CSV parse failed: {e}")
        return None


async def _get_fii_dii_from_yfinance(date: str) -> dict:
    """
    Fallback: estimate institutional sentiment from Nifty 50 volume and
    large-cap stock behavior via yfinance.

    Uses the ratio of price change vs volume as a proxy for institutional
    conviction (large price moves on average volume = informed trading).
    """
    try:
        import yfinance as yf

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _yfinance_volume_proxy)
        if result:
            return {**result, "date": date, "source": "yfinance_proxy"}
    except Exception as e:
        logger.warning(f"yfinance FII/DII proxy failed: {e}")

    return {
        "date": date,
        "fii_net_buy_crores": None,
        "dii_net_buy_crores": None,
        "fii_sentiment": "UNKNOWN",
        "dii_sentiment": "UNKNOWN",
        "source": "unavailable",
        "note": "NSE Bhav Copy and yfinance proxy both unavailable.",
    }


def _yfinance_volume_proxy() -> dict:
    """
    Compute a rough institutional activity proxy from Nifty index components.
    Not accurate — only used when both primary sources fail.
    """
    try:
        import yfinance as yf

        # Use Nifty 50 index itself for broad flow estimate
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="5d")
        if hist.empty or len(hist) < 2:
            return {}

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else latest
        price_change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
        volume_ratio = latest["Volume"] / hist["Volume"].tail(20).mean()

        # Large-cap NSE stocks that proxy for institutional activity
        proxy_tickers = ["^NSEI", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        delivery_estimates = []

        for t in proxy_tickers:
            try:
                stock = yf.Ticker(t)
                dh = stock.history(period="5d")
                if len(dh) >= 2:
                    vol_r = dh.iloc[-1]["Volume"] / dh["Volume"].tail(20).mean()
                    delivery_estimates.append(vol_r)
            except Exception:
                continue

        avg_vol_ratio = sum(delivery_estimates) / len(delivery_estimates) if delivery_estimates else 1.0

        # High volume ratio + large price drop = FII selling
        # High volume ratio + large price rise = FII buying
        if abs(price_change) > 1.0 and avg_vol_ratio > 1.3:
            if price_change > 0:
                sentiment = "FII_BUYING"
            else:
                sentiment = "FII_SELLING"
        elif avg_vol_ratio > 1.5:
            sentiment = "HIGH_INSTITUTIONAL"
        elif avg_vol_ratio < 0.7:
            sentiment = "RETAIL_DOMINATED"
        else:
            sentiment = "NORMAL"

        return {
            "fii_sentiment": sentiment,
            "dii_sentiment": "UNKNOWN",
            "price_change_pct": round(price_change, 2),
            "volume_ratio": round(avg_vol_ratio, 2),
        }
    except Exception:
        return {}


def _parse_fii_dii_response(data: list | dict, date: str) -> dict:
    """Parse the NSE FII/DII API response into a clean format."""
    result = {
        "date": date,
        "fii_net_buy_crores": 0.0,
        "dii_net_buy_crores": 0.0,
        "fii_sentiment": "NEUTRAL",
        "dii_sentiment": "NEUTRAL",
        "source": "nse_api",
    }

    try:
        if isinstance(data, list):
            for entry in data:
                category = entry.get("category", "").upper()
                net_value = float(entry.get("netValue", 0))

                if "FII" in category or "FPI" in category:
                    result["fii_net_buy_crores"] = net_value
                elif "DII" in category:
                    result["dii_net_buy_crores"] = net_value
        elif isinstance(data, dict):
            result["fii_net_buy_crores"] = float(data.get("fpiNetValue", 0))
            result["dii_net_buy_crores"] = float(data.get("diiNetValue", 0))

        # Determine sentiment
        fii = result["fii_net_buy_crores"]
        dii = result["dii_net_buy_crores"]

        if fii and fii > 500:
            result["fii_sentiment"] = "BUYING"
        elif fii and fii < -500:
            result["fii_sentiment"] = "SELLING"
        else:
            result["fii_sentiment"] = "NEUTRAL"

        if dii and dii > 500:
            result["dii_sentiment"] = "BUYING"
        elif dii and dii < -500:
            result["dii_sentiment"] = "SELLING"
        else:
            result["dii_sentiment"] = "NEUTRAL"

    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Failed to parse FII/DII data: {e}")

    return result


# -----------------------------------------------------------------------
# 3. Promoter Holding
# -----------------------------------------------------------------------
async def get_promoter_holding(ticker: str) -> Optional[dict]:
    """
    Get promoter, institutional, and public holding percentages for a stock.
    
    Uses yfinance major_holders as the data source.
    Many stocks won't have this data — returns None gracefully.
    
    Args:
        ticker: NSE ticker (e.g. RELIANCE.NS)
        
    Returns:
        Dict with promoter_pct, institution_pct, public_pct or None
    """
    try:
        import yfinance as yf

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _fetch_promoter_holding_sync, ticker
        )
        return result
    except Exception as e:
        logger.warning(f"Promoter holding unavailable for {ticker}: {e}")
        return None


def _fetch_promoter_holding_sync(ticker: str) -> Optional[dict]:
    """Synchronous promoter holding fetch via yfinance."""
    import yfinance as yf

    stock = yf.Ticker(ticker)

    try:
        holders = stock.major_holders
        if holders is None or holders.empty:
            return None

        # yfinance returns a DataFrame with % and description
        holding = {
            "ticker": ticker,
            "promoter_pct": None,
            "institution_pct": None,
            "public_pct": None,
        }

        for _, row in holders.iterrows():
            desc = str(row.iloc[1]).lower() if len(row) > 1 else ""
            pct_str = str(row.iloc[0]).replace("%", "").strip()

            try:
                pct = float(pct_str)
            except ValueError:
                continue

            if "insider" in desc or "promoter" in desc:
                holding["promoter_pct"] = pct
            elif "institution" in desc:
                holding["institution_pct"] = pct
            elif "float" in desc or "public" in desc:
                holding["public_pct"] = pct

        # If we got at least some data, return it
        if any(v is not None for k, v in holding.items() if k != "ticker"):
            return holding
        return None

    except Exception:
        return None


# -----------------------------------------------------------------------
# 4. Sector Lookup
# -----------------------------------------------------------------------
def get_sector_for_ticker(ticker: str) -> str:
    """
    Returns the sector for a Nifty 50 ticker.
    
    Args:
        ticker: NSE ticker (e.g. RELIANCE.NS)
        
    Returns:
        Sector string, or "Unknown" if not in Nifty 50
    """
    return _TICKER_TO_SECTOR.get(ticker, "Unknown")


def get_company_name(ticker: str) -> str:
    """Returns company name for a Nifty 50 ticker, or the ticker itself."""
    return _TICKER_TO_COMPANY.get(ticker, ticker.replace(".NS", ""))


def get_ticker_for_company(company_name: str) -> Optional[str]:
    """
    Reverse lookup: company name → ticker.
    Useful for matching news headlines to stocks.
    """
    return _COMPANY_NAME_TO_TICKER.get(company_name.lower())


# -----------------------------------------------------------------------
# 5. Sector Performance
# -----------------------------------------------------------------------
async def get_nifty50_sector_performance() -> dict:
    """
    Compute average daily change per sector across Nifty 50 stocks.
    
    Groups stocks by sector, fetches current price + change_pct for each,
    and computes sector-level average.
    
    Returns:
        Dict mapping sector → average change_pct
        Example: {"Banking": +1.2, "IT": -0.4, "Energy": +0.8, ...}
    """
    from data.loader import data_loader

    # Get all tickers
    tickers = [s["ticker"] for s in NIFTY_50_STOCKS]

    # Batch fetch prices
    prices = await data_loader.get_batch_prices(tickers)

    # Group by sector
    sector_changes: dict[str, list[float]] = {}
    for stock in NIFTY_50_STOCKS:
        ticker = stock["ticker"]
        sector = stock["sector"]
        price_data = prices.get(ticker, {})
        change = price_data.get("change_pct")

        if change is not None:
            if sector not in sector_changes:
                sector_changes[sector] = []
            sector_changes[sector].append(change)

    # Compute averages
    performance = {}
    for sector, changes in sector_changes.items():
        if changes:
            avg = sum(changes) / len(changes)
            performance[sector] = round(avg, 2)
        else:
            performance[sector] = 0.0

    # Sort by performance (best first)
    performance = dict(sorted(performance.items(), key=lambda x: x[1], reverse=True))

    logger.info(f"Sector performance computed: {len(performance)} sectors")
    return performance


# -----------------------------------------------------------------------
# Utility: Get all sector names
# -----------------------------------------------------------------------
def get_all_sectors() -> list[str]:
    """Returns list of unique sectors in the Nifty 50."""
    return list(set(s["sector"] for s in NIFTY_50_STOCKS))


# -----------------------------------------------------------------------
# Utility: Get stocks by sector
# -----------------------------------------------------------------------
def get_stocks_by_sector(sector: str) -> list[dict]:
    """Returns all Nifty 50 stocks in a given sector."""
    return [s for s in NIFTY_50_STOCKS if s["sector"].lower() == sector.lower()]
