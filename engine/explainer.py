class Explainer:
    def generate(self, ticker: str, scorer_output: dict, debate_output: dict, orchestrator_output: dict) -> dict:
        """
        Generates the 3-line explanation for any AlphaHive signal.
        Returns the "explanation" section of AlphaHiveSignal.
        """
        signal = scorer_output
        swarm = orchestrator_output.get("swarm", {})
        specs = orchestrator_output.get("specialists", {})
        quality = orchestrator_output.get("quality", {})
        
        line1 = self._generate_line1(ticker, signal, orchestrator_output)
        line2 = self._generate_line2(signal, specs, debate_output)
        line3 = self._generate_line3(swarm, signal)
        
        return {
            "line1": line1,
            "line2": line2,
            "line3": line3,
            "full_text": f"{line1} {line2} {line3}",
            "bull_case": debate_output.get("bull_case", ""),
            "bear_case": debate_output.get("bear_case", ""),
            "deciding_factor": signal.get("deciding_factor", ""),
            "trust_summary": quality.get("research_quality", {}).get("summary", ""),
            "top_conflicts": [
                item.get("title", "")
                for item in quality.get("conflicts", [])[:3]
            ],
            "evidence_facts": quality.get("evidence", {}).get("facts", [])[:5],
        }

    def _generate_line1(self, ticker: str, signal: dict, orchestrator_output: dict) -> str:
        """
        Line 1: The headline — what is the verdict and how strong.
        Format: "{Company} is {prob}% bullish with {confidence} conviction."
        OR: "{Company} shows bearish signals at {prob}% with {risk} risk."
        """
        company = orchestrator_output.get("company", ticker.replace(".NS", ""))
        prob = signal.get("bullish_probability", 50)
        call = signal.get("final_call", "NEUTRAL")
        conf = signal.get("confidence", "MEDIUM")
        risk = signal.get("risk_level", "MEDIUM")
        
        if call == "BULLISH":
            conf_phrase = {
                "HIGH": "high conviction",
                "MEDIUM": "moderate conviction",
                "LOW": "low conviction — use caution"
            }.get(conf, "moderate conviction")
            return f"{company} is {prob}% bullish with {conf_phrase}."
        
        elif call == "BEARISH":
            bear_prob = 100 - prob
            risk_phrase = {
                "HIGH": "elevated risk",
                "MEDIUM": "moderate risk",
                "LOW": "manageable risk"
            }.get(risk, "moderate risk")
            return f"{company} shows bearish signals at {bear_prob}% with {risk_phrase}."
        
        else:  # NEUTRAL
            return (f"{company} shows mixed signals at {prob}% bullish. "
                    f"No clear directional edge currently.")

    def _generate_line2(self, signal: dict, specs: dict, debate_output: dict) -> str:
        """
        Line 2: The facts — what the specialist data shows.
        References actual numbers from fundamental and technical reports.
        """
        fund = specs.get("fundamental", {})
        tech = specs.get("technical", {})
        sent = specs.get("sentiment", {})
        
        mentions = []
        
        # Fundamental signals
        derived = fund.get("derived", {})
        pe_vs_sector = derived.get("pe_vs_sector")
        if pe_vs_sector == "cheap":
            mentions.append("PE below sector average")
        elif pe_vs_sector == "expensive":
            mentions.append("PE above sector average")
        
        earnings_trend = derived.get("earnings_trend")
        if earnings_trend == "improving":
            eps_growth = fund.get("raw_data", {}).get("eps_growth_yoy")
            if eps_growth is not None:
                mentions.append(f"EPS +{eps_growth * 100 if eps_growth < 10 else eps_growth:.0f}% YoY")
            else:
                mentions.append("improving earnings trend")
        elif earnings_trend == "declining":
            mentions.append("declining earnings trend")
        
        # Technical signals
        indicators = tech.get("indicators", {})
        rsi = indicators.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                mentions.append(f"RSI {rsi:.0f} (oversold territory)")
            elif rsi > 70:
                mentions.append(f"RSI {rsi:.0f} (overbought — watch carefully)")
            elif 45 <= rsi <= 65:
                mentions.append(f"RSI {rsi:.0f} (healthy momentum zone)")
        
        trend = indicators.get("trend_structure")
        if trend == "uptrend":
            mentions.append("price in confirmed uptrend")
        elif trend == "downtrend":
            mentions.append("price in downtrend structure")
        
        vol_ratio = indicators.get("volume_ratio")
        if vol_ratio is not None and vol_ratio > 1.5:
            mentions.append(f"volume {vol_ratio:.1f}x above average")
        
        golden = indicators.get("golden_cross")
        death = indicators.get("death_cross")
        if golden:
            mentions.append("golden cross recently formed")
        elif death:
            mentions.append("death cross recently formed — bearish signal")
        
        # Sentiment
        sent_verdict = sent.get("verdict")
        if sent_verdict == "POSITIVE":
            mentions.append("positive news sentiment")
        elif sent_verdict == "NEGATIVE":
            mentions.append("negative news sentiment")
        
        deciding = signal.get("deciding_factor")
        
        if mentions:
            top_mentions = mentions[:3]
            facts_str = ", ".join(top_mentions) + "."
            if deciding:
                return f"Key factors: {facts_str} {deciding}"
            return f"Key factors: {facts_str}"
        else:
            if fund.get("summary"):
                return f"Fundamentals: {fund['summary']}"
            return "Specialist analysis completed. See full report for details."

    def _generate_line3(self, swarm: dict, signal: dict) -> str:
        """
        Line 3: The crowd — what the swarm simulation shows.
        This is AlphaHive's unique differentiator. Always reference specific numbers.
        """
        bullish_pct = swarm.get("bullish_pct", 50)
        panic = swarm.get("panic_index", 0)
        fomo = swarm.get("fomo_index", 0)
        conviction = swarm.get("conviction", 50)
        crowd_narrative = swarm.get("crowd_narrative", "")
        
        # Panic description
        if panic > 60:
            panic_phrase = f"Retail panic elevated at {panic:.0f}% — crowd fear is high."
        elif panic > 35:
            panic_phrase = f"Moderate retail panic at {panic:.0f}%."
        else:
            panic_phrase = f"Retail panic low at {panic:.0f}% — crowd is calm."
        
        # FOMO description  
        if fomo > 60:
            fomo_phrase = f"FOMO buying strong at {fomo:.0f}% — momentum chasers active."
        elif fomo > 35:
            fomo_phrase = ""
        else:
            fomo_phrase = ""
        
        # Conviction description
        if conviction > 80:
            conv_phrase = f"High crowd conviction ({conviction:.0f}%)."
        elif conviction < 40:
            conv_phrase = f"Low crowd conviction ({conviction:.0f}%) — uncertain signal."
        else:
            conv_phrase = ""
        
        # Divergence check
        agreement = signal.get("agreement_type", "")
        if "DIVERGENCE" in agreement:
            if "SWARM_BULLISH" in agreement:
                return (f"Crowd simulation shows {bullish_pct:.0f}% bullish "
                        f"but specialist data is cautious — divergence detected. "
                        f"{panic_phrase} Verify before acting.")
            else:
                return (f"Crowd simulation cautious at {bullish_pct:.0f}% bullish "
                        f"but specialist data is positive — divergence detected. "
                        f"Fundamentals may not yet be reflected in crowd behavior.")
        
        parts = [
            f"Crowd simulation: {bullish_pct:.0f}% of market participants bullish.",
            panic_phrase,
            fomo_phrase,
            conv_phrase,
        ]
        
        if crowd_narrative and len(crowd_narrative) > 20:
            parts.append(crowd_narrative)
        
        return " ".join(p for p in parts if p).strip()
