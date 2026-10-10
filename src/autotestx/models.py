"""Plain data containers shared across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Deterministic test statuses (never influenced by ML).
PASS, FAIL, TIMEOUT, ERROR = "PASS", "FAIL", "TIMEOUT", "ERROR"
STATUSES = (PASS, FAIL, TIMEOUT, ERROR)
EXPECTATIONS = {"pass": PASS, "fail": FAIL, "timeout": TIMEOUT, "error": ERROR}


@dataclass(frozen=True)
class TestSpec:
    __test__ = False  # not a pytest class
    name: str
    command: tuple
    timeout_seconds: float
    description: str = ""
    tags: tuple = ()
    expect: str = "pass"


@dataclass(frozen=True)
class Config:
    project_name: str
    simulator: str
    output_dir: str
    default_timeout_seconds: float
    enable_ml_classification: bool
    ml_model_path: str
    ml_confidence_threshold: float
    tools: dict
    tests: tuple
    root: str            # directory commands run in and relative paths resolve against
    source_path: str
    max_log_bytes: int = 5 * 1024 * 1024


@dataclass
class RawRun:
    """Outcome of one subprocess execution."""
    exit_code: Optional[int]
    timed_out: bool
    launch_error: Optional[str]
    start_time: str
    duration_seconds: float
    launch_error_kind: Optional[str] = None   # missing_executable | permission_denied | launch_error | invalid_command
    log_bytes_total: int = 0                  # bytes the process produced (before truncation)
    log_truncated: bool = False


@dataclass
class TestResult:
    __test__ = False
    name: str
    run_id: str
    status: str
    expected_status: str
    exit_code: Optional[int]
    timed_out: bool
    start_time: str
    duration_seconds: float
    log_path: str
    command: list
    tags: list = field(default_factory=list)
    description: str = ""
    # Deterministic analysis
    findings: list = field(default_factory=list)       # Perl parser events
    parser_error: Optional[str] = None
    rule_category: Optional[str] = None                # rule-based failure category
    status_reason: str = ""
    log_bytes_total: int = 0
    log_truncated: bool = False
    # ML (kept separate; never alters status)
    ml_prediction: Optional[dict] = None

    @property
    def matches_expectation(self) -> bool:
        return self.status == self.expected_status

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "run_id": self.run_id,
            "status": self.status,
            "expected_status": self.expected_status,
            "matches_expectation": self.matches_expectation,
            "status_reason": self.status_reason,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "start_time": self.start_time,
            "duration_seconds": round(self.duration_seconds, 3),
            "log_path": self.log_path,
            "log_bytes_total": self.log_bytes_total,
            "log_truncated": self.log_truncated,
            "command": self.command,
            "tags": self.tags,
            "description": self.description,
            "rule_based": {"category": self.rule_category, "findings": self.findings,
                           "parser_error": self.parser_error},
            "ml_prediction": self.ml_prediction,
        }
