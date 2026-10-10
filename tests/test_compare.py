import json

import pytest

from autotestx.compare import compare_runs, format_comparison, load_results


def run(project, expect=None, **tests):
    expect = expect or {}
    out = []
    for n, st in tests.items():
        exp = expect.get(n, "PASS")
        out.append({"name": n, "status": st, "command": ["c", n], "expected_status": exp,
                    "matches_expectation": st == exp})
    return {"run_id": "r", "project": project, "tests": out}


def test_regression_fix_and_membership():
    c = compare_runs(run("p", a="PASS", b="FAIL", c="PASS", d="PASS"), run("p", a="FAIL", b="PASS", c="PASS", e="PASS"))
    assert [x["name"] for x in c["regressions"]] == ["a"]
    assert [x["name"] for x in c["fixes"]] == ["b"]
    assert c["only_before"] == ["d"] and c["only_after"] == ["e"]


def test_expected_failure_staying_failed_is_not_a_change():
    exp = {"neg": "FAIL"}
    c = compare_runs(run("p", exp, neg="FAIL", a="PASS"), run("p", exp, neg="FAIL", a="PASS"))
    assert not (c["regressions"] or c["fixes"] or c["other_changes"])


def test_expected_failure_that_starts_passing_is_a_regression():
    exp = {"neg": "FAIL"}
    c = compare_runs(run("p", exp, neg="FAIL"), run("p", exp, neg="PASS"))
    assert [(x["name"], x["before"], x["after"]) for x in c["regressions"]] == [("neg", "FAIL", "PASS")]


def test_expected_failure_that_starts_failing_after_unexpected_pass_is_a_fix():
    exp = {"neg": "FAIL"}
    c = compare_runs(run("p", exp, neg="PASS"), run("p", exp, neg="FAIL"))
    assert [x["name"] for x in c["fixes"]] == ["neg"]


def test_timeout_transitions():
    c = compare_runs(run("p", a="PASS"), run("p", a="TIMEOUT"))
    assert [x["after"] for x in c["regressions"]] == ["TIMEOUT"]
    exp = {"hang": "TIMEOUT"}
    assert compare_runs(run("p", exp, hang="TIMEOUT"), run("p", exp, hang="TIMEOUT"))["regressions"] == []
    c = compare_runs(run("p", exp, hang="TIMEOUT"), run("p", exp, hang="PASS"))
    assert [x["name"] for x in c["regressions"]] == ["hang"]       # timeout test stopped timing out
    c = compare_runs(run("p", a="FAIL"), run("p", a="TIMEOUT"))
    assert c["regressions"] == [] and [x["name"] for x in c["other_changes"]] == ["a"]


def test_expectation_change_is_config_change_not_verdict():
    before, after = run("p", {"a": "PASS"}, a="PASS"), run("p", {"a": "FAIL"}, a="FAIL")
    c = compare_runs(before, after)
    assert c["config_changed"] == ["a"] and not c["regressions"] and not c["fixes"]


def test_old_results_without_matches_field_still_compare():
    before, after = run("p", a="PASS"), run("p", a="FAIL")
    for r in (before, after):
        for t in r["tests"]:
            del t["matches_expectation"]
    assert [x["name"] for x in compare_runs(before, after)["regressions"]] == ["a"]


def test_incompatible_projects_infer_nothing():
    c = compare_runs(run("p", a="PASS"), run("q", a="FAIL"))
    assert not c["compatible"] and c["regressions"] == []
    assert "not comparable" in format_comparison(c, "1", "2")


def test_no_common_tests():
    assert not compare_runs(run("p", a="PASS"), run("p", b="PASS"))["compatible"]


def test_changed_command_not_a_regression():
    before, after = run("p", a="PASS"), run("p", a="FAIL")
    after["tests"][0]["command"] = ["different"]
    c = compare_runs(before, after)
    assert c["regressions"] == [] and c["config_changed"] == ["a"]


def test_load_results_rejects_garbage(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"hello": 1}))
    with pytest.raises(ValueError):
        load_results(p)


def test_results_missing_command_rejected_cleanly(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"project": "p", "run_id": "1", "tests": [{"name": "a", "status": "PASS"}]}))
    with pytest.raises(ValueError, match="command"):
        load_results(p)
