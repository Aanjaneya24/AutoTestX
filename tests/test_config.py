import json
from pathlib import Path

import pytest

from autotestx.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]

VALID = """
project: {name: t, simulator: iverilog}
tools: {simulator: iverilog, runtime: vvp, python: python3, perl: perl, tclsh: tclsh}
tests:
  - name: a
    command: [echo, hi]
"""


def write(tmp_path, text, name="c.yaml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_demo_config_loads():
    cfg = load_config(ROOT / "configs" / "demo.yaml")
    assert len(cfg.tests) == 6
    assert cfg.tests[0].command[0] == "bash"
    assert cfg.root == str(ROOT)


def test_defaults_applied(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.tests[0].timeout_seconds == 30
    assert cfg.tests[0].expect == "pass"
    assert cfg.tools["bash"] == "bash"


def test_json_config(tmp_path):
    data = {"project": {"name": "t", "simulator": "x"},
            "tools": {"simulator": "a", "runtime": "b", "python": "c", "perl": "d", "tclsh": "e"},
            "tests": [{"name": "a", "command": ["true"]}]}
    assert load_config(write(tmp_path, json.dumps(data), "c.json")).project_name == "t"


def test_malformed_yaml(tmp_path):
    with pytest.raises(ConfigError, match="malformed"):
        load_config(write(tmp_path, "tests: [unclosed"))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "nope.yaml")


def test_missing_fields_named(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, "project: {name: t}\ntests:\n  - name: a\n"))
    msg = str(exc.value)
    assert "project.simulator" in msg
    assert "tools" in msg
    assert "tests[a].command" in msg


def test_unknown_field_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown field 'bogus'"):
        load_config(write(tmp_path, VALID + "    bogus: 1\n"))


def test_command_must_be_list(tmp_path):
    with pytest.raises(ConfigError, match="command"):
        load_config(write(tmp_path, VALID.replace("[echo, hi]", "echo hi")))


def test_duplicate_names_and_bad_timeout(tmp_path):
    text = VALID + "    timeout_seconds: -1\n  - name: a\n    command: [x]\n"
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, text))
    assert "duplicate" in str(exc.value) and "timeout_seconds" in str(exc.value)


def test_bad_expect(tmp_path):
    with pytest.raises(ConfigError, match="expect"):
        load_config(write(tmp_path, VALID + "    expect: maybe\n"))


# ---- regression tests from the audit ----
def test_case_insensitive_duplicate_names_rejected(tmp_path):
    text = VALID + "  - name: A\n    command: [x]\n"
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(write(tmp_path, text))


def test_nul_byte_in_command_rejected(tmp_path):
    with pytest.raises(ConfigError, match="NUL"):
        load_config(write(tmp_path, VALID.replace("[echo, hi]", '["a\\0b"]')))


@pytest.mark.parametrize("bad", [".inf", ".nan", "0", "-5", "true"])
def test_non_finite_or_nonpositive_timeouts_rejected(tmp_path, bad):
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_config(write(tmp_path, VALID + f"    timeout_seconds: {bad}\n"))


def test_max_log_bytes_validation(tmp_path):
    ok = load_config(write(tmp_path, VALID.replace("tools:", "settings: {max_log_bytes: 2048}\ntools:")))
    assert ok.max_log_bytes == 2048
    assert load_config(write(tmp_path, VALID, "d.yaml")).max_log_bytes == 5 * 1024 * 1024
    for bad in ("10", "1.5e6", "true", '"big"'):
        with pytest.raises(ConfigError, match="max_log_bytes"):
            load_config(write(tmp_path, VALID.replace("tools:", f"settings: {{max_log_bytes: {bad}}}\ntools:"), "e.yaml"))
