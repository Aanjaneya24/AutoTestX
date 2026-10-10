import json
import subprocess
from pathlib import Path

import pytest

from autotestx.log_analysis import PARSER, rule_classify, run_parser

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "sample_logs"


def cats(name):
    events, err = run_parser(str(SAMPLES / name))
    assert err is None
    return {e["category"] for e in events}


def test_pass_log():
    assert cats("pass.log") >= {"PASS"}
    assert not cats("pass.log") & {"FAIL", "ASSERT", "FATAL", "ERROR"}


def test_compile_error_log():
    assert "ERROR" in cats("compile_error.log")


def test_assertion_log():
    assert {"ASSERT", "FAIL"} <= cats("assertion_failure.log")


def test_timeout_log():
    assert "TIMEOUT" in cats("timeout.log")


def test_runtime_log():
    assert "FATAL" in cats("runtime_error.log")


def test_empty_and_unknown_logs_do_not_crash():
    assert cats("empty.log") == set()
    assert not cats("unknown.log") & {"FAIL", "ASSERT", "FATAL", "TIMEOUT"}


def test_line_numbers_and_snippets():
    events, _ = run_parser(str(SAMPLES / "assertion_failure.log"))
    first = events[0]
    assert first["line"] == 3 and first["snippet"].startswith("ASSERT FAIL")


def test_missing_log_reports_error():
    events, err = run_parser("/no/such/log.txt")
    assert events == [] and "cannot open" in err


def test_snippet_bounded_and_json_valid_on_binary(tmp_path):
    p = tmp_path / "x.log"
    p.write_bytes(b"error " + b"A" * 5000 + b"\n\xff\xfe\x00 FAIL \x01\n")
    out = subprocess.run(["perl", str(PARSER), str(p)], capture_output=True, text=True)
    data = json.loads(out.stdout)
    assert all(len(e["snippet"]) <= 203 for e in data["events"])
    assert [e["category"] for e in data["events"]] == ["ERROR", "FAIL"]


def test_event_cap(tmp_path):
    p = tmp_path / "big.log"
    p.write_text("error\n" * 1000)
    out = json.loads(subprocess.run(["perl", str(PARSER), str(p)], capture_output=True, text=True).stdout)
    assert len(out["events"]) == 500 and out["truncated"] is True


@pytest.mark.parametrize("name,expected", [
    ("compile_error.log", "compile_error"), ("assertion_failure.log", "assertion_failure"),
    ("timeout.log", "timeout"), ("runtime_error.log", "runtime_error"), ("unknown.log", "unknown"),
    ("empty.log", "unknown"),
])
def test_rule_classifier_on_fixtures(name, expected):
    assert rule_classify((SAMPLES / name).read_text()) == expected


# ---- regression tests from the audit ----
def _parse(tmp_path, text):
    p = tmp_path / "x.log"
    p.write_text(text)
    events, err = run_parser(str(p))
    assert err is None
    return events


def test_plural_errors_and_warnings_are_found_but_zero_counts_are_not(tmp_path):
    ev = _parse(tmp_path, "2 errors found\n3 warnings\n0 errors\nno warnings\nPASS: done with 0 errors\n")
    assert [(e["line"], e["category"]) for e in ev] == [(1, "ERROR"), (2, "WARNING"), (5, "PASS")]


def test_directory_is_not_a_clean_log(tmp_path):
    events, err = run_parser(str(tmp_path))
    assert events == [] and "not a regular file" in err


def test_summary_lines_do_not_fail_an_exit_zero_test(tmp_path):
    from autotestx.log_analysis import determine_status
    for text in ("Summary: 5 PASS, 0 FAIL\n", "PASS: assertion a1 passed\n", "ASSERT PASSED: a2\n",
                 "tests FAILED: 0\n"):
        assert determine_status(0, False, None, _parse(tmp_path, text))[0] == "PASS", text


def test_explicit_failure_lines_still_fail_an_exit_zero_test(tmp_path):
    from autotestx.log_analysis import determine_status
    for text in ("FAIL: tb\n", "ASSERT FAIL: x\n", "[100] Assertion violated\n", "FATAL: boom\n",
                 "  FAILED: x\n"):
        assert determine_status(0, False, None, _parse(tmp_path, text))[0] == "FAIL", text


def test_timeout_rule_needs_word_boundaries():
    assert rule_classify("Runtime out of memory") == "runtime_error"
    assert rule_classify("lifetime outside scope") == "unknown"
    assert rule_classify("Simulation timed out") == "timeout"
    assert rule_classify("Time-out: x") == "timeout"
