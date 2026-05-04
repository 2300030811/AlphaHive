import os
import json
import logging
from datetime import datetime, timezone
import httpx
import pandas as pd
import numpy as np
from typing import Optional

from data.loader import data_loader

logger = logging.getLogger(__name__)

class TechnicalAnalyst:
    """
    Technical Analyst agent.
    Computes indicators (Trend, Momentum, Volume, Volatility) from price history using pandas.
    Uses llama3.1:8b for final assessment based on computed metrics.
    """

    def __init__(self):
        self.model = os.getenv("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = 45.0
        # shared httpx client for this analyst instance
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def analyze(self, ticker: str, market_data: dict) -> dict:
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch 90 days of OHLCV history
        try:
            df = await data_loader.get_price_history(ticker, days=90)
            if df is None or df.empty:
                logger.warning(f"No historical data for {ticker}")
                return self._fallback_report(ticker, start_time)
        except Exception as e:
            logger.warning(f"Failed to fetch historical data for {ticker}: {e}")
            return self._fallback_report(ticker, start_time)

        # Basic check to ensure we have enough data
        if len(df) < 20:
            logger.warning(f"Not enough historical data for {ticker}: {len(df)} rows")
            return self._fallback_report(ticker, start_time)

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        current_price = close.iloc[-1]

        indicators = {}

        # TREND INDICATORS
        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()
        ema_200 = close.ewm(span=200, adjust=False).mean()
        
        c_ema_20 = ema_20.iloc[-1]
        c_ema_50 = ema_50.iloc[-1]
        c_ema_200 = ema_200.iloc[-1] if len(df) >= 200 else c_ema_50 # fallback if <200 days

        indicators['ema_20'] = c_ema_20
        indicators['ema_50'] = c_ema_50
        indicators['ema_200'] = c_ema_200

        if c_ema_20 > c_ema_50 > c_ema_200:
            trend_structure = "uptrend"
        elif c_ema_20 < c_ema_50 < c_ema_200:
            trend_structure = "downtrend"
        else:
            trend_structure = "ranging"
        indicators['trend_structure'] = trend_structure

        # Golden Cross / Death Cross check over last 10 days
        golden_cross = False
        death_cross = False
        if len(df) >= 10:
            recent_ema_50 = ema_50.iloc[-10:]
            recent_ema_200 = ema_200.iloc[-10:] if len(df) >= 200 else recent_ema_50
            # If 50 crossed above 200
            if (recent_ema_50.iloc[0] <= recent_ema_200.iloc[0]) and (c_ema_50 > c_ema_200):
                golden_cross = True
            # If 50 crossed below 200
            elif (recent_ema_50.iloc[0] >= recent_ema_200.iloc[0]) and (c_ema_50 < c_ema_200):
                death_cross = True
                
        indicators['golden_cross'] = golden_cross
        indicators['death_cross'] = death_cross

        # MOMENTUM INDICATORS
        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window=14).mean()
        loss = (-delta.clip(upper=0)).rolling(window=14).mean()
        # To avoid division by zero
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        # fallback for NaN
        rsi_series = rsi_series.fillna(50) 
        
        c_rsi_14 = rsi_series.iloc[-1]
        indicators['rsi_14'] = c_rsi_14

        if c_rsi_14 < 30:
            rsi_signal = "oversold"
        elif c_rsi_14 > 70:
            rsi_signal = "overbought"
        else:
            rsi_signal = "neutral"
        indicators['rsi_signal'] = rsi_signal

        # MACD
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        macd_signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal_line
        
        indicators['macd_line'] = macd_line.iloc[-1]
        indicators['macd_signal'] = macd_signal_line.iloc[-1]
        indicators['macd_histogram'] = macd_hist.iloc[-1]

        if len(macd_hist) >= 2:
            prev_hist = macd_hist.iloc[-2]
            curr_hist = macd_hist.iloc[-1]
            if prev_hist <= 0 and curr_hist > 0:
                macd_signal_type = "bullish_crossover"
            elif prev_hist >= 0 and curr_hist < 0:
                macd_signal_type = "bearish_crossover"
            else:
                macd_signal_type = "neutral"
        else:
            macd_signal_type = "neutral"
        indicators['macd_signal_type'] = macd_signal_type

        # VOLUME INDICATORS
        volume_avg_20 = volume.rolling(window=20).mean()
        c_volume_avg_20 = volume_avg_20.iloc[-1]
        c_volume = volume.iloc[-1]
        
        volume_ratio = c_volume / c_volume_avg_20 if c_volume_avg_20 else 1.0
        indicators['volume_avg_20'] = c_volume_avg_20
        indicators['volume_ratio'] = volume_ratio
        
        if len(volume) >= 5:
            vol_5d_avg = volume.iloc[-5:].mean()
            if vol_5d_avg > c_volume_avg_20:
                volume_trend = "expanding"
            elif vol_5d_avg < c_volume_avg_20 * 0.8:
                volume_trend = "contracting"
            else:
                volume_trend = "neutral"
        else:
            volume_trend = "neutral"
        indicators['volume_trend'] = volume_trend

        # Support / Resistance / 52-Week
        # df contains 90 days, we'll try to use that as 52w if real 52w is unavailable
        try:
            week_52_high = df['high'].max() # Approx if only 90 days are given
            week_52_low = df['low'].min()
        except Exception:
            week_52_high = current_price * 1.2
            week_52_low = current_price * 0.8
            
        indicators['week_52_high'] = week_52_high
        indicators['week_52_low'] = week_52_low
        indicators['pct_from_52w_high'] = ((current_price - week_52_high) / week_52_high) * 100 if week_52_high else 0

        breakout_confirmed = False
        if abs(current_price - week_52_high) / week_52_high < 0.03 and volume_ratio > 1.5:
            breakout_confirmed = True
        indicators['breakout_confirmed'] = breakout_confirmed

        if len(df) >= 20:
            support_level = low.iloc[-20:].min()
            resistance_level = high.iloc[-20:].max()
        else:
            support_level = low.min()
            resistance_level = high.max()
        indicators['support_level'] = support_level
        indicators['resistance_level'] = resistance_level

        # VOLATILITY INDICATORS
        # ATR 14
        if len(df) >= 15:
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = tr.rolling(window=14).mean().iloc[-1]
        else:
            atr_14 = current_price * 0.02
            
        indicators['atr_14'] = atr_14
        indicators['atr_pct'] = (atr_14 / current_price) * 100 if current_price else 0

        # Bollinger Bands 20
        rolling_mean = close.rolling(window=20).mean()
        rolling_std = close.rolling(window=20).std()
        bb_upper = rolling_mean + (rolling_std * 2)
        bb_lower = rolling_mean - (rolling_std * 2)
        
        c_bb_upper = bb_upper.iloc[-1]
        c_bb_lower = bb_lower.iloc[-1]
        c_bb_middle = rolling_mean.iloc[-1]
        
        indicators['bb_upper'] = c_bb_upper
        indicators['bb_lower'] = c_bb_lower
        indicators['bb_middle'] = c_bb_middle

        if current_price > c_bb_upper:
            bb_position = "above_upper"
        elif current_price < c_bb_lower:
            bb_position = "below_lower"
        else:
            bb_position = "inside"
        indicators['bb_position'] = bb_position

        # BB Squeeze: bandwidth < 20 day average of bandwidth
        bandwidth = (bb_upper - bb_lower) / rolling_mean
        if len(bandwidth.dropna()) >= 20:
            bb_squeeze = bandwidth.iloc[-1] < bandwidth.rolling(window=20).mean().iloc[-1]
        else:
            bb_squeeze = False
        indicators['bb_squeeze'] = bb_squeeze


        # 2. Derive deterministic composite score (0-100)
        score = 50
        
        # Trend
        if trend_structure == "uptrend": score += 10
        elif trend_structure == "downtrend": score -= 10
        if golden_cross: score += 5
        if death_cross: score -= 5
            
        # Momentum
        if 40 <= c_rsi_14 <= 65: score += 10
        elif c_rsi_14 > 75: score -= 10
        elif c_rsi_14 < 25: score -= 5
        
        if macd_signal_type == "bullish_crossover": score += 5
        elif macd_signal_type == "bearish_crossover": score -= 5
            
        # Volume
        if breakout_confirmed: score += 10
        if volume_ratio > 1.5 and close.iloc[-1] >= close.iloc[-2]: score += 5
        if volume_ratio > 1.5 and close.iloc[-1] < close.iloc[-2]: score -= 5
            
        score = max(0, min(100, int(score)))

        # 3. Call Ollama
        def fmt(val):
            return str(round(val, 2)) if isinstance(val, (int, float)) else str(val)

        formatted_indicators_summary = f"""
        Price: {fmt(current_price)}
        Trend: {trend_structure} (EMA20: {fmt(c_ema_20)}, EMA50: {fmt(c_ema_50)}, EMA200: {fmt(c_ema_200)})
        Golden Cross: {golden_cross}, Death Cross: {death_cross}
        
        RSI (14): {fmt(c_rsi_14)} ({rsi_signal})
        MACD Signal: {macd_signal_type}
        
        Volume Ratio: {fmt(volume_ratio)} (Trend: {volume_trend})
        Breakout Confirmed: {breakout_confirmed}
        
        Bollinger Bands: {bb_position} (Squeeze: {bb_squeeze})
        ATR (Volatility): {fmt(indicators['atr_pct'])}%
        
        Support: {fmt(support_level)}
        Resistance: {fmt(resistance_level)}
        % from 52w High: {fmt(indicators['pct_from_52w_high'])}%
        """

        system_prompt = (
            "You are a technical analyst for Indian equity markets.\n"
            "Analyze the provided indicators and return a concise technical verdict.\n"
            "Respond in valid JSON only. No preamble."
        )

        user_prompt = (
            f"Technical analysis for {ticker}:\n"
            f"{formatted_indicators_summary}\n\n"
            "Return JSON:\n"
            "{\n"
            "  \"verdict\": \"BULLISH\" | \"BEARISH\" | \"NEUTRAL\",\n"
            "  \"key_signals\": [list of max 3 most important signals],\n"
            "  \"watch_levels\": { \"support\": price, \"resistance\": price },\n"
            "  \"summary\": \"one sentence technical assessment\"\n"
            "}"
        )

        llm_response = await self._call_llm(system_prompt, user_prompt)
        
        verdict = "NEUTRAL"
        key_signals = []
        watch_levels = {"support": support_level, "resistance": resistance_level}
        summary = f"Technical score is {score} with {trend_structure} trend."

        if llm_response:
            try:
                text = llm_response.strip()
                if text.startswith("```json"): text = text[7:]
                if text.startswith("```"): text = text[3:]
                if text.endswith("```"): text = text[:-3]
                
                parsed = json.loads(text.strip())
                verdict = parsed.get("verdict", "NEUTRAL")
                key_signals = parsed.get("key_signals", [])
                
                # Some LLMs might return a string or dict for watch_levels
                wl = parsed.get("watch_levels", {})
                if isinstance(wl, dict):
                    watch_levels["support"] = wl.get("support", support_level)
                    watch_levels["resistance"] = wl.get("resistance", resistance_level)
                
                summary = parsed.get("summary", summary)
            except Exception as e:
                logger.error(f"Failed to parse TechnicalAnalyst LLM response: {e}")

        # Replace NaN/inf with None, and convert numpy types to native Python types for JSON serialization
        for k, v in indicators.items():
            if isinstance(v, (int, float, np.integer, np.floating)):
                if pd.isna(v) or np.isinf(v):
                    indicators[k] = None
                else:
                    indicators[k] = float(v) if isinstance(v, (float, np.floating)) else int(v)
            elif isinstance(v, (np.bool_, bool)):
                indicators[k] = bool(v)
            else:
                indicators[k] = v

        return {
            "analyst": "technical",
            "ticker": ticker,
            "indicators": indicators,
            "score": score,
            "verdict": verdict,
            "key_signals": key_signals,
            "watch_levels": watch_levels,
            "summary": summary,
            "timestamp": start_time.isoformat()
        }

    def _fallback_report(self, ticker: str, start_time: datetime) -> dict:
        return {
            "analyst": "technical",
            "ticker": ticker,
            "indicators": {},
            "score": 50,
            "verdict": "NEUTRAL",
            "key_signals": ["Insufficient technical data"],
            "watch_levels": {"support": 0, "resistance": 0},
            "summary": "Technical analysis unavailable due to missing historical price data.",
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
            logger.error(f"TechnicalAnalyst LLM call failed: {e}")
            return None

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass
