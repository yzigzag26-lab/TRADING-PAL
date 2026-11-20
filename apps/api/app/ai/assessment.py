"""Structured market-assessment contract shared by strategy, AI and API layers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.schemas import (
    MarketIntelligenceReport,
    TimeframeAnalysis,
)
from app.orchestration.requests import PreparedAnalysisInput
from app.strategy.schemas import ExitGuidance, SafetyResult, Scenario, StrategyOutcome

AssessmentDecision = Literal["BUY", "SELL", "WAIT"]


class IndicatorSection(BaseModel):
    """One verified indicator reading exposed to the UI."""

    model_config = ConfigDict(extra="forbid")

    name: str
    parameters: dict[str, int | float] = Field(default_factory=dict)
    values: dict[str, float] = Field(default_factory=dict)
    candle_count: int = 0
    sufficient_history: bool = False


class ZoneSection(BaseModel):
    """One verified support/resistance zone."""

    model_config = ConfigDict(extra="forbid")

    side: str
    lower: str
    upper: str
    touches: int
    strength: float
    active: bool


class TimeframeSection(BaseModel):
    """Complete per-timeframe evidence for one analysis interval."""

    model_config = ConfigDict(extra="forbid")

    interval: str
    usable: bool
    candle_count: int = 0
    closed_candle_count: int = 0
    series_complete: bool = False
    snapshot_id: str | None = None
    last_closed_close: str | None = None
    trend_direction: str | None = None
    trend_score: float | None = None
    trend_evidence: tuple[str, ...] = ()
    structure_kinds: tuple[str, ...] = ()
    structure_details: tuple[str, ...] = ()
    zones: tuple[ZoneSection, ...] = ()
    volatility_level: str | None = None
    volatility_direction: str | None = None
    atr: float | None = None
    atr_percent: float | None = None
    bollinger_width_percentile: float | None = None
    indicators: tuple[IndicatorSection, ...] = ()
    limitations: tuple[str, ...] = ()


class IntelligenceSection(BaseModel):
    """Complete deterministic evidence section of the final assessment."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    exchange: str
    market: str
    analyzed_at: datetime
    current_price: str
    price_provenance_id: str | None = None
    alignment_status: str
    alignment_directions: dict[str, str] = Field(default_factory=dict)
    alignment_notes: tuple[str, ...] = ()
    data_quality: str
    readiness: str
    missing_inputs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    timeframes: tuple[TimeframeSection, ...] = ()


class MarketAssessment(BaseModel):
    """Machine-readable final assessment returned to the owner.

    ``decision`` is always the deterministic safety-gated result. ``summary``
    is natural-language interpretation; it may explain but never override the
    decision or invent the numeric levels in ``scenario``/``exit_guidance``.
    ``model_decision`` records Groq's independent proposal for auditability.
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
    exit_guidance: dict[str, object] | None = None
    model_decision: str | None = None
    intelligence: IntelligenceSection | None = None


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


def _exit_guidance_payload(guidance: ExitGuidance) -> dict[str, object]:
    return {
        "kind": guidance.kind,
        "decision": guidance.decision,
        "note": guidance.note,
        "trim_levels": [
            {"price": str(level.price), "method": level.method} for level in guidance.trim_levels
        ],
        "breakdown_exit": (
            {
                "price": str(guidance.breakdown_exit.price),
                "method": guidance.breakdown_exit.method,
            }
            if guidance.breakdown_exit is not None
            else None
        ),
        "hold_invalidation": guidance.hold_invalidation,
        "methodology": guidance.methodology,
    }


def compact_intelligence_context(
    report: MarketIntelligenceReport,
    candidate: StrategyOutcome,
) -> dict[str, object]:
    """Build the verified evidence payload for Groq's independent proposal.

    Only deterministic, verified values are included. The payload deliberately
    contains NO Python-selected final decision: Groq must reason about the
    evidence and propose BUY / SELL / WAIT itself. Candidate levels are
    labelled as candidates, not instructions.
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

    candidate_payload: dict[str, object] | None = None
    if candidate.scenario is not None:
        scenario = candidate.scenario
        candidate_payload = {
            "kind": "buy_scenario_candidate",
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
        }
    elif candidate.exit_guidance is not None:
        candidate_payload = _exit_guidance_payload(candidate.exit_guidance)

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
            "directions": {k: str(v) for k, v in report.alignment.directions.items()},
            "notes": list(report.alignment.notes),
        },
        "timeframes": timeframes,
        "candidate_levels": candidate_payload,
        "strategy_evidence": {
            "candidate_direction": candidate.direction,
            "reasons": list(candidate.reasons),
            "blocking_reasons": list(candidate.blocking_reasons),
        },
        "missing_inputs": list(report.missing_inputs),
        "limitations": list(report.limitations),
    }


