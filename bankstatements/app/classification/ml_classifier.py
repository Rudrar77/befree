"""Machine Learning classifier for bank statement transactions."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.classification.feature_extractor import extract_features_df

logger = logging.getLogger(__name__)


class TransactionClassifier:
    """Production ML classifier using TF-IDF and tabular features."""

    def __init__(self, model_version: str = "v1.0.0") -> None:
        self.model_version = model_version
        self.pipeline: Optional[Pipeline] = None
        self.classes_: Optional[np.ndarray] = None
        self.metrics_: Optional[dict[str, Any]] = None

    def _build_pipeline(self, classifier_type: str = "logistic_regression") -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "text_tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        analyzer="word",
                        min_df=1,
                        max_features=5000,
                        sublinear_tf=True,
                    ),
                    "text",
                ),
                (
                    "num_features",
                    StandardScaler(),
                    ["is_debit", "log_amount"],
                ),
            ],
            remainder="drop",
        )

        clf = LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=42,
            class_weight="balanced",
        )

        return Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", clf),
        ])

    def train(
        self,
        df: pd.DataFrame,
        random_state: int = 42,
    ) -> dict[str, Any]:
        """Train the classifier on labeled transactions.

        Args:
            df: DataFrame containing 'description', 'debit', 'credit', 'category_name'

        Returns:
            Dictionary of evaluation metrics
        """
        if len(df) < 5:
            raise ValueError("Insufficient training data: need at least 5 labeled transactions.")

        # Prepare features
        X_df = extract_features_df(df.to_dict(orient="records"))
        y = df["category_name"].values

        # Stratified train/test split with fallback if class frequencies are too low
        # or if test_size < n_classes (scikit-learn requirement for stratified split)
        class_counts = pd.Series(y).value_counts()
        min_class_count = int(class_counts.min())
        n_classes = len(class_counts)
        test_count = int(0.2 * len(y))
        train_count = len(y) - test_count

        can_stratify = (
            min_class_count >= 2
            and len(y) >= 10
            and test_count >= n_classes
            and train_count >= n_classes
        )

        if can_stratify:
            X_train, X_test, y_train, y_test = train_test_split(
                X_df, y, test_size=0.2, random_state=random_state, stratify=y
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X_df, y, test_size=0.2, random_state=random_state
            )

        self.pipeline = self._build_pipeline()
        self.pipeline.fit(X_train, y_train)
        self.classes_ = self.pipeline.named_steps["classifier"].classes_

        # Evaluate on test set
        y_pred = self.pipeline.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))

        macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
            y_test, y_pred, average="macro", zero_division=0
        )
        weighted_p, weighted_r, weighted_f1, _ = precision_recall_fscore_support(
            y_test, y_pred, average="weighted", zero_division=0
        )

        self.metrics_ = {
            "model_version": self.model_version,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "sample_count": len(df),
            "train_count": len(X_train),
            "test_count": len(X_test),
            "accuracy": round(acc, 4),
            "macro_precision": round(float(macro_p), 4),
            "macro_recall": round(float(macro_r), 4),
            "macro_f1": round(float(macro_f1), 4),
            "weighted_precision": round(float(weighted_p), 4),
            "weighted_recall": round(float(weighted_r), 4),
            "weighted_f1": round(float(weighted_f1), 4),
            "classes": list(self.classes_),
        }

        # Refit on full dataset so saved model benefits from all labeled data
        self.pipeline.fit(X_df, y)
        self.classes_ = self.pipeline.named_steps["classifier"].classes_

        return self.metrics_

    def predict(
        self,
        transactions: List[dict[str, Any]],
    ) -> List[Tuple[str, float]]:
        """Predict categories and confidence scores using predict_proba.

        Returns:
            List of tuples: (predicted_category_name, confidence_score)
        """
        if self.pipeline is None or self.classes_ is None:
            return [("Uncategorized", 0.0) for _ in transactions]

        X_df = extract_features_df(transactions)
        probabilities = self.pipeline.predict_proba(X_df)

        results: List[Tuple[str, float]] = []
        for proba_row in probabilities:
            best_idx = int(np.argmax(proba_row))
            best_cat = str(self.classes_[best_idx])
            best_conf = float(proba_row[best_idx])
            # Cap confidence strictly below 1.0 per Appendix A1
            best_conf = min(round(best_conf, 4), 0.99)
            results.append((best_cat, best_conf))

        return results

    def save(self, model_path: str) -> None:
        """Save model and metadata using joblib."""
        dir_name = os.path.dirname(model_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        data = {
            "model_version": self.model_version,
            "pipeline": self.pipeline,
            "classes": self.classes_,
            "metrics": self.metrics_,
        }
        joblib.dump(data, model_path)

        # Also write metrics JSON next to model
        metrics_path = os.path.splitext(model_path)[0] + "_metrics.json"
        if self.metrics_:
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(self.metrics_, f, indent=2)

    @classmethod
    def load(cls, model_path: str) -> Optional[TransactionClassifier]:
        """Load trained model from path, returning None if file does not exist."""
        if not os.path.exists(model_path):
            logger.info("Model file does not exist at %s. Running on rules only.", model_path)
            return None

        try:
            data = joblib.load(model_path)
            instance = cls(model_version=data.get("model_version", "v1.0.0"))
            instance.pipeline = data.get("pipeline")
            instance.classes_ = data.get("classes")
            instance.metrics_ = data.get("metrics")
            return instance
        except Exception as exc:
            logger.warning("Failed to load model from %s: %s. Running on rules only.", model_path, exc)
            return None

