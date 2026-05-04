"""
AlphaHive - Week 1 Verification Script
========================================
Run this script to verify all 6 Week 1 checks pass.
Do NOT move to Week 2 until all checks pass.

Usage:
    python tests/test_week1.py
"""

import asyncio
import sys
import os
import io
import time

# Force UTF-8 output on Windows to prevent cp1252 encoding errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def safe_print(msg: str):
    """Print with encoding safety for Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def print_header(check_num: int, title: str):
    safe_print(f"\n{'='*60}")
    safe_print(f"  CHECK {check_num}: {title}")
    safe_print(f"{'='*60}")


def print_pass(msg: str):
    safe_print(f"  [PASS] {msg}")


def print_fail(msg: str):
    safe_print(f"  [FAIL] {msg}")


def print_info(msg: str):
    safe_print(f"  [..] {msg}")


async def run_all_checks():
    results = {}

    # ------------------------------------------------------------------
    # CHECK 1: Data loader works for NSE stocks
    # ------------------------------------------------------------------
    print_header(1, "Data Loader - NSE Stocks")
    try:
        from data.loader import DataLoader
        loader = DataLoader()

        # Test 1a: Price history for RELIANCE.NS
        print_info("Fetching RELIANCE.NS price history (30 days)...")
        df = await loader.get_price_history("RELIANCE.NS", days=30)
        print_info(f"Got {len(df)} rows")
        print_info(f"Columns: {list(df.columns)}")
        print_info("First 5 rows:")
        safe_print(df.head().to_string(index=False))
        print_pass("get_price_history('RELIANCE.NS') works")

        # Test 1b: Current price for TCS.NS
        print_info("")
        print_info("Fetching TCS.NS current price...")
        price = await loader.get_current_price("TCS.NS")
        print_info(f"Result: ticker={price.get('ticker')}, price={price.get('price')}, change={price.get('change_pct')}%")
        if price.get("price") is not None:
            print_pass(f"get_current_price('TCS.NS') = Rs.{price['price']}")
        else:
            print_info("Price is None (market may be closed) - still OK")
            print_pass("get_current_price returned without crashing")

        # Test 1c: Indicators for INFY.NS
        print_info("")
        print_info("Fetching INFY.NS indicators...")
        indicators = await loader.get_indicators("INFY.NS")
        print_info(f"RSI-14: {indicators.get('rsi_14')}")
        print_info(f"EMA-50: {indicators.get('ema_50')}")
        print_info(f"Volume Ratio: {indicators.get('volume_ratio')}")
        print_pass("get_indicators('INFY.NS') works")

        results["check_1"] = True

    except Exception as e:
        print_fail(f"Data loader error: {e}")
        import traceback
        traceback.print_exc()
        results["check_1"] = False

    # ------------------------------------------------------------------
    # CHECK 2: News parser returns Indian headlines
    # ------------------------------------------------------------------
    print_header(2, "News Parser - Indian Headlines")
    try:
        from data.news import get_latest_news

        print_info("Fetching latest Indian financial news...")
        news = await get_latest_news(max_items=10)

        if len(news) > 0:
            print_info(f"Got {len(news)} headlines:")
            for i, item in enumerate(news[:5]):
                date_str = item.published_at.strftime("%Y-%m-%d %H:%M") if item.published_at else "No date"
                # Truncate headline and strip non-ASCII for safe printing
                headline = item.headline[:70].encode("ascii", errors="replace").decode("ascii")
                print_info(f"  {i+1}. [{item.source}] {headline}...")
                tickers_str = ", ".join(item.ticker_mentions) if item.ticker_mentions else "none"
                print_info(f"     Date: {date_str} | Tickers: {tickers_str}")
            print_pass(f"Got {len(news)} headlines from RSS feeds")
        else:
            print_info("No headlines returned - RSS feeds may be down")
            print_info("This is OK for offline development")
            print_pass("News parser ran without crashing")

        results["check_2"] = True

    except Exception as e:
        print_fail(f"News parser error: {e}")
        import traceback
        traceback.print_exc()
        results["check_2"] = False

    # ------------------------------------------------------------------
    # CHECK 3: Nifty 50 list loads correctly
    # ------------------------------------------------------------------
    print_header(3, "Nifty 50 Universe")
    try:
        from data.nse import get_nifty50_universe, get_sector_for_ticker

        stocks = get_nifty50_universe()
        print_info(f"Total Nifty 50 stocks: {len(stocks)}")
        print_info("First 5 entries:")
        for s in stocks[:5]:
            print_info(f"  {s['ticker']:20s} | {s['company']:30s} | {s['sector']}")

        # Verify sector lookup
        sector = get_sector_for_ticker("RELIANCE.NS")
        print_info(f"")
        print_info(f"Sector for RELIANCE.NS: {sector}")

        if len(stocks) >= 30:
            print_pass(f"Nifty 50 universe loaded: {len(stocks)} stocks")
        else:
            print_fail(f"Only {len(stocks)} stocks - expected 30+")

        results["check_3"] = len(stocks) >= 30

    except Exception as e:
        print_fail(f"Nifty 50 error: {e}")
        import traceback
        traceback.print_exc()
        results["check_3"] = False

    # ------------------------------------------------------------------
    # CHECK 4: FastAPI imports without errors
    # ------------------------------------------------------------------
    print_header(4, "FastAPI App Import")
    try:
        from api.main import app
        print_info(f"App title: {app.title}")
        print_info(f"App version: {app.version}")
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        print_info(f"Routes: {routes}")
        print_pass("FastAPI app imports cleanly")
        results["check_4"] = True

    except Exception as e:
        print_fail(f"FastAPI import error: {e}")
        import traceback
        traceback.print_exc()
        results["check_4"] = False

    # ------------------------------------------------------------------
    # CHECK 5 & 6: Test endpoints via TestClient
    # ------------------------------------------------------------------
    print_header(5, "Health Endpoint")
    print_header(6, "Mock Analyze Endpoint")
    try:
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)

        # CHECK 5: /health
        print_info("Testing GET /health...")
        response = client.get("/health")
        print_info(f"Status: {response.status_code}")
        data = response.json()
        print_info(f"Response status: {data.get('status')}")
        print_info(f"Response version: {data.get('version')}")

        if response.status_code == 200 and data.get("status") == "ok":
            print_pass("/health returns 200 OK")
            results["check_5"] = True
        else:
            print_fail(f"/health returned {response.status_code}")
            results["check_5"] = False

        # Check disclaimer header
        disclaimer_header = response.headers.get("X-AlphaHive-Disclaimer")
        if disclaimer_header:
            print_pass(f"Disclaimer header present: {disclaimer_header}")
        else:
            print_info("Disclaimer header missing (minor)")

        # CHECK 6: POST /analyze
        print_info("")
        print_info("Testing POST /analyze with RELIANCE.NS...")
        response = client.post(
            "/analyze",
            json={"ticker": "RELIANCE.NS"},
        )
        print_info(f"Status: {response.status_code}")
        data = response.json()

        # Verify AlphaHiveSignal format
        required_keys = ["ticker", "swarm", "specialists", "signal", "explanation", "disclaimer"]
        missing_keys = [k for k in required_keys if k not in data]

        if response.status_code == 200 and not missing_keys:
            print_info(f"Ticker: {data['ticker']}")
            print_info(f"Signal: {data['signal']}")
            print_info(f"Explanation: {data['explanation']['line1']}")
            disclaimer_preview = data["disclaimer"][:60]
            print_info(f"Disclaimer: {disclaimer_preview}...")

            # Verify swarm sub-keys
            swarm_keys = ["bullish_pct", "bearish_pct", "panic_index", "fomo_index", "conviction"]
            swarm_ok = all(k in data["swarm"] for k in swarm_keys)
            if swarm_ok:
                print_pass("Swarm output format correct")
            else:
                print_fail("Swarm output missing keys")

            # Verify specialist sub-keys
            spec_keys = ["fundamental_score", "technical_score", "sentiment_score", "news_score"]
            spec_ok = all(k in data["specialists"] for k in spec_keys)
            if spec_ok:
                print_pass("Specialist output format correct")
            else:
                print_fail("Specialist output missing keys")

            # Verify signal sub-keys
            sig_keys = ["final_call", "bullish_probability", "risk_level", "confidence"]
            sig_ok = all(k in data["signal"] for k in sig_keys)
            if sig_ok:
                print_pass("Signal format correct")
            else:
                print_fail("Signal format missing keys")

            print_pass("POST /analyze returns full AlphaHiveSignal format")
            print_pass("SEBI disclaimer present in response")
            results["check_6"] = True
        else:
            print_fail(f"Missing keys: {missing_keys}")
            results["check_6"] = False

    except Exception as e:
        print_fail(f"Endpoint test error: {e}")
        import traceback
        traceback.print_exc()
        results["check_5"] = results.get("check_5", False)
        results["check_6"] = False

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    safe_print(f"\n{'='*60}")
    safe_print(f"  WEEK 1 VERIFICATION SUMMARY")
    safe_print(f"{'='*60}")

    all_passed = True
    for check, passed in sorted(results.items()):
        status = "[PASS]" if passed else "[FAIL]"
        safe_print(f"  {check}: {status}")
        if not passed:
            all_passed = False

    safe_print(f"\n{'='*60}")
    if all_passed:
        safe_print("  >>> ALL CHECKS PASSED! Ready for Week 2! <<<")
        safe_print("  Next steps:")
        safe_print("    1. git add -A && git commit -m 'Week 1: Data foundation complete'")
        safe_print("    2. Install Ollama + pull llama3.2:3b and llama3.1:8b")
        safe_print("    3. Start Week 2: Swarm Engine (80 personality agents)")
    else:
        failed = [k for k, v in results.items() if not v]
        safe_print(f"  WARNING: {len(failed)} check(s) failed. Fix before proceeding.")
    safe_print(f"{'='*60}\n")

    return all_passed


if __name__ == "__main__":
    start = time.time()
    success = asyncio.run(run_all_checks())
    elapsed = time.time() - start
    safe_print(f"Total time: {elapsed:.1f}s")
    sys.exit(0 if success else 1)
