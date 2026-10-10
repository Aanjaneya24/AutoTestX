"""Tcl testbench lint: positive and negative cases (skipped if tclsh is absent)."""
import shutil
import subprocess
from pathlib import Path

import pytest

TCL = Path(__file__).resolve().parents[1] / "tcl" / "demo_tests.tcl"
pytestmark = pytest.mark.skipif(not shutil.which("tclsh"), reason="tclsh not installed")

GOOD = 'module tb;\n initial begin\n  if (x) $display("FAIL: bad");\n  else $display("PASS: ok");\n end\nendmodule\n'


def lint(tmp_path, *specs, **tbs):
    for name, body in tbs.items():
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / "tb.v").write_text(body)
    p = subprocess.run(["tclsh", str(TCL), str(tmp_path), *specs], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_complete_testbench_ok(tmp_path):
    rc, out, _ = lint(tmp_path, "good", good=GOOD)
    assert rc == 0 and "SCENARIO good OK" in out and "ok=1 bad=0" in out


def test_fatal_call_counts_as_failure_marker(tmp_path):
    rc, out, _ = lint(tmp_path, "t", t='module tb;\ninitial begin $display("PASS"); $fatal(1, "x"); end\nendmodule\n')
    assert rc == 0, out


@pytest.mark.parametrize("body", [
    'module tb;\n// $display("PASS"); $display("FAIL");\nendmodule\n',
    'module tb;\n/* $display("PASS");\n $display("FAIL"); */\nendmodule\n',
    'module tb; initial $display("hello"); // PASS FAIL\nendmodule\n',
])
def test_markers_only_in_comments_are_rejected(tmp_path, body):
    rc, out, _ = lint(tmp_path, "c", c=body)
    assert rc == 1 and "SCENARIO c BAD" in out


def test_comment_markers_rejected_specific_message(tmp_path):
    rc, out, _ = lint(tmp_path, "c", c='module tb;\n// "PASS" "FAIL"\nendmodule\n')
    assert rc == 1 and "no string literal containing PASS" in out


def test_marker_inside_string_with_slashes_still_counts(tmp_path):
    rc, out, _ = lint(tmp_path, "s", s='module tb; initial begin $display("// PASS http://x"); $display("ERROR: y"); end endmodule\n')
    assert rc == 0, out


def test_missing_failure_marker_rejected(tmp_path):
    rc, out, _ = lint(tmp_path, "p", p='module tb; initial $display("PASS"); endmodule\n')
    assert rc == 1 and "no FAIL/ASSERT/ERROR" in out


def test_module_name_only_in_comment_or_wrong_top_rejected(tmp_path):
    rc, out, _ = lint(tmp_path, "a", "b", a='// module tb;\nmodule other; endmodule\n', b="module tb_x; endmodule\n")
    assert rc == 1 and out.count("BAD") == 2 and "ok=0 bad=2" in out


def test_missing_file_and_directory(tmp_path):
    rc, out, _ = lint(tmp_path, "nope")
    assert rc == 1 and "missing" in out


def test_relax_flags_are_explicit_and_scoped(tmp_path):
    body = 'module tb; initial $display("hello"); endmodule\n'
    assert lint(tmp_path, "h", h=body)[0] == 1                       # no hardcoded exemption by name
    assert lint(tmp_path, "h:no-pass,no-fail")[0] == 0
    assert lint(tmp_path, "h:no-pass")[0] == 1                       # still needs a failure marker
    assert lint(tmp_path, "h:no-fail")[0] == 1                       # still needs a PASS marker


def test_hang_and_compile_error_names_get_no_special_treatment(tmp_path):
    rc, out, _ = lint(tmp_path, "hang", "compile_error", hang='module tb; endmodule\n', compile_error='module tb; endmodule\n')
    assert rc == 1 and out.count("BAD") == 2


def test_usage_and_unknown_relax_exit_64(tmp_path):
    assert subprocess.run(["tclsh", str(TCL)], capture_output=True).returncode == 64
    rc, _, err = lint(tmp_path, "x:bogus")
    assert rc == 64 and "unknown relax keyword" in err
