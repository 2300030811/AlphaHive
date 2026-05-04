"""
AlphaHive — Swarm Aggregator
===============================
Takes the raw output from SwarmRunner (80 agent decisions across 2 rounds)
and computes the final swarm signal metrics:

  - bullish_pct / bearish_pct / hold_pct (weighted)
  - panic_index  — % of panic-type agents selling
  - fomo_index   — % of FOMO agents buying + upgraded confidence
  - conviction   — how stable agents were between rounds
  - crowd_amplification — did social influence help or hurt
  - dominant_signal / signal_strength

Also generates a plain-English crowd narrative (no LLM — pure logic).

For educational purposes only. Not investment advice.
AlphaHive is not SEBI-registered. All trading decisions are your own.
"""

import logging

logger = logging.getLogger("alphahive.agents.swarm.aggregator")

# Agent name prefixes for panic-type identification
PANIC_AGENT_PREFIXES = ("Panic_Seller", "Bad_News_Overreactor", "Zerodha_Newbie")

# Agent name prefixes for FOMO-type identification
FOMO_AGENT_PREFIXES = ("FOMO_Buyer", "Good_News_Chaser")


class SwarmAggregator:
    """
    Computes the final swarm signal metrics from raw runner output.

    Input:  SwarmRunner.run() output dict
    Output: The "swarm" section of AlphaHiveSignal
    """

    def compute(self, runner_output: dict) -> dict:
        """
        Compute all swarm metrics from the runner's raw output.

        Args:
            runner_output: Dict from SwarmRunner.run() containing:
                - round1_results: list of 80 dicts
                - round2_results: list of 80 dicts

        Returns:
            Swarm signal dict matching AlphaHiveSignal.swarm format
        """
        round1 = runner_output.get("round1_results", [])
        round2 = runner_output.get("round2_results", [])

        if not round2:
            logger.warning("No Round 2 results — using Round 1 as final")
            round2 = round1

        # 1-3. Weighted bullish / bearish / hold percentages (Round 2)
        bullish_pct = self._weighted_action_pct(round2, "buy")
        bearish_pct = self._weighted_action_pct(round2, "sell")
        hold_pct = self._weighted_action_pct(round2, "hold")

        # Normalize to exactly 100% (floating point rounding)
        total = bullish_pct + bearish_pct + hold_pct
        if total > 0:
            bullish_pct = round((bullish_pct / total) * 100, 1)
            bearish_pct = round((bearish_pct / total) * 100, 1)
            hold_pct = round(100.0 - bullish_pct - bearish_pct, 1)

        # 4. Panic Index — % of panic-type agents selling in Round 2
        panic_index = self._compute_panic_index(round2)

        # 5. FOMO Index — % of FOMO agents buying + who upgraded R1→R2
        fomo_index = self._compute_fomo_index(round1, round2)

        # 6. Conviction — stability between Round 1 and Round 2
        conviction = self._compute_conviction(round1, round2)

        # 7-8. Round 1 vs Round 2 bullish comparison
        round1_bullish = self._weighted_action_pct(round1, "buy")
        round2_bullish = bullish_pct  # already computed

        # Normalize round1_bullish
        r1_total = (
            self._weighted_action_pct(round1, "buy")
            + self._weighted_action_pct(round1, "sell")
            + self._weighted_action_pct(round1, "hold")
        )
        if r1_total > 0:
            round1_bullish = round((round1_bullish / r1_total) * 100, 1)

        # Crowd amplification: positive = crowd amplified bullishness
        crowd_amplification = round(round2_bullish - round1_bullish, 1)

        # Dominant signal
        dominant_signal = self._determine_dominant_signal(bullish_pct, bearish_pct)

        # Signal strength
        signal_strength = self._determine_signal_strength(
            bullish_pct, bearish_pct, conviction
        )

        result = {
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "hold_pct": hold_pct,
            "panic_index": panic_index,
            "fomo_index": fomo_index,
            "conviction": conviction,
            "round1_bullish": round1_bullish,
            "round2_bullish": round2_bullish,
            "crowd_amplification": crowd_amplification,
            "dominant_signal": dominant_signal,
            "signal_strength": signal_strength,
            "influence_edges": runner_output.get("influence_edges", []),
        }
        result["crowd_narrative"] = self.generate_crowd_narrative(result)

        logger.info(
            f"Swarm signal: {dominant_signal} ({signal_strength}) — "
            f"bull={bullish_pct}%, bear={bearish_pct}%, "
            f"panic={panic_index}, conviction={conviction}%"
        )

        return result

    # -------------------------------------------------------------------
    # Weighted action percentage
    # -------------------------------------------------------------------
    def _weighted_action_pct(
        self, decisions: list[dict], action: str
    ) -> float:
        """
        Compute the weighted percentage of agents choosing a given action.

        Uses agent weight to give institutional/experienced agents more
        influence in the final signal.
        """
        total_weight = sum(d.get("weight", 1.0) for d in decisions)
        if total_weight == 0:
            return 0.0

        action_weight = sum(
            d.get("weight", 1.0)
            for d in decisions
            if d.get("action") == action
        )
        return (action_weight / total_weight) * 100

    # -------------------------------------------------------------------
    # Panic Index
    # -------------------------------------------------------------------
    def _compute_panic_index(self, round2: list[dict]) -> float:
        """
        Compute panic index — weighted % of panic-type agents selling.

        Panic agents: PanicSeller, BadNewsOverreactor, ZerodhaNewbie (partial).
        Scale: 0 (no panic) to 100 (maximum panic).
        """
        panic_agents = [
            d for d in round2
            if any(d.get("agent_name", "").startswith(p) for p in PANIC_AGENT_PREFIXES)
        ]

        if not panic_agents:
            return 0.0

        total_weight = sum(d.get("weight", 1.0) for d in panic_agents)
        sell_weight = sum(
            d.get("weight", 1.0)
            for d in panic_agents
            if d.get("action") == "sell"
        )

        if total_weight == 0:
            return 0.0

        return round((sell_weight / total_weight) * 100, 1)

    # -------------------------------------------------------------------
    # FOMO Index
    # -------------------------------------------------------------------
    def _compute_fomo_index(
        self, round1: list[dict], round2: list[dict]
    ) -> float:
        """
        Compute FOMO index:
          - % of FOMO-type agents buying in Round 2
          - Bonus for agents who upgraded (hold→buy or sell→buy) from R1→R2

        FOMO agents: FOMOBuyer, GoodNewsChaser.
        """
        fomo_r2 = [
            d for d in round2
            if any(d.get("agent_name", "").startswith(p) for p in FOMO_AGENT_PREFIXES)
        ]

        if not fomo_r2:
            return 0.0

        # Build lookup for round 1 decisions
        r1_actions = {
            d.get("agent_name"): d.get("action") for d in round1
        }

        total_weight = sum(d.get("weight", 1.0) for d in fomo_r2)
        if total_weight == 0:
            return 0.0

        # Count FOMO agents buying + upgraded
        fomo_buy_weight = 0.0
        upgrade_bonus = 0.0
        for d in fomo_r2:
            if d.get("action") == "buy":
                fomo_buy_weight += d.get("weight", 1.0)

                # Check if they upgraded from R1
                r1_action = r1_actions.get(d.get("agent_name"), "hold")
                if r1_action != "buy":
                    # Upgraded! Extra weight for FOMO momentum
                    upgrade_bonus += d.get("weight", 1.0) * 0.5

        base_fomo = (fomo_buy_weight / total_weight) * 100
        upgrade_pct = (upgrade_bonus / total_weight) * 100

        # Combined FOMO index (capped at 100)
        return round(min(base_fomo + upgrade_pct, 100.0), 1)

    # -------------------------------------------------------------------
    # Conviction Score
    # -------------------------------------------------------------------
    def _compute_conviction(
        self, round1: list[dict], round2: list[dict]
    ) -> float:
        """
        Compute conviction — how stable was the crowd signal.

        For each agent: did they change action from Round 1 → Round 2?
        High conviction = few agents changed = strong signal.
        Low conviction = many agents changed = uncertain signal.

        Returns:
            0-100 scale (100 = no agents changed = max conviction)
        """
        if not round1 or not round2:
            return 50.0

        # Build lookup: agent_name → Round 1 action
        r1_actions = {
            d.get("agent_name"): d.get("action") for d in round1
        }

        total_agents = len(round2)
        changed = 0

        for d in round2:
            agent_name = d.get("agent_name")
            r2_action = d.get("action")
            r1_action = r1_actions.get(agent_name)

            if r1_action and r1_action != r2_action:
                changed += 1

        if total_agents == 0:
            return 50.0

        conviction = ((total_agents - changed) / total_agents) * 100
        return round(conviction, 1)

    # -------------------------------------------------------------------
    # Dominant Signal
    # -------------------------------------------------------------------
    def _determine_dominant_signal(
        self, bullish_pct: float, bearish_pct: float
    ) -> str:
        """
        Determine the dominant signal.

        - BULLISH if bullish_pct > 60
        - BEARISH if bearish_pct > 60
        - NEUTRAL otherwise
        """
        if bullish_pct > 60:
            return "BULLISH"
        elif bearish_pct > 60:
            return "BEARISH"
        return "NEUTRAL"

    # -------------------------------------------------------------------
    # Signal Strength
    # -------------------------------------------------------------------
    def _determine_signal_strength(
        self,
        bullish_pct: float,
        bearish_pct: float,
        conviction: float,
    ) -> str:
        """
        Determine signal strength based on conviction + directional %.

        - STRONG if conviction > 80 AND direction > 65%
        - MODERATE if conviction > 60
        - WEAK otherwise
        """
        max_direction = max(bullish_pct, bearish_pct)

        if conviction > 80 and max_direction > 65:
            return "STRONG"
        elif conviction > 60:
            return "MODERATE"
        return "WEAK"

    # -------------------------------------------------------------------
    # Crowd Narrative (no LLM — pure logic)
    # -------------------------------------------------------------------
    def generate_crowd_narrative(self, swarm_output: dict) -> str:
        """
        Generate a plain-English sentence describing crowd behavior.

        Uses the computed metrics to template narratives.
        No LLM calls — pure deterministic logic.

        Args:
            swarm_output: Dict from self.compute()

        Returns:
            A single human-readable sentence about the crowd
        """
        bullish = swarm_output.get("bullish_pct", 50)
        bearish = swarm_output.get("bearish_pct", 50)
        panic = swarm_output.get("panic_index", 0)
        fomo = swarm_output.get("fomo_index", 0)
        conviction = swarm_output.get("conviction", 50)
        amplification = swarm_output.get("crowd_amplification", 0)
        signal = swarm_output.get("dominant_signal", "NEUTRAL")

        parts = []

        # Core direction
        if signal == "BULLISH":
            if bullish > 75:
                parts.append("Overwhelming bullish consensus across the swarm")
            else:
                parts.append("Bullish leaning from the majority of agents")
        elif signal == "BEARISH":
            if bearish > 75:
                parts.append("Strong bearish consensus across agents")
            else:
                parts.append("Bearish leaning with selling pressure")
        else:
            parts.append("Mixed signals — no clear directional consensus")

        # Panic narrative
        if panic > 70:
            parts.append("widespread retail panic selling")
        elif panic > 40:
            parts.append("moderate retail anxiety")
        elif panic < 15:
            parts.append("retail panic very low")

        # FOMO narrative
        if fomo > 70:
            parts.append("high FOMO momentum chasing detected")
        elif fomo > 40:
            parts.append("moderate momentum chasing")

        # Conviction narrative
        if conviction > 85:
            parts.append("with very high conviction (agents barely changed between rounds)")
        elif conviction > 70:
            parts.append("with solid conviction")
        elif conviction < 50:
            parts.append("conviction is low — significant opinion shifts between rounds")

        # Amplification narrative
        if amplification > 5:
            parts.append("crowd amplified the bullish signal")
        elif amplification < -5:
            parts.append("crowd dampened initial bullishness")

        # Join with appropriate connectors
        if len(parts) == 1:
            return f"{parts[0]}."
        elif len(parts) == 2:
            return f"{parts[0]}, {parts[1]}."
        else:
            # First part as main sentence, rest as details
            main = parts[0]
            details = ", ".join(parts[1:])
            return f"{main} — {details}."
