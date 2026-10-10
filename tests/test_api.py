"""API tests. Real regression runs use the actual CLI via a subprocess (skipped without Icarus Verilog)."""
import json
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from autotestx.web.app import create_app  # noqa: E402
from autotestx.web.settings import Settings  # noqa: E402

from conftest import needs_sim  # noqa: E402


@pytest.fixture
def ctx(project):
    settings = Settings(project_root=project, allowed_configs=("configs/demo.yaml", "../escape.yaml", "configs/missing.yaml"))
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    return client, settings, project


def wait_done(client, run_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/api/runs/{run_id}").json()
        if d["state"] not in ("starting", "running"):
            return d
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def fake_run(settings, run_id, project="autotestx-demo", status="PASS", expect="PASS", cmd=("c",)):
    d = settings.runs_root / run_id
    (d / "logs").mkdir(parents=True)
    t = {"name": "t1", "status": status, "expected_status": expect, "matches_expectation": status == expect,
         "exit_code": 0, "duration_seconds": 0.1, "command": list(cmd), "rule_based": {"category": None, "findings": []}}
    res = {"run_id": run_id, "project": project, "started": "2026-01-01T00:00:00+00:00",
           "finished": "2026-01-01T00:00:05+00:00", "totals": {"total": 1, "passed": 1, "failed": 0, "errored": 0,
           "timed_out": 0, "unexpected": 0}, "all_as_expected": status == expect, "unexpected_tests": [],
           "environment": {}, "tests": [t]}
    (d / "results.json").write_text(json.dumps(res))
    (d / "logs" / "t1.log").write_text("line one\nERROR: boom\nline three\n")
    return d


# ------------------------------------------------------------------ basics / security
def test_health(ctx):
    r = ctx[0].get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["active_run"] is None


def test_configs_allowlist_only(ctx):
    client, settings, project = ctx
    body = client.get("/api/configs").json()["configs"]
    assert [c["id"] for c in body] == ["demo"]                      # escape.yaml and missing.yaml are not offered
    assert body[0]["valid"] and len(body[0]["tests"]) == 6
    assert str(project) not in json.dumps(body)                     # no absolute paths
    assert {t["expect"] for t in body[0]["tests"]} == {"pass", "fail", "timeout"}


@needs_sim
def test_validate_config(ctx):
    r = ctx[0].post("/api/configs/validate", json={"config_id": "demo"})
    assert r.status_code == 200 and r.json()["valid"] is True
    assert any(t["role"] == "simulator" and t["found"] for t in r.json()["tools"])


@pytest.mark.parametrize("body", [{"config_id": "../../etc/passwd"}, {"config_id": "demo/../x"}, {"config_id": ""},
                                  {"config_id": "demo", "command": ["rm", "-rf", "/"]}, {}, {"config_id": 5}])
def test_untrusted_or_malformed_requests_rejected(ctx, body):
    client = ctx[0]
    for url in ("/api/configs/validate", "/api/runs"):
        assert client.post(url, json=body).status_code == 422
    assert client.get("/api/runs").json()["runs"] == []             # nothing was started


def test_unknown_config_id_is_404(ctx):
    r = ctx[0].post("/api/runs", json={"config_id": "nope"})
    assert r.status_code == 404 and r.json()["detail"]["error"] == "unknown_config"


def test_invalid_config_cannot_launch(ctx):
    client, settings, project = ctx
    (project / "configs" / "demo.yaml").write_text("project: {name: x}\n")
    r = client.post("/api/runs", json={"config_id": "demo"})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "invalid_config" and r.json()["detail"]["problems"]
    assert client.get("/api/runs").json()["runs"] == []
    v = client.post("/api/configs/validate", json={"config_id": "demo"}).json()
    assert v["valid"] is False and v["problems"]


def test_config_with_foreign_output_dir_is_refused(ctx):
    client, settings, project = ctx
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("output_dir: reports/runs", "output_dir: elsewhere"))
    r = client.post("/api/runs", json={"config_id": "demo"})
    assert r.status_code == 422 and "outside" in json.dumps(r.json())