def build_intelligence_section(
    report: MarketIntelligenceReport,
    prepared: PreparedAnalysisInput,
) -> IntelligenceSection:
    """Serialize the complete deterministic evidence for the API response."""
    timeframes: list[TimeframeSection] = []
    for analysis in report.timeframe_analyses:
        indicators = tuple(
            IndicatorSection(
                name=reading.name,
                parameters=dict(reading.parameters),
                values=dict(reading.values),
                candle_count=reading.candle_count,
                sufficient_history=reading.sufficient_history,
            )
            for reading in analysis.indicators
        )
        zones = tuple(
            ZoneSection(
                side=str(zone.side),
                lower=str(zone.lower),
                upper=str(zone.upper),
                touches=zone.touches,
                strength=zone.strength,
                active=zone.active,
            )
            for zone in analysis.zones
        )
        timeframes.append(
            TimeframeSection(
                interval=analysis.interval,
                usable=analysis.usable,
                candle_count=analysis.candle_count,
                closed_candle_count=analysis.closed_candle_count,
                series_complete=analysis.series_complete,
                snapshot_id=(
                    str(analysis.snapshot_id) if analysis.snapshot_id is not None else None
                ),
                last_closed_close=(
                    str(analysis.last_closed_close)
                    if analysis.last_closed_close is not None
                    else None
                ),
                trend_direction=str(analysis.trend.direction),
                trend_score=analysis.trend.score,
                trend_evidence=analysis.trend.evidence,
                structure_kinds=tuple(str(f.kind) for f in analysis.structure),
                structure_details=tuple(f.detail for f in analysis.structure),
                zones=zones,
                volatility_level=str(analysis.volatility.level),
                volatility_direction=str(analysis.volatility.direction),
                atr=analysis.volatility.atr,
                atr_percent=analysis.volatility.atr_percent,
                bollinger_width_percentile=analysis.volatility.bollinger_width_percentile,
                indicators=indicators,
                limitations=analysis.limitations,
            )
        )
    price_snapshot = prepared.market_snapshot_id
    return IntelligenceSection(
        symbol=report.symbol,
        exchange=report.exchange,
        market=report.market,
        analyzed_at=report.analyzed_at,
        current_price=report.current_price,
        price_provenance_id=(str(price_snapshot) if price_snapshot is not None else None),
        alignment_status=str(report.alignment.status),
        alignment_directions={k: str(v) for k, v in report.alignment.directions.items()},
        alignment_notes=report.alignment.notes,
        data_quality=str(report.data_quality),
        readiness=str(report.readiness),
        missing_inputs=report.missing_inputs,
        limitations=report.limitations,
        timeframes=tuple(timeframes),
    )


def _scenario_or_exit_payload(
    scenario: Scenario | None,
    exit_guidance: ExitGuidance | None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    scenario_payload: dict[str, object] | None = None
    if scenario is not None:
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
            "risk_distance": str(scenario.risk_distance),
            "reward_distance": str(scenario.reward_distance),
            "risk_reward_ratio": str(scenario.risk_reward_ratio),
            "invalidation": scenario.invalidation,
            "methodology": scenario.methodology,
        }
    exit_payload = _exit_guidance_payload(exit_guidance) if exit_guidance else None
    return scenario_payload, exit_payload


def build_market_assessment(
    report: MarketIntelligenceReport,
    prepared: PreparedAnalysisInput,
    safety: SafetyResult,
    draft: MarketAssessment | None,
) -> MarketAssessment:
    """Merge Groq's validated proposal with deterministic evidence.

    The final ``decision`` always comes from the safety gate. Groq's text is
    used only when its proposal matches the final decision; a vetoed or
    mismatched proposal falls back to the deterministic summary while the
    original proposal is preserved in ``model_decision``.
    """
    scenario_payload, exit_payload = _scenario_or_exit_payload(
        safety.scenario, safety.exit_guidance
    )
    intelligence = build_intelligence_section(report, prepared)
    proposal = draft.decision if draft is not None else None
    report_limitations = tuple(report.limitations[:10])

    if draft is not None and draft.decision == safety.decision:
        limitations = tuple(dict.fromkeys((*draft.limitations, *report_limitations)))
        return MarketAssessment(
            decision=safety.decision,
            summary=draft.summary,
            key_evidence=draft.key_evidence,
            risks=draft.risks,
            invalidation_conditions=draft.invalidation_conditions,
            limitations=limitations,
            timeframe_alignment=report.alignment.status,
            data_quality=str(report.data_quality),
            scenario=scenario_payload,
            exit_guidance=exit_payload,
            model_decision=proposal,
            intelligence=intelligence,
        )

    fallback_notes: list[str] = []
    if draft is None:
        fallback_notes.append("AI interpretation unavailable; deterministic summary shown")
    else:
        fallback_notes.append(
            f"Model proposed {proposal}; the safety gate returned "
            f"{safety.decision} — model text was not used for the verdict"
        )
    return MarketAssessment(
        decision=safety.decision,
        summary=deterministic_fallback_summary(report, safety),
        limitations=tuple(dict.fromkeys((*report_limitations, *fallback_notes))),
        timeframe_alignment=report.alignment.status,
        data_quality=str(report.data_quality),
        scenario=scenario_payload,
        exit_guidance=exit_payload,
        model_decision=proposal,
        intelligence=intelligence,
    )


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
    scenario = safety.scenario
    if scenario is not None:
        lines += [
            "",
            "### Scenario (deterministic)",
            f"- Entry zone: {scenario.entry_zone.lower} – {scenario.entry_zone.upper}",
            f"- Stop-loss: {scenario.stop_loss.price}",
            f"- Take-profit 1: {scenario.take_profit_1.price}",
            *(
                [f"- Take-profit 2: {scenario.take_profit_2.price}"]
                if scenario.take_profit_2 is not None
                else []
            ),
            f"- Risk/reward: {scenario.risk_reward_ratio}",
            f"- Invalidation: {scenario.invalidation}",
        ]
    guidance = safety.exit_guidance
    if guidance is not None:
        lines += [
            "",
            "### Spot exit guidance (deterministic)",
            f"- {guidance.note}",
            *[f"- Trim level: {level.price}" for level in guidance.trim_levels],
            *(
                [f"- Breakdown exit: {guidance.breakdown_exit.price}"]
                if guidance.breakdown_exit is not None
                else []
            ),
            f"- Invalidation: {guidance.hold_invalidation}",
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
    "IndicatorSection",
    "IntelligenceSection",
    "MarketAssessment",
    "TimeframeSection",
    "ZoneSection",
    "build_intelligence_section",
    "build_market_assessment",
    "compact_intelligence_context",
    "deterministic_fallback_summary",
]
