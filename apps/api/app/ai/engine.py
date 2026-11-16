"""End-to-end Baymax intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.classifier import (
    BaymaxIntentClassifier,
    IntentClassificationError,
)
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

    async def respond(self, message: str) -> BaymaxAIResult:
        """Classify first, prepare only necessary inputs, then generate the answer."""
        classification = await self._classifier.classify(message)
        if classification.needs_clarification:
            raise IntentClassificationError("Baymax needs clarification before proceeding")

        request = AnalysisRequest(
            message=message,
            intent=classification.intent,
            symbol=classification.symbol,
        )
        prepared = await self._orchestrator.prepare(request)
        answer = await self._generator.generate(request, prepared)
        return BaymaxAIResult(
            answer=answer,
            intent=classification.intent,
            symbol=classification.symbol,
            market_data_status=prepared.market_data_status,
        )


__all__ = [
    "AnalysisGenerationError",
    "AnalysisInputUnavailable",
    "BaymaxAIEngine",
    "BaymaxAIResult",
    "IntentClassificationError",
]
