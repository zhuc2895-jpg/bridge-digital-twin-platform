"""Majority-vote policy and diagnostics for the three-model ensemble."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.ml.contracts import BaseDetector, DetectionResult

CONFIDENCE_THRESHOLD = 0.7
MIN_VOTES = 2
COGNITION_THRESHOLD = 0.35
UNCERTAINTY_THRESHOLD = 0.45


@dataclass(frozen=True)
class ModelVote:
    """One model's complete contribution to a vote."""

    model_id: str
    source: str | None
    ready: bool
    vote: bool
    raw_anomalous: bool
    confidence: float
    score: float
    reason: str
    cognition: float = 1.0
    uncertainty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ready": self.ready,
            "vote": self.vote,
            "raw_anomalous": self.raw_anomalous,
            "confidence": self.confidence,
            "score": self.score,
            "reason": self.reason,
            "cognition": self.cognition,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class VoteTally:
    """Immutable result of collecting all model votes for one reading."""

    votes: tuple[ModelVote, ...]
    min_votes: int = MIN_VOTES
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    cognition_threshold: float = COGNITION_THRESHOLD
    uncertainty_threshold: float = UNCERTAINTY_THRESHOLD

    @property
    def participating_models(self) -> list[str]:
        return [vote.model_id for vote in self.votes if vote.vote]

    @property
    def ready_models(self) -> list[str]:
        return [vote.model_id for vote in self.votes if vote.ready]

    @property
    def confirmed(self) -> bool:
        return len(self.participating_models) >= self.min_votes

    @property
    def cognition(self) -> float:
        ready = [vote for vote in self.votes if vote.ready]
        return min((vote.cognition for vote in ready), default=1.0)

    @property
    def uncertainty(self) -> float:
        ready = [vote for vote in self.votes if vote.ready]
        return max((vote.uncertainty for vote in ready), default=0.0)

    @property
    def consensus_confidence(self) -> float:
        participating = [vote for vote in self.votes if vote.vote]
        if not participating:
            return 0.0
        average_confidence = sum(
            vote.confidence for vote in participating
        ) / len(participating)
        return max(0.0, min(1.0, average_confidence * self.cognition))

    @property
    def uncertainty_gate(self) -> bool:
        return (
            self.cognition < self.cognition_threshold
            or self.uncertainty >= self.uncertainty_threshold
        )

    def to_details(
        self,
        *,
        inference_elapsed_ms: float | None = None,
        confidence_threshold: float | None = None,
    ) -> dict[str, Any]:
        effective_confidence_threshold = (
            self.confidence_threshold
            if confidence_threshold is None
            else confidence_threshold
        )
        participating = self.participating_models
        details = {
            "votes": {vote.model_id: vote.vote for vote in self.votes},
            "scores": {vote.model_id: vote.score for vote in self.votes},
            "confidences": {vote.model_id: vote.confidence for vote in self.votes},
            "vote_count": len(participating),
            "participating_models": participating,
            "triggered_models": list(participating),
            "ready_models": self.ready_models,
            "model_ready": bool(self.ready_models),
            "model_results": {vote.model_id: vote.to_dict() for vote in self.votes},
            "confidence_threshold": effective_confidence_threshold,
            "min_votes": self.min_votes,
            "cognition": round(self.cognition, 6),
            "uncertainty": round(self.uncertainty, 6),
            "consensus_confidence": round(self.consensus_confidence, 6),
            "uncertainty_gate": self.uncertainty_gate,
            "cognition_threshold": self.cognition_threshold,
            "uncertainty_threshold": self.uncertainty_threshold,
            "gate_reasons": [
                reason
                for reason, active in (
                    ("low_cognition", self.cognition < self.cognition_threshold),
                    (
                        "high_uncertainty",
                        self.uncertainty >= self.uncertainty_threshold,
                    ),
                )
                if active
            ],
            "voting_parameters": {
                "confidence_threshold": effective_confidence_threshold,
                "min_votes": self.min_votes,
                "cognition_threshold": self.cognition_threshold,
                "uncertainty_threshold": self.uncertainty_threshold,
                "models": [vote.model_id for vote in self.votes],
            },
        }
        if inference_elapsed_ms is not None:
            details["inference_elapsed_ms"] = round(inference_elapsed_ms, 3)
        return details


