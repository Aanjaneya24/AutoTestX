"""Compare two results.json files."""
from __future__ import annotations

import json
from pathlib import Path


def load_results(path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read results file {path}: {exc}")
    if not isinstance(data, dict) or "tests" not in data or "project" not in data:
        raise ValueError(f"{path} is not an AutoTestX results.json")
    for i, t in enumerate(data["tests"] if isinstance(data["tests"], list) else [None]):
        if not isinstance(t, dict) or not {"name", "status", "command"} <= set(t):
            raise ValueError(f"{path}: tests[{i}] lacks name/status/command (not a complete AutoTestX results.json)")
    return data


def _as_expected(t: dict) -> bool:
    """Did this test end in the outcome the config expected? (Older files without the field: PASS expected.)"""
    if "matches_expectation" in t:
        return bool(t["matches_expectation"])
    return t["status"] == t.get("expected_status", "PASS")


def compare_runs(before: dict, after: dict) -> dict:
    """Return {'compatible', 'warnings', 'regressions', 'fixes', 'other_changes', 'config_changed', 'only_before', 'only_after'}.

    A *regression* is a test that matched its expectation before and does not now; a *fix* is the
    reverse. So PASS->FAIL of an `expect: pass` test and FAIL->PASS of an `expect: fail` test are both
    regressions, while a deliberately failing test staying FAIL is unchanged. Tests whose command or
    expectation changed are listed under `config_changed` and never judged. Incompatible suites
    (different project, or no tests in common) produce a warning and no verdicts.
    """
    b = {t["name"]: t for t in before["tests"]}
    a = {t["name"]: t for t in after["tests"]}
    common = sorted(set(a) & set(b))
    out = {"compatible": True, "warnings": [], "regressions": [], "fixes": [], "other_changes": [],
           "config_changed": [], "only_before": sorted(set(b) - set(a)), "only_after": sorted(set(a) - set(b))}
    if before["project"] != after["project"]:
        out["warnings"].append(f"project differs ({before['project']!r} vs {after['project']!r})")
        out["compatible"] = False
    if not common:
        out["warnings"].append("no tests in common")
        out["compatible"] = False
    if not out["compatible"]:
        out["warnings"].append("runs are not comparable; no regressions inferred")
        return out
    for name in common:
        tb, ta = b[name], a[name]
        if tb["command"] != ta["command"] or tb.get("expected_status") != ta.get("expected_status"):
            out["config_changed"].append(name)
            continue
        ok_before, ok_after = _as_expected(tb), _as_expected(ta)
        entry = {"name": name, "before": tb["status"], "after": ta["status"],
                 "expected": ta.get("expected_status", "PASS")}
        if ok_before and not ok_after:
            out["regressions"].append(entry)
        elif ok_after and not ok_before:
            out["fixes"].append(entry)
        elif tb["status"] != ta["status"]:      # wrong before and wrong now, but differently
            out["other_changes"].append(entry)
    return out


def format_comparison(cmp: dict, before_id: str, after_id: str) -> str:
    lines = [f"Compare {before_id} -> {after_id}"]
    for w in cmp["warnings"]:
        lines.append(f"WARNING: {w}")
    for key, title in (("regressions", "REGRESSION"), ("fixes", "FIXED"), ("other_changes", "still unexpected, changed")):
        for e in cmp[key]:
            lines.append(f"{title}: {e['name']} ({e['before']} -> {e['after']}, expected {e['expected']})")
    if cmp["config_changed"]:
        lines.append("command/expectation changed (not compared): " + ", ".join(cmp["config_changed"]))
    if cmp["only_before"]:
        lines.append("only in before: " + ", ".join(cmp["only_before"]))
    if cmp["only_after"]:
        lines.append("only in after: " + ", ".join(cmp["only_after"]))
    if len(lines) == 1:
        lines.append("no differences")
    return "\n".join(lines)
