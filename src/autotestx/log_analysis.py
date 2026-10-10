"""Deterministic log analysis: Perl parser wrapper, rule-based classifier, status mapping."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from .models import ERROR, FAIL, PASS, TIMEOUT

PARSER = Path(__file__).resolve().parents[2] / "scripts" / "parse_logs.pl"

# Failure categories shared by the rule baseline and the ML model.
LABELS = ("compile_error", "assertion_failure", "timeout", "runtime_error", "unknown")

# Parser categories that mean "the test itself reported a problem".
FAILURE_EVENTS = {"FAIL", "ASSERT", "FATAL"}

# With exit code 0, only a line that *starts* with a failure marker (optionally after a [time]
# prefix) overrides the exit code. Summaries such as "5 PASS, 0 FAIL" or "assertion a1 passed" do not.
_STRICT_FAILURE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(?:FAIL(?:ED|URE)?|ASSERT\w*|FATAL|\$fatal|UVM_(?:ERROR|FATAL))\b", re.I)
_ASSERT_PASSED = re.compile(r"^\W*ASSERT\w*\W+PASS", re.I)


def _is_failure_marker(finding: dict) -> bool:
    snippet = finding.get("snippet", "")
    return (finding.get("category") in FAILURE_EVENTS and bool(_STRICT_FAILURE.match(snippet))
            and not _ASSERT_PASSED.match(snippet))
EVIDENCE_EVENTS = {"TIMEOUT", "ASSERT", "FATAL", "FAIL", "ERROR"}

# Ordered: first matching label wins.
_RULES = (
    ("timeout", re.compile(r"\btime[d ]?-?\s?out\b|\btimeout\b|watchdog|exceeded .{0,30}limit", re.I)),
    ("compile_error", re.compile(
        r"syntax error|compilation failed|malformed statement|unable to bind|unknown module type"
        r"|cannot be elaborated|undefined (?:symbol|reference|identifier)|\.s?v:\d+: error"
        r"|could not find (?:module|include)|I give up", re.I)),
    ("assertion_failure", re.compile(
        r"assert(?:ion)?|expected .{0,40}(?:got|but|actual)|mismatch|check failed", re.I)),
    ("runtime_error", re.compile(
        r"\bFATAL\b|segmentation fault|core dumped|runtime error|out of memory|stack overflow"
        r"|division by zero|illegal instruction|bus error|killed", re.I)),
)


def run_parser(log_path: str, perl: str = "perl", timeout: float = 30) -> tuple:
    """Run the Perl parser. Returns (events, error_message_or_None); never raises."""
    try:
        proc = subprocess.run([perl, str(PARSER), log_path], capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"parser could not run: {exc}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], f"parser produced invalid JSON (exit {proc.returncode}): {proc.stderr.strip()[:200]}"
    if proc.returncode != 0 or data.get("error"):
        return [], data.get("error") or f"parser exit {proc.returncode}"
    return data.get("events", []), None


def rule_classify(text: str) -> str:
    """Transparent keyword baseline. Returns one of LABELS."""
    for label, pattern in _RULES:
        if pattern.search(text or ""):
            return label
    return "unknown"


def failure_snippet(log_text: str, findings: list, max_events: int = 10, tail_lines: int = 20) -> str:
    """Evidence text for classification: key parser events, else the log tail."""
    picked = [f["snippet"] for f in findings if f.get("category") in EVIDENCE_EVENTS][:max_events]
    if picked:
        return "\n".join(picked)
    return "\n".join(log_text.splitlines()[-tail_lines:])


def execution_category(exit_code: Optional[int], timed_out: bool, launch_error_kind: Optional[str]) -> Optional[str]:
    """Category for failures that are about *how the process ran*, not what it printed (None if not applicable)."""
    if launch_error_kind:
        return {"missing_executable": "missing_tool", "permission_denied": "permission_denied"}.get(
            launch_error_kind, "launch_error")
    if timed_out:
        return "timeout"
    if exit_code in (127,):
        return "missing_tool"
    if exit_code == 126:
        return "permission_denied"
    if exit_code is not None and exit_code < 0:
        return "runtime_error"          # killed by a signal (e.g. SIGSEGV)
    return None


def _signal_name(exit_code: int) -> str:
    import signal
    try:
        return signal.Signals(-exit_code).name
    except ValueError:
        return str(-exit_code)


def determine_status(exit_code: Optional[int], timed_out: bool, launch_error: Optional[str],
                     findings: list) -> tuple:
    """Map process outcome + explicit log markers to (status, reason). ML is never consulted."""
    if launch_error:
        return ERROR, f"could not launch command: {launch_error}"
    if timed_out:
        return TIMEOUT, "exceeded timeout; process tree killed"
    if exit_code == 127:
        return ERROR, "exit 127: a required tool or command was not found"
    if exit_code == 126:
        return ERROR, "exit 126: command found but not executable (permission denied)"
    if exit_code < 0:
        return FAIL, f"terminated by signal {_signal_name(exit_code)} (exit code {exit_code})"
    if exit_code != 0:
        return FAIL, f"non-zero exit code {exit_code}"
    marked = sorted({f["category"] for f in findings if _is_failure_marker(f)})
    if marked:
        return FAIL, f"exit 0 but log contains explicit failure markers: {', '.join(marked)}"
    return PASS, "exit 0 and no failure markers in log"
