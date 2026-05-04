"""
AlphaHive — Swarm Engine Package
==================================
The 80-agent swarm simulation layer.

Usage:
    from agents.swarm.runner import SwarmRunner
    from agents.swarm.aggregator import SwarmAggregator

    runner = SwarmRunner()
    result = await runner.run("RELIANCE.NS")
    signal = SwarmAggregator().compute(result)
"""
