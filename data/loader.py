"""
AlphaHive — Data Loader
========================
Primary: yfinance (handles .NS format for NSE stocks)
Fallback: AKShare (when yfinance fails or returns empty)

Auto-fallback pattern inspired by Vibe-Trading's registry pattern:
  1. Try primary source
  2. If it raises any exception OR returns empty → try fallback
  3. Log which source was actually used
  4. Never crash — always return something or raise a clear exception

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("alphahive.data.loader")

# IST timezone offset
IST = timezone(timedelta(hours=5, minutes=30))


class DataLoaderError(Exception):
    """Raised when both primary and fallback data sources fail."""
    pass


class DataLoader:
    """
    Unified data loader for AlphaHive.
    Fetches OHLCV price history, current prices, and technical indicators
    for NSE and global stocks.
    
    Primary: yfinance
    Fallback: AKShare (limited India coverage — handled gracefully)
    
    All methods are async-compatible for integration with FastAPI and
    the swarm engine's asyncio runner.
    """

    def __init__(self):
        self._cache: dict = {}  # Simple in-memory cache
        self._cache_ttl = 300   # 5 minutes cache TTL

    # -----------------------------------------------------------------------
    # Primary method: Price History
    # -----------------------------------------------------------------------
    async def get_price_history(
        self,
        ticker: str,
        days: int = 60,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV price history for a stock.
        
        Args:
            ticker: Stock ticker in Yahoo Finance format (e.g. RELIANCE.NS)
            days: Number of trading days of history to fetch
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            
        Raises:
            DataLoaderError: If both yfinance and AKShare fail
        """
        # Try yfinance first
        try:
            df = await self._fetch_yfinance_history(ticker, days)
            if df is not None and not df.empty:
                logger.info(f"yfinance succeeded for {ticker} ({len(df)} rows)")
                return df
            logger.warning(f"yfinance returned empty data for {ticker}")
        except Exception as e:
            logger.warning(f"yfinance failed for {ticker}: {e}")

        # Fallback to AKShare
        try:
            df = await self._fetch_akshare_history(ticker, days)
            if df is not None and not df.empty:
                logger.info(f"AKShare fallback succeeded for {ticker} ({len(df)} rows)")
                return df
            logger.warning(f"AKShare returned empty data for {ticker}")
        except Exception as e:
            logger.warning(f"AKShare fallback also failed for {ticker}: {e}")

        raise DataLoaderError(
            f"All data sources failed for {ticker}. "
            f"Check ticker format (NSE should be {ticker.split('.')[0]}.NS)"
        )

    # -----------------------------------------------------------------------
    # Current Price
    # -----------------------------------------------------------------------
    async def get_current_price(self, ticker: str) -> dict:
        """
        Get the latest price data for a stock.
        
        Args:
            ticker: Stock ticker (e.g. RELIANCE.NS)
            
        Returns:
            Dict with: ticker, price, change_pct, volume, timestamp
        """
        # Check cache first
        cache_key = f"price_{ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Try yfinance fast_info first
        try:
            result = await self._fetch_yfinance_current(ticker)
            if result is not None:
                self._set_cached(cache_key, result)
                logger.info(f"yfinance current price succeeded for {ticker}")
                return result
        except Exception as e:
            logger.warning(f"yfinance current price failed for {ticker}: {e}")

        # Fallback: use last row of price history
        try:
            df = await self.get_price_history(ticker, days=5)
            if not df.empty:
                last = df.iloc[-1]
                prev_close = df.iloc[-2]["close"] if len(df) >= 2 else last["close"]
                change_pct = ((last["close"] - prev_close) / prev_close * 100) if prev_close else 0.0

                result = {
                    "ticker": ticker,
                    "price": round(float(last["close"]), 2),
                    "change_pct": round(float(change_pct), 2),
                    "volume": int(last["volume"]),
                    "timestamp": datetime.now(IST).isoformat(),
                }
                self._set_cached(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"All current price methods failed for {ticker}: {e}")

        return {
            "ticker": ticker,
            "price": None,
            "change_pct": None,
            "volume": None,
            "timestamp": datetime.now(IST).isoformat(),
            "error": f"Unable to fetch price for {ticker}",
        }

    # -----------------------------------------------------------------------
    # Batch Prices
    # -----------------------------------------------------------------------
    async def get_batch_prices(self, tickers: list[str]) -> dict[str, dict]:
        """
        Fetch current prices for multiple tickers concurrently.
        
        Never fails entirely — if one ticker fails, its entry includes
        the error message instead of price data.
        
        Args:
            tickers: List of ticker strings
            
        Returns:
            Dict mapping ticker → price dict
        """
        tasks = [self.get_current_price(t) for t in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch = {}
        for ticker, result in zip(tickers, results):
            if isinstance(result, Exception):
                batch[ticker] = {
                    "ticker": ticker,
                    "price": None,
                    "error": str(result),
                    "timestamp": datetime.now(IST).isoformat(),
                }
            else:
                batch[ticker] = result

        logger.info(f"Batch prices fetched for {len(tickers)} tickers")
        return batch

    # -----------------------------------------------------------------------
    # Technical Indicators
    # -----------------------------------------------------------------------
    async def get_indicators(self, ticker: str, days: int = 200) -> dict:
        """
        Compute technical indicators from price history.
        
        Indicators computed:
          - rsi_14:       Relative Strength Index (14-period)
          - ema_50:       50-day Exponential Moving Average
          - ema_200:      200-day Exponential Moving Average
          - atr_14:       Average True Range (14-period)
          - volume_avg_30: 30-day average volume
          - volume_ratio:  Today's volume / 30-day avg
          
        Args:
            ticker: Stock ticker
            days: Days of history to fetch (minimum 200 for EMA-200)
            
        Returns:
            Dict with all indicator values
        """
        # Need enough data for EMA-200
        fetch_days = max(days, 250)
        df = await self.get_price_history(ticker, days=fetch_days)

        if df.empty or len(df) < 14:
            return {
                "ticker": ticker,
                "error": "Insufficient data for indicator calculation",
                "rsi_14": None, "ema_50": None, "ema_200": None,
                "atr_14": None, "volume_avg_30": None, "volume_ratio": None,
            }

        indicators = {"ticker": ticker}

        # RSI-14
        indicators["rsi_14"] = round(float(self._compute_rsi(df["close"], 14)), 2)

        # EMA-50
        ema_50 = df["close"].ewm(span=50, adjust=False).mean()
        indicators["ema_50"] = round(float(ema_50.iloc[-1]), 2) if len(df) >= 50 else None

        # EMA-200
        ema_200 = df["close"].ewm(span=200, adjust=False).mean()
        indicators["ema_200"] = round(float(ema_200.iloc[-1]), 2) if len(df) >= 200 else None

        # ATR-14
        indicators["atr_14"] = round(float(self._compute_atr(df, 14)), 2)

        # Volume metrics
        vol_avg_30 = df["volume"].tail(30).mean()
        indicators["volume_avg_30"] = int(vol_avg_30) if not np.isnan(vol_avg_30) else None

        today_vol = float(df["volume"].iloc[-1])
        indicators["volume_ratio"] = (
            round(today_vol / vol_avg_30, 2) if vol_avg_30 and vol_avg_30 > 0 else None
        )

        # Bonus: Bollinger Bands (useful for specialist analysts later)
        sma_20 = df["close"].rolling(window=20).mean()
        std_20 = df["close"].rolling(window=20).std()
        indicators["bollinger_upper"] = round(float(sma_20.iloc[-1] + 2 * std_20.iloc[-1]), 2) if len(df) >= 20 else None
        indicators["bollinger_lower"] = round(float(sma_20.iloc[-1] - 2 * std_20.iloc[-1]), 2) if len(df) >= 20 else None

        # Current price position relative to indicators
        current = float(df["close"].iloc[-1])
        indicators["current_price"] = round(current, 2)
        if indicators["ema_50"]:
            indicators["price_vs_ema50"] = "above" if current > indicators["ema_50"] else "below"
        if indicators["ema_200"]:
            indicators["price_vs_ema200"] = "above" if current > indicators["ema_200"] else "below"

        # EMA crossover signal
        if indicators["ema_50"] and indicators["ema_200"]:
            indicators["ema_signal"] = (
                "golden_cross" if indicators["ema_50"] > indicators["ema_200"]
                else "death_cross"
            )

        logger.info(f"Indicators computed for {ticker}: RSI={indicators['rsi_14']}")
        return indicators

    # -----------------------------------------------------------------------
    # Stock info (fundamental data)
    # -----------------------------------------------------------------------
    async def get_stock_info(self, ticker: str) -> dict:
        """
        Get fundamental stock info from yfinance.
        
        Returns PE ratio, EPS, market cap, sector, etc.
        """
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self._fetch_yfinance_info, ticker)
            return info
        except Exception as e:
            logger.warning(f"Failed to fetch stock info for {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}

    # ===================================================================
    # PRIVATE: yfinance methods
    # ===================================================================
    async def _fetch_yfinance_history(self, ticker: str, days: int) -> Optional[pd.DataFrame]:
        """Fetch OHLCV from yfinance in a thread executor (yfinance is sync)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._yfinance_history_sync, ticker, days)

    def _yfinance_history_sync(self, ticker: str, days: int) -> pd.DataFrame:
        """Synchronous yfinance history fetch."""
        stock = yf.Ticker(ticker)
        # Use period string for cleaner date handling
        period_map = {
            5: "5d", 10: "10d", 30: "1mo", 60: "3mo",
            90: "3mo", 180: "6mo", 250: "1y", 365: "1y",
        }
        # Find the closest period
        period = "3mo"  # default
        for threshold, p in sorted(period_map.items()):
            if days <= threshold:
                period = p
                break
        if days > 365:
            period = "2y"

        df = stock.history(period=period, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()

        # Standardize column names to lowercase
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Rename 'date' column if needed
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})

        # Keep only the columns we need
        keep_cols = ["date", "open", "high", "low", "close", "volume"]
        available = [c for c in keep_cols if c in df.columns]
        df = df[available]

        # Remove timezone from date for consistency
        if "date" in df.columns and hasattr(df["date"].dtype, "tz"):
            df["date"] = df["date"].dt.tz_localize(None)

        # Trim to requested days
        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)

        return df

    async def _fetch_yfinance_current(self, ticker: str) -> Optional[dict]:
        """Fetch current price using yfinance fast_info."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._yfinance_current_sync, ticker)

    def _yfinance_current_sync(self, ticker: str) -> Optional[dict]:
        """Synchronous current price fetch."""
        stock = yf.Ticker(ticker)

        try:
            info = stock.fast_info
            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)

            if price is None:
                # Fallback: get from history
                hist = stock.history(period="2d")
                if hist.empty:
                    return None
                price = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price

            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

            return {
                "ticker": ticker,
                "price": round(float(price), 2),
                "change_pct": round(float(change_pct), 2),
                "volume": int(getattr(info, "last_volume", 0) or 0),
                "timestamp": datetime.now(IST).isoformat(),
            }
        except Exception:
            return None

    def _fetch_yfinance_info(self, ticker: str) -> dict:
        """Fetch fundamental info from yfinance."""
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        return {
            "ticker": ticker,
            "company": info.get("longName", info.get("shortName", "Unknown")),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "dividend_yield": info.get("dividendYield"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
            "beta": info.get("beta"),
        }

    # ===================================================================
    # PRIVATE: AKShare fallback methods
    # ===================================================================
    async def _fetch_akshare_history(self, ticker: str, days: int) -> Optional[pd.DataFrame]:
        """
        Fallback: Fetch from AKShare.
        AKShare India coverage is limited — handle gracefully.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._akshare_history_sync, ticker, days)

    def _akshare_history_sync(self, ticker: str, days: int) -> pd.DataFrame:
        """Synchronous AKShare history fetch."""
        try:
            import akshare as ak

            if ticker.endswith((".NS", ".BO")):
                logger.warning(
                    "AKShare fallback skipped for NSE ticker %s; returning empty DataFrame.",
                    ticker,
                )
                return pd.DataFrame()

            # Strip .NS / .BO suffix for AKShare
            symbol = ticker.replace(".NS", "").replace(".BO", "")

            # Try Indian stock endpoint
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

            try:
                # AKShare's Indian stock function
                df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
            except Exception:
                # If that fails, try another endpoint
                try:
                    df = ak.stock_hk_daily(symbol=symbol, adjust="qfq")
                except Exception:
                    return pd.DataFrame()

            if df is None or df.empty:
                return pd.DataFrame()

            # Standardize columns
            col_map = {
                "date": "date", "open": "open", "high": "high",
                "low": "low", "close": "close", "volume": "volume",
            }
            df.columns = [c.lower() for c in df.columns]
            available = {k: v for k, v in col_map.items() if k in df.columns}
            df = df.rename(columns=available)

            keep = ["date", "open", "high", "low", "close", "volume"]
            available_cols = [c for c in keep if c in df.columns]
            df = df[available_cols]

            # Trim to requested days
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)

            return df

        except ImportError:
            logger.error("AKShare not installed. Run: pip install akshare")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"AKShare fetch failed for {ticker}: {e}")
            return pd.DataFrame()

    # ===================================================================
    # PRIVATE: Technical indicator computations
    # ===================================================================
    @staticmethod
    def _compute_rsi(prices: pd.Series, period: int = 14) -> float:
        """
        Compute RSI (Relative Strength Index).
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss over period
        """
        deltas = prices.diff()
        gain = deltas.where(deltas > 0, 0.0)
        loss = -deltas.where(deltas < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        # Use exponential moving average for smoother RSI
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1] if not rsi.empty else 50.0

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
        """
        Compute ATR (Average True Range).
        
        TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        ATR = SMA(TR, period)
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr.iloc[-1] if not atr.empty else 0.0

    # ===================================================================
    # PRIVATE: Simple cache
    # ===================================================================
    def _get_cached(self, key: str):
        """Get value from cache if not expired."""
        if key in self._cache:
            entry = self._cache[key]
            if (datetime.now(timezone.utc) - entry["time"]).seconds < self._cache_ttl:
                return entry["value"]
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value):
        """Store value in cache with current timestamp."""
        self._cache[key] = {
            "value": value,
            "time": datetime.now(timezone.utc),
        }


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------
data_loader = DataLoader()
