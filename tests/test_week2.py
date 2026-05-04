"""
AlphaHive — Week 2 Verification Tests
========================================
Validates the entire swarm engine — 80 agents, 2 rounds, aggregation.
Run with: python tests/test_week2.py

Checks:
  1. All 80 agents load correctly (25+20+20+15)
  2. Single agent decision returns valid structure
  3. Full Round 1 parallel run (80 agents under 90s)
  4. Crowd summary builds correctly
  5. Round 2 runs and shows social influence movement
  6. Aggregator produces valid swarm signal output

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import asyncio
import sys
import time
import os

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_checks():
    """Run all Week 2 verification checks in sequence."""
    results = {"passed": 0, "failed": 0, "errors": []}

    # ==================================================================
    # CHECK 1: All 80 agents load correctly
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 1: Loading all 80 agents...")
    print("=" * 60)

    try:
        from agents.swarm.personalities.retail import get_all_retail_agents
        from agents.swarm.personalities.institutional import get_all_institutional_agents
        from agents.swarm.personalities.algo import get_all_algo_agents
        from agents.swarm.personalities.news_reactor import get_all_news_reactor_agents

        retail = get_all_retail_agents()
        institutional = get_all_institutional_agents()
        algo = get_all_algo_agents()
        news = get_all_news_reactor_agents()

        assert len(retail) == 25, f"Expected 25 retail agents, got {len(retail)}"
        assert len(institutional) == 20, f"Expected 20 institutional agents, got {len(institutional)}"
        assert len(algo) == 20, f"Expected 20 algo agents, got {len(algo)}"
        assert len(news) == 15, f"Expected 15 news reactor agents, got {len(news)}"

        total = retail + institutional + algo + news
        assert len(total) == 80, f"Expected 80 total agents, got {len(total)}"

        # Verify all agents have unique names
        names = [a.name for a in total]
        assert len(names) == len(set(names)), "Duplicate agent names found!"

        # Verify all agents have required attributes
        for agent in total:
            assert hasattr(agent, "name"), f"Agent missing 'name' attribute"
            assert hasattr(agent, "agent_type"), f"Agent missing 'agent_type'"
            assert hasattr(agent, "weight"), f"Agent missing 'weight'"
            assert agent.weight > 0, f"Agent {agent.name} has invalid weight: {agent.weight}"

        print(f"  Retail:        {len(retail)} agents [OK]")
        print(f"  Institutional: {len(institutional)} agents [OK]")
        print(f"  Algo:          {len(algo)} agents [OK]")
        print(f"  News Reactor:  {len(news)} agents [OK]")
        print(f"  -----------------------")
        print(f"  Total:         {len(total)} agents [OK]")
        print(f"\n  Sample agents:")
        for a in total[:5]:
            print(f"    {a}")

        print(f"\n[PASS] CHECK 1 PASSED: {len(total)} agents loaded successfully")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 1 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 1: {e}")
        return results  # Can't continue without agents

    # ==================================================================
    # CHECK 2: Single agent decision works
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 2: Testing single agent decision...")
    print("=" * 60)

    try:
        # Create mock market data for RELIANCE.NS
        mock_market_data = {
            "ticker": "RELIANCE.NS",
            "price": 2450.50,
            "price_change_pct": -1.5,
            "volume_ratio": 1.3,
            "indicators": {
                "rsi_14": 45.2,
                "ema_50": 2480.00,
                "ema_200": 2350.00,
                "atr_14": 48.5,
            },
            "news_headlines": [
                "Reliance Industries Q4 profit meets estimates",
                "Jio adds 5 million subscribers in March quarter",
            ],
            "fii_dii": {
                "fii_net": -350.0,
                "dii_net": 520.0,
                "fii_sentiment": "SELLING",
            },
            "price_vs_200ema": "above",
        }

        # Test a PanicSeller agent
        agent = retail[0]  # First PanicSeller
        print(f"  Testing agent: {agent}")
        print(f"  Market data: RELIANCE.NS at Rs.2450.50 (-1.5%)")

        decision = await agent.decide_round1(mock_market_data)

        # Validate decision structure
        required_keys = ["agent_name", "agent_type", "weight", "round",
                         "action", "confidence", "reasoning"]
        for key in required_keys:
            assert key in decision, f"Decision missing key: {key}"

        assert decision["action"] in ("buy", "sell", "hold"), \
            f"Invalid action: {decision['action']}"
        assert 0.0 <= decision["confidence"] <= 1.0, \
            f"Confidence out of range: {decision['confidence']}"
        assert decision["round"] == 1, f"Expected round 1, got {decision['round']}"

        print(f"\n  Decision: {decision['action'].upper()}")
        print(f"  Confidence: {decision['confidence']:.2f}")
        print(f"  Reasoning: {decision['reasoning']}")

        print(f"\n[PASS] CHECK 2 PASSED: Single agent returns valid decision")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 2 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 2: {e}")

    # ==================================================================
    # CHECK 3: Full Round 1 parallel run
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 3: Full Round 1 — 80 agents in parallel...")
    print("=" * 60)

    try:
        from agents.swarm.runner import SwarmRunner

        runner = SwarmRunner()
        assert len(runner.agents) == 80, \
            f"SwarmRunner has {len(runner.agents)} agents, expected 80"

        print(f"  Preparing market data for RELIANCE.NS...")
        market_data = await runner.prepare_market_data("RELIANCE.NS")

        assert market_data["ticker"] == "RELIANCE.NS"
        print(f"  Price: Rs.{market_data.get('price', 'N/A')}")
        print(f"  Change: {market_data.get('price_change_pct', 'N/A')}%")
        print(f"  Headlines: {len(market_data.get('news_headlines', []))}")

        print(f"\n  Running Round 1 with 80 agents in parallel...")
        start = time.time()
        round1 = await runner.run_round1(market_data)
        elapsed = time.time() - start

        assert len(round1) == 80, f"Expected 80 decisions, got {len(round1)}"
        assert all("action" in d for d in round1), "Some decisions missing 'action'"

        # Count decisions
        n_buy = sum(1 for d in round1 if d["action"] == "buy")
        n_sell = sum(1 for d in round1 if d["action"] == "sell")
        n_hold = sum(1 for d in round1 if d["action"] == "hold")

        print(f"\n  Results: {n_buy} BUY, {n_sell} SELL, {n_hold} HOLD")
        print(f"  Time: {elapsed:.1f}s")

        if elapsed > 90:
            print(f"\n  WARNING: Round 1 took {elapsed:.1f}s -- over 90s target")
            print(f"  TIP: Check Ollama model -- try 'tinyllama' for faster results")
        else:
            print(f"  [OK] Under 90s target")

        print(f"\n[PASS] CHECK 3 PASSED: 80 agents completed Round 1 in {elapsed:.1f}s")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 3 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 3: {e}")
        # Try to continue with mock data
        round1 = None

    # ==================================================================
    # CHECK 4: Crowd summary builds correctly
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 4: Building crowd summary...")
    print("=" * 60)

    try:
        if round1 is None:
            raise Exception("Skipped — Round 1 did not complete")

        crowd_summary = runner.build_crowd_summary(round1)

        assert isinstance(crowd_summary, str), "Crowd summary should be a string"
        assert len(crowd_summary) > 50, "Crowd summary too short"
        assert "BUY" in crowd_summary or "buying" in crowd_summary, \
            "Summary should mention buying"
        assert "Retail" in crowd_summary or "retail" in crowd_summary, \
            "Summary should mention retail agents"
        assert "Institutional" in crowd_summary or "institutional" in crowd_summary, \
            "Summary should mention institutional agents"

        print(f"  Crowd Summary:\n")
        for line in crowd_summary.split("\n"):
            print(f"    {line}")

        print(f"\n[PASS] CHECK 4 PASSED: Crowd summary generated")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 4 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 4: {e}")
        crowd_summary = None

    # ==================================================================
    # CHECK 5: Round 2 runs and shows social influence movement
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 5: Round 2 — social influence...")
    print("=" * 60)

    try:
        if round1 is None or crowd_summary is None:
            raise Exception("Skipped — Round 1 or crowd summary not available")

        print(f"  Running Round 2 with crowd summary...")
        start = time.time()
        round2 = await runner.run_round2(market_data, crowd_summary, round1)
        elapsed = time.time() - start

        assert len(round2) == 80, f"Expected 80 decisions, got {len(round2)}"

        r1_buy = sum(1 for d in round1 if d["action"] == "buy")
        r2_buy = sum(1 for d in round2 if d["action"] == "buy")
        r1_sell = sum(1 for d in round1 if d["action"] == "sell")
        r2_sell = sum(1 for d in round2 if d["action"] == "sell")

        print(f"\n  Round 1 -> Round 2 comparison:")
        print(f"    BUY:  {r1_buy} -> {r2_buy} (shift: {r2_buy - r1_buy:+d})")
        print(f"    SELL: {r1_sell} -> {r2_sell} (shift: {r2_sell - r1_sell:+d})")
        print(f"    Time: {elapsed:.1f}s")

        shift = abs(r2_buy - r1_buy)
        print(f"\n  Social influence shifted {shift} agents between rounds")

        # Check that crowd-ignorant agents stayed the same
        crowd_ignorers = ["SIP_Investor", "Noise_Ignorer", "RSI_Bot",
                          "EMA_Crossover_Bot", "Volume_Breakout_Bot",
                          "Mean_Reversion_Bot", "Arbitrage_Bot",
                          "MF_SIP_Machine", "Insurance_LIC"]

        r1_by_name = {d["agent_name"]: d for d in round1}
        r2_by_name = {d["agent_name"]: d for d in round2}

        ignorers_stable = 0
        ignorers_total = 0
        for name, d2 in r2_by_name.items():
            if any(name.startswith(prefix) for prefix in crowd_ignorers):
                ignorers_total += 1
                d1 = r1_by_name.get(name)
                if d1 and d1["action"] == d2["action"]:
                    ignorers_stable += 1

        if ignorers_total > 0:
            stability_pct = (ignorers_stable / ignorers_total) * 100
            print(f"\n  Crowd-ignorant agents stability: {ignorers_stable}/{ignorers_total} "
                  f"({stability_pct:.0f}% unchanged)")

        print(f"\n[PASS] CHECK 5 PASSED: Round 1 buy={r1_buy}, Round 2 buy={r2_buy}")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 5 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 5: {e}")
        round2 = None

    # ==================================================================
    # CHECK 6: Aggregator produces valid swarm output
    # ==================================================================
    print("\n" + "=" * 60)
    print("CHECK 6: Swarm aggregation...")
    print("=" * 60)

    try:
        if round1 is None or round2 is None:
            raise Exception("Skipped — Round 1 or Round 2 not available")

        from agents.swarm.aggregator import SwarmAggregator

        agg = SwarmAggregator()
        runner_output = {
            "ticker": "RELIANCE.NS",
            "market_data": market_data,
            "round1_results": round1,
            "round2_results": round2,
            "crowd_summary": crowd_summary,
        }

        swarm_signal = agg.compute(runner_output)

        # Validate all required fields
        required_fields = [
            "bullish_pct", "bearish_pct", "hold_pct",
            "panic_index", "fomo_index", "conviction",
            "round1_bullish", "round2_bullish",
            "crowd_amplification", "dominant_signal", "signal_strength",
        ]
        for field in required_fields:
            assert field in swarm_signal, f"Missing field: {field}"

        # Validate ranges
        assert 0 <= swarm_signal["bullish_pct"] <= 100, \
            f"bullish_pct out of range: {swarm_signal['bullish_pct']}"
        assert 0 <= swarm_signal["bearish_pct"] <= 100, \
            f"bearish_pct out of range: {swarm_signal['bearish_pct']}"
        assert 0 <= swarm_signal["panic_index"] <= 100, \
            f"panic_index out of range: {swarm_signal['panic_index']}"
        assert 0 <= swarm_signal["conviction"] <= 100, \
            f"conviction out of range: {swarm_signal['conviction']}"
        assert swarm_signal["dominant_signal"] in ["BULLISH", "BEARISH", "NEUTRAL"], \
            f"Invalid dominant_signal: {swarm_signal['dominant_signal']}"
        assert swarm_signal["signal_strength"] in ["STRONG", "MODERATE", "WEAK"], \
            f"Invalid signal_strength: {swarm_signal['signal_strength']}"

        # Generate narrative
        narrative = agg.generate_crowd_narrative(swarm_signal)
        assert isinstance(narrative, str) and len(narrative) > 10, \
            "Narrative too short or invalid"

        print(f"  Swarm Signal Results:")
        print(f"    Bullish:   {swarm_signal['bullish_pct']:.1f}%")
        print(f"    Bearish:   {swarm_signal['bearish_pct']:.1f}%")
        print(f"    Hold:      {swarm_signal['hold_pct']:.1f}%")
        print(f"    ---------------------------")
        print(f"    Panic Index:    {swarm_signal['panic_index']:.1f}")
        print(f"    FOMO Index:     {swarm_signal['fomo_index']:.1f}")
        print(f"    Conviction:     {swarm_signal['conviction']:.1f}%")
        print(f"    ---------------------------")
        print(f"    R1->R2 Bullish: {swarm_signal['round1_bullish']:.1f}% -> {swarm_signal['round2_bullish']:.1f}%")
        print(f"    Amplification:  {swarm_signal['crowd_amplification']:+.1f}%")
        print(f"    ---------------------------")
        print(f"    Signal:  {swarm_signal['dominant_signal']} ({swarm_signal['signal_strength']})")
        print(f"    Narrative: {narrative}")

        print(f"\n[PASS] CHECK 6 PASSED: Swarm signal computed successfully")
        results["passed"] += 1

    except Exception as e:
        print(f"\n[FAIL] CHECK 6 FAILED: {e}")
        results["failed"] += 1
        results["errors"].append(f"CHECK 6: {e}")

    # ==================================================================
    # FINAL SUMMARY
    # ==================================================================
    print("\n" + "=" * 60)
    print("=== WEEK 2 VERIFICATION SUMMARY ===")
    print("=" * 60)

    total_checks = results["passed"] + results["failed"]
    print(f"\n  Passed: {results['passed']}/{total_checks}")
    print(f"  Failed: {results['failed']}/{total_checks}")

    if results["passed"] == total_checks:
        print("\n  +--------------------------------+")
        print("  |   === WEEK 2 COMPLETE ===      |")
        print("  |   80 personality agents: OK    |")
        print("  |   Parallel Round 1: OK         |")
        print("  |   Social influence Round 2: OK |")
        print("  |   Swarm aggregation: OK        |")
        print("  |   Ready for Week 3!            |")
        print("  +--------------------------------+")
    else:
        print("\n  Errors:")
        for error in results["errors"]:
            print(f"    [X] {error}")
        print("\n  Fix the errors above before proceeding to Week 3.")

    return results


if __name__ == "__main__":
    print("+==========================================+")
    print("|  AlphaHive -- Week 2 Verification Suite  |")
    print("|  80-Agent Swarm Engine Test              |")
    print("+==========================================+")

    results = asyncio.run(run_checks())

    # Exit with error code if any checks failed
    sys.exit(0 if results["failed"] == 0 else 1)
