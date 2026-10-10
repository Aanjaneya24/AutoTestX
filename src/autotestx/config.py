"""Load and validate a YAML/JSON suite configuration."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import yaml

from .models import EXPECTATIONS, Config, TestSpec


class ConfigError(Exception):
    """Raised with every validation problem found, one per line."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_REQUIRED_TOOLS = ("simulator", "runtime", "python", "perl", "tclsh")
_DEFAULT_TOOLS = {"bash": "bash"}

_TOP_KEYS = {"project", "settings", "tools", "tests"}
_PROJECT_KEYS = {"name", "simulator"}
_SETTINGS_KEYS = {"output_dir", "default_timeout_seconds", "enable_ml_classification",
                  "ml_model_path", "ml_confidence_threshold", "max_log_bytes"}
_TOOLS_KEYS = set(_REQUIRED_TOOLS) | set(_DEFAULT_TOOLS)
_TEST_KEYS = {"name", "description", "command", "timeout_seconds", "tags", "expect"}


def _find_root(config_path: Path) -> Path:
    """Project root = nearest ancestor holding pyproject.toml, else the config's directory."""
    for parent in [config_path.parent, *config_path.parent.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return config_path.parent


def _unknown(section: str, data: dict, allowed: set, problems: list) -> None:
    for key in sorted(set(data) - allowed):
        problems.append(f"{section}: unknown field '{key}'")


def _number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def load_config(path) -> Config:
    path = Path(path).resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"cannot read config {path}: {exc.strerror or exc}"])
    try:
        raw = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ConfigError([f"malformed config {path.name}: {exc}"])
    if not isinstance(raw, dict):
        raise ConfigError([f"{path.name}: top level must be a mapping"])

    problems: list = []
    _unknown("config", raw, _TOP_KEYS, problems)

    def section(name, required=True):
        value = raw.get(name)
        if value is None:
            if required:
                problems.append(f"missing required section '{name}'")
            return {}
        if not isinstance(value, dict):
            problems.append(f"'{name}' must be a mapping")
            return {}
        return value

    project = section("project")
    settings = section("settings", required=False)
    tools = section("tools")
    _unknown("project", project, _PROJECT_KEYS, problems)
    _unknown("settings", settings, _SETTINGS_KEYS, problems)
    _unknown("tools", tools, _TOOLS_KEYS, problems)

    for key in ("name", "simulator"):
        if not isinstance(project.get(key), str) or not project.get(key):
            problems.append(f"project.{key} is required and must be a non-empty string")
    for key in _REQUIRED_TOOLS:
        if not isinstance(tools.get(key), str) or not tools.get(key):
            problems.append(f"tools.{key} is required and must be a non-empty string")
    merged_tools = {**_DEFAULT_TOOLS, **{k: v for k, v in tools.items() if isinstance(v, str)}}

    default_timeout = settings.get("default_timeout_seconds", 30)
    if not _number(default_timeout):
        problems.append("settings.default_timeout_seconds must be a positive number")
        default_timeout = 30
    ml_enabled = settings.get("enable_ml_classification", False)
    if not isinstance(ml_enabled, bool):
        problems.append("settings.enable_ml_classification must be true or false")
        ml_enabled = False
    threshold = settings.get("ml_confidence_threshold", 0.5)
    if not (isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and 0 < threshold <= 1):
        problems.append("settings.ml_confidence_threshold must be in (0, 1]")
        threshold = 0.5
    max_log = settings.get("max_log_bytes", 5 * 1024 * 1024)
    if not (isinstance(max_log, int) and not isinstance(max_log, bool) and max_log >= 1024):
        problems.append("settings.max_log_bytes must be an integer >= 1024")
        max_log = 5 * 1024 * 1024
    for key in ("output_dir", "ml_model_path"):
        if key in settings and not isinstance(settings[key], str):
            problems.append(f"settings.{key} must be a string")

    tests_raw = raw.get("tests")
    specs: list = []
    if not isinstance(tests_raw, list) or not tests_raw:
        problems.append("'tests' is required and must be a non-empty list")
        tests_raw = []
    seen: set = set()
    for i, item in enumerate(tests_raw):
        label = f"tests[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be a mapping")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            problems.append(f"{label}.name is required (letters, digits, '_', '.', '-' only)")
            name = None
        else:
            label = f"tests[{name}]"
            if name.lower() in seen:  # log files are named after tests; macOS/Windows are case-insensitive
                problems.append(f"{label}: duplicate test name (names are compared case-insensitively)")
            seen.add(name.lower())
        _unknown(label, item, _TEST_KEYS, problems)
        command = item.get("command")
        if (not isinstance(command, list) or not command
                or not all(isinstance(c, str) and c and "\0" not in c for c in command)):
            problems.append(f"{label}.command is required and must be a non-empty list of non-empty strings without NUL bytes")
            command = None
        timeout = item.get("timeout_seconds", default_timeout)
        if not _number(timeout):
            problems.append(f"{label}.timeout_seconds must be a positive number")
            timeout = None
        tags = item.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            problems.append(f"{label}.tags must be a list of strings")
            tags = []
        expect = item.get("expect", "pass")
        if expect not in EXPECTATIONS:
            problems.append(f"{label}.expect must be one of {sorted(EXPECTATIONS)}")
            expect = "pass"
        desc = item.get("description", "")
        if not isinstance(desc, str):
            problems.append(f"{label}.description must be a string")
            desc = ""
        if name and command and timeout:
            specs.append(TestSpec(name, tuple(command), float(timeout), desc, tuple(tags), expect))

    if problems:
        raise ConfigError(problems)

    return Config(
        project_name=project["name"],
        simulator=project["simulator"],
        output_dir=settings.get("output_dir", "reports/runs"),
        default_timeout_seconds=float(default_timeout),
        enable_ml_classification=ml_enabled,
        ml_model_path=settings.get("ml_model_path", "models/log_classifier.joblib"),
        ml_confidence_threshold=float(threshold),
        tools=merged_tools,
        tests=tuple(specs),
        root=str(_find_root(path)),
        source_path=str(path),
        max_log_bytes=max_log,
    )


def resolve(config: Config, relative: str) -> str:
    """Resolve a config-relative path against the project root."""
    return relative if os.path.isabs(relative) else os.path.join(config.root, relative)
