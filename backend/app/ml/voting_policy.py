"""Majority-vote policy and diagnostics for the three-model ensemble."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.ml.contracts import BaseDetector, DetectionResult

CONFIDENCE_THRESHOLD = 0.7
MIN_VOTES = 2


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ready": self.ready,
            "vote": self.vote,
            "raw_anomalous": self.raw_anomalous,
            "confidence": self.confidence,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VoteTally:
    """Immutable result of collecting all model votes for one reading."""

    votes: tuple[ModelVote, ...]

    @property
    def participating_models(self) -> list[str]:
        return [vote.model_id for vote in self.votes if vote.vote]

    @property
    def ready_models(self) -> list[str]:
        return [vote.model_id for vote in self.votes if vote.ready]

    @property
    def confirmed(self) -> bool:
        return len(self.participating_models) >= MIN_VOTES

    def to_details(
        self,
        *,
        inference_elapsed_ms: float | None = None,
    ) -> dict[str, Any]:
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
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "min_votes": MIN_VOTES,
            "voting_parameters": {
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "min_votes": MIN_VOTES,
                "models": [vote.model_id for vote in self.votes],
            },
        }
        if inference_elapsed_ms is not None:
            details["inference_elapsed_ms"] = round(inference_elapsed_ms, 3)
        return details


class MajorityVotePolicy:
    """Convert model outputs into one confirmed or non-confirmed detection."""

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
            votes.append(
                ModelVote(
                    model_id=model_id,
                    source=(result.source if result is not None else detector.source),
                    ready=ready,
                    vote=bool(
                        ready
                        and result is not None
                        and result.anomalous
                        and confidence >= CONFIDENCE_THRESHOLD
                    ),
                    raw_anomalous=(result.anomalous if result is not None else False),
                    confidence=confidence,
                    score=score,
                    reason=(result.reason if result is not None else "model_failed"),
                )
            )
        return VoteTally(tuple(votes))

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
                )
                for detector in detectors
            )
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
        )
        participating = tally.participating_models
        if tally.confirmed:
            confidence = max(vote.confidence for vote in tally.votes if vote.vote)
            score = max(vote.score for vote in tally.votes if vote.vote)
            details["level_reason"] = (
                "all three confident models confirmed"
                if len(participating) >= 3
                else "two independent models confirmed"
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
                reason="at least two confident detectors voted anomaly",
                level="red" if len(participating) >= 3 else "orange",
                source="ai_dual_confirm",
                message=(
                    f"[AI多模型确认] {reading.get('name', sensor_id)} 异常 "
                    f"(投票:{'+'.join(participating)}, 置信度:{confidence:.0%})"
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
                "insufficient confident model votes"
                if tally.ready_models
                else "models_not_ready"
            ),
            details=details,
        )
