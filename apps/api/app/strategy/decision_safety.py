"""Final fail-closed decision gate for Gate 4 market intelligence.

The safety gate is the authoritative veto layer. It re-runs the shared Gate 3
market-evidence validation (freshness recomputed at the *release* time,
provenance, identity, timestamp ordering) plus report-level checks, then
validates Groq's proposed decision against the deterministic candidate. It
never invents levels and never lets the model override verified evidence.

Division of responsibility (approved architecture):

- Python calculates all verified evidence and candidate levels.
- Groq independently proposes BUY / SELL / WAIT.
- This gate validates the proposal and decides the final outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.intelligence.schemas import MarketIntelligenceReport
from app.market_data.decision_safety import validate_market_price_inputs
from app.orchestration.requests import AnalysisRequest, PreparedAnalysisInput
from app.strategy.schemas import Decision, SafetyResult, StrategyOutcome

MAX_PRICE_AGE_MS = 3000
EXPECTED_TIMEFRAMES = frozenset({"5m", "15m", "1h", "4h", "1d"})
MIN_REPORT_TIMEFRAMES = len(EXPECTED_TIMEFRAMES)
MIN_USABLE_TIMEFRAMES = len(EXPECTED_TIMEFRAMES)
MIN_CANDLES_PER_TIMEFRAME = 60
MIN_SAFETY_RISK_REWARD = Decimal("1.5")


class DecisionSafetyGate:
    """Evaluate a Groq proposal against verified intelligence evidence."""

    def __init__(self, *, require_provenance: bool = False) -> None:
        self._require_provenance = require_provenance

    def evaluate(
        self,
        report: MarketIntelligenceReport,
        candidate: StrategyOutcome,
        proposal: str | None,
        *,
        request: AnalysisRequest,
        prepared: PreparedAnalysisInput,
        now: datetime,
    ) -> SafetyResult:
        """Validate ``proposal`` and return the authoritative final decision."""
        checks: list[str] = []
        blocks: list[str] = []
        try:
            current_time = self._utc(now)
        except ValueError:
            return SafetyResult(
                decision="WAIT",
                blocked=True,
                block_reasons=("Safety clock is not timezone-aware",),
                checks=(),
                model_proposal=proposal,
            )

        # --- Gate 3 market-evidence boundary, revalidated at release time ---
        try:
            validate_market_price_inputs(request, prepared, now=current_time)
            checks.append("gate3_market_evidence_revalidated")
        except Exception as exc:  # AnalysisInputUnavailable or clock anomaly
            blocks.append(f"Market evidence failed release-time validation: {exc}")

        # --- Report-level evidence checks ---
        if report.symbol != request.symbol:
            blocks.append("Report symbol does not match the validated request symbol")
        present = {tf.interval for tf in report.timeframe_analyses}
        missing = sorted(EXPECTED_TIMEFRAMES - present)
        if missing:
            blocks.append(f"Missing timeframe(s): {', '.join(missing)}")
        if len(report.timeframe_analyses) < MIN_REPORT_TIMEFRAMES:
            blocks.append(
                f"Only {len(report.timeframe_analyses)} timeframe(s) analyzed; "
                f"minimum is {MIN_REPORT_TIMEFRAMES}"
            )
        usable = [tf for tf in report.timeframe_analyses if tf.usable]
        if len(usable) < MIN_USABLE_TIMEFRAMES:
            blocks.append(
                f"Only {len(usable)} usable timeframe(s); minimum is {MIN_USABLE_TIMEFRAMES}"
            )
        for tf in report.timeframe_analyses:
            if not tf.usable:
                blocks.append(f"Timeframe {tf.interval} is not usable")
            if not tf.series_complete:
                blocks.append(f"Incomplete candle series for timeframe {tf.interval}")
            if tf.candle_count < MIN_CANDLES_PER_TIMEFRAME:
                blocks.append(f"Timeframe {tf.interval} has only {tf.candle_count} candles")
            if tf.limitations:
                blocks.append(
                    f"Timeframe {tf.interval} has analysis limitations: "
                    + "; ".join(tf.limitations[:2])
                )
            if tf.last_closed_close is None or tf.last_closed_close <= 0:
                blocks.append(f"Timeframe {tf.interval} lacks a valid close price")
            if self._require_provenance and tf.snapshot_id is None:
                blocks.append(f"Timeframe {tf.interval} lacks provenance snapshot")

        # --- Alignment / readiness checks ---
        alignment = report.alignment
        if alignment.status == "conflicting":
            blocks.append("Multi-timeframe alignment is conflicting")
        if report.data_quality == "insufficient":
            blocks.append("Market data quality is insufficient")
        if report.readiness == "blocked":
            blocks.append("Report readiness is blocked")
        if report.missing_inputs:
            blocks.append("Missing required inputs: " + ", ".join(report.missing_inputs))

        # --- Candidate-level checks ---
        if candidate.blocking_reasons:
            blocks.extend(candidate.blocking_reasons)
        if candidate.proposed_decision in ("BUY", "SELL"):
            payload = (
                candidate.scenario
                if candidate.proposed_decision == "BUY"
                else candidate.exit_guidance
            )
            if payload is None:
                blocks.append("Candidate decision lacks its required payload")
        if candidate.scenario is not None:
            scenario = candidate.scenario
            if scenario.risk_reward_ratio < MIN_SAFETY_RISK_REWARD:
                blocks.append(
                    f"Scenario risk/reward {scenario.risk_reward_ratio} below "
                    f"safety minimum {MIN_SAFETY_RISK_REWARD}"
                )
            if scenario.stop_loss.price <= 0 or scenario.take_profit_1.price <= 0:
                blocks.append("Scenario contains a non-positive price level")

        # --- Proposal validation (Stage 3: Python validates Groq) ---
        final = self._resolve_proposal(proposal, candidate, blocks, checks)
        return SafetyResult(
            decision=final,
            scenario=(
                candidate.scenario if final == "BUY" and candidate.scenario is not None else None
            ),
            exit_guidance=(
                candidate.exit_guidance
                if final == "SELL" and candidate.exit_guidance is not None
                else None
            ),
            blocked=final == "WAIT" and bool(blocks),
            block_reasons=tuple(blocks),
            checks=tuple(checks),
            model_proposal=proposal,
        )

    @staticmethod
    def _resolve_proposal(
        proposal: str | None,
        candidate: StrategyOutcome,
        blocks: list[str],
        checks: list[str],
    ) -> Decision:
        """Map Groq's proposal to the final decision with veto authority."""
        if proposal is None:
            checks.append("model_proposal_unavailable")
            blocks.append("No model proposal; deterministic WAIT returned")
            return "WAIT"
        if proposal == "WAIT":
            checks.append("model_proposed_wait")
            return "WAIT"
        if blocks:
            checks.append("model_proposal_vetoed_by_safety")
            blocks.append(f"Model proposed {proposal} but safety checks failed; forced WAIT")
            return "WAIT"
        if proposal == candidate.proposed_decision and candidate.proposed_decision in (
            "BUY",
            "SELL",
        ):
            checks.append("model_proposal_confirmed_by_evidence")
            return candidate.proposed_decision
        # Proposal disagrees with the deterministic candidate.
        checks.append("model_proposal_mismatch")
        blocks.append(
            f"Model proposed {proposal} but deterministic evidence supports "
            f"{candidate.proposed_decision}; forced WAIT"
        )
        return "WAIT"

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Safety clock must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "EXPECTED_TIMEFRAMES",
    "MAX_PRICE_AGE_MS",
    "MIN_CANDLES_PER_TIMEFRAME",
    "MIN_REPORT_TIMEFRAMES",
    "MIN_SAFETY_RISK_REWARD",
    "MIN_USABLE_TIMEFRAMES",
    "DecisionSafetyGate",
]
