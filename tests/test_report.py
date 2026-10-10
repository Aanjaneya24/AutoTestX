import csv
import json

from autotestx.models import Config, TestResult
from autotestx.report import build_summary, text_summary, write_all

ENV = {"autotestx_version": "0", "platform": "p", "python": "3", "tools": []}


def cfg(tmp_path):
    return Config("proj", "iverilog", "out", 30, False, "m", 0.5, {}, (), str(tmp_path), "c.yaml")


def result(tmp_path, name, status, expected="PASS", exit_code=0, ml=None):
    log = tmp_path / "logs" / f"{name}.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text("x")
    return TestResult(name, "r1", status, expected, exit_code, status == "TIMEOUT", "t", 1.5, str(log),
                      ["echo"], findings=[{"line": 1, "category": "ERROR", "snippet": "<b>boom</b> & more"}],
                      rule_category="compile_error" if status != "PASS" else None,
                      status_reason="why", ml_prediction=ml)


def build(tmp_path, results):
    s = build_summary(cfg(tmp_path), "r1", str(tmp_path), "t0", results, ENV)
    write_all(s)
    return s


def test_zero_tests(tmp_path):
    s = build(tmp_path, [])
    assert s["totals"]["total"] == 0 and s["all_as_expected"]
    assert "No tests were run" in (tmp_path / "report.html").read_text()
    assert len(list(csv.reader(open(tmp_path / "results.csv")))) == 1


def test_mixed_results_totals_and_files(tmp_path):
    ml = {"label": "timeout", "confidence": 0.9, "needs_review": False}
    s = build(tmp_path, [result(tmp_path, "a", "PASS"), result(tmp_path, "b", "FAIL", exit_code=1),
                         result(tmp_path, "c", "TIMEOUT", exit_code=None, ml=ml),
                         result(tmp_path, "d", "ERROR", exit_code=None)])
    t = s["totals"]
    assert (t["passed"], t["failed"], t["timed_out"], t["errored"], t["unexpected"]) == (1, 1, 1, 1, 3)
    assert not s["all_as_expected"]
    data = json.loads((tmp_path / "results.json").read_text())
    assert data["tests"][2]["ml_prediction"]["label"] == "timeout"
    assert data["tests"][2]["rule_based"]["category"] == "compile_error"  # kept separate from ML
    page = (tmp_path / "report.html").read_text()
    assert "&lt;b&gt;boom&lt;/b&gt;" in page and "<b>boom</b>" not in page  # escaped
    assert "logs/b.log" in page
    assert "UNEXPECTED" in text_summary(s)


def test_expected_failure_counts_as_expected(tmp_path):
    s = build(tmp_path, [result(tmp_path, "neg", "FAIL", expected="FAIL", exit_code=1)])
    assert s["all_as_expected"] and s["totals"]["failed"] == 1
