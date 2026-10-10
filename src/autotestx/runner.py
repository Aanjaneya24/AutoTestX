"""Execute configured tests safely (argument lists, timeouts, process-group kill)."""
from __future__ import annotations

import json
import os
import platform
import secrets
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .config import resolve
from .log_analysis import (determine_status, execution_category, failure_snippet, rule_classify, run_parser)
from .models import EXPECTATIONS, Config, RawRun, TestResult, TestSpec
from .preflight import check_tools
from .report import build_summary, write_all

KILL_GRACE_SECONDS = 2.0
DEFAULT_MAX_LOG_BYTES = 5 * 1024 * 1024
_DRAIN_GRACE_SECONDS = 2.0


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def _error_kind(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "missing_executable"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, ValueError):
        return "invalid_command"
    return "launch_error"


def _drain_to_log(fd: int, path: str, max_bytes: int, stop: threading.Event, stats: dict) -> None:
    """Copy `fd` to `path`, keeping at most ~max_bytes: the first half and the last half of the output.

    Memory is bounded by max_bytes (+ one read chunk); the process is never blocked because the
    pipe is always drained. A marker line records how many bytes were omitted.
    """
    head_cap = max_bytes // 2
    tail_cap = max_bytes - head_cap
    head_written = total = tail_len = 0
    tail: deque = deque()
    stop_at = None
    with open(path, "wb") as out:
        while True:
            if stop.is_set() and stop_at is None:
                stop_at = time.monotonic()
            if stop_at is not None and time.monotonic() - stop_at > _DRAIN_GRACE_SECONDS:
                break          # a surviving descendant still holds the pipe open and keeps writing
            if not select.select([fd], [], [], 0.1)[0]:
                if stop_at is not None:
                    break
                continue
            data = os.read(fd, 65536)
            if not data:
                break
            total += len(data)
            if head_written < head_cap:
                take = data[:head_cap - head_written]
                out.write(take)
                head_written += len(take)
                data = data[len(take):]
            if data:
                tail.append(data)
                tail_len += len(data)
                while tail_len - len(tail[0]) >= tail_cap:
                    tail_len -= len(tail.popleft())
        tail_bytes = b"".join(tail)[-tail_cap:]
        omitted = total - head_written - len(tail_bytes)
        if omitted > 0:
            out.write(f"\nAUTOTESTX: LOG TRUNCATED: {omitted} of {total} bytes omitted "
                      f"(max_log_bytes={max_bytes}); kept first {head_written} and last {len(tail_bytes)} bytes\n".encode())
        out.write(tail_bytes)
    stats["total"], stats["truncated"] = total, omitted > 0


