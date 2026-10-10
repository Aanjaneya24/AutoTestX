"""Terminal, JSON, CSV and HTML reporting."""
from __future__ import annotations

import csv
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .models import Config

CSV_FIELDS = ["run_id", "name", "status", "expected_status", "matches_expectation", "exit_code",
              "duration_seconds", "start_time", "rule_category", "ml_label", "ml_confidence",
              "log_path", "log_truncated", "status_reason"]


def build_summary(config: Config, run_id: str, run_dir: str, started: str, results: list,
                  environment: dict) -> dict:
    count = lambda s: sum(1 for r in results if r.status == s)  # noqa: E731
    unexpected = [r.name for r in results if not r.matches_expectation]
    return {
        "run_id": run_id,
        "project": config.project_name,
        "simulator": config.simulator,
        "config_file": config.source_path,
        "run_dir": run_dir,
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {"total": len(results), "passed": count("PASS"), "failed": count("FAIL"),
                   "errored": count("ERROR"), "timed_out": count("TIMEOUT"),
                   "unexpected": len(unexpected)},
        "unexpected_tests": unexpected,
        "all_as_expected": not unexpected,
        "environment": environment,
        "tests": [r.to_dict() for r in results],
    }


def write_json(summary: dict, path) -> None:
    Path(path).write_text(json.dumps(summary, indent=2) + "\n")


def write_csv(summary: dict, path) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for t in summary["tests"]:
            ml = t.get("ml_prediction") or {}
            writer.writerow({
                "run_id": t["run_id"], "name": t["name"], "status": t["status"],
                "expected_status": t["expected_status"], "matches_expectation": t["matches_expectation"],
                "exit_code": "" if t["exit_code"] is None else t["exit_code"],
                "duration_seconds": t["duration_seconds"], "start_time": t["start_time"],
                "rule_category": t["rule_based"]["category"] or "",
                "ml_label": ml.get("label", ""), "ml_confidence": ml.get("confidence", ""),
                "log_path": t["log_path"], "log_truncated": t.get("log_truncated", False),
                "status_reason": t["status_reason"],
            })


def text_summary(summary: dict) -> str:
    tot = summary["totals"]
    w = max([24] + [len(t["name"]) + 2 for t in summary["tests"]])
    lines = [f"Run {summary['run_id']}  project={summary['project']}",
             f"{'TEST':<{w}}{'STATUS':<9}{'EXPECT':<9}{'EXIT':<6}{'TIME':>7}  CATEGORY"]
    for t in summary["tests"]:
        mark = "" if t["matches_expectation"] else "  <-- UNEXPECTED"
        exit_code = "-" if t["exit_code"] is None else t["exit_code"]
        lines.append(f"{t['name']:<{w}}{t['status']:<9}{t['expected_status']:<9}{exit_code!s:<6}"
                     f"{t['duration_seconds']:>6.2f}s  {t['rule_based']['category'] or '-'}{mark}")
    lines.append(f"Total {tot['total']}: {tot['passed']} passed, {tot['failed']} failed, "
                 f"{tot['errored']} errored, {tot['timed_out']} timed out; "
                 f"{tot['unexpected']} differ from expectation")
    lines.append(f"Reports: {summary['run_dir']}")
    return "\n".join(lines)


_CSS = """
body{font-family:system-ui,sans-serif;margin:2rem;color:#1b1f24;background:#fff}
table{border-collapse:collapse;width:100%;margin:1rem 0}
th,td{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left;font-size:.9rem;vertical-align:top}
th{background:#f6f8fa}
.PASS{color:#1a7f37;font-weight:600}.FAIL,.ERROR{color:#cf222e;font-weight:600}.TIMEOUT{color:#9a6700;font-weight:600}
.unexpected{background:#fff8c5}
code,pre{font-family:ui-monospace,monospace;font-size:.85rem}
pre{background:#f6f8fa;padding:.5rem;overflow:auto;max-height:12rem}
.note{color:#57606a;font-size:.85rem}
@media (prefers-color-scheme:dark){body{background:#0d1117;color:#e6edf3}th{background:#161b22}
th,td{border-color:#30363d}pre{background:#161b22}.PASS{color:#3fb950}.FAIL,.ERROR{color:#ff7b72}
.TIMEOUT{color:#d29922}.unexpected{background:#3b2f00}.note{color:#8b949e}}
"""


