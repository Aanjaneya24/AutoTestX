# Architecture

```
configs/demo.yaml ──> config.py (validate) ──> preflight.py ──> scripts/preflight.sh
                                   │
                                   ▼
                              runner.py ── subprocess (arg list, own process group, timeout)
                                   │            └─ scripts/run_simulation.sh ─> iverilog / vvp
                                   │            └─ tclsh tcl/demo_tests.tcl
                                   ▼
                  raw log ──> scripts/parse_logs.pl (JSON events) ──> log_analysis.py
                                   │                                  (status + rule category)
                                   ▼
                       ml_classifier.py (optional, separate field)
                                   ▼
                    report.py ──> results.json / results.csv / report.html
                    compare.py ──> run-to-run diff
```

## Web layer (optional)

```
React UI (frontend/) --/api--> FastAPI (src/autotestx/web/app.py) --subprocess--> python -m autotestx run --run-id X
                                   |                                                  |
                                   +-- reads reports/runs/X/{status,results}.json, logs/ <----+
```
`web/store.py` is read-only access to run directories (state derivation, safe log paths, chunked reads, search); `web/jobs.py` is a
one-slot job manager that launches the CLI; `web/app.py` defines the endpoints (see `docs/api.md`). The engine gained only
`status.json` progress writing, `--run-id`, and SIGTERM handling (stopping a run kills the current test's whole process tree).

## Who does what (and why)

| Language | Responsibility | Why not Python |
|---|---|---|
| Python | CLI, config validation, process control, status mapping, ML, reports | It is the orchestrator: testable, portable, safe `subprocess` argument lists. |
| Bash | `run_simulation.sh` (compile + run one test), `preflight.sh` (tool/version probe) | Thin glue around the simulator CLI; keeps tool commands out of Python. |
| Perl | `parse_logs.pl`: line-oriented regex scan of a log into JSON events with line numbers and bounded snippets | Honest note: Python could do this too. Perl is used because regex-over-text is its home turf and the parser is a self-contained, independently testable tool. |
| Tcl | `tcl/demo_tests.tcl`: scenario lint. Verifies each testbench exists, declares top `tb`, and can emit PASS and failure markers | **Icarus Verilog is not controlled by Tcl, and this component does not drive the simulator.** It is a real flow check run as its own configured test. |
| Verilog | `rtl/counter.v` and testbenches in `examples/*/tb.v` | The design under test. |

## PASS / FAIL decision (deterministic, ML never involved)

1. Command could not be launched -> `ERROR`.
2. Timeout -> `TIMEOUT`. The process tree is frozen (SIGSTOP), every descendant found via `ps` (any session) plus the
   process group gets SIGTERM, then SIGKILL after 2 s. Limit: a process orphaned to init before the timeout cannot be found.
3. Exit code 127 -> `ERROR` (tool missing); 126 -> `ERROR` (not executable); death by signal -> `FAIL` (`runtime_error`).
4. Any other non-zero exit -> `FAIL`.
5. Exit 0 but a log line *starts with* a failure marker (`FAIL`, `ASSERT...`, `FATAL`, `$fatal`, `UVM_ERROR/FATAL`, optionally
   after a `[time]` prefix) -> `FAIL`. Mid-line mentions such as `Summary: 5 PASS, 0 FAIL` or `assertion a1 passed` do not count.
6. Otherwise `PASS`.

Rule 5 means a testbench that prints a failure line but exits 0 is not silently passed. It is deliberately conservative about
what counts as a marker; a testbench that reports failure only mid-line and exits 0 will be recorded as PASS, so make testbenches
exit non-zero on failure (`$fatal`).
If the parser itself breaks, the failure is recorded (`parser_error`) and the status falls back to rules 1-4.

## Log capture

stdout and stderr are piped through a reader thread into the test log. The log is capped at `settings.max_log_bytes`: the first
and last halves are kept and a `AUTOTESTX: LOG TRUNCATED` line records the omitted bytes; results carry `log_truncated`
and `log_bytes_total`. The pipe is always drained so a chatty test is never blocked, and memory stays bounded.

## Tcl component

`tcl/demo_tests.tcl` strips comments and string contents before looking for `module tb`, and requires a PASS string literal and a
FAIL/ASSERT/ERROR string literal (or `$fatal`/`$error`). Intentionally non-reporting testbenches are declared in the config as
`name:no-pass,no-fail`; there are no built-in exceptions.

## Run comparison

`compare` judges each test against its own `expect`. Regression = matched expectation before, not now (so an `expect: fail`
test that starts passing is a regression); fix = the reverse. Changed command/expectation or incompatible suites are reported, not judged.

## Expectations

Each test has `expect: pass|fail|timeout|error` (default `pass`). The run exit code is 0 only if every test
matches its expectation, so deliberately failing demo tests do not break CI, while an *unexpected* pass or
fail does.

## Safety

Commands are argument arrays executed without a shell. Config commands are trusted local project code,
not a sandbox for untrusted input. Test names are restricted to `[A-Za-z0-9_.-]` because they become file names.
