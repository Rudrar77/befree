"""Cached inference service for the authorized transaction-classification model."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import warnings
from pathlib import Path
from typing import Any

import joblib

logger = logging.getLogger(__name__)

MODEL_CATEGORIES = (
    "Food & Dining",
    "Shopping",
    "Transport",
    "Utilities",
    "Entertainment",
    "Salary",
    "Freelance / Business Income",
    "Rent",
    "Investment",
    "Cash Withdrawal",
    "Bank Charges",
    "Credit Card Payment",
    "Cashback / Rewards",
    "Healthcare",
    "Insurance",
    "Fitness",
    "Interest Income",
    "Charity/Donation",
    "Transfer",
    "Other",
)

MODEL_REPOSITORY_COMMIT = "f3c77eb2b9fb291c189dc3194d66f0c38d1d0e75"
MODEL_SHA256 = "63f7cffc114dd72572374db6f17f88aa35219b8514335263d1ded1fe62a31fd6"


class ClassifierUnavailableError(RuntimeError):
    """The configured pretrained model cannot be used."""


def normalize_description(description: str) -> str:
    """Apply the upstream model's lowercase and whitespace normalization."""
    return re.sub(r"\s+", " ", description.lower()).strip()


class PretrainedTransactionClassifier:
    """Load the verified sklearn pipeline once and reuse it for predictions."""

    def __init__(
        self,
        model_path: str | Path,
        expected_sha256: str = MODEL_SHA256,
        confidence_threshold: float = 0.6,
    ) -> None:
        self.model_path = Path(model_path)
        self.expected_sha256 = expected_sha256.lower()
        self.confidence_threshold = confidence_threshold
        self.model_version = f"transaction_classifier_v3@{MODEL_REPOSITORY_COMMIT[:12]}"
        self._pipeline: Any = None
        self._classes: tuple[str, ...] = ()
        self._lock = threading.RLock()
        self._last_error: str | None = None
        self._loading = False

    def _verify_artifact(self) -> None:
        try:
            if not self.model_path.is_file():
                raise ClassifierUnavailableError(
                    "The configured classifier model file is missing."
                )
            digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ClassifierUnavailableError(
                "The configured classifier model file cannot be read."
            ) from exc
        if digest != self.expected_sha256:
            raise ClassifierUnavailableError(
                "The classifier model checksum does not match the approved artifact."
            )

    def _load(self) -> None:
        if self._pipeline is not None:
            return

        with self._lock:
            if self._pipeline is not None:
                return

            self._loading = True
            try:
                self._verify_artifact()
                with warnings.catch_warnings(record=True) as load_warnings:
                    warnings.simplefilter("always")
                    pipeline = joblib.load(self.model_path)

                steps = getattr(pipeline, "named_steps", {})
                if not {"tfidf", "clf"}.issubset(steps):
                    raise ClassifierUnavailableError(
                        "The classifier artifact does not contain the expected TF-IDF and Logistic Regression steps."
                    )

                classes = tuple(str(value) for value in steps["clf"].classes_)
                if len(classes) != len(MODEL_CATEGORIES) or set(classes) != set(MODEL_CATEGORIES):
                    raise ClassifierUnavailableError(
                        "The classifier artifact category set does not match the supported 20 categories."
                    )

                self._pipeline = pipeline
                self._classes = classes
                self._last_error = None
                for warning in load_warnings:
                    logger.warning(
                        "Classifier artifact compatibility warning: %s",
                        warning.message,
                    )
            except ClassifierUnavailableError as exc:
                self._last_error = str(exc)
                raise
            except Exception as exc:
                self._last_error = "The classifier artifact could not be loaded."
                logger.exception("Could not load approved classifier artifact.")
                raise ClassifierUnavailableError(self._last_error) from exc
            finally:
                self._loading = False

    def ensure_loaded(self) -> None:
        """Load and validate the model once, raising if it cannot be used."""
        self._load()

    def status(self) -> dict[str, Any]:
        """Return model availability without forcing an expensive deserialization."""
        try:
            self._verify_artifact()
            available = True
            error = self._last_error
        except ClassifierUnavailableError as exc:
            available = False
            error = str(exc)

        return {
            "available": available,
            "loaded": self._pipeline is not None,
            "loading": self._loading,
            "model_version": self.model_version,
            "model_file": self.model_path.name,
            "categories": list(MODEL_CATEGORIES),
            "confidence_threshold": self.confidence_threshold,
            "error": error,
        }

    def classify(self, descriptions: list[str]) -> list[dict[str, Any]]:
        """Predict labels and probabilities, retaining uncertain labels for review."""
        if not descriptions:
            return []

        if any(not isinstance(description, str) for description in descriptions):
            raise ValueError("Every transaction description must be a string.")

        normalized = [normalize_description(description) for description in descriptions]
        results: list[dict[str, Any] | None] = [None] * len(descriptions)
        if not any(normalized):
            return [
                {
                    "category": None,
                    "confidence": 0.0,
                    "classification_method": "ML",
                    "needs_review": True,
                    "status": "needs_review",
                    "reason": "empty_description",
                }
                for _ in descriptions
            ]

        self._load()
        nonempty_indices = [
            index for index, description in enumerate(normalized) if description
        ]

        for index, description in enumerate(normalized):
            if not description:
                results[index] = {
                    "category": None,
                    "confidence": 0.0,
                    "classification_method": "ML",
                    "needs_review": True,
                    "status": "needs_review",
                    "reason": "empty_description",
                }

        if nonempty_indices:
            pipeline = self._pipeline
            vectorizer = pipeline.named_steps["tfidf"]
            documents = [normalized[index] for index in nonempty_indices]
            feature_rows = vectorizer.transform(documents)
            known_indices = [
                offset for offset in range(len(documents))
                if feature_rows[offset].getnnz() > 0
            ]
            known_index_set = set(known_indices)

            for offset, index in enumerate(nonempty_indices):
                if offset not in known_index_set:
                    results[index] = {
                        "category": None,
                        "confidence": 0.0,
                        "classification_method": "ML",
                        "needs_review": True,
                        "status": "needs_review",
                        "reason": "no_known_model_features",
                    }

            if known_indices:
                known_documents = [documents[offset] for offset in known_indices]
                try:
                    predictions = pipeline.predict(known_documents)
                    probabilities = pipeline.predict_proba(known_documents)
                except Exception as exc:
                    self._last_error = "The classifier could not process the supplied descriptions."
                    logger.exception("Pretrained transaction prediction failed.")
                    raise ClassifierUnavailableError(self._last_error) from exc

                for prediction, probability, offset in zip(
                    predictions, probabilities, known_indices
                ):
                    category = str(prediction)
                    category_index = self._classes.index(category)
                    confidence = round(float(probability[category_index]), 4)
                    needs_review = confidence < self.confidence_threshold
                    results[nonempty_indices[offset]] = {
                        "category": category,
                        "confidence": confidence,
                        "classification_method": "ML",
                        "needs_review": needs_review,
                        "status": "needs_review" if needs_review else "classified",
                        "reason": "below_confidence_threshold" if needs_review else None,
                    }

        return [result for result in results if result is not None]

    def predict(
        self, transactions: list[dict[str, Any]]
    ) -> list[tuple[str | None, float]]:
        """Adapt model predictions to the application's classification pipeline."""
        predictions = self.classify([
            str(transaction.get("description") or "")
            for transaction in transactions
        ])
        return [
            (prediction["category"], prediction["confidence"])
            for prediction in predictions
        ]


_classifier_registry: dict[tuple[str, str, float], PretrainedTransactionClassifier] = {}
_registry_lock = threading.Lock()


def get_pretrained_classifier() -> PretrainedTransactionClassifier:
    """Get the per-model singleton used by API and background processing."""
    from flask import current_app

    model_path = str(current_app.config["PRETRAINED_TRANSACTION_MODEL_PATH"])
    expected_sha256 = str(current_app.config["PRETRAINED_TRANSACTION_MODEL_SHA256"])
    confidence_threshold = float(
        current_app.config["PRETRAINED_TRANSACTION_CONFIDENCE_THRESHOLD"]
    )
    key = (model_path, expected_sha256.lower(), confidence_threshold)

    with _registry_lock:
        classifier = _classifier_registry.get(key)
        if classifier is None:
            classifier = PretrainedTransactionClassifier(
                model_path=model_path,
                expected_sha256=expected_sha256,
                confidence_threshold=confidence_threshold,
            )
            _classifier_registry[key] = classifier
    return classifier
