class Scorer:
    def compute(self, debate_output: dict, orchestrator_output: dict) -> dict:
        """
        Computes the final AlphaHive signal from debate + orchestrator outputs.
        Returns the "signal" section of AlphaHiveSignal.
        """
        
        verdict = debate_output.get("final_verdict") or {}
        swarm = orchestrator_output.get("swarm", {})
        specialists = orchestrator_output.get("specialists", {})
        risk_score = debate_output.get("risk_score", 50)
        invalidation_conditions = debate_output.get("invalidation_conditions", [])
        key_risks = debate_output.get("key_risks", [])
        
        # --- BULLISH PROBABILITY ---
        # Start with the risk manager's stated probability
        base_prob = verdict.get("bullish_probability", 50)
        
        # Adjust based on agreement between layers
        agreement = orchestrator_output.get("signal_preview", {}).get("agreement", "NEUTRAL")
        
        if "STRONG_AGREEMENT_BULLISH" in agreement:
            base_prob = min(95, base_prob + 8)
        elif "STRONG_AGREEMENT_BEARISH" in agreement:
            base_prob = max(5, base_prob - 8)
        elif "DIVERGENCE" in agreement:
            # Pull toward 50 when layers disagree
            base_prob = base_prob * 0.85 + 50 * 0.15
        
        # Cap extremes — never say 100% or 0% (markets are uncertain)
        bullish_probability = round(max(5, min(95, base_prob)))
        
        # --- RISK LEVEL ---
        # Start with risk manager verdict, validate against metrics
        risk_level = verdict.get("risk_level", "MEDIUM")
        
        # Override rules (hard rules that always apply)
        # Risk score from dedicated risk analyst takes precedence
        if risk_score > 75:
            risk_level = "HIGH"  # Elevated risk from analyst assessment
        elif risk_score > 60 and risk_level == "LOW":
            risk_level = "MEDIUM"  # Upgrade from low if notable risks identified
        
        if orchestrator_output.get("signal_preview", {}).get("alert"):
            # Any high-priority alert = at least MEDIUM risk
            if risk_level == "LOW":
                risk_level = "MEDIUM"
        
        if swarm.get("panic_index", 0) > 70:
            risk_level = "HIGH"  # Widespread panic = always high risk
        
        if swarm.get("conviction", 100) < 40:
            # Low conviction swarm = uncertain = at least MEDIUM
            if risk_level == "LOW":
                risk_level = "MEDIUM"
        
        # --- CONFIDENCE ---
        confidence = verdict.get("confidence", "MEDIUM")
        
        # Downgrade confidence if specialist data was missing
        specialist_errors = sum(
            1 for name in ["fundamental", "technical", "sentiment", "news"]
            if "error" in specialists.get(name, {})
        )
        if specialist_errors >= 2:
            confidence = "LOW"  # Too much data missing to be confident
        
        # Also downgrade if risk is very high and invalidation conditions exist
        if risk_score > 75 and invalidation_conditions:
            if confidence == "HIGH":
                confidence = "MEDIUM"
        
        # --- FINAL CALL ---
        # Derive from bullish_probability (not from LLM verdict directly)
        # This ensures consistency: the call always matches the probability
        if bullish_probability >= 60:
            final_call = "BULLISH"
        elif bullish_probability <= 40:
            final_call = "BEARISH"
        else:
            final_call = "NEUTRAL"
        
        # --- SCORES BREAKDOWN ---
        scores = {
            "swarm_bullish_pct": round(swarm.get("bullish_pct", 50), 1),
            "fundamental_score": specialists.get("fundamental", {}).get("score", 50),
            "technical_score": specialists.get("technical", {}).get("score", 50),
            "sentiment_score": specialists.get("sentiment", {}).get("score", 50),
            "news_score": specialists.get("news", {}).get("score", 50),
            "combined_specialist_score": round(specialists.get("combined_score", 50), 1),
            "bull_case_score": round(debate_output.get("bull_score", 50), 1),
            "bear_case_score": round(debate_output.get("bear_score", 50), 1),
            "risk_score": round(risk_score, 1),
        }
        
        return {
            "final_call": final_call,
            "bullish_probability": bullish_probability,
            "risk_level": risk_level,
            "confidence": confidence,
            "deciding_factor": verdict.get("deciding_factor", ""),
            "key_risk": verdict.get("key_risk", ""),
            "key_risks": key_risks,
            "invalidation_conditions": invalidation_conditions,
            "risk_assessment": debate_output.get("risk_assessment", ""),
            "scores": scores,
            "agreement_type": agreement,
        }