def run_command(command, cwd: str, log_path: str, timeout: float, env: Optional[dict] = None,
                max_log_bytes: int = DEFAULT_MAX_LOG_BYTES) -> RawRun:
    """Run `command` (argument list, never a shell string); combined stdout+stderr go to log_path (size-capped)."""
    start_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.monotonic()
    timed_out = False
    exit_code: Optional[int] = None
    launch_error: Optional[str] = None
    kind: Optional[str] = None
    stats = {"total": 0, "truncated": False}
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(list(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True,
                                env={**os.environ, **(env or {})})
    except (OSError, ValueError) as exc:  # ValueError: e.g. embedded NUL byte in an argument
        launch_error = f"{type(exc).__name__}: {getattr(exc, 'strerror', None) or exc}"
        kind = _error_kind(exc)
        Path(log_path).write_text(f"AUTOTESTX: ERROR could not launch {list(command)!r}: {launch_error}\n")
    else:
        stop = threading.Event()
        reader = threading.Thread(target=_drain_to_log, daemon=True,
                                  args=(proc.stdout.fileno(), log_path, max_log_bytes, stop, stats))
        reader.start()
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
        except BaseException:       # SIGTERM/Ctrl-C of the whole run: never leave the test's processes behind
            _kill_tree(proc)
            stop.set()
            raise
        stop.set()
        reader.join(timeout=_DRAIN_GRACE_SECONDS + 5)
        proc.stdout.close()
        if timed_out:
            with open(log_path, "ab") as log:
                log.write(f"\nAUTOTESTX: TIMEOUT after {timeout:g}s; process tree killed\n".encode())
    return RawRun(exit_code, timed_out, launch_error, start_iso, time.monotonic() - t0,
                  kind, stats["total"], stats["truncated"])


def _descendants(root_pid: int) -> set:
    """All live descendants of root_pid (any session/process group), via `ps`. Empty set if unavailable."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    children: dict = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, stack = set(), [root_pid]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


def _signal_all(pgid: int, pids, sig) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the test's process group AND every descendant, including ones that left the group.

    The tree is SIGSTOPped and enumerated while the parent is still alive (so children that called
    setsid are still linked to it), then SIGTERMed, given a grace period, then SIGKILLed.
    Not guaranteed: a process that was already orphaned (re-parented to init) before the snapshot
    cannot be found. Windows is unsupported.
    """
    # Freeze the tree first so nothing can fork while we look for it, then repeat until no new
    # descendants appear (a stopped process cannot spawn more).
    known: set = set()
    _signal_all(proc.pid, known, signal.SIGSTOP)
    for _ in range(10):
        new = _descendants(proc.pid) - known
        if not new:
            break
        known |= new
        _signal_all(proc.pid, new, signal.SIGSTOP)
    _signal_all(proc.pid, known, signal.SIGTERM)
    _signal_all(proc.pid, known, signal.SIGCONT)       # let them act on SIGTERM
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while time.monotonic() < deadline and (proc.poll() is None or any(_alive(p) for p in known)):
        time.sleep(0.05)
    _signal_all(proc.pid, {p for p in known if _alive(p)}, signal.SIGKILL)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL cannot be ignored
        pass


def analyse(spec: TestSpec, raw: RawRun, log_path: str, run_id: str, perl: str) -> TestResult:
    findings, parser_error = run_parser(log_path, perl)
    status, reason = determine_status(raw.exit_code, raw.timed_out, raw.launch_error, findings)
    result = TestResult(
        name=spec.name, run_id=run_id, status=status, expected_status=EXPECTATIONS[spec.expect],
        exit_code=raw.exit_code, timed_out=raw.timed_out, start_time=raw.start_time,
        duration_seconds=raw.duration_seconds, log_path=log_path, command=list(spec.command),
        tags=list(spec.tags), description=spec.description, findings=findings,
        parser_error=parser_error, status_reason=reason,
        log_bytes_total=raw.log_bytes_total, log_truncated=raw.log_truncated,
    )
    if status != "PASS":
        result.rule_category = execution_category(raw.exit_code, raw.timed_out, raw.launch_error_kind)
        if result.rule_category is None:
            text = Path(log_path).read_text(errors="replace")
            result.rule_category = rule_classify(failure_snippet(text, findings))
    return result


def environment_info(config: Config, tool_statuses: list) -> dict:
    return {
        "autotestx_version": __version__,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "tools": [{"role": s.role, "executable": s.executable, "path": s.path, "version": s.version}
                  for s in tool_statuses],
    }


def write_status(run_dir: Path, state: str, **fields) -> None:
    """Atomically write <run_dir>/status.json (live progress for the CLI user, the API and the UI)."""
    payload = {"state": state, "pid": os.getpid(), "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               **fields}
    tmp = run_dir / "status.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, run_dir / "status.json")


def run_suite(config: Config, run_id: Optional[str] = None,
              classify: Optional[Callable[[str], dict]] = None,
              progress: Optional[Callable[[TestResult], None]] = None,
              tool_statuses: Optional[list] = None) -> dict:
    """Run every test; write logs and results.json under a fresh run directory. Returns the summary dict."""
    run_id = run_id or new_run_id()
    run_dir = Path(resolve(config, config.output_dir)) / run_id
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(config.source_path, run_dir / ("config_snapshot" + Path(config.source_path).suffix))
    statuses = tool_statuses if tool_statuses is not None else check_tools(config.tools, config.enable_ml_classification)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan = [{"name": sp.name, "description": sp.description, "expect": EXPECTATIONS[sp.expect], "state": "pending"}
            for sp in config.tests]
    meta = {"run_id": run_id, "project": config.project_name, "started": started, "total": len(plan)}
    write_status(run_dir, "running", completed=0, current=None, tests=plan, **meta)
    results = []
    try:
        for i, spec in enumerate(config.tests):
            plan[i]["state"] = "running"
            write_status(run_dir, "running", completed=len(results), current=spec.name, tests=plan, **meta)
            log_path = str(log_dir / f"{spec.name}.log")
            build_dir = str(run_dir / "build" / spec.name)
            raw = run_command(spec.command, config.root, log_path, spec.timeout_seconds,
                              env={"AUTOTESTX_BUILD_DIR": build_dir, "AUTOTESTX_RUN_ID": run_id,
                                   "AUTOTESTX_TEST_NAME": spec.name},
                              max_log_bytes=config.max_log_bytes)
            result = analyse(spec, raw, log_path, run_id, config.tools["perl"])
            if classify and result.status != "PASS":
                text = Path(log_path).read_text(errors="replace")
                result.ml_prediction = classify(failure_snippet(text, result.findings))
            results.append(result)
            plan[i].update(state="done", status=result.status, duration_seconds=round(result.duration_seconds, 3),
                           exit_code=result.exit_code, category=result.rule_category,
                           matches_expectation=result.matches_expectation)
            write_status(run_dir, "running", completed=len(results), current=None, tests=plan, **meta)
            if progress:
                progress(result)
        shutil.rmtree(run_dir / "build", ignore_errors=True)

        summary = build_summary(config, run_id, str(run_dir), started, results, environment_info(config, statuses))
        write_all(summary)
    except KeyboardInterrupt:
        write_status(run_dir, "interrupted", completed=len(results), current=None, tests=plan,
                     error="the run was stopped (SIGTERM or Ctrl-C) before it finished", **meta)
        raise
    except BaseException as exc:
        write_status(run_dir, "failed", completed=len(results), current=None, tests=plan,
                     error=f"{type(exc).__name__}: {exc}", **meta)
        raise
    write_status(run_dir, "completed", completed=len(results), current=None, tests=plan,
                 finished=summary["finished"], all_as_expected=summary["all_as_expected"], **meta)
    return summary