def test_cross_site_and_oversized_and_foreign_host_requests(ctx):
    client = ctx[0]
    r = client.post("/api/runs", json={"config_id": "demo"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/configs/validate", content=b"x" * 20000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_unexpected_error_is_generic_500(ctx, monkeypatch):
    from autotestx.web import store
    monkeypatch.setattr(store, "summarise", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret detail /etc")))
    fake_run(ctx[1], "20260101-000000-aaaa")
    r = ctx[0].get("/api/runs")
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"] == "internal_error"


# ------------------------------------------------------------------ run lookup, logs, state
def test_unknown_and_malformed_run_ids(ctx):
    client = ctx[0]
    assert client.get("/api/runs/20990101-000000-ffff").status_code == 404
    assert client.get("/api/runs/bad id").status_code == 400
    assert client.get("/api/runs/.hidden").status_code == 400
    assert client.get("/api/runs/..").status_code in (400, 404)
    assert client.get("/api/runs/%2e%2e%2f%2e%2e/results").status_code in (400, 404)
    assert client.get("/api/runs/x/logs/y").status_code in (400, 404)


def test_log_access_paging_search_and_safety(ctx):
    client, settings, _ = ctx
    d = fake_run(settings, "20260101-000000-aaaa")
    base = "/api/runs/20260101-000000-aaaa/logs/t1"
    full = client.get(base).json()
    assert full["text"].startswith("line one") and full["has_more"] is False and full["start_line"] == 1
    page = client.get(base, params={"offset": 9, "limit": 10}).json()
    assert page["text"] == "ERROR: boo" and page["has_more"] and page["start_line"] == 2
    assert client.get(base, params={"tail": True, "limit": 6}).json()["text"] == "three\n"
    assert client.get(base, params={"limit": 10_000_000}).status_code == 422
    s = client.get(base + "/search", params={"q": "error"}).json()
    assert s["total_matches"] == 1 and s["matches"][0]["line"] == 2
    assert client.get(base + "/search", params={"q": ""}).status_code == 422
    from autotestx.web.store import safe_log_path
    for evil in ("..", ".", "../results", "a/b", "t1\0", ""):
        assert safe_log_path(settings.runs_root, "20260101-000000-aaaa", evil) is None
    assert safe_log_path(settings.runs_root, "../..", "t1") is None
    assert client.get("/api/runs/20260101-000000-aaaa/logs/unlisted").status_code == 404
    (d / "logs" / "t1.log").unlink()                                  # missing log
    r = client.get(base)
    assert r.status_code == 404 and r.json()["detail"]["error"] == "log_missing"


def test_symlinked_log_is_refused(ctx, tmp_path):
    client, settings, _ = ctx
    d = fake_run(settings, "20260101-000000-bbbb")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    (d / "logs" / "t1.log").unlink()
    (d / "logs" / "t1.log").symlink_to(secret)
    r = client.get("/api/runs/20260101-000000-bbbb/logs/t1")
    assert r.status_code == 404 and "SECRET" not in r.text


def test_state_derivation(ctx):
    client, settings, _ = ctx
    runs = settings.runs_root
    d = runs / "20260101-000001-aaaa"
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"state": "running", "pid": 2_000_000_000, "total": 2, "completed": 1,
                                               "tests": [{"name": "a", "state": "done", "status": "PASS"}]}))
    assert client.get("/api/runs/20260101-000001-aaaa").json()["state"] == "interrupted"
    d2 = runs / "20260101-000002-aaaa"
    d2.mkdir()
    (d2 / "status.json").write_text(json.dumps({"state": "failed", "error": "OSError: disk"}))
    j = client.get("/api/runs/20260101-000002-aaaa").json()
    assert j["state"] == "failed" and "disk" in j["error"]
    (runs / ".console").mkdir()
    (runs / ".console" / "20260101-000003-aaaa.log").write_text("Traceback: boom\n")
    j = client.get("/api/runs/20260101-000003-aaaa").json()
    assert j["state"] == "failed" and "boom" in j["console_tail"]
    ids = [r["run_id"] for r in client.get("/api/runs").json()["runs"]]
    assert ids == sorted(ids, reverse=True) and ".console" not in ids


