from autotestx.preflight import check_tools, missing


def test_found_and_missing_tools_named():
    st = check_tools({"perl": "perl", "ghost": "no-such-tool-xyz"})
    gone = missing(st)
    assert [s.role for s in gone] == ["ghost"]
    assert next(s for s in st if s.role == "perl").found


def test_support_files_present_in_source_tree():
    from autotestx.preflight import missing_support_files
    assert missing_support_files() == []


def test_missing_support_files_blocks_run_and_doctor(monkeypatch, capsys):
    from autotestx import cli
    monkeypatch.setattr(cli, "missing_support_files", lambda: ["/nowhere/parse_logs.pl"])
    assert cli.main(["doctor"]) == 3
    assert cli.main(["run", "--config", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "configs" / "demo.yaml")]) == 3
    assert "editable" in capsys.readouterr().err
