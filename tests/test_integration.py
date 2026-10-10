"""End-to-end runs against the real simulator (skipped if Icarus Verilog is absent)."""
import json
from pathlib import Path

import pytest


from autotestx.cli import main
from autotestx.config import load_config
from autotestx.runner import run_suite

from conftest import needs_sim

pytestmark = needs_sim


def test_demo_suite_end_to_end(project):
    summary = run_suite(load_config(project / "configs" / "demo.yaml"))
    by = {t["name"]: t for t in summary["tests"]}
    assert by["counter_basic"]["status"] == "PASS" and by["counter_basic"]["exit_code"] == 0
    assert by["counter_reset"]["status"] == "PASS"
    assert by["tcl_scenario_lint"]["status"] == "PASS"
    assert by["counter_fail_intentional"]["status"] == "FAIL"
    assert by["counter_fail_intentional"]["rule_based"]["category"] == "assertion_failure"
    assert by["compile_error_intentional"]["status"] == "FAIL"
    assert by["compile_error_intentional"]["rule_based"]["category"] == "compile_error"
    assert by["hang_intentional"]["status"] == "TIMEOUT"
    assert by["hang_intentional"]["duration_seconds"] < 10
    assert summary["all_as_expected"]
    run_dir = Path(summary["run_dir"])
    for t in summary["tests"]:                      # raw logs preserved
        assert Path(t["log_path"]).is_file() and t["run_id"] == summary["run_id"]
    assert (run_dir / "config_snapshot.yaml").is_file()
    page = (run_dir / "report.html").read_text()
    assert "counter_fail_intentional" in page and "logs/hang_intentional.log" in page
    assert json.loads((run_dir / "results.json").read_text())["totals"]["total"] == 6
    assert (run_dir / "results.csv").is_file()
    assert not (run_dir / "build").exists()


def test_unexpected_pass_is_flagged(project):
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("tags: [negative, rtl]\n    expect: fail", "tags: [negative, rtl]\n    expect: pass", 1))
    summary = run_suite(load_config(cfg))
    assert not summary["all_as_expected"]
    assert summary["unexpected_tests"] == ["counter_fail_intentional"]


def test_cli_exit_codes(project, capsys):
    cfg = str(project / "configs" / "demo.yaml")
    assert main(["validate", "--config", cfg]) == 0
    bad = project / "configs" / "bad.yaml"
    bad.write_text("project: {name: x}\n")
    assert main(["validate", "--config", str(bad)]) == 2
    assert not (project / "reports").exists()  # nothing executed on invalid config
    assert main(["run", "--config", str(bad)]) == 2
    assert not (project / "reports").exists()


def test_missing_tool_blocks_run(project, capsys):
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("tclsh: tclsh", "tclsh: tclsh-not-installed"))
    assert main(["run", "--config", str(cfg)]) == 3
    assert "tclsh" in capsys.readouterr().err
    assert not (project / "reports").exists()


def test_two_runs_compare(project, capsys):
    cfg = project / "configs" / "demo.yaml"
    a = run_suite(load_config(cfg), run_id="run-a")
    cfg.write_text(cfg.read_text().replace("examples/counter_reset]", "examples/counter_fail]"))
    b = run_suite(load_config(cfg), run_id="run-b")
    rc = main(["compare", "--before", str(Path(a["run_dir"]) / "results.json"),
               "--after", str(Path(b["run_dir"]) / "results.json")])
    out = capsys.readouterr().out
    # command changed for counter_reset, so it must not be called a regression
    assert rc == 0 and "counter_reset" in out and "not compared" in out


def test_ml_does_not_override_status(project):
    cfg = load_config(project / "configs" / "demo.yaml")
    summary = run_suite(cfg, classify=lambda text: {"label": "runtime_error", "confidence": 0.99,
                                                    "needs_review": False})
    by = {t["name"]: t for t in summary["tests"]}
    assert by["hang_intentional"]["status"] == "TIMEOUT"
    assert by["hang_intentional"]["ml_prediction"]["label"] == "runtime_error"
    assert by["counter_basic"]["ml_prediction"] is None


def test_unwritable_output_dir_is_a_clean_error(project, capsys):
    cfg = project / "configs" / "demo.yaml"
    blocker = project / "blocker"
    blocker.write_text("a file, not a directory")
    cfg.write_text(cfg.read_text().replace("output_dir: reports/runs", f"output_dir: {blocker}/sub"))
    assert main(["run", "--config", str(cfg)]) == 4
    assert "cannot write run output" in capsys.readouterr().err


def test_nul_in_command_blocks_run_before_any_test(project):
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("[tclsh, tcl/demo_tests.tcl", '["tclsh\\0", tcl/demo_tests.tcl'))
    assert main(["run", "--config", str(cfg)]) == 2
    assert not (project / "reports").exists()


