import sys


from autotestx.log_analysis import determine_status
from autotestx.runner import run_command


def test_success(tmp_path):
    raw = run_command([sys.executable, "-c", "print('ok')"], str(tmp_path), str(tmp_path / "l.log"), 10)
    assert raw.exit_code == 0 and not raw.timed_out
    assert "ok" in (tmp_path / "l.log").read_text()


def test_nonzero_exit(tmp_path):
    raw = run_command([sys.executable, "-c", "import sys; sys.exit(3)"], str(tmp_path), str(tmp_path / "l.log"), 10)
    assert raw.exit_code == 3
    assert determine_status(raw.exit_code, raw.timed_out, raw.launch_error, [])[0] == "FAIL"


def test_timeout_kills_process_group(tmp_path):
    marker = tmp_path / "child_alive"
    child = tmp_path / "child.py"
    child.write_text(f"import time\ntime.sleep(1.5)\nopen({str(marker)!r}, 'w').close()\n")
    parent = tmp_path / "parent.py"
    parent.write_text("import subprocess, sys, time\n"
                      f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
                      "time.sleep(60)\n")
    raw = run_command([sys.executable, str(parent)], str(tmp_path), str(tmp_path / "l.log"), 0.5)
    assert raw.timed_out and raw.duration_seconds < 10
    assert "TIMEOUT" in (tmp_path / "l.log").read_text()
    import time
    time.sleep(2)
    assert not marker.exists(), "grandchild survived the timeout"
    assert determine_status(None, True, None, [])[0] == "TIMEOUT"


def test_missing_executable_is_error(tmp_path):
    raw = run_command(["definitely-not-a-real-tool-xyz"], str(tmp_path), str(tmp_path / "l.log"), 5)
    assert raw.launch_error and raw.exit_code is None
    assert determine_status(raw.exit_code, raw.timed_out, raw.launch_error, [])[0] == "ERROR"
    assert "could not launch" in (tmp_path / "l.log").read_text()


def test_arguments_with_spaces_and_metacharacters(tmp_path):
    out = tmp_path / "dir with space"
    out.mkdir()
    tricky = "a b; echo INJECTED $(whoami)"
    raw = run_command([sys.executable, "-c", "import sys; print(sys.argv[1])", tricky],
                      str(out), str(out / "l.log"), 10)
    text = (out / "l.log").read_text()
    assert raw.exit_code == 0 and text.strip() == tricky


def test_status_mapping():
    assert determine_status(0, False, None, [])[0] == "PASS"
    assert determine_status(0, False, None, [{"category": "FAIL", "snippet": "FAIL: x"}])[0] == "FAIL"
    assert determine_status(0, False, None, [{"category": "ERROR"}])[0] == "PASS"  # plain ERROR text alone is not a verdict
    assert determine_status(1, False, None, [])[0] == "FAIL"
    assert determine_status(127, False, None, [])[0] == "ERROR"
    assert determine_status(0, True, None, [])[0] == "TIMEOUT"


# ---- regression tests from the audit ----
def test_nul_byte_argument_is_an_error_not_a_crash(tmp_path):
    raw = run_command(["echo", "a\0b"], str(tmp_path), str(tmp_path / "l.log"), 5)
    assert raw.launch_error and raw.exit_code is None
    assert determine_status(raw.exit_code, raw.timed_out, raw.launch_error, [])[0] == "ERROR"


# ---- timeout / process-tree cleanup ----
def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    return str(p)


def test_timeout_kills_child_that_started_its_own_session(tmp_path):
    marker = tmp_path / "escaped_child_survived"
    child = _write(tmp_path, "child.py", f"import time\ntime.sleep(2)\nopen({str(marker)!r}, 'w').close()\n")
    parent = _write(tmp_path, "parent.py",
                    "import subprocess, sys, time\n"
                    f"subprocess.Popen([sys.executable, {child!r}], start_new_session=True)\n"
                    "time.sleep(60)\n")
    raw = run_command([sys.executable, parent], str(tmp_path), str(tmp_path / "l.log"), 0.7)
    assert raw.timed_out
    import time
    time.sleep(3)
    assert not marker.exists(), "child in a separate session survived the timeout"


