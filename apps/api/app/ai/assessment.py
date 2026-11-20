"""Structured market-assessment contract shared by strategy, AI and API layers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.schemas import MarketIntelligenceReport, TimeframeAnalysis
from app.strategy.schemas import SafetyResult, StrategyOutcome

AssessmentDecision = Literal["BUY", "SELL", "WAIT"]


class MarketAssessment(BaseModel):
    """Machine-readable final assessment returned to the owner.

    ``decision`` is always the deterministic safety-gated result. The ``summary``
    is natural-language interpretation; it may explain but never override the
    decision or invent the numeric levels in ``scenario``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AssessmentDecision
    summary: str = Field(min_length=1, max_length=20_000)
    key_evidence: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    timeframe_alignment: str | None = None
    data_quality: str | None = None
    scenario: dict[str, object] | None = None


def _indicator_summary(analysis: TimeframeAnalysis) -> dict[str, object]:
    """Compact deterministic indicator readings for the model context."""
    summary: dict[str, object] = {}
    wanted = {
        ("SMA", 20): "sma20",
        ("SMA", 50): "sma50",
        ("EMA", 20): "ema20",
        ("EMA", 50): "ema50",
        ("RSI", 14): "rsi14",
    }
    for reading in analysis.indicators:
        if not reading.sufficient_history:
            continue
        key = wanted.get((reading.name, int(reading.parameters.get("period", -1))))
        if key is not None:
            summary[key] = reading.values.get("value")
        elif reading.name == "MACD":
            summary["macd_histogram"] = reading.values.get("histogram")
        elif reading.name == "ATR":
            summary["atr_percent"] = reading.values.get("percent")
        elif reading.name == "ADX":
            summary["adx"] = reading.values.get("adx")
            summary["plus_di"] = reading.values.get("plus_di")
            summary["minus_di"] = reading.values.get("minus_di")
        elif reading.name == "VOLUME":
            summary["relative_volume"] = reading.values.get("relative")
        elif reading.name == "BOLLINGER":
            summary["bollinger_width_percentile"] = reading.values.get("width_percentile")
    return summary


def _zone_summary(analysis: TimeframeAnalysis) -> dict[str, object]:
    return {
        "support": [
            {
                "lower": str(z.lower),
                "upper": str(z.upper),
                "touches": z.touches,
                "strength": z.strength,
                "active": z.active,
            }
            for z in analysis.zones
            if z.side == "support"
        ][:3],
        "resistance": [
            {
                "lower": str(z.lower),
                "upper": str(z.upper),
                "touches": z.touches,
                "strength": z.strength,
                "active": z.active,
            }
            for z in analysis.zones
            if z.side == "resistance"
        ][:3],
    }


def compact_intelligence_context(
    report: MarketIntelligenceReport,
    outcome: StrategyOutcome,
    safety: SafetyResult,
) -> dict[str, object]:
    """Build the compact structured evidence payload for the Groq assessment.

    Only verified, deterministic values are included. The model receives no
    raw candle dumps and no ability to fetch data.
    """
    timeframes: dict[str, object] = {}
    for analysis in report.timeframe_analyses:
        if not analysis.usable:
            timeframes[analysis.interval] = {
                "usable": False,
                "limitations": list(analysis.limitations),
            }
            continue
        timeframes[analysis.interval] = {
            "usable": True,
            "trend": analysis.trend.direction,
            "trend_score": analysis.trend.score,
            "last_closed_close": (
                str(analysis.last_closed_close) if analysis.last_closed_close is not None else None
            ),
            "structure": [finding.kind for finding in analysis.structure][-6:],
            "volatility": {
                "level": analysis.volatility.level,
                "direction": analysis.volatility.direction,
                "atr_percent": analysis.volatility.atr_percent,
            },
            "indicators": _indicator_summary(analysis),
            "zones": _zone_summary(analysis),
        }

    scenario_payload: dict[str, object] | None = None
    if safety.scenario is not None:
        scenario = safety.scenario
        scenario_payload = {
            "decision": scenario.decision,
            "direction": scenario.direction,
            "entry_zone": {
                "lower": str(scenario.entry_zone.lower),
                "upper": str(scenario.entry_zone.upper),
            },
            "stop_loss": str(scenario.stop_loss.price),
            "take_profit_1": str(scenario.take_profit_1.price),
            "take_profit_2": (
                str(scenario.take_profit_2.price) if scenario.take_profit_2 is not None else None
            ),
            "risk_reward_ratio": str(scenario.risk_reward_ratio),
            "invalidation": scenario.invalidation,
            "methodology": scenario.methodology,
        }

    return {
        "symbol": report.symbol,
        "exchange": report.exchange,
        "market": report.market,
        "analyzed_at": report.analyzed_at.isoformat(),
        "current_price": report.current_price,
        "data_quality": report.data_quality,
        "readiness": report.readiness,
        "timeframe_alignment": {
            "status": report.alignment.status,
            "directions": report.alignment.directions,
            "notes": list(report.alignment.notes),
        },
        "timeframes": timeframes,
        "deterministic_scenario": scenario_payload,
        "safety": {
            "final_decision": safety.decision,
            "blocked": safety.blocked,
            "block_reasons": list(safety.block_reasons),
            "checks": list(safety.checks),
        },
        "strategy_reasons": list(outcome.reasons),
        "strategy_blocking_reasons": list(outcome.blocking_reasons),
        "missing_inputs": list(report.missing_inputs),
        "limitations": list(report.limitations),
    }


