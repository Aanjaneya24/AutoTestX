from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from autotestx.ml_classifier import LogClassifier, evaluate, load_dataset, normalize, train_and_save

DATASET = Path(__file__).resolve().parents[1] / "data" / "labeled_log_snippets.csv"


def test_normalize_masks_numbers_hex_and_files():
    out = normalize("tb.v:17: error 0xFF at 900")
    assert "17" not in out and "0xff" not in out and "tb.v" not in out


def test_dataset_valid_and_documented():
    rows = load_dataset(DATASET)
    assert {r["source_type"] for r in rows} == {"synthetic"}
    assert len({r["label"] for r in rows}) == 5


def test_bad_label_rejected(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("sample_id,log_text,label,source_type,family_id\n1,x,not_a_label,synthetic,f\n")
    with pytest.raises(ValueError, match="labels"):
        load_dataset(p)


def test_evaluation_is_reproducible_and_leak_free():
    a, b = evaluate(DATASET), evaluate(DATASET)
    assert a["ml_model"]["macro_f1"] == b["ml_model"]["macro_f1"]
    assert a["rule_baseline"]["macro_f1"] == b["rule_baseline"]["macro_f1"]
    for fold in a["folds"]:  # family sets are disjoint from training by construction (asserted in evaluate)
        assert fold["test"] > 0
    assert sum(sum(r) for r in a["ml_model"]["confusion_matrix"]) == a["n_samples"]


def test_predict_and_low_confidence(tmp_path):
    clf = train_and_save(DATASET, tmp_path / "m.joblib", threshold=0.5)
    pred = clf.predict("tb.v:5: syntax error\ntb.v:5: error: Malformed statement")
    assert pred["top_label"] == "compile_error" and not pred["needs_review"]
    strict = LogClassifier.load(tmp_path / "m.joblib", threshold=0.999)
    p2 = strict.predict("zzz qqq completely novel words")
    assert p2["label"] == "needs_review" and p2["needs_review"]
    assert "not a verified root cause" in p2["note"]


def test_sklearn_version_mismatch_is_reported(tmp_path, monkeypatch):
    from autotestx import cli
    from autotestx.config import load_config
    root = Path(__file__).resolve().parents[1]
    model = tmp_path / "m.joblib"
    clf = train_and_save(DATASET, model)
    clf.metadata["sklearn_version"] = "0.0.1"
    clf.save(model)
    cfg = load_config(root / "configs" / "demo.yaml")
    object.__setattr__(cfg, "ml_model_path", str(model))
    fn, note = cli._make_classifier(cfg)
    assert fn is not None and "0.0.1" in note
