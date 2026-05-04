import os
import asyncio
import sys

# Ensure UTF-8 output for Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Mock OLLAMA environment for testing if not set
os.environ.setdefault("OLLAMA_SPECIALIST_MODEL", "llama3.1:8b")

async def run_checks():
    print("\n============================================================")
    print("=== WEEK 3 VERIFICATION: SPECIALISTS & ORCHESTRATOR ===")
    print("============================================================\n")

    # ---------------------------------------------------------
    # CHECK 1: Fundamental Analyst
    # ---------------------------------------------------------
    print("CHECK 1: Fundamental Analyst...")
    from agents.specialists.fundamental import FundamentalAnalyst
    try:
        fund_analyst = FundamentalAnalyst()
        fund_report = await fund_analyst.analyze("RELIANCE.NS", {})
        
        assert fund_report["analyst"] == "fundamental", "Analyst name mismatch"
        assert 0 <= fund_report["score"] <= 100, "Score out of bounds"
        assert fund_report["verdict"] in ["STRONG", "MODERATE", "WEAK"], "Invalid verdict"
        assert isinstance(fund_report["key_positives"], list), "key_positives must be list"
        assert isinstance(fund_report["summary"], str) and len(fund_report["summary"]) > 10, "Summary must be valid string"
        
        print("  [PASS] CHECK 1 PASSED")
        print(f"    Fundamental score: {fund_report['score']}")
        print(f"    Verdict: {fund_report['verdict']}")
        print(f"    Summary: {fund_report['summary']}")
        print(f"    PE vs sector: {fund_report['derived'].get('pe_vs_sector')}")
    except AssertionError as e:
        print(f"  [FAIL] CHECK 1 FAILED: {e}")
        return

    # ---------------------------------------------------------
    # CHECK 2: Technical Analyst
    # ---------------------------------------------------------
    print("\nCHECK 2: Technical Analyst...")
    from agents.specialists.technical import TechnicalAnalyst
    try:
        tech_analyst = TechnicalAnalyst()
        tech_report = await tech_analyst.analyze("TCS.NS", {})
        
        assert "rsi_14" in tech_report["indicators"], "Missing rsi_14"
        assert "ema_50" in tech_report["indicators"], "Missing ema_50"
        assert "ema_200" in tech_report["indicators"], "Missing ema_200"
        assert "trend_structure" in tech_report["indicators"], "Missing trend_structure"
        assert 0 <= tech_report["score"] <= 100, "Score out of bounds"
        assert tech_report["verdict"] in ["BULLISH", "BEARISH", "NEUTRAL"], "Invalid verdict"
        
        print("  [PASS] CHECK 2 PASSED")
        print(f"    RSI-14: {tech_report['indicators']['rsi_14']:.1f}" if tech_report['indicators']['rsi_14'] else "    RSI-14: None")
        print(f"    Trend: {tech_report['indicators']['trend_structure']}")
        print(f"    Technical score: {tech_report['score']}")
        print(f"    Key signals: {tech_report['key_signals']}")
    except AssertionError as e:
        print(f"  [FAIL] CHECK 2 FAILED: {e}")
        return

    # ---------------------------------------------------------
    # CHECK 3: FinBERT Sentiment Analyst
    # ---------------------------------------------------------
    print("\nCHECK 3: FinBERT Sentiment Analyst...")
    from agents.specialists.sentiment import SentimentAnalyst
    try:
        sent_analyst = SentimentAnalyst()
        sent_report = await sent_analyst.analyze("INFY.NS", {})
        
        assert sent_report["analyst"] == "sentiment", "Analyst name mismatch"
        assert -1.0 <= sent_report["net_sentiment"] <= 1.0, "Net sentiment out of bounds"
        assert 0 <= sent_report["score"] <= 100, "Score out of bounds"
        assert sent_report["verdict"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"], "Invalid verdict"
        
        print("  [PASS] CHECK 3 PASSED")
        print(f"    Headlines analyzed: {sent_report['headlines_analyzed']}")
        print(f"    Net sentiment: {sent_report['net_sentiment']:.3f}")
        print(f"    Sentiment score: {sent_report['score']}")
        print(f"    Top headline: {sent_report['top_headlines'][0]['headline'] if sent_report['top_headlines'] else 'none'}")
    except AssertionError as e:
        print(f"  [FAIL] CHECK 3 FAILED: {e}")
        return

    # ---------------------------------------------------------
    # CHECK 4: News Analyst
    # ---------------------------------------------------------
    print("\nCHECK 4: News Analyst...")
    from agents.specialists.news import NewsAnalyst
    try:
        news_analyst = NewsAnalyst()
        news_report = await news_analyst.analyze("HDFCBANK.NS", {})
        
        assert news_report["analyst"] == "news", "Analyst name mismatch"
        assert 0 <= news_report["score"] <= 100, "Score out of bounds"
        assert news_report["verdict"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"], "Invalid verdict"
        
        print("  [PASS] CHECK 4 PASSED")
        print(f"    Bullish events: {news_report['bullish_events']}")
        print(f"    Bearish events: {news_report['bearish_events']}")
        print(f"    Alert: {news_report['alert']}")
        print(f"    Summary: {news_report['summary']}")
    except AssertionError as e:
        print(f"  [FAIL] CHECK 4 FAILED: {e}")
        return

    # ---------------------------------------------------------
    # CHECK 5: Orchestrator
    # ---------------------------------------------------------
    print("\nCHECK 5: Orchestrator Full Pipeline...")
    from engine.orchestrator import AlphaHiveOrchestrator
    try:
        import time
        orchestrator = AlphaHiveOrchestrator()
        
        start = time.time()
        result = await orchestrator.analyze("RELIANCE.NS")
        elapsed = time.time() - start
        
        assert "swarm" in result, "Missing swarm layer"
        assert "specialists" in result, "Missing specialists layer"
        assert "signal_preview" in result, "Missing signal_preview"
        assert "disclaimer" in result, "Missing disclaimer"
        assert result["disclaimer"] != "", "Disclaimer empty"
        
        assert result["specialists"]["fundamental"] is not None, "Missing fundamental report"
        assert result["specialists"]["technical"] is not None, "Missing technical report"
        assert result["specialists"]["sentiment"] is not None, "Missing sentiment report"
        assert result["specialists"]["news"] is not None, "Missing news report"
        
        print(f"  [PASS] CHECK 5 PASSED — Full pipeline in {elapsed:.1f}s")
        print(f"    Ticker: {result['ticker']}")
        print(f"    Swarm dominant: {result['signal_preview']['swarm_call']}")
        print(f"    Specialist combined score: {result['signal_preview']['specialist_score']}")
        print(f"    Agreement state: {result['signal_preview']['agreement']}")
        print(f"    Alert: {result['signal_preview']['alert']}")
        
    except AssertionError as e:
        print(f"  [FAIL] CHECK 5 FAILED: {e}")
        return
        
    print("\n============================================================")
    print("=== WEEK 3 COMPLETE: READY FOR WEEK 4 ===")
    print("============================================================\n")

if __name__ == "__main__":
    # Workaround for Windows asyncio bug
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_checks())
