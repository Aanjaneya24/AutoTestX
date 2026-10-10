"""TF-IDF + Logistic Regression failure-log classifier and its evaluation against the rule baseline."""
from __future__ import annotations

import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .log_analysis import LABELS, rule_classify

SEED = 42
N_SPLITS = 4
REQUIRED_COLUMNS = {"sample_id", "log_text", "label", "source_type", "family_id"}

_HEX = re.compile(r"0x[0-9a-f]+", re.I)
_NUM = re.compile(r"\d+")
_FILE = re.compile(r"[\w./-]+\.s?v\b", re.I)


def normalize(text: str) -> str:
    """Conservative normalisation: lowercase, mask hex literals, numbers and source file names."""
    text = _HEX.sub(" hexval ", text.lower())
    text = _FILE.sub(" srcfile ", text)
    return _NUM.sub(" num ", text)


def _make_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    return Pipeline([
        ("tfidf", TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), sublinear_tf=True)),
        ("clf", LogisticRegression(max_iter=2000, C=10.0, random_state=SEED)),
    ])


def load_dataset(path) -> list:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"dataset {path} lacks columns: {sorted(missing)}")
        rows = list(reader)
    bad = sorted({r["label"] for r in rows} - set(LABELS))
    if bad:
        raise ValueError(f"dataset has labels outside {LABELS}: {bad}")
    if not rows:
        raise ValueError("dataset is empty")
    return rows


class LogClassifier:
    def __init__(self, threshold: float = 0.5):
        self.pipeline = _make_pipeline()
        self.threshold = threshold
        self.metadata: dict = {}

    def fit(self, texts, labels, metadata=None) -> "LogClassifier":
        self.pipeline.fit(list(texts), list(labels))
        self.metadata = dict(metadata or {})
        return self

    def predict(self, text: str) -> dict:
        """Return {'label','top_label','confidence','needs_review'}; a low-confidence guess is 'needs_review'."""
        proba = self.pipeline.predict_proba([text])[0]
        idx = int(proba.argmax())
        top, conf = str(self.pipeline.classes_[idx]), float(proba[idx])
        low = conf < self.threshold
        return {"label": "needs_review" if low else top, "top_label": top,
                "confidence": round(conf, 4), "needs_review": low,
                "note": "experimental text-pattern prediction; not a verified root cause"}

    def save(self, path) -> None:
        import joblib
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "metadata": self.metadata}, path)

    @classmethod
    def load(cls, path, threshold: float = 0.5) -> "LogClassifier":
        import joblib
        blob = joblib.load(path)
        obj = cls(threshold)
        obj.pipeline, obj.metadata = blob["pipeline"], blob["metadata"]
        return obj


def evaluate(dataset_path, n_splits: int = N_SPLITS, seed: int = SEED) -> dict:
    """Family-grouped cross-validation of the ML model and the rule baseline on identical folds.

    Every variant of a template family is on one side of each split (no near-duplicate leakage);
    metrics are computed on the pooled out-of-fold predictions.
    """
    import numpy as np
    from sklearn.metrics import classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedGroupKFold

    rows = load_dataset(dataset_path)
    texts = np.array([r["log_text"] for r in rows], dtype=object)
    labels = np.array([r["label"] for r in rows], dtype=object)
    groups = np.array([r["family_id"] for r in rows], dtype=object)

    ml_pred = np.empty(len(rows), dtype=object)
    folds = []
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for train, test in cv.split(texts, labels, groups):
        model = _make_pipeline().fit(texts[train], labels[train])
        ml_pred[test] = model.predict(texts[test])
        folds.append({"train": len(train), "test": len(test),
                      "test_families": sorted(set(groups[test].tolist()))})
        assert not set(groups[train]) & set(groups[test]), "family leakage across split"
    rule_pred = np.array([rule_classify(t) for t in texts], dtype=object)

    def metrics(pred):
        rep = classification_report(labels, pred, labels=list(LABELS), output_dict=True, zero_division=0)
        return {
            "accuracy": round(float((pred == labels).mean()), 4),
            "macro_f1": round(float(f1_score(labels, pred, labels=list(LABELS), average="macro", zero_division=0)), 4),
            "per_class": {c: {"precision": round(rep[c]["precision"], 3), "recall": round(rep[c]["recall"], 3),
                              "f1": round(rep[c]["f1-score"], 3), "support": int(rep[c]["support"])}
                          for c in LABELS},
            "confusion_matrix": confusion_matrix(labels, pred, labels=list(LABELS)).tolist(),
        }

    def misses(pred, limit=6):
        return [{"text": texts[i], "true": labels[i], "predicted": pred[i]}
                for i in range(len(rows)) if pred[i] != labels[i]][:limit]

    # Inference latency of the single-sample path, using a model trained on all data.
    final = _make_pipeline().fit(texts, labels)
    sample = texts[:50]
    t0 = time.perf_counter()
    for t in sample:
        final.predict_proba([t])
    infer_ms = (time.perf_counter() - t0) / len(sample) * 1000

    import sklearn
    return {
        "dataset": str(dataset_path),
        "n_samples": len(rows),
        "class_counts": {c: int((labels == c).sum()) for c in LABELS},
        "n_families": int(len(set(groups.tolist()))),
        "source_types": sorted({r["source_type"] for r in rows}),
        "protocol": f"StratifiedGroupKFold(n_splits={n_splits}, shuffle=True, random_state={seed}), "
                    "grouped by family_id; metrics on pooled out-of-fold predictions",
        "folds": folds,
        "labels": list(LABELS),
        "rule_baseline": metrics(rule_pred),
        "ml_model": metrics(ml_pred),
        "rule_misclassified_examples": misses(rule_pred),
        "ml_misclassified_examples": misses(ml_pred),
        "inference_ms_per_sample": round(infer_ms, 3),
        "inference_sample_size": int(len(sample)),
        "sklearn_version": sklearn.__version__,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def train_and_save(dataset_path, model_path, threshold: float = 0.5) -> LogClassifier:
    rows = load_dataset(dataset_path)
    import sklearn
    meta = {"dataset": str(dataset_path), "n_samples": len(rows), "labels": list(LABELS),
            "seed": SEED, "sklearn_version": sklearn.__version__,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "trained on synthetic data; see docs/ml_evaluation.md"}
    clf = LogClassifier(threshold).fit([r["log_text"] for r in rows], [r["label"] for r in rows], meta)
    clf.save(model_path)
    return clf
