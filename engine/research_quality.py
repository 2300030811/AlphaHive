import math
from datetime import datetime, timezone
from typing import Any


class ResearchQualityAnalyzer:
    """
    Deterministic audit layer for AlphaHive signals.

    This does not decide the market call. It explains how much trust the
    generated signal deserves, where the evidence came from, and which
    cross-layer conflicts a retail investor should notice before reading
    the plain-English summary.
    """

    COMPONENT_WEIGHTS = {
        "data_freshness": 0.20,
        "data_completeness": 0.25,
        "layer_agreement": 0.20,
        "swarm_stability": 0.20,
        "event_risk": 0.10,
        "backtest_support": 0.05,
    }

    def evaluate(
        self,
        ticker: str,
        orchestrator_output: dict,
        debate_output: dict,
        signal: dict,
    ) -> dict:
        specialists = orchestrator_output.get("specialists", {})
        swarm = orchestrator_output.get("swarm", {})

        evidence = self._build_evidence(ticker, orchestrator_output)
        conflicts = self._detect_conflicts(swarm, specialists, debate_output, signal)
        risk_notes = self._build_risk_notes(specialists, swarm, signal, conflicts)
        research_quality = self._compute_research_quality(
            specialists=specialists,
            swarm=swarm,
            signal=signal,
            evidence=evidence,
            conflicts=conflicts,
        )

        return {
            "research_quality": research_quality,
            "conflicts": conflicts,
            "evidence": evidence,
            "risk_notes": risk_notes,
        }

    def _compute_research_quality(
        self,
        specialists: dict,
        swarm: dict,
        signal: dict,
        evidence: dict,
        conflicts: list[dict],
    ) -> dict:
        components = {
            "data_freshness": self._score_data_freshness(specialists, evidence),
            "data_completeness": self._score_data_completeness(specialists),
            "layer_agreement": self._score_layer_agreement(signal),
            "swarm_stability": self._bounded(swarm.get("conviction", 50)),
            "event_risk": self._score_event_risk(specialists, swarm),
            "backtest_support": 50.0,
        }

        weighted_score = sum(
            components[name] * self.COMPONENT_WEIGHTS[name]
            for name in self.COMPONENT_WEIGHTS
        )

        high_conflicts = sum(1 for item in conflicts if item["severity"] == "HIGH")
        medium_conflicts = sum(1 for item in conflicts if item["severity"] == "MEDIUM")
        conflict_penalty = high_conflicts * 8 + medium_conflicts * 4
        overall_score = round(self._bounded(weighted_score - conflict_penalty), 1)

        return {
            "trust_score": overall_score,
            "trust_label": self._label(overall_score),
            "component_scores": {k: round(v, 1) for k, v in components.items()},
            "summary": self._quality_summary(overall_score, conflicts),
            "limitations": [
                "Backtest support is not connected yet, so historical edge is not included in the trust score.",
                "News and fundamentals depend on the availability and freshness of upstream public data sources.",
            ],
        }

    def _score_data_freshness(self, specialists: dict, evidence: dict) -> float:
        timestamps = []
        for name in ["fundamental", "technical", "sentiment", "news"]:
            parsed = self._parse_timestamp(specialists.get(name, {}).get("timestamp"))
            if parsed:
                timestamps.append(parsed)

        if not timestamps:
            return 45.0

        newest = max(timestamps)
        oldest = min(timestamps)
        evidence["freshness"] = {
            "newest_timestamp": newest.isoformat(),
            "oldest_timestamp": oldest.isoformat(),
            "max_age_hours": round(
                (datetime.now(timezone.utc) - oldest).total_seconds() / 3600,
                2,
            ),
        }

        max_age_hours = evidence["freshness"]["max_age_hours"]
        if max_age_hours <= 6:
            return 92.0
        if max_age_hours <= 24:
            return 78.0
        if max_age_hours <= 72:
            return 58.0
        return 35.0

    def _score_data_completeness(self, specialists: dict) -> float:
        expected = ["fundamental", "technical", "sentiment", "news"]
        non_error = sum(1 for name in expected if "error" not in specialists.get(name, {}))

        raw_fields = [
            specialists.get("fundamental", {}).get("raw_data", {}).get("pe_ratio"),
            specialists.get("fundamental", {}).get("raw_data", {}).get("eps_growth_yoy"),
            specialists.get("fundamental", {}).get("raw_data", {}).get("sector_avg_pe"),
            specialists.get("technical", {}).get("indicators", {}).get("rsi_14"),
            specialists.get("technical", {}).get("indicators", {}).get("ema_50"),
            specialists.get("technical", {}).get("indicators", {}).get("trend_structure"),
            specialists.get("sentiment", {}).get("headlines_analyzed"),
            specialists.get("news", {}).get("headlines_analyzed"),
        ]
        populated = sum(1 for value in raw_fields if self._has_value(value))

        return self._bounded((non_error / len(expected)) * 55 + (populated / len(raw_fields)) * 45)

    def _score_layer_agreement(self, signal: dict) -> float:
        agreement = signal.get("agreement_type", "")
        if "STRONG_AGREEMENT" in agreement:
            return 90.0
        if "DIVERGENCE" in agreement:
            return 42.0
        return 62.0

    def _score_event_risk(self, specialists: dict, swarm: dict) -> float:
        news = specialists.get("news", {})
        alert = str(news.get("alert") or "").lower()
        news_score = self._number(news.get("score"), 50)
        panic = self._number(swarm.get("panic_index"), 0)

        score = 85.0
        if "high risk" in alert:
            score = 25.0
        elif news.get("alert"):
            score = 62.0
        elif news_score < 40:
            score = 48.0

        if panic > 65:
            score -= 15
        return self._bounded(score)

    def _detect_conflicts(
        self,
        swarm: dict,
        specialists: dict,
        debate_output: dict,
        signal: dict,
    ) -> list[dict]:
        conflicts: list[dict] = []

        bullish_pct = self._number(swarm.get("bullish_pct"), 50)
        panic = self._number(swarm.get("panic_index"), 0)
        fomo = self._number(swarm.get("fomo_index"), 0)
        conviction = self._number(swarm.get("conviction"), 50)
        combined = self._number(specialists.get("combined_score"), 50)
        final_call = signal.get("final_call", "NEUTRAL")

        fund_score = self._number(specialists.get("fundamental", {}).get("score"), 50)
        tech_score = self._number(specialists.get("technical", {}).get("score"), 50)
        sent_score = self._number(specialists.get("sentiment", {}).get("score"), 50)
        news_score = self._number(specialists.get("news", {}).get("score"), 50)
        news_alert = specialists.get("news", {}).get("alert")
        bull_score = self._number(debate_output.get("bull_score"), 50)
        bear_score = self._number(debate_output.get("bear_score"), 50)

        if bullish_pct >= 60 and combined < 50:
            conflicts.append(self._conflict(
                "HIGH",
                "Crowd bullish, specialists cautious",
                "The behavioral swarm is strongly bullish, but the combined specialist score is below neutral.",
                [f"Swarm bullish {bullish_pct:.1f}%", f"Specialist score {combined:.1f}/100"],
            ))

        if bullish_pct <= 40 and combined > 60:
            conflicts.append(self._conflict(
                "HIGH",
                "Specialists positive, crowd cautious",
                "Fact-based analysts are constructive, but the simulated market crowd is not yet participating.",
                [f"Swarm bullish {bullish_pct:.1f}%", f"Specialist score {combined:.1f}/100"],
            ))

        if abs(fund_score - tech_score) >= 30:
            conflicts.append(self._conflict(
                "MEDIUM",
                "Fundamental and technical split",
                "Valuation/business quality and price action are sending meaningfully different messages.",
                [f"Fundamental {fund_score:.0f}/100", f"Technical {tech_score:.0f}/100"],
            ))

        if final_call == "BULLISH" and news_alert:
            conflicts.append(self._conflict(
                "HIGH" if "HIGH RISK" in str(news_alert).upper() else "MEDIUM",
                "Bullish signal with news alert",
                "The final call is bullish while the news layer has flagged a material event.",
                [str(news_alert), f"News score {news_score:.0f}/100"],
            ))

        if final_call == "BULLISH" and panic > 60:
            conflicts.append(self._conflict(
                "HIGH",
                "Bullish signal during elevated panic",
                "The headline signal is constructive, but panic-type agents are selling aggressively.",
                [f"Panic index {panic:.1f}", f"Final call {final_call}"],
            ))

        if fomo > 65 and conviction < 60:
            conflicts.append(self._conflict(
                "MEDIUM",
                "FOMO without stable conviction",
                "Momentum chasing is high, but the crowd did not hold a stable view across rounds.",
                [f"FOMO index {fomo:.1f}", f"Conviction {conviction:.1f}%"],
            ))

        if abs(bull_score - bear_score) <= 10 and final_call != "NEUTRAL":
            conflicts.append(self._conflict(
                "MEDIUM",
                "Contested debate",
                "The bull and bear cases are close, so a directional call should be treated carefully.",
                [f"Bull score {bull_score:.0f}", f"Bear score {bear_score:.0f}"],
            ))

        if abs(sent_score - news_score) >= 30:
            conflicts.append(self._conflict(
                "LOW",
                "Sentiment and event layer mismatch",
                "Headline tone and event significance are not telling the same story.",
                [f"Sentiment {sent_score:.0f}/100", f"News {news_score:.0f}/100"],
            ))

        return conflicts

    def _build_evidence(self, ticker: str, orchestrator_output: dict) -> dict:
        specialists = orchestrator_output.get("specialists", {})
        fund = specialists.get("fundamental", {})
        tech = specialists.get("technical", {})
        sentiment = specialists.get("sentiment", {})
        news = specialists.get("news", {})

        facts = []
        raw = fund.get("raw_data", {})
        derived = fund.get("derived", {})
        indicators = tech.get("indicators", {})

        self._append_fact(
            facts,
            "fundamental",
            "P/E vs sector",
            self._format_pair(raw.get("pe_ratio"), raw.get("sector_avg_pe"), "vs"),
            "yfinance stock.info plus AlphaHive sector averages",
            derived.get("pe_vs_sector"),
        )
        self._append_fact(
            facts,
            "fundamental",
            "EPS growth YoY",
            self._format_percent(raw.get("eps_growth_yoy")),
            "yfinance stock.info earningsQuarterlyGrowth",
            derived.get("earnings_trend"),
        )
        self._append_fact(
            facts,
            "fundamental",
            "Promoter holding",
            self._format_percent(raw.get("promoter_holding_pct"), already_percent=True),
            "AlphaHive NSE/promoter holding lookup",
            derived.get("promoter_confidence"),
        )
        self._append_fact(
            facts,
            "technical",
            "RSI 14",
            self._format_number(indicators.get("rsi_14")),
            "AlphaHive calculation from OHLCV history",
            indicators.get("rsi_signal"),
        )
        self._append_fact(
            facts,
            "technical",
            "EMA trend",
            indicators.get("trend_structure"),
            "AlphaHive calculation from OHLCV history",
            self._format_pair(indicators.get("ema_50"), indicators.get("ema_200"), "50/200"),
        )
        self._append_fact(
            facts,
            "technical",
            "Volume ratio",
            self._format_multiple(indicators.get("volume_ratio")),
            "AlphaHive calculation from OHLCV history",
            indicators.get("volume_trend"),
        )
        self._append_fact(
            facts,
            "sentiment",
            "Headlines analyzed",
            sentiment.get("headlines_analyzed"),
            "RSS headlines scored with FinBERT",
            sentiment.get("verdict"),
        )
        self._append_fact(
            facts,
            "news",
            "Material events",
            f"{news.get('bullish_events', 0)} bullish / {news.get('bearish_events', 0)} bearish",
            "RSS headline event rules plus optional specialist LLM summary",
            news.get("alert") or news.get("verdict"),
        )

        return {
            "ticker": ticker,
            "facts": facts,
            "top_headlines": self._top_headlines(sentiment),
            "top_events": self._top_events(news),
            "freshness": {},
        }

    def _build_risk_notes(
        self,
        specialists: dict,
        swarm: dict,
        signal: dict,
        conflicts: list[dict],
    ) -> dict:
        technical = specialists.get("technical", {})
        indicators = technical.get("indicators", {})
        watch_levels = technical.get("watch_levels", {})
        news = specialists.get("news", {})
        final_call = signal.get("final_call", "NEUTRAL")

        support = self._number(watch_levels.get("support") or indicators.get("support_level"))
        resistance = self._number(watch_levels.get("resistance") or indicators.get("resistance_level"))
        ema_50 = self._number(indicators.get("ema_50"))
        panic = self._number(swarm.get("panic_index"), 0)

        invalidation_conditions = []
        monitoring_points = []

        if final_call == "BULLISH":
            if support:
                invalidation_conditions.append(
                    f"A close below support near {support:.2f} would weaken the bullish setup."
                )
            elif ema_50:
                invalidation_conditions.append(
                    f"A close below the 50 EMA near {ema_50:.2f} would weaken the bullish setup."
                )
            invalidation_conditions.append(
                "A high-priority negative exchange filing or earnings miss should trigger manual review."
            )
        elif final_call == "BEARISH":
            if resistance:
                invalidation_conditions.append(
                    f"A close above resistance near {resistance:.2f} would weaken the bearish setup."
                )
            elif ema_50:
                invalidation_conditions.append(
                    f"A reclaim of the 50 EMA near {ema_50:.2f} would weaken the bearish setup."
                )
            invalidation_conditions.append(
                "Improving earnings guidance or a material positive filing would weaken the bearish case."
            )
        else:
            if support and resistance:
                invalidation_conditions.append(
                    f"Wait for a decisive break below {support:.2f} or above {resistance:.2f}; current edge is mixed."
                )
            else:
                invalidation_conditions.append(
                    "Neutral signals need fresh price action, earnings, or news confirmation before directional conviction improves."
                )

        if panic > 50:
            monitoring_points.append(f"Track panic index; it is elevated at {panic:.1f}.")
        if news.get("alert"):
            monitoring_points.append(str(news["alert"]))
        if conflicts:
            monitoring_points.append(f"Resolve {len(conflicts)} detected cross-layer conflict(s).")
        monitoring_points.append("Re-run analysis after market close or after material filings.")

        primary_risk = (
            signal.get("key_risk")
            or (conflicts[0]["title"] if conflicts else "")
            or "Market data or news can change quickly after the signal is generated."
        )

        return {
            "primary_risk": primary_risk,
            "invalidation_conditions": invalidation_conditions[:3],
            "monitoring_points": monitoring_points[:4],
        }

    def _top_headlines(self, sentiment: dict) -> list[dict]:
        headlines = []
        for item in sentiment.get("top_headlines", [])[:5]:
            headlines.append({
                "headline": item.get("headline"),
                "source": item.get("source", "Unknown"),
                "label": item.get("label"),
                "confidence": self._round_or_none(item.get("confidence")),
                "published_at": item.get("published_at"),
            })
        return headlines

    def _top_events(self, news: dict) -> list[dict]:
        events = []
        for item in news.get("top_events", [])[:5]:
            events.append({
                "headline": item.get("headline"),
                "event_type": item.get("event_type"),
                "impact": self._round_or_none(item.get("impact")),
            })
        return events

    def _append_fact(
        self,
        facts: list[dict],
        category: str,
        label: str,
        value: Any,
        source: str,
        interpretation: Any = None,
    ) -> None:
        if not self._has_value(value):
            return
        facts.append({
            "category": category,
            "label": label,
            "value": str(value),
            "source": source,
            "interpretation": str(interpretation) if self._has_value(interpretation) else None,
        })

    def _conflict(
        self,
        severity: str,
        title: str,
        description: str,
        evidence: list[str],
    ) -> dict:
        return {
            "severity": severity,
            "title": title,
            "description": description,
            "evidence": evidence,
        }

    def _quality_summary(self, score: float, conflicts: list[dict]) -> str:
        label = self._label(score).lower()
        if not conflicts:
            return f"Research trust is {label}; no major cross-layer conflicts were detected."
        high = sum(1 for item in conflicts if item["severity"] == "HIGH")
        if high:
            return f"Research trust is {label}; {high} high-severity conflict(s) need manual attention."
        return f"Research trust is {label}; {len(conflicts)} moderate/low conflict(s) should be reviewed."

    def _label(self, score: float) -> str:
        if score >= 75:
            return "HIGH"
        if score >= 55:
            return "MEDIUM"
        return "LOW"

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _number(self, value: Any, default: float | None = None) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return number

    def _bounded(self, value: Any, default: float = 50.0) -> float:
        number = self._number(value, default)
        if number is None:
            number = default
        return max(0.0, min(100.0, number))

    def _has_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return True

    def _round_or_none(self, value: Any) -> float | None:
        number = self._number(value)
        return round(number, 4) if number is not None else None

    def _format_number(self, value: Any) -> str | None:
        number = self._number(value)
        return f"{number:.2f}" if number is not None else None

    def _format_percent(self, value: Any, already_percent: bool = False) -> str | None:
        number = self._number(value)
        if number is None:
            return None
        if not already_percent and abs(number) <= 2:
            number *= 100
        return f"{number:.2f}%"

    def _format_multiple(self, value: Any) -> str | None:
        number = self._number(value)
        return f"{number:.2f}x" if number is not None else None

    def _format_pair(self, left: Any, right: Any, separator: str) -> str | None:
        left_number = self._number(left)
        right_number = self._number(right)
        if left_number is None or right_number is None:
            return None
        return f"{left_number:.2f} {separator} {right_number:.2f}"