def test_old_results_without_new_fields_are_tolerated(ctx):
    client, settings, _ = ctx
    d = fake_run(settings, "20260101-000004-aaaa")
    res = json.loads((d / "results.json").read_text())
    for k in ("log_truncated", "log_bytes_total"):
        res["tests"][0].pop(k, None)
    (d / "results.json").write_text(json.dumps(res))
    r = client.get("/api/runs/20260101-000004-aaaa/results").json()["tests"][0]
    assert r["log_truncated"] is False and r["outcome"] == "passed"


def test_outcome_never_presents_expected_failure_as_success(ctx):
    from autotestx.web.store import classify_test
    assert classify_test({"status": "FAIL", "expected_status": "FAIL"}) == "expected_failure"
    assert classify_test({"status": "TIMEOUT", "expected_status": "TIMEOUT"}) == "expected_failure"
    assert classify_test({"status": "PASS", "expected_status": "FAIL"}) == "unexpected_pass"
    assert classify_test({"status": "TIMEOUT", "expected_status": "FAIL"}) == "unexpected_failure"
    assert classify_test({"status": "FAIL", "expected_status": "PASS"}) == "unexpected_failure"
    assert classify_test({"status": "PASS", "expected_status": "PASS"}) == "passed"


# ------------------------------------------------------------------ compare / ML
def test_compare_reuses_engine_logic(ctx):
    client, settings, _ = ctx
    fake_run(settings, "20260101-000010-aaaa", status="PASS")
    fake_run(settings, "20260101-000011-aaaa", status="FAIL")
    fake_run(settings, "20260101-000012-aaaa", project="other-project")
    r = client.get("/api/runs/compare", params={"before": "20260101-000010-aaaa", "after": "20260101-000011-aaaa"}).json()
    assert r["compatible"] and [x["name"] for x in r["regressions"]] == ["t1"] and "REGRESSION" in r["text"]
    r = client.get("/api/runs/compare", params={"before": "20260101-000010-aaaa", "after": "20260101-000012-aaaa"}).json()
    assert r["compatible"] is False and r["regressions"] == []
    assert client.get("/api/runs/compare", params={"before": "20260101-000010-aaaa", "after": "nope"}).status_code in (400, 404)
    assert client.get("/api/runs/compare", params={"before": "20260101-000010-aaaa"}).status_code == 422
    inc = settings.runs_root / "20260101-000013-aaaa"
    inc.mkdir()
    (inc / "status.json").write_text(json.dumps({"state": "failed"}))
    assert client.get("/api/runs/compare", params={"before": "20260101-000010-aaaa", "after": "20260101-000013-aaaa"}).status_code == 409


def test_ml_evaluation_endpoint(ctx):
    client, settings, _ = ctx
    r = client.get("/api/ml/evaluation")
    assert r.status_code == 404 and r.json()["detail"]["error"] == "no_evaluation"
    ev = {"n_samples": 10, "dataset": "/private/path.csv", "rule_baseline": {"macro_f1": 0.8}, "ml_model": {"macro_f1": 0.6}}
    settings.ml_eval_path.parent.mkdir(parents=True, exist_ok=True)
    settings.ml_eval_path.write_text(json.dumps(ev))
    body = client.get("/api/ml/evaluation").json()
    assert body["evaluation"]["ml_model"]["macro_f1"] == 0.6 and "dataset" not in body["evaluation"]
    assert body["baseline_higher"] is True and "does not diagnose hardware defects" in body["statement"]
    assert body["limitations"]