def _e(value) -> str:
    return html.escape(str(value))


def write_html(summary: dict, path) -> None:
    path = Path(path)
    base = path.parent
    tot = summary["totals"]
    rows = []
    for t in summary["tests"]:
        rb = t["rule_based"]
        findings = "".join(
            f"<li><code>{_e(f['category'])}</code> line {f['line']}: {_e(f['snippet'])}</li>"
            for f in rb["findings"] if f["category"] in {"ERROR", "WARNING", "ASSERT", "FATAL", "FAIL", "TIMEOUT"}
        ) or "<li class='note'>none</li>"
        if rb["parser_error"]:
            findings += f"<li class='note'>parser error: {_e(rb['parser_error'])}</li>"
        ml = t.get("ml_prediction")
        if ml:
            ml_html = (f"<code>{_e(ml['label'])}</code> (confidence {ml['confidence']:.2f})"
                       f"{' &mdash; needs review' if ml.get('needs_review') else ''}")
        else:
            ml_html = "<span class='note'>n/a</span>"
        rel = os.path.relpath(t["log_path"], base)
        cls = "" if t["matches_expectation"] else " class='unexpected'"
        rows.append(
            f"<tr{cls}><td>{_e(t['name'])}<br><span class='note'>{_e(t['description'])}</span></td>"
            f"<td class='{_e(t['status'])}'>{_e(t['status'])}</td>"
            f"<td>{_e(t['expected_status'])}</td>"
            f"<td>{'-' if t['exit_code'] is None else t['exit_code']}</td>"
            f"<td>{t['duration_seconds']:.2f}s</td>"
            f"<td><a href='{_e(rel)}'>{_e(rel)}</a><br><span class='note'>{_e(t['status_reason'])}"
            f"{' &middot; LOG TRUNCATED (' + str(t['log_bytes_total']) + ' bytes produced)' if t.get('log_truncated') else ''}</span></td>"
            f"<td><code>{_e(rb['category'] or '-')}</code><ul>{findings}</ul></td>"
            f"<td>{ml_html}</td></tr>"
        )
    tools = "".join(f"<li><code>{_e(x['role'])}</code>: {_e(x['path'] or 'MISSING')} "
                    f"<span class='note'>{_e(x['version'])}</span></li>" for x in summary["environment"]["tools"])
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AutoTestX report {_e(summary['run_id'])}</title><style>{_CSS}</style></head><body>
<h1>AutoTestX &mdash; {_e(summary['project'])}</h1>
<p class="note">Run <code>{_e(summary['run_id'])}</code> &middot; started {_e(summary['started'])} &middot; simulator {_e(summary['simulator'])}</p>
<p><strong>{tot['total']}</strong> tests: <span class="PASS">{tot['passed']} passed</span>,
<span class="FAIL">{tot['failed']} failed</span>, <span class="ERROR">{tot['errored']} errored</span>,
<span class="TIMEOUT">{tot['timed_out']} timed out</span> &middot; {tot['unexpected']} differ from expectation
(highlighted).</p>
<table><thead><tr><th>Test</th><th>Status</th><th>Expected</th><th>Exit</th><th>Duration</th><th>Log</th>
<th>Rule-based findings (deterministic)</th><th>ML prediction (experimental)</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="8">No tests were run.</td></tr>'}</tbody></table>
<p class="note">Status comes only from exit code, timeout and explicit log markers. ML predictions are
text-pattern guesses over the failure log, not verified root causes, and never change a status.</p>
<h2>Environment</h2><ul>{tools}</ul>
<p class="note">{_e(summary['environment']['platform'])} &middot; Python {_e(summary['environment']['python'])}
 &middot; AutoTestX {_e(summary['environment']['autotestx_version'])}</p>
</body></html>
"""
    path.write_text(doc, encoding="utf-8")


def write_all(summary: dict) -> None:
    run_dir = Path(summary["run_dir"])
    write_json(summary, run_dir / "results.json")
    write_csv(summary, run_dir / "results.csv")
    write_html(summary, run_dir / "report.html")
