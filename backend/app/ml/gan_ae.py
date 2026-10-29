"""Adversarial autoencoder anomaly detector using reconstruction error."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Any, Mapping

import numpy as np

from app.ml.baseline import BaselineLearner
from app.ml.contracts import BaseDetector, BaselineStatus, DetectionResult


@dataclass(frozen=True)
class _AdversarialModel:
    generator_weight: np.ndarray
    generator_bias: np.ndarray
    discriminator_weight: np.ndarray
    discriminator_bias: float
    discriminator_loss: float
    steps: int


@dataclass(frozen=True)
class _ReconstructionModel:
    window_mean: np.ndarray
    window_scale: float
    components: np.ndarray
    error_mean: float
    error_std: float
    threshold: float
    training_windows: int
    adversarial: _AdversarialModel


@dataclass
class _SensorState:
    sensor_id: str
    normal_values: deque[float] = field(default_factory=deque)
    history: deque[float] = field(default_factory=deque)
    model: _ReconstructionModel | None = None


class GanAEDetector(BaseDetector):
    """Combine linear-AE reconstruction with a GAN normal-window discriminator."""

    detector_id = "gan_ae"
    display_name = "GAN-AE Reconstruction"
    source = "ai_gan_ae"

    def __init__(
        self,
        *,
        required_readings: int = 100,
        sequence_length: int = 8,
        window_size: int = 200,
        latent_rank: int = 1,
        threshold_sigma: float = 3.0,
        min_scale: float = 1e-9,
        adversarial_steps: int = 25,
        adversarial_learning_rate: float = 0.05,
        random_state: int = 42,
    ) -> None:
        if required_readings < 2:
            raise ValueError("required_readings must be at least two")
        if window_size < 2:
            raise ValueError("window_size must be at least two")
        if not 2 <= sequence_length <= window_size:
            raise ValueError("sequence_length must be between two and window_size")
        if not 1 <= latent_rank < sequence_length:
            raise ValueError("latent_rank must be between one and sequence_length - 1")
        if threshold_sigma <= 0:
            raise ValueError("threshold_sigma must be positive")
        if min_scale <= 0:
            raise ValueError("min_scale must be positive")
        if adversarial_steps < 1:
            raise ValueError("adversarial_steps must be positive")
        if adversarial_learning_rate <= 0:
            raise ValueError("adversarial_learning_rate must be positive")

        self.sequence_length = sequence_length
        self.window_size = window_size
        self.latent_rank = latent_rank
        self.threshold_sigma = float(threshold_sigma)
        self.min_scale = float(min_scale)
        self.adversarial_steps = adversarial_steps
        self.adversarial_learning_rate = float(adversarial_learning_rate)
        self.random_state = random_state
        self._baselines = BaselineLearner(required_readings=required_readings)
        self._states: dict[str, _SensorState] = {}
        self._total_detections = 0
        self._anomalies_detected = 0

    @property
    def parameters(self) -> dict[str, float | int]:
        return {
            "required_readings": self._baselines.required_readings,
            "sequence_length": self.sequence_length,
            "window_size": self.window_size,
            "latent_rank": self.latent_rank,
            "threshold_sigma": self.threshold_sigma,
            "min_scale": self.min_scale,
            "adversarial_steps": self.adversarial_steps,
            "adversarial_learning_rate": self.adversarial_learning_rate,
            "random_state": self.random_state,
        }

    def learn_baseline(
        self,
        reading: Mapping[str, Any],
        *,
        is_normal: bool = True,
    ) -> BaselineStatus:
        sensor_id = str(reading["sensor_id"])
        value = float(reading["value"])
        state = self._state_for(sensor_id)
        status = self._baselines.observe(
            sensor_id,
            value,
            is_normal=is_normal,
        )
        if is_normal:
            state.normal_values.append(value)
            state.history.append(value)
        if status.ready and state.model is None:
            state.model = self._fit_model(state)
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
            self._states.clear()
            return
        self._states.pop(str(sensor_id), None)

    def detect_one(self, reading: Mapping[str, Any]) -> DetectionResult:
        sensor_id = str(reading["sensor_id"])
        value = float(reading["value"])
        status = self._baselines.get_status(sensor_id)
        state = self._state_for(sensor_id)
        self._total_detections += 1

        if not status.ready:
            return self.make_result(
                reading,
                anomalous=False,
                reason=f"baseline_{status.state}",
                details={"vote": False, "baseline": status.to_dict()},
            )

        model = state.model
        if model is None:
            state.model = self._fit_model(state)
            model = state.model
        if model is None:
            return self.make_result(
                reading,
                anomalous=False,
                reason="gan_ae_not_ready",
                details={
                    "vote": False,
                    "model_ready": False,
                    "training_readings": len(state.normal_values),
                    "parameters": self.parameters,
                },
            )

        if (
            model.window_scale <= self.min_scale * 10
            and abs(value - model.window_mean[0]) <= self.min_scale * 10
        ):
            state.history.append(value)
            discriminator_probability = self._discriminator_probability(
                model.window_mean,
                model,
            )
            return self.make_result(
                reading,
                anomalous=False,
                score=0.0,
                confidence=0.0,
                reason="steady value matches the learned reconstruction window",
                details={
                    "vote": False,
                    "model_ready": True,
                    "reconstruction_error": 0.0,
                    "reconstruction_mean": round(model.error_mean, 9),
                    "reconstruction_std": round(model.error_std, 9),
                    "threshold": round(model.threshold, 9),
                    "threshold_sigma": self.threshold_sigma,
                    "training_windows": model.training_windows,
                    "gan_enabled": True,
                    "discriminator_real_probability": round(
                        discriminator_probability,
                        6,
                    ),
                    "adversarial_steps": model.adversarial.steps,
                    "discriminator_loss": round(
                        model.adversarial.discriminator_loss,
                        6,
                    ),
                    "parameters": self.parameters,
                },
            )

        window = self._window_with(state, value)
        error = self._reconstruction_error(window, model)
        discriminator_probability = self._discriminator_probability(window, model)
        anomalous = error > model.threshold
        score = min(1.0, error / max(model.threshold * 2.0, self.min_scale))
        confidence = min(
            1.0,
            self._confidence(error, model) + (1.0 - discriminator_probability) * 0.05,
        )
        if anomalous:
            self._anomalies_detected += 1
        else:
            state.history.append(value)

        reason = (
            f"reconstruction error {error:.6f} exceeds threshold {model.threshold:.6f}"
            if anomalous
            else f"reconstruction error {error:.6f} is within threshold"
        )
        return self.make_result(
            reading,
            anomalous=anomalous,
            score=round(score, 6),
            confidence=round(confidence, 6),
            reason=reason,
            details={
                "vote": anomalous,
                "model_ready": True,
                "reconstruction_error": round(error, 9),
                "reconstruction_mean": round(model.error_mean, 9),
                "reconstruction_std": round(model.error_std, 9),
                "threshold": round(model.threshold, 9),
                "threshold_sigma": self.threshold_sigma,
                "training_windows": model.training_windows,
                "gan_enabled": True,
                "discriminator_real_probability": round(
                    discriminator_probability,
                    6,
                ),
                "adversarial_steps": model.adversarial.steps,
                "discriminator_loss": round(
                    model.adversarial.discriminator_loss,
                    6,
                ),
                "parameters": self.parameters,
            },
        )

    def get_stats(self) -> dict:
        statuses = self._baselines.get_statuses()
        sensors = {}
        for sensor_id, status in statuses.items():
            state = self._states.get(sensor_id)
            model = state.model if state is not None else None
            sensors[sensor_id] = {
                "ready": status.ready,
                "readings": status.readings,
                "model_ready": model is not None,
                "training_windows": model.training_windows if model else 0,
                "reconstruction_mean": (
                    model.error_mean if model is not None else None
                ),
                "reconstruction_std": (model.error_std if model is not None else None),
                "threshold": model.threshold if model is not None else None,
                "adversarial_steps": (
                    model.adversarial.steps if model is not None else 0
                ),
                "discriminator_loss": (
                    model.adversarial.discriminator_loss if model is not None else None
                ),
            }

        return {
            "total_detections": self._total_detections,
            "anomalies_detected": self._anomalies_detected,
            "baseline_readings": sum(status.readings for status in statuses.values()),
            "parameters": self.parameters,
            "sensors": sensors,
        }

    def _state_for(self, sensor_id: str) -> _SensorState:
        state = self._states.get(sensor_id)
        if state is None:
            state = _SensorState(
                sensor_id=sensor_id,
                normal_values=deque(maxlen=self.window_size),
                history=deque(maxlen=self.window_size),
            )
            self._states[sensor_id] = state
        return state

    def _fit_model(self, state: _SensorState) -> _ReconstructionModel | None:
        values = np.asarray(state.normal_values, dtype=float)
        if values.size < self.sequence_length:
            return None
        windows = np.lib.stride_tricks.sliding_window_view(
            values,
            self.sequence_length,
        )
        window_mean = windows.mean(axis=0)
        centered = windows - window_mean
        rms = float(np.sqrt(np.mean(np.square(centered))))
        value_scale = float(np.mean(np.abs(window_mean)))
        window_scale = max(rms, value_scale * 1e-6, self.min_scale)
        normalized = centered / window_scale
        # SVD learns the optimal linear autoencoder: the right vectors are
        # the decoder basis and their transpose forms the encoder.
        _, _, right_vectors = np.linalg.svd(normalized, full_matrices=False)
        components = right_vectors[: self.latent_rank]
        reconstructed = (normalized @ components.T) @ components
        errors = np.mean(np.square(normalized - reconstructed), axis=1)
        error_mean = float(np.mean(errors))
        error_std = float(np.std(errors))
        threshold = error_mean + self.threshold_sigma * error_std
        adversarial = self._train_adversarial_model(
            normalized,
            sensor_id=state.sensor_id,
        )
        return _ReconstructionModel(
            window_mean=window_mean,
            window_scale=window_scale,
            components=components,
            error_mean=error_mean,
            error_std=error_std,
            threshold=threshold,
            training_windows=len(windows),
            adversarial=adversarial,
        )

    def _train_adversarial_model(
        self,
        normalized_windows: np.ndarray,
        *,
        sensor_id: str,
    ) -> _AdversarialModel:
        """Train a normal-window generator and discriminator for the GAN branch."""
        sample_count, window_length = normalized_windows.shape
        latent_width = max(2, min(self.latent_rank + 1, window_length))
        seed = self.random_state + sum(
            (index + 1) * ord(character) for index, character in enumerate(sensor_id)
        )
        rng = np.random.default_rng(seed)
        generator_weight = rng.normal(
            0.0,
            1.0 / math.sqrt(latent_width),
            size=(latent_width, window_length),
        )
        generator_bias = np.zeros(window_length, dtype=float)
        discriminator_weight = np.zeros(window_length, dtype=float)
        discriminator_bias = 0.0
        learning_rate = self.adversarial_learning_rate

        for _ in range(self.adversarial_steps):
            latent = rng.normal(size=(sample_count, latent_width))
            generated = np.tanh(latent @ generator_weight + generator_bias)
            real_probability = self._sigmoid(
                normalized_windows @ discriminator_weight + discriminator_bias
            )
            fake_probability = self._sigmoid(
                generated @ discriminator_weight + discriminator_bias
            )

            discriminator_weight -= (
                learning_rate
                * (
                    normalized_windows.T @ (real_probability - 1.0)
                    + generated.T @ fake_probability
                )
                / sample_count
            )
            discriminator_bias -= learning_rate * (
                float(np.mean(real_probability - 1.0))
                + float(np.mean(fake_probability))
            )
            discriminator_weight = np.clip(discriminator_weight, -5.0, 5.0)

            latent = rng.normal(size=(sample_count, latent_width))
            generated = np.tanh(latent @ generator_weight + generator_bias)
            fake_probability = self._sigmoid(
                generated @ discriminator_weight + discriminator_bias
            )
            generator_delta = (fake_probability[:, None] - 1.0) * (
                1.0 - np.square(generated)
            )
            generator_weight -= (
                learning_rate * (latent.T @ generator_delta) / sample_count
            )
            generator_bias -= learning_rate * np.mean(generator_delta, axis=0)
            generator_weight = np.clip(generator_weight, -5.0, 5.0)

        final_latent = rng.normal(size=(sample_count, latent_width))
        final_fake = np.tanh(final_latent @ generator_weight + generator_bias)
        final_real_probability = self._sigmoid(
            normalized_windows @ discriminator_weight + discriminator_bias
        )
        final_fake_probability = self._sigmoid(
            final_fake @ discriminator_weight + discriminator_bias
        )
        epsilon = 1e-9
        discriminator_loss = float(
            -np.mean(np.log(np.clip(final_real_probability, epsilon, 1.0)))
            - np.mean(np.log(np.clip(1.0 - final_fake_probability, epsilon, 1.0)))
        )
        return _AdversarialModel(
            generator_weight=generator_weight,
            generator_bias=generator_bias,
            discriminator_weight=discriminator_weight,
            discriminator_bias=discriminator_bias,
            discriminator_loss=discriminator_loss,
            steps=self.adversarial_steps,
        )

    def _discriminator_probability(
        self,
        window: np.ndarray,
        model: _ReconstructionModel,
    ) -> float:
        normalized = (window - model.window_mean) / model.window_scale
        logit = (
            float(normalized @ model.adversarial.discriminator_weight)
            + model.adversarial.discriminator_bias
        )
        return float(self._sigmoid(logit))

    @staticmethod
    def _sigmoid(value: float | np.ndarray) -> np.ndarray:
        clipped = np.clip(value, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-clipped))

    def _window_with(self, state: _SensorState, value: float) -> np.ndarray:
        history = list(state.history)[-(self.sequence_length - 1) :]
        while len(history) < self.sequence_length - 1:
            history.insert(0, value)
        return np.asarray([*history, value], dtype=float)

    def _reconstruction_error(
        self,
        window: np.ndarray,
        model: _ReconstructionModel,
    ) -> float:
        normalized = (window - model.window_mean) / model.window_scale
        latent = self._encode(normalized, model)
        reconstructed = self._decode(latent, model)
        return float(np.mean(np.square(normalized - reconstructed)))

    @staticmethod
    def _encode(
        normalized_window: np.ndarray,
        model: _ReconstructionModel,
    ) -> np.ndarray:
        return normalized_window @ model.components.T

    @staticmethod
    def _decode(
        latent: np.ndarray,
        model: _ReconstructionModel,
    ) -> np.ndarray:
        return latent @ model.components

    def _confidence(self, error: float, model: _ReconstructionModel) -> float:
        if error <= model.threshold:
            if model.threshold <= self.min_scale:
                return 0.0
            return min(0.69, 0.69 * error / model.threshold)
        denominator = max(model.error_std, model.threshold * 0.05, self.min_scale)
        excess = (error - model.threshold) / denominator
        return min(1.0, 0.7 + 0.3 * (1.0 - math.exp(-excess)))