def test_timeout_kills_grandchild_chain_and_sigterm_ignorers(tmp_path):
    marker = tmp_path / "grandchild_survived"
    grandchild = _write(tmp_path, "gc.py",
                        "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        f"time.sleep(4)\nopen({str(marker)!r}, 'w').close()\n")   # outlives the 2 s SIGTERM grace
    child = _write(tmp_path, "c.py", "import subprocess, sys, time\n"
                   f"subprocess.Popen([sys.executable, {grandchild!r}], start_new_session=True)\ntime.sleep(60)\n")
    parent = _write(tmp_path, "p.py", "import subprocess, sys, time\n"
                    f"subprocess.Popen([sys.executable, {child!r}], start_new_session=True)\ntime.sleep(60)\n")
    t0 = __import__("time").monotonic()
    raw = run_command([sys.executable, parent], str(tmp_path), str(tmp_path / "l.log"), 0.7)
    assert raw.timed_out and __import__("time").monotonic() - t0 < 10
    __import__("time").sleep(3)
    assert not marker.exists()


def test_orphan_that_left_before_timeout_is_a_documented_limit(tmp_path):
    """Documents the limit: a daemon already re-parented to init cannot be found. Not asserted as killed."""
    from autotestx.runner import _descendants
    import os
    assert os.getpid() not in _descendants(os.getpid())


# ---- log size cap ----
def test_oversized_output_is_capped_keeping_head_and_tail(tmp_path):
    code = ("import sys\nprint('HEAD-MARKER')\n"
            "for i in range(200000): print('line', i, 'x' * 50)\nprint('TAIL-MARKER')\n")
    log = tmp_path / "big.log"
    raw = run_command([sys.executable, "-c", code], str(tmp_path), str(log), 30, max_log_bytes=64 * 1024)
    assert raw.exit_code == 0 and raw.log_truncated and raw.log_bytes_total > 10_000_000
    data = log.read_bytes()
    assert len(data) < 64 * 1024 + 400
    text = data.decode(errors="replace")
    assert "HEAD-MARKER" in text and "TAIL-MARKER" in text and "AUTOTESTX: LOG TRUNCATED" in text


def test_small_output_is_not_marked_truncated(tmp_path):
    raw = run_command([sys.executable, "-c", "print('hi')"], str(tmp_path), str(tmp_path / "l.log"), 10,
                      max_log_bytes=4096)
    assert not raw.log_truncated and raw.log_bytes_total == 3


def test_flooding_process_is_still_killed_by_timeout_and_log_stays_small(tmp_path):
    code = "while True:\n    print('y' * 1000)\n"
    log = tmp_path / "flood.log"
    raw = run_command([sys.executable, "-c", code], str(tmp_path), str(log), 1, max_log_bytes=32 * 1024)
    assert raw.timed_out and raw.log_truncated
    assert log.stat().st_size < 32 * 1024 + 600
    assert "TIMEOUT" in log.read_text(errors="replace")


# ---- error classification ----
from autotestx.log_analysis import execution_category  # noqa: E402


def test_launch_error_kinds(tmp_path):
    missing = run_command(["no-such-binary-xyz"], str(tmp_path), str(tmp_path / "a.log"), 5)
    assert missing.launch_error_kind == "missing_executable"
    script = tmp_path / "s.sh"
    script.write_text("#!/bin/sh\necho hi\n")           # not executable
    denied = run_command([str(script)], str(tmp_path), str(tmp_path / "b.log"), 5)
    assert denied.launch_error_kind == "permission_denied"
    nul = run_command(["echo", "a\0b"], str(tmp_path), str(tmp_path / "c.log"), 5)
    assert nul.launch_error_kind == "invalid_command"
    garbage = tmp_path / "g.bin"
    garbage.write_bytes(b"\x00\x01\x02not a program")
    garbage.chmod(0o755)
    bad = run_command([str(garbage)], str(tmp_path), str(tmp_path / "d.log"), 5)
    assert bad.launch_error_kind == "launch_error"


def test_execution_categories():
    assert execution_category(None, False, "missing_executable") == "missing_tool"
    assert execution_category(None, False, "permission_denied") == "permission_denied"
    assert execution_category(None, False, "invalid_command") == "launch_error"
    assert execution_category(None, True, None) == "timeout"
    assert execution_category(127, False, None) == "missing_tool"
    assert execution_category(126, False, None) == "permission_denied"
    assert execution_category(-11, False, None) == "runtime_error"
    assert execution_category(1, False, None) is None
    assert execution_category(0, False, None) is None


def test_signal_death_is_fail_with_signal_name(tmp_path):
    raw = run_command([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"],
                      str(tmp_path), str(tmp_path / "l.log"), 10)
    status, reason = determine_status(raw.exit_code, raw.timed_out, raw.launch_error, [])
    assert raw.exit_code == -11 and status == "FAIL" and "SIGSEGV" in reason


def test_exit_126_is_error_not_fail():
    assert determine_status(126, False, None, [])[0] == "ERROR"
