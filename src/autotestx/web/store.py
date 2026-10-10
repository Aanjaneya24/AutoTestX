"""Read-only access to run directories. Never trusts paths found inside result files."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TEST_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
CONSOLE_DIR = ".console"
CONSOLE_TAIL_BYTES = 32 * 1024


def valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_RE.fullmatch(run_id or ""))


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def console_path(runs_root: Path, run_id: str) -> Path:
    return runs_root / CONSOLE_DIR / f"{run_id}.log"


def console_tail(runs_root: Path, run_id: str) -> str:
    p = console_path(runs_root, run_id)
    try:
        size = p.stat().st_size
        with open(p, "rb") as fh:
            fh.seek(max(0, size - CONSOLE_TAIL_BYTES))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def run_exists(runs_root: Path, run_id: str, active_id: Optional[str] = None) -> bool:
    return valid_run_id(run_id) and ((runs_root / run_id).is_dir() or console_path(runs_root, run_id).is_file()
                                     or run_id == active_id)


def list_run_ids(runs_root: Path) -> list:
    ids = set()
    if runs_root.is_dir():
        ids.update(p.name for p in runs_root.iterdir() if p.is_dir() and valid_run_id(p.name) and p.name != CONSOLE_DIR)
        console = runs_root / CONSOLE_DIR
        if console.is_dir():
            ids.update(p.stem for p in console.glob("*.log") if valid_run_id(p.stem))
    return sorted(ids, reverse=True)       # ids start with a timestamp, so this is newest first


def run_state(runs_root: Path, run_id: str, active_id: Optional[str], exit_code: Optional[int]) -> dict:
    """Derive {'state', 'status' (status.json or None), 'results' (results.json or None), 'error'}.

    states: starting | running | completed | failed | interrupted
    """
    run_dir = runs_root / run_id
    status = _read_json(run_dir / "status.json")
    results = _read_json(run_dir / "results.json")
    error = None
    if results is not None and (status is None or status.get("state") != "failed"):
        state = "completed"
    elif status is not None:
        state = status.get("state", "failed")
        if state == "running" and run_id != active_id and not pid_alive(status.get("pid")):
            state = "interrupted"
            error = "the run process is gone before finishing (server or machine restarted, or it was killed)"
        elif state in ("failed", "interrupted"):
            error = status.get("error")
    elif run_id == active_id:
        state = "starting"
    else:
        state = "failed"
        error = "the run never started a result directory"
    if state == "failed" and error is None:
        error = f"run process exited with code {exit_code}" if exit_code is not None else "run failed"
    return {"state": state, "status": status, "results": results, "error": error}


def _duration(started: Optional[str], finished: Optional[str], state: str) -> Optional[float]:
    s = _parse(started)
    if s is None:
        return None
    f = _parse(finished) if finished else (datetime.now(timezone.utc) if state in ("running", "starting") else None)
    return round((f - s).total_seconds(), 1) if f else None


def classify_test(t: dict) -> str:
    """passed | expected_failure | unexpected_failure | unexpected_pass (never show an expected failure as success)."""
    expected = t.get("expected_status", "PASS")
    status = t.get("status")
    if status == expected:
        return "passed" if status == "PASS" else "expected_failure"
    return "unexpected_pass" if status == "PASS" else "unexpected_failure"


def public_test(t: dict, run_dir: Path) -> dict:
    """A test record without absolute filesystem paths."""
    rb = t.get("rule_based") or {}
    name = t["name"]
    log = run_dir / "logs" / f"{name}.log"
    return {
        "name": name,
        "status": t.get("status"),
        "expected_status": t.get("expected_status", "PASS"),
        "outcome": classify_test(t),
        "exit_code": t.get("exit_code"),
        "timed_out": t.get("timed_out", False),
        "duration_seconds": t.get("duration_seconds"),
        "start_time": t.get("start_time"),
        "status_reason": t.get("status_reason", ""),
        "description": t.get("description", ""),
        "tags": t.get("tags", []),
        "command": t.get("command", []),
        "rule_category": rb.get("category"),
        "findings": rb.get("findings", []),
        "parser_error": rb.get("parser_error"),
        "ml_prediction": t.get("ml_prediction"),
        "log_available": log.is_file() and not log.is_symlink(),
        "log_truncated": bool(t.get("log_truncated", False)),
        "log_bytes_total": t.get("log_bytes_total"),
    }


def ml_summary(tests: list) -> dict:
    preds = [t for t in tests if t.get("ml_prediction")]
    labels: dict = {}
    agree = review = 0
    for t in preds:
        p = t["ml_prediction"]
        labels[p.get("label")] = labels.get(p.get("label"), 0) + 1
        review += 1 if p.get("needs_review") else 0
        agree += 1 if p.get("top_label", p.get("label")) == (t.get("rule_based") or {}).get("category") else 0
    return {"classified": len(preds), "labels": labels, "needs_review": review, "agree_with_rules": agree}


def summarise(runs_root: Path, run_id: str, active_id: Optional[str], exit_code: Optional[int]) -> dict:
    st = run_state(runs_root, run_id, active_id, exit_code)
    results, status = st["results"], st["status"] or {}
    totals = results.get("totals") if results else None
    if totals is None and status.get("tests"):
        done = [t for t in status["tests"] if t.get("state") == "done"]
        totals = {"total": status.get("total", len(status["tests"])),
                  "passed": sum(1 for t in done if t.get("status") == "PASS"),
                  "failed": sum(1 for t in done if t.get("status") == "FAIL"),
                  "errored": sum(1 for t in done if t.get("status") == "ERROR"),
                  "timed_out": sum(1 for t in done if t.get("status") == "TIMEOUT"),
                  "unexpected": sum(1 for t in done if t.get("matches_expectation") is False),
                  "completed": len(done)}
    started = (results or {}).get("started") or status.get("started")
    finished = (results or {}).get("finished") or status.get("finished")
    state = st["state"]
    if state == "completed":
        overall = "as_expected" if (results or {}).get("all_as_expected", status.get("all_as_expected")) else "unexpected_results"
    else:
        overall = state
    return {
        "run_id": run_id, "state": state, "overall": overall, "error": st["error"],
        "project": (results or {}).get("project") or status.get("project"),
        "started": started, "finished": finished,
        "duration_seconds": _duration(started, finished, state),
        "totals": totals, "all_as_expected": (results or {}).get("all_as_expected"),
        "unexpected_tests": (results or {}).get("unexpected_tests", []),
        "ml": ml_summary((results or {}).get("tests", [])) if results else None,
    }


def log_dir_for(runs_root: Path, run_id: str) -> Path:
    return runs_root / run_id / "logs"


def safe_log_path(runs_root: Path, run_id: str, test_name: str) -> Optional[Path]:
    """Path of a test's log, or None. The name has already been checked against the run's own test list."""
    if not valid_run_id(run_id) or not TEST_NAME_RE.fullmatch(test_name or ""):
        return None
    logs = log_dir_for(runs_root, run_id).resolve()
    p = logs / f"{test_name}.log"
    if p.is_symlink() or not p.is_file():
        return None
    try:
        p.resolve().relative_to(logs)
    except ValueError:
        return None
    return p


def offset_of_line(path: Path, line: int) -> int:
    """Byte offset where 1-based `line` starts (end of file if the log is shorter)."""
    offset = 0
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh, 1):
            if n >= line:
                return offset
            offset += len(raw)
    return offset


def read_log_chunk(path: Path, offset: int, limit: int, tail: bool) -> dict:
    size = path.stat().st_size
    if tail:
        offset = max(0, size - limit)
    offset = max(0, min(offset, size))
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(limit)
        newlines_before = 0
        if offset:
            fh.seek(0)
            remaining = offset
            while remaining > 0:
                block = fh.read(min(65536, remaining))
                if not block:
                    break
                newlines_before += block.count(b"\n")
                remaining -= len(block)
    return {"text": data.decode("utf-8", errors="replace"), "offset": offset, "next_offset": offset + len(data),
            "size": size, "has_more": offset + len(data) < size, "start_line": newlines_before + 1}


def search_log(path: Path, query: str, max_matches: int) -> dict:
    needle = query.lower()
    matches, total = [], 0
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if needle in line.lower():
                total += 1
                if len(matches) < max_matches:
                    matches.append({"line": n, "text": line[:300]})
    return {"query": query, "matches": matches, "total_matches": total, "capped": total > len(matches)}