def deterministic_fallback_summary(
    report: MarketIntelligenceReport,
    safety: SafetyResult,
) -> str:
    """Honest markdown summary used when the model is unavailable or invalid.

    Contains only verified facts from the deterministic pipeline — no invented
    analysis, prices or predictions.
    """
    lines = [
        f"## Market assessment: {report.symbol}",
        "",
        f"**Decision: {safety.decision}**",
        "",
        f"Timeframe alignment: {report.alignment.status} "
        f"({', '.join(f'{k}={v}' for k, v in report.alignment.directions.items())})",
        f"Data quality: {report.data_quality}; readiness: {report.readiness}.",
        "",
        "### Timeframe trends",
    ]
    for analysis in report.timeframe_analyses:
        if analysis.usable:
            lines.append(
                f"- {analysis.interval}: {analysis.trend.direction} "
                f"(score {analysis.trend.score:+.2f}), "
                f"volatility {analysis.volatility.level}/{analysis.volatility.direction}"
            )
        else:
            lines.append(f"- {analysis.interval}: unusable ({'; '.join(analysis.limitations)})")
    if safety.scenario is not None:
        scenario = safety.scenario
        lines += [
            "",
            "### Scenario (deterministic)",
            f"- Entry zone: {scenario.entry_zone.lower} – {scenario.entry_zone.upper}",
            f"- Stop-loss: {scenario.stop_loss.price} ({scenario.stop_loss.method})",
            f"- Take-profit 1: {scenario.take_profit_1.price} ({scenario.take_profit_1.method})",
            *(
                [f"- Take-profit 2: {scenario.take_profit_2.price}"]
                if scenario.take_profit_2 is not None
                else []
            ),
            f"- Risk/reward: {scenario.risk_reward_ratio}",
            f"- Invalidation: {scenario.invalidation}",
        ]
    if safety.block_reasons:
        lines += ["", "### Why no recommendation", *[f"- {r}" for r in safety.block_reasons]]
    if report.limitations:
        lines += ["", "### Limitations", *[f"- {item}" for item in report.limitations[:10]]]
    lines += [
        "",
        "_This is analysis only. No order was placed or will be placed._",
    ]
    return "\n".join(lines)


ASSESSMENT_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "baymax_market_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["BUY", "SELL", "WAIT"]},
                "summary": {"type": "string"},
                "key_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "risks": {"type": "array", "items": {"type": "string"}},
                "invalidation_conditions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "limitations": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "decision",
                "summary",
                "key_evidence",
                "risks",
                "invalidation_conditions",
                "limitations",
            ],
            "additionalProperties": False,
        },
    },
}


__all__ = [
    "ASSESSMENT_RESPONSE_SCHEMA",
    "AssessmentDecision",
    "MarketAssessment",
]
