"""End-to-end Baymax intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.ai.classifier import BaymaxIntentClassifier, IntentClassificationError
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
)


@dataclass(frozen=True, slots=True)
class BaymaxAIResult:
    """User-facing result and the trusted intent selected by the classifier."""

    answer: str
    intent: str
    symbol: str | None
    market_data_status: str
    needs_clarification: bool = False
    market_snapshot_id: UUID | None = None


class BaymaxAIEngine:
    """Connect Groq classification, verified input orchestration and generation."""

    def __init__(
        self,
        *,
        classifier: BaymaxIntentClassifier,
        generator: BaymaxAnalysisGenerator,
        orchestrator: BaymaxRequestOrchestrator,
    ) -> None:
        self._classifier = classifier
        self._generator = generator
        self._orchestrator = orchestrator

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
        answer = await self._generator.generate(request, prepared)
        return BaymaxAIResult(
            answer=answer,
            intent=classification.intent,
            symbol=classification.symbol,
            market_data_status=prepared.market_data_status,
            market_snapshot_id=prepared.market_snapshot_id,
        )


__all__ = [
    "AnalysisGenerationError",
    "AnalysisInputUnavailable",
    "BaymaxAIEngine",
    "BaymaxAIResult",
    "IntentClassificationError",
]
