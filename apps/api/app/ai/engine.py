"""End-to-end Baymax intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.ai.assessment import (
    MarketAssessment,
    compact_intelligence_context,
    deterministic_fallback_summary,
)
from app.ai.classifier import BaymaxIntentClassifier, IntentClassificationError
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.intelligence.analyzer import MarketIntelligenceEngine
from app.market_data.analysis_input import (
    MarketIntelligenceInputBuilder,
    MarketIntelligenceInputUnavailable,
)
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)
from app.strategy.decision_safety import DecisionSafetyGate
from app.strategy.schemas import Scenario
from app.strategy.setup import evaluate_setup


@dataclass(frozen=True, slots=True)
class BaymaxAIResult:
    """User-facing result and the trusted intent selected by the classifier."""

    answer: str
    intent: str
    symbol: str | None
    market_data_status: str
    needs_clarification: bool = False
    market_snapshot_id: UUID | None = None
    assessment: MarketAssessment | None = None


def _scenario_payload(scenario: Scenario) -> dict[str, object]:
    return {
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


class BaymaxAIEngine:
    """Connect Groq classification, verified input orchestration and generation."""

    def __init__(
        self,
        *,
        classifier: BaymaxIntentClassifier,
        generator: BaymaxAnalysisGenerator,
        orchestrator: BaymaxRequestOrchestrator,
        intelligence_builder: MarketIntelligenceInputBuilder | None = None,
        intelligence_engine: MarketIntelligenceEngine | None = None,
        safety_gate: DecisionSafetyGate | None = None,
    ) -> None:
        self._classifier = classifier
        self._generator = generator
        self._orchestrator = orchestrator
        self._intelligence_builder = intelligence_builder
        self._intelligence_engine = intelligence_engine or MarketIntelligenceEngine()
        self._safety_gate = safety_gate or DecisionSafetyGate()

    async def respond(
        self,
        message: str,
        *,
        request_id: UUID | None = None,
    ) -> BaymaxAIResult:
        """Classify first, prepare only necessary inputs, then generate the answer."""
        classification = await self._classifier.classify(message)
        if classification.needs_clarification:
            return BaymaxAIResult(
                answer=(
                    "I need one clarification before I continue. Which cryptocurrency or "
                    "trading pair are you referring to, and are you asking about its current "
                    "market state or its historical performance?"
                ),
                intent=classification.intent,
                symbol=classification.symbol,
                market_data_status="not_requested",
                needs_clarification=True,
            )

        request = AnalysisRequest(
            message=message,
            intent=classification.intent,
            symbol=classification.symbol,
        )
        prepared = await self._orchestrator.prepare(request, request_id=request_id)

        if (
            request.intent == "current_market"
            and self._intelligence_builder is not None
            and prepared.current_price is not None
        ):
            return await self._respond_with_intelligence(request, prepared, request_id=request_id)

        answer = await self._generator.generate(request, prepared)
        return BaymaxAIResult(
            answer=answer,
            intent=classification.intent,
            symbol=classification.symbol,
            market_data_status=prepared.market_data_status,
            market_snapshot_id=prepared.market_snapshot_id,
        )

    async def _respond_with_intelligence(
        self,
        request: AnalysisRequest,
        prepared: PreparedAnalysisInput,
        *,
        request_id: UUID | None,
    ) -> BaymaxAIResult:
        """Run the full Gate 4 pipeline and return a structured assessment."""
        assert self._intelligence_builder is not None
        try:
            bundle = await self._intelligence_builder.build(prepared, request_id=request_id)
        except MarketIntelligenceInputUnavailable as exc:
            raise AnalysisInputUnavailable(str(exc)) from exc

        report = self._intelligence_engine.analyze(bundle)
        outcome = evaluate_setup(report)
        safety = self._safety_gate.evaluate(report, outcome, prepared.current_price)
        context = compact_intelligence_context(report, outcome, safety)

        assessment: MarketAssessment
        try:
            draft = await self._generator.generate_assessment(request, context)
        except AnalysisGenerationError:
            assessment = MarketAssessment(
                decision=safety.decision,
                summary=deterministic_fallback_summary(report, safety),
                limitations=tuple(report.limitations[:10])
                + ("AI interpretation unavailable; deterministic summary shown",),
                timeframe_alignment=report.alignment.status,
                data_quality=report.data_quality,
                scenario=(
                    _scenario_payload(safety.scenario) if safety.scenario is not None else None
                ),
            )
        else:
            if draft.decision != safety.decision:
                # The deterministic safety gate is authoritative; a disagreeing
                # model interpretation is discarded entirely.
                assessment = MarketAssessment(
                    decision=safety.decision,
                    summary=deterministic_fallback_summary(report, safety),
                    limitations=tuple(report.limitations[:10])
                    + (
                        "Model interpretation disagreed with the deterministic "
                        "decision and was discarded",
                    ),
                    timeframe_alignment=report.alignment.status,
                    data_quality=report.data_quality,
                    scenario=(
                        _scenario_payload(safety.scenario) if safety.scenario is not None else None
                    ),
                )
            else:
                assessment = draft.model_copy(
                    update={
                        "decision": safety.decision,
                        "timeframe_alignment": report.alignment.status,
                        "data_quality": report.data_quality,
                        "scenario": (
                            _scenario_payload(safety.scenario)
                            if safety.scenario is not None
                            else None
                        ),
                        "limitations": tuple(
                            dict.fromkeys((*draft.limitations, *report.limitations[:10]))
                        ),
                    }
                )

        return BaymaxAIResult(
            answer=assessment.summary,
            intent=request.intent,
            symbol=request.symbol,
            market_data_status=prepared.market_data_status,
            market_snapshot_id=prepared.market_snapshot_id,
            assessment=assessment,
        )


__all__ = [
    "AnalysisGenerationError",
    "AnalysisInputUnavailable",
    "BaymaxAIEngine",
    "BaymaxAIResult",
    "IntentClassificationError",
]
