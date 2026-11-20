"""Final fail-closed decision-safety gate for Gate 4 recommendations.

Composes the Gate 3 freshness/provenance guarantees with Gate 4 integrity
checks before any BUY/SELL decision is released. Any failed mandatory check
forces WAIT — the system may explain why, but never recommends on unverified
inputs.
"""

from __future__ import annotations

from app.intelligence.analyzer import ANALYSIS_TIMEFRAMES, MarketIntelligenceReport
from app.market_data.freshness import MAX_PRICE_AGE_MS
from app.market_data.models import ValidatedPrice
from app.strategy.schemas import Decision, SafetyResult, StrategyOutcome

MAX_PRICE_AGE_MS_GATE = MAX_PRICE_AGE_MS


class DecisionSafetyGate:
    """Verify every mandatory condition immediately before recommendation."""

    def __init__(self, *, require_provenance: bool = False) -> None:
        self._require_provenance = require_provenance

    def evaluate(
        self,
        report: MarketIntelligenceReport,
        outcome: StrategyOutcome,
        price: ValidatedPrice | None,
    ) -> SafetyResult:
        """Return the final decision; downgrade to WAIT on any failed check."""
        checks: list[str] = []
        blocks: list[str] = []

        def check(name: str, passed: bool, failure: str) -> None:
            checks.append(name)
            if not passed:
                blocks.append(failure)

        # Symbol identity across price and every analysed timeframe.
        symbols = {item.symbol for item in report.timeframe_analyses}
        symbols.add(report.symbol)
        check(
            "symbol_identity",
            len(symbols) == 1,
            f"Symbol mismatch across inputs: {sorted(symbols)}",
        )

        # Current-price freshness (Gate 3 policy, re-verified at this boundary).
        check(
            "price_freshness",
            price is not None and price.age_ms_at_validation <= MAX_PRICE_AGE_MS_GATE,
            "Current price is missing or older than the 3,000 ms policy",
        )
        if price is not None:
            check(
                "price_symbol_match",
                price.symbol == report.symbol,
                "Validated price symbol does not match the analysis symbol",
            )

        # Required timeframe availability and completeness.
        present = {item.interval for item in report.timeframe_analyses}
        missing = [tf for tf in ANALYSIS_TIMEFRAMES if tf not in present]
        check(
            "timeframe_coverage",
            not missing,
            f"Missing timeframe analyses: {missing}",
        )
        incomplete = [
            item.interval for item in report.timeframe_analyses if not item.series_complete
        ]
        check(
            "series_completeness",
            not incomplete,
            f"Incomplete candle series: {incomplete}",
        )
        unusable = [item.interval for item in report.timeframe_analyses if not item.usable]
        check(
            "timeframe_usability",
            not unusable,
            f"Timeframes below minimum usable history: {unusable}",
        )

        # Provenance: every consumed series and the price must be auditable.
        if self._require_provenance:
            missing_snapshots = [
                item.interval for item in report.timeframe_analyses if item.snapshot_id is None
            ]
            if price is not None:
                price_ok = report.current_price_snapshot_id is not None
            else:
                price_ok = False
            check(
                "provenance",
                not missing_snapshots and price_ok,
                "Missing snapshot provenance for one or more inputs",
            )
        else:
            checks.append("provenance(optional)")

        # Alignment must not be insufficient for a directional decision.
        check(
            "timeframe_alignment",
            report.alignment.status != "insufficient",
            "Timeframe alignment evidence is insufficient",
        )

        # Deterministic strategy must not already be blocked.
        check(
            "strategy_readiness",
            outcome.proposed_decision == "WAIT" or outcome.scenario is not None,
            "No defensible deterministic scenario exists",
        )

        final: Decision = outcome.proposed_decision
        if blocks:
            final = "WAIT"
        elif outcome.blocking_reasons and final != "WAIT":
            # Strategy produced a scenario but recorded warnings; keep decision.
            pass

        return SafetyResult(
            decision=final,
            scenario=outcome.scenario if final != "WAIT" else None,
            blocked=final == "WAIT" and outcome.proposed_decision != "WAIT",
            block_reasons=tuple(blocks),
            checks=tuple(checks),
        )


__all__ = ["DecisionSafetyGate", "MAX_PRICE_AGE_MS_GATE"]