class MajorityVotePolicy:
    """Convert model outputs into one confirmed or non-confirmed detection."""

    def __init__(
        self,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        min_votes: int = MIN_VOTES,
        cognition_threshold: float = COGNITION_THRESHOLD,
        uncertainty_threshold: float = UNCERTAINTY_THRESHOLD,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between zero and one")
        if not 2 <= min_votes <= 3:
            raise ValueError("min_votes must be between two and three")
        if not 0 <= cognition_threshold <= 1:
            raise ValueError("cognition_threshold must be between zero and one")
        if not 0 <= uncertainty_threshold <= 1:
            raise ValueError("uncertainty_threshold must be between zero and one")
        self.confidence_threshold = float(confidence_threshold)
        self.min_votes = int(min_votes)
        self.cognition_threshold = float(cognition_threshold)
        self.uncertainty_threshold = float(uncertainty_threshold)

    def tally(
        self,
        detectors: Sequence[BaseDetector],
        results: Sequence[DetectionResult | None],
        readiness: Mapping[str, bool],
    ) -> VoteTally:
        votes = []
        for detector, result in zip(detectors, results, strict=True):
            model_id = detector.detector_id
            ready = readiness.get(model_id, False)
            confidence = float(result.confidence) if result is not None else 0.0
            score = float(result.score) if result is not None else 0.0
            details = result.details if result is not None else {}
            cognition = _bounded_float(details.get("cognition"), 1.0)
            uncertainty = _bounded_float(details.get("uncertainty"), 0.0)
            votes.append(
                ModelVote(
                    model_id=model_id,
                    source=(result.source if result is not None else detector.source),
                    ready=ready,
                    vote=bool(
                        ready
                        and result is not None
                        and result.anomalous
                        and confidence >= self.confidence_threshold
                    ),
                    raw_anomalous=(result.anomalous if result is not None else False),
                    confidence=confidence,
                    score=score,
                    reason=(result.reason if result is not None else "model_failed"),
                    cognition=cognition,
                    uncertainty=uncertainty,
                )
            )
        return VoteTally(
            tuple(votes),
            min_votes=self.min_votes,
            confidence_threshold=self.confidence_threshold,
            cognition_threshold=self.cognition_threshold,
            uncertainty_threshold=self.uncertainty_threshold,
        )

    def known_normal(
        self,
        detectors: Sequence[BaseDetector],
    ) -> VoteTally:
        return VoteTally(
            tuple(
                ModelVote(
                    model_id=detector.detector_id,
                    source=detector.source,
                    ready=True,
                    vote=False,
                    raw_anomalous=False,
                    confidence=0.0,
                    score=0.0,
                    reason="known normal batch",
                    cognition=1.0,
                    uncertainty=0.0,
                )
                for detector in detectors
            ),
            min_votes=self.min_votes,
            confidence_threshold=self.confidence_threshold,
            cognition_threshold=self.cognition_threshold,
            uncertainty_threshold=self.uncertainty_threshold,
        )

    def result(
        self,
        reading: Mapping[str, Any],
        tally: VoteTally,
        *,
        detector_id: str,
        inference_elapsed_ms: float | None = None,
    ) -> DetectionResult:
        sensor_id = str(reading["sensor_id"])
        details = tally.to_details(
            inference_elapsed_ms=inference_elapsed_ms,
            confidence_threshold=self.confidence_threshold,
        )
        participating = tally.participating_models
        if tally.confirmed and not tally.uncertainty_gate:
            confidence = max(vote.confidence for vote in tally.votes if vote.vote)
            score = max(vote.score for vote in tally.votes if vote.vote)
            details["level_reason"] = (
                "all three confident models confirmed"
                if len(participating) >= 3
                else f"{self.min_votes} independent models confirmed"
            )
            return DetectionResult(
                sensor_id=sensor_id,
                name=str(reading.get("name", sensor_id)),
                value=float(reading["value"]),
                timestamp=float(reading["timestamp"]),
                detector_id=detector_id,
                anomalous=True,
                score=score,
                confidence=confidence,
                reason=(
                    f"at least {self.min_votes} confident detectors voted anomaly"
                ),
                level="red" if len(participating) >= 3 else "orange",
                source="ai_dual_confirm",
                message=(
                    f"[AI多模型确认] {reading.get('name', sensor_id)} 异常 "
                    f"(投票:{'+'.join(participating)}, 置信度:{confidence:.0%})"
                ),
                details=details,
            )

        if tally.confirmed:
            confidence = max(vote.confidence for vote in tally.votes if vote.vote)
            score = max(vote.score for vote in tally.votes if vote.vote)
            details["level_reason"] = (
                "uncertainty gate caps alert level at yellow"
            )
            return DetectionResult(
                sensor_id=sensor_id,
                name=str(reading.get("name", sensor_id)),
                value=float(reading["value"]),
                timestamp=float(reading["timestamp"]),
                detector_id=detector_id,
                anomalous=True,
                score=score,
                confidence=confidence,
                reason="low cognition or high uncertainty requires arbitration",
                level="yellow",
                source="ai_dual_confirm",
                message=(
                    f"[AI疑似] {reading.get('name', sensor_id)} 异常 "
                    f"(认知度:{tally.cognition:.0%}, "
                    f"不确定度:{tally.uncertainty:.0%})，进入特征仲裁"
                ),
                details=details,
            )

        return DetectionResult(
            sensor_id=sensor_id,
            name=str(reading.get("name", sensor_id)),
            value=float(reading["value"]),
            timestamp=float(reading["timestamp"]),
            detector_id=detector_id,
            anomalous=False,
            score=max((vote.score for vote in tally.votes), default=0.0),
            confidence=max(
                (vote.confidence for vote in tally.votes),
                default=0.0,
            ),
            reason=(
                (
                    "uncertainty gate requires arbitration"
                    if tally.uncertainty_gate
                    else "insufficient confident model votes"
                )
                if tally.ready_models
                else "models_not_ready"
            ),
            details=details,
        )


def _bounded_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
