"""C1 classifier, baseline variant: TF-IDF (word 1–2 + char 3–5) + LogisticRegression.

- class: LogisticRegression(class_weight="balanced"), C tuned on val (macro-F1);
- component: one-vs-rest LogisticRegression over the top-15 train components + "other", ranked by probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import MultiLabelBinarizer

from src.schemas.c1 import COMPONENTS

SEED = 42


def build_features(min_df_word: int = 2, min_df_char: int = 3) -> FeatureUnion:
    return FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=min_df_word, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=min_df_char, sublinear_tf=True)),
        ]
    )


def fit_class_model(x: spmatrix, labels: list[str], c: float) -> LogisticRegression:
    return LogisticRegression(C=c, class_weight="balanced", max_iter=3000, random_state=SEED).fit(x, labels)


def fit_component_model(x: spmatrix, component_sets: list[set[str]], c: float) -> OneVsRestClassifier:
    y = MultiLabelBinarizer(classes=COMPONENTS).fit_transform(component_sets)
    return OneVsRestClassifier(LogisticRegression(C=c, max_iter=3000, random_state=SEED)).fit(x, y)


def rank_components(model: OneVsRestClassifier, x: spmatrix, top: int = 3) -> list[list[str]]:
    proba = model.predict_proba(x)
    return [[COMPONENTS[j] for j in np.argsort(-row, kind="stable")[:top]] for row in proba]


@dataclass
class BaselineC1:
    """Fitted features + class model + component model for one input mode."""

    features: FeatureUnion
    class_model: LogisticRegression
    component_model: OneVsRestClassifier

    @classmethod
    def fit(
        cls, texts: list[str], labels: list[str], component_sets: list[set[str]], c_class: float, c_component: float
    ) -> BaselineC1:
        features = build_features()
        x = features.fit_transform(texts)
        return cls(features, fit_class_model(x, labels, c_class), fit_component_model(x, component_sets, c_component))

    def predict(self, texts: list[str]) -> list[dict[str, Any]]:
        x = self.features.transform(texts)
        proba = self.class_model.predict_proba(x)
        classes = list(self.class_model.classes_)
        components = rank_components(self.component_model, x)
        return [
            {"label": classes[int(np.argmax(p))], "confidence": float(np.max(p)), "component": comp}
            for p, comp in zip(proba, components, strict=True)
        ]