# ------------------------------------------------------------------ real runs through the real CLI
@needs_sim
def test_full_run_through_api(ctx):
    client, settings, project = ctx
    r = client.post("/api/runs", json={"config_id": "demo"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    # repeated launch while active is refused, not queued
    again = client.post("/api/runs", json={"config_id": "demo"})
    assert again.status_code == 409 and again.json()["detail"]["active_run"] == run_id
    assert client.get("/api/health").json()["active_run"] == run_id
    seen_progress = set()
    end = time.time() + 60
    while time.time() < end:
        d = client.get(f"/api/runs/{run_id}").json()
        seen_progress.add(d["progress"]["completed"])
        if d["state"] not in ("starting", "running"):
            break
        time.sleep(0.2)
    assert d["state"] == "completed" and d["overall"] == "as_expected"
    assert d["totals"]["total"] == 6 and d["totals"]["passed"] == 3 and d["totals"]["timed_out"] == 1
    assert len(seen_progress) > 2, "progress should be visible while the run is in flight"
    res = client.get(f"/api/runs/{run_id}/results").json()
    by = {t["name"]: t for t in res["tests"]}
    assert by["counter_basic"]["outcome"] == "passed"
    assert by["counter_fail_intentional"]["outcome"] == "expected_failure" and by["counter_fail_intentional"]["rule_category"] == "assertion_failure"
    assert by["hang_intentional"]["status"] == "TIMEOUT" and by["hang_intentional"]["outcome"] == "expected_failure"
    assert str(project) not in json.dumps(res) and str(settings.runs_root) not in json.dumps(res)
    log = client.get(f"/api/runs/{run_id}/logs/counter_fail_intentional").json()
    assert "ASSERT FAIL" in log["text"] and any(f["category"] == "ASSERT" for f in log["findings"])
    assert (settings.runs_root / run_id / "report.html").is_file()
    # the run is persisted on disk: a brand-new app instance (a "restart") sees it
    client2 = TestClient(create_app(settings), raise_server_exceptions=False)
    assert client2.get(f"/api/runs/{run_id}").json()["totals"]["total"] == 6
    assert client2.get("/api/runs").json()["latest"] == run_id
    # a second launch is allowed after completion and compares cleanly with the first
    second = client.post("/api/runs", json={"config_id": "demo"}).json()["run_id"]
    wait_done(client, second)
    cmp = client.get("/api/runs/compare", params={"before": run_id, "after": second}).json()
    assert cmp["compatible"] and cmp["regressions"] == [] and cmp["fixes"] == []


@needs_sim
def test_cli_failure_is_reported_with_console_output(ctx):
    client, settings, project = ctx
    # passes API pre-checks, then the CLI itself fails: make the runs dir unwritable for the run directory
    runs = settings.runs_root
    runs.mkdir(parents=True, exist_ok=True)
    (runs / ".console").mkdir(exist_ok=True)
    runs.chmod(0o555)
    try:
        r = client.post("/api/runs", json={"config_id": "demo"})
        if r.status_code != 202:                      # console dir not creatable: refused up front, also acceptable
            assert r.status_code >= 400
            return
        d = wait_done(client, r.json()["run_id"])
    finally:
        runs.chmod(0o755)
    assert d["state"] == "failed" and d["error"]
    assert "error" in d["console_tail"].lower() or d["exit_code"] not in (0, None)


def test_log_chunk_around_a_line(ctx):
    client, settings, _ = ctx
    fake_run(settings, "20260101-000020-aaaa")
    d = client.get("/api/runs/20260101-000020-aaaa/logs/t1", params={"around_line": 3, "limit": 100}).json()
    assert d["start_line"] == 1 and "ERROR: boom" in d["text"]
    d = client.get("/api/runs/20260101-000020-aaaa/logs/t1", params={"around_line": 999}).json()
    assert d["text"] == "" and d["has_more"] is False
    assert client.get("/api/runs/20260101-000020-aaaa/logs/t1", params={"around_line": 0}).status_code == 422