def test_exit_zero_summary_line_not_misreported(project):
    (project / "examples" / "summary").mkdir()
    (project / "examples" / "summary" / "tb.v").write_text("")
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text() + (
        "\n  - name: summary_line\n    command: [python3, -c, \"print('Summary: 5 PASS, 0 FAIL')\"]\n"))
    by = {t["name"]: t for t in run_suite(load_config(cfg))["tests"]}
    assert by["summary_line"]["status"] == "PASS"


def test_oversized_test_output_in_a_real_suite(project):
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("settings:\n", "settings:\n  max_log_bytes: 8192\n", 1) + (
        "\n  - name: chatty\n    command: [python3, -c, \"print('A'*100)\\nfor i in range(5000): print('noise', i)\\nprint('FINAL-LINE')\"]\n"))
    summary = run_suite(load_config(cfg))
    chatty = next(t for t in summary["tests"] if t["name"] == "chatty")
    assert chatty["status"] == "PASS" and chatty["log_truncated"] is True
    assert Path(chatty["log_path"]).stat().st_size < 8192 + 400
    assert "FINAL-LINE" in Path(chatty["log_path"]).read_text()
    run_dir = Path(summary["run_dir"])
    assert "LOG TRUNCATED" in (run_dir / "report.html").read_text()
    assert "True" in (run_dir / "results.csv").read_text()


def test_error_categories_in_a_real_suite(project):
    cfg = project / "configs" / "demo.yaml"
    script = project / "noexec.sh"
    script.write_text("#!/bin/sh\n")
    cfg.write_text(cfg.read_text() + (
        "\n  - name: e_missing\n    expect: error\n    command: [definitely-not-installed-xyz]\n"
        "\n  - name: e_denied\n    expect: error\n    command: [./noexec.sh]\n"
        "\n  - name: e_signal\n    expect: fail\n    command: [python3, -c, \"import os,signal;os.kill(os.getpid(),signal.SIGSEGV)\"]\n"))
    by = {t["name"]: t for t in run_suite(load_config(cfg))["tests"]}
    assert by["e_missing"]["rule_based"]["category"] == "missing_tool"
    assert by["e_denied"]["rule_based"]["category"] == "permission_denied"
    assert by["e_signal"]["rule_based"]["category"] == "runtime_error"
    assert by["hang_intentional"]["rule_based"]["category"] == "timeout"


def test_status_file_tracks_progress_and_completion(project):
    seen = []
    cfg = load_config(project / "configs" / "demo.yaml")
    run_dir = project / "reports" / "runs" / "st-1"

    def snap(_result):
        seen.append(json.loads((run_dir / "status.json").read_text()))

    summary = run_suite(cfg, run_id="st-1", progress=snap)
    assert [s["completed"] for s in seen] == [1, 2, 3, 4, 5, 6]
    assert all(s["state"] == "running" for s in seen)
    final = json.loads((run_dir / "status.json").read_text())
    assert final["state"] == "completed" and final["completed"] == 6 and final["all_as_expected"] is True
    by = {t["name"]: t for t in final["tests"]}
    assert by["hang_intentional"]["status"] == "TIMEOUT" and by["counter_basic"]["state"] == "done"
    assert summary["run_id"] == "st-1"


def test_cli_run_id_flag(project, capsys):
    cfg = str(project / "configs" / "demo.yaml")
    assert main(["run", "--config", cfg, "--run-id", "fixed-id"]) == 0
    assert (project / "reports" / "runs" / "fixed-id" / "results.json").is_file()
    assert main(["run", "--config", cfg, "--run-id", "fixed-id"]) == 4          # no overwrite
    assert "already exists" in capsys.readouterr().err
    assert main(["run", "--config", cfg, "--run-id", "../evil"]) == 2


def test_failed_state_recorded_when_engine_raises(project):
    cfg = load_config(project / "configs" / "demo.yaml")

    def boom(_r):
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError):
        run_suite(cfg, run_id="boom", progress=boom)
    st = json.loads((project / "reports" / "runs" / "boom" / "status.json").read_text())
    assert st["state"] == "failed" and "synthetic failure" in st["error"]


def test_sigterm_stops_the_run_and_leaves_no_test_processes(project):
    import os
    import signal
    import subprocess
    import sys
    import time
    cfg = project / "configs" / "demo.yaml"
    cfg.write_text(cfg.read_text().replace("timeout_seconds: 3\n", "timeout_seconds: 120\n"))   # the hang test would run 2 min
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.Popen([sys.executable, "-m", "autotestx", "run", "--config", str(cfg), "--run-id", "sig-1"],
                            cwd=project, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    status = project / "reports" / "runs" / "sig-1" / "status.json"
    deadline = time.time() + 30
    while time.time() < deadline:                        # wait until the hanging test is the one running
        try:
            if json.loads(status.read_text()).get("current") == "hang_intentional":
                break
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    time.sleep(1.0)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=30) == 130
    st = json.loads(status.read_text())
    assert st["state"] == "interrupted" and "stopped" in st["error"]
    leftover = subprocess.run(["pgrep", "-f", str(project / "reports" / "runs" / "sig-1")], capture_output=True, text=True)
    assert leftover.stdout.strip() == "", f"processes survived: {leftover.stdout}"
