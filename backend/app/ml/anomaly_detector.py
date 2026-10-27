"""Pluggable baseline-aware ensemble anomaly detector."""

from __future__ import annotations

from collections import deque
import time
from typing import Any, Dict, Mapping, Optional

import numpy as np

from app.ml.baseline import BaselineLearner
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult


class AnomalyDetector(BaseDetector):
    """STALWART-inspired ensemble behind the common detector contract."""

    detector_id = "ensemble"
    display_name = "STALWART ensemble"

    WARMUP_COUNT = 100

    def __init__(self, window_size: int = 200):
        self.window_size = window_size

        self.stalwart_loaded = True
        self.gan_ae_loaded = True
        self.iforest_loaded = True

        self._buffers: Dict[str, deque] = {}
        self._ema: Dict[str, float] = {}
        self._ema_slow: Dict[str, float] = {}
        self._alpha_fast = 0.3
        self._alpha_slow = 0.05
        self._baselines = BaselineLearner(
            required_readings=self.WARMUP_COUNT,
            fast_alpha=self._alpha_fast,
            slow_alpha=self._alpha_slow,
        )

        self._total_detections = 0
        self._stalwart_detections = 0
        self._gan_ae_detections = 0
        self._iforest_detections = 0
        self._dual_confirmations = 0
        self._ml_alerts_triggered = 0

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        """Evaluate one reading after its sensor baseline is ready."""
        sid = str(reading["sensor_id"])
        value = float(reading["value"])
        name = str(reading.get("name", sid))
        ts = float(reading.get("timestamp", time.time()))
        status = self._baselines.get_status(sid)

        if not status.ready:
            return self._waiting_result(sid, name, value, ts, status)

        previous_ema = self._ema.get(sid)
        previous_ema_slow = self._ema_slow.get(sid)
        if sid not in self._ema or sid not in self._ema_slow:
            self._ema[sid] = float(status.ema_fast or status.mean or value)
            self._ema_slow[sid] = float(status.ema_slow or status.mean or value)
        else:
            self._ema[sid] = (
                self._alpha_fast * value + (1 - self._alpha_fast) * self._ema[sid]
            )
            self._ema_slow[sid] = (
                self._alpha_slow * value
                + (1 - self._alpha_slow) * self._ema_slow[sid]
            )

        buffer = self._buffers.setdefault(sid, deque(maxlen=self.window_size))
        evicted_value = (
            buffer[0]
            if buffer.maxlen is not None and len(buffer) == buffer.maxlen
            else None
        )
        buffer.append(value)

        baseline_mean = float(status.mean or 0.0)
        baseline_std = float(status.std or 0.0)
        if baseline_std <= 0.01 and abs(value - baseline_mean) <= 0.01:
            self._total_detections += 1
            return DetectionResult(
                sensor_id=sid,
                name=name,
                value=value,
                timestamp=ts,
                detector_id=self.detector_id,
                anomalous=False,
                reason="normal",
                details={"baseline": status.to_dict()},
            )

        score_stalwart = self._score_stalwart(sid, value)
        score_gan_ae = self._score_gan_ae(sid, value)
        score_iforest = self._score_isolation_forest(sid, value)
        votes = {
            "stalwart": score_stalwart > 0.6,
            "gan_ae": score_gan_ae > 0.6,
            "isolation_forest": score_iforest > 0.6,
        }
        vote_count = sum(votes.values())
        max_score = max(score_stalwart, score_gan_ae, score_iforest)
        details = {
            "votes": votes,
            "scores": {
                "stalwart": score_stalwart,
                "gan_ae": score_gan_ae,
                "isolation_forest": score_iforest,
            },
        }

        if vote_count >= 2:
            self._dual_confirmations += 1
            level = "red" if max_score > 0.85 else "orange"
            triggered = [name for name, voted in votes.items() if voted]
            self._ml_alerts_triggered += 1
            self._total_detections += 1
            self._rollback_observation(
                sid,
                previous_ema,
                previous_ema_slow,
                evicted_value,
            )
            return DetectionResult(
                sensor_id=sid,
                name=name,
                value=value,
                timestamp=ts,
                detector_id=self.detector_id,
                anomalous=True,
                score=max_score,
                confidence=max_score,
                reason="at least two detectors voted anomaly",
                level=level,
                source="ai_dual_confirm",
                message=(
                    f"[AI多模型确认] {name} 异常 "
                    f"(投票:{'+'.join(triggered)}, 置信度:{max_score:.0%})"
                ),
                details=details,
            )

        if vote_count == 1:
            arbitration = self._feature_arbitration(sid, value, name, ts)
            if arbitration is not None:
                self._ml_alerts_triggered += 1
                self._total_detections += 1
                self._rollback_observation(
                    sid,
                    previous_ema,
                    previous_ema_slow,
                    evicted_value,
                )
                return arbitration

        self._total_detections += 1
        return DetectionResult(
            sensor_id=sid,
            name=name,
            value=value,
            timestamp=ts,
            detector_id=self.detector_id,
            anomalous=False,
            score=max_score,
            confidence=max_score,
            reason="normal",
            details=details,
        )

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        sid = str(reading["sensor_id"])
        value = float(reading["value"])
        status = self._baselines.get_status(sid)
        if status.ready or not is_normal:
            return status

        self._buffers.setdefault(sid, deque(maxlen=self.window_size)).append(value)
        status = self._baselines.observe(sid, value, is_normal=True)
        if status.ready:
            self._ema[sid] = float(status.ema_fast or status.mean or value)
            self._ema_slow[sid] = float(status.ema_slow or status.mean or value)
        return status

    def get_baseline_status(
        self,
        sensor_id: str | None = None,
    ) -> BaselineStatus | dict[str, BaselineStatus]:
        if sensor_id is not None:
            return self._baselines.get_status(sensor_id)
        return self._baselines.get_statuses()

    def reset_baseline(self, sensor_id: str | None = None) -> None:
        self._baselines.reset(sensor_id)
        if sensor_id is None:
            self._buffers.clear()
            self._ema.clear()
            self._ema_slow.clear()
            return

        self._buffers.pop(sensor_id, None)
        self._ema.pop(sensor_id, None)
        self._ema_slow.pop(sensor_id, None)

    def _waiting_result(
        self,
        sid: str,
        name: str,
        value: float,
        ts: float,
        status: BaselineStatus,
    ) -> DetectionResult:
        return DetectionResult(
            sensor_id=sid,
            name=name,
            value=value,
            timestamp=ts,
            detector_id=self.detector_id,
            anomalous=False,
            reason=f"baseline_{status.state}",
            details={"baseline": status.to_dict()},
        )


    def _rollback_observation(
        self,
        sid: str,
        previous_ema: float | None,
        previous_ema_slow: float | None,
        evicted_value: float | None,
    ) -> None:
        buffer = self._buffers.get(sid)
        if buffer:
            buffer.pop()
            if evicted_value is not None:
                buffer.appendleft(evicted_value)
        if previous_ema is None:
            self._ema.pop(sid, None)
        else:
            self._ema[sid] = previous_ema
        if previous_ema_slow is None:
            self._ema_slow.pop(sid, None)
        else:
            self._ema_slow[sid] = previous_ema_slow

    def _score_stalwart(self, sid: str, value: float) -> float:
        """STALWART-inspired score from EMA divergence and baseline deviation."""
        ema_fast = self._ema[sid]
        ema_slow = self._ema_slow[sid]
        baseline = self._baselines.get_status(sid)
        base_mean = float(baseline.mean or 0.0)
        base_std = max(float(baseline.std or 0.0), 0.01)

        z_score = abs(value - base_mean) / base_std
        ema_diff = abs(ema_fast - ema_slow) / base_std
        score = min((z_score * 0.6 + ema_diff * 0.4) / 5.0, 1.0)

        if score > 0.6:
            self._stalwart_detections += 1
        return round(score, 4)

    def _score_gan_ae(self, sid: str, value: float) -> float:
        """Compare recent and historical windows to estimate reconstruction error."""
        buf = list(self._buffers[sid])
        if len(buf) < 80:
            return 0.0

        recent = np.array(buf[-20:])
        historical = np.array(buf[-80:-20])
        recent_mean = np.mean(recent)
        hist_mean = np.mean(historical)
        recent_std = np.std(recent) if np.std(recent) > 0.01 else 0.01
        hist_std = np.std(historical) if np.std(historical) > 0.01 else 0.01

        mean_shift = abs(recent_mean - hist_mean) / hist_std
        std_ratio = max(recent_std / hist_std, hist_std / recent_std)
        extremeness = abs(value - recent_mean) / recent_std if recent_std > 0 else 0
        score = min(
            (
                mean_shift * 0.4
                + (std_ratio - 1) * 0.3
                + extremeness * 0.3
            )
            / 4.0,
            1.0,
        )

        if score > 0.6:
            self._gan_ae_detections += 1
        return round(score, 4)

    def _score_isolation_forest(self, sid: str, value: float) -> float:
        """Estimate how isolated the current value is in its recent window."""
        buf = list(self._buffers[sid])
        if len(buf) < 50:
            return 0.0

        sorted_arr = np.sort(np.array(buf))
        n = len(sorted_arr)
        idx = int(np.searchsorted(sorted_arr, value))
        position_ratio = idx / n
        isolation = 2 * abs(position_ratio - 0.5)

        if idx == 0:
            nn_dist = sorted_arr[1] - sorted_arr[0]
        elif idx >= n - 1:
            nn_dist = sorted_arr[-1] - sorted_arr[-2]
        else:
            nn_dist = min(value - sorted_arr[idx - 1], sorted_arr[idx] - value)

        mean_dist = float(np.mean(np.abs(np.diff(sorted_arr))))
        if mean_dist < 0.001:
            mean_dist = 0.001
        nn_ratio = nn_dist / mean_dist
        score = min(
            isolation * 0.5 + min(nn_ratio / 5.0, 1.0) * 0.5,
            1.0,
        )

        if score > 0.6:
            self._iforest_detections += 1
        return round(score, 4)

    def _feature_arbitration(
        self,
        sid: str,
        value: float,
        name: str,
        ts: float,
    ) -> Optional[DetectionResult]:
        """Confirm a single-model vote with multi-window features."""
        buf = list(self._buffers[sid])
        if len(buf) < 60:
            return None

        arr = np.array(buf)
        features = {}
        for window_size in [5, 10, 30]:
            window = arr[-window_size:]
            features[f"mean_{window_size}"] = float(np.mean(window))
            features[f"std_{window_size}"] = float(np.std(window))
            features[f"max_{window_size}"] = float(np.max(window))
            features[f"min_{window_size}"] = float(np.min(window))

        diffs = np.diff(arr[-10:])
        features["roc"] = float(np.mean(np.abs(diffs)))
        features["max_jump"] = float(np.max(np.abs(diffs)))

        baseline = self._baselines.get_status(sid)
        base_mean = float(baseline.mean or 0.0)
        base_std = max(float(baseline.std or 0.0), 0.01)
        deviation = abs(value - base_mean) / base_std

        if deviation > 3.5 or features["max_jump"] > base_std * 4:
            level = "orange" if deviation < 5 else "yellow"
            return DetectionResult(
                sensor_id=sid,
                name=name,
                value=value,
                timestamp=ts,
                detector_id=self.detector_id,
                anomalous=True,
                score=deviation / 10.0,
                confidence=min(deviation / 10.0, 0.8),
                reason="single model confirmed by feature arbitration",
                level=level,
                source="ai_feature_arbitration",
                message=(
                    f"[AI特征仲裁] {name} 偏离{deviation:.1f}σ "
                    "(单模型触发+特征确认)"
                ),
                details={"features": features},
            )

        return None

    def get_stats(self) -> dict:
        statuses = self._baselines.get_statuses()
        return {
            "total_detections": self._total_detections,
            "ml_alerts_triggered": self._ml_alerts_triggered,
            "baseline_readings": sum(status.readings for status in statuses.values()),
            "stalwart_detections": self._stalwart_detections,
            "gan_ae_detections": self._gan_ae_detections,
            "iforest_detections": self._iforest_detections,
            "dual_confirmations": self._dual_confirmations,
            "models_loaded": {
                "STALWART-LSTM": self.stalwart_loaded,
                "GAN-Autoencoder": self.gan_ae_loaded,
                "IsolationForest": self.iforest_loaded,
            },
        }
