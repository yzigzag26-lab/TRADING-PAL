"""End-to-end Baymax intelligence pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.ai.assessment import (
    MarketAssessment,
    build_market_assessment,
    compact_intelligence_context,
)
from app.ai.classifier import BaymaxIntentClassifier, IntentClassificationError
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.intelligence.analyzer import MarketIntelligenceEngine
from app.market_data.analysis_input import (
    MarketIntelligenceInputBuilder,
    MarketIntelligenceInputUnavailable,
)
from app.market_data.decision_safety import (
    is_trading_decision_request,
    validate_prepared_analysis_inputs,
)
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)
from app.strategy.decision_safety import DecisionSafetyGate
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
        decision_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._classifier = classifier
        self._generator = generator
        self._orchestrator = orchestrator
        self._intelligence_builder = intelligence_builder
        self._intelligence_engine = intelligence_engine or MarketIntelligenceEngine()
        self._safety_gate = safety_gate or DecisionSafetyGate()
        self._decision_clock = decision_clock or (lambda: datetime.now(UTC))

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
            decision_requested=(
                classification.decision_requested
                or is_trading_decision_request(message, intent=classification.intent)
            ),
        )
        prepared = await self._orchestrator.prepare(request, request_id=request_id)

        if (
            request.intent == "current_market"
            and self._intelligence_builder is not None
            and prepared.current_price is not None
        ):
            return await self._respond_with_intelligence(request, prepared, request_id=request_id)

        # Revalidate at the final boundary because data may expire during processing.
        validate_prepared_analysis_inputs(request, prepared, now=self._decision_clock())
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
        """Run the Gate 4 pipeline: Python calculates, Groq proposes, Python validates.

        Stage 1: deterministic multi-timeframe analysis and candidate levels.
        Stage 2: Groq independently proposes BUY / SELL / WAIT from the evidence.
        Stage 3: the safety gate revalidates freshness/provenance at release time
        and vetoes any unsafe or unsupported proposal.
        Stage 4: the validated decision is returned with full evidence.
        """
        assert self._intelligence_builder is not None
        try:
            bundle = await self._intelligence_builder.build(prepared, request_id=request_id)
        except MarketIntelligenceInputUnavailable as exc:
            raise AnalysisInputUnavailable(str(exc)) from exc

        report = self._intelligence_engine.analyze(bundle)
        candidate = evaluate_setup(report)
        context = compact_intelligence_context(report, candidate)

        proposal: MarketAssessment | None = None
        try:
            proposal = await self._generator.generate_assessment(request, context)
        except AnalysisGenerationError:
            proposal = None

        # Stage 3 runs at the release boundary, after all analysis and model
        # latency, so the market-event age is recomputed against current UTC.
        safety = self._safety_gate.evaluate(
            report,
            candidate,
            proposal.decision if proposal is not None else None,
            request=request,
            prepared=prepared,
            now=self._decision_clock(),
        )
        assessment = build_market_assessment(report, prepared, safety, proposal)

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
