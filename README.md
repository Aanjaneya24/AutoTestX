# AutoTestX

RTL regression automation with a local web dashboard. One command (or one button) runs a suite of Verilog
simulations with Icarus Verilog, captures each test's log, exit code and duration, parses the logs with Perl,
classifies failures with transparent rules plus an experimental ML model, and produces JSON, CSV and HTML reports.

It is an educational portfolio project, not a production EDA platform. Results below were measured on one
machine (macOS, Apple silicon); see [Known limitations](#known-limitations).

## Quick start (macOS)

```bash
brew install icarus-verilog                 # simulator (once)
pip install -r requirements.txt             # Python packages (once)
cd frontend && npm install && cd ..         # frontend packages, ~130 MB, project-local (once)

./start.sh                                  # checks everything, starts API + UI, prints the URL
```
Open **http://127.0.0.1:5173**, go to **Run**, validate, start the demo suite, then explore **Results**, **Logs**,
**ML analysis** and **Compare**. Stop with **Ctrl+C** in the terminal running `start.sh`.

`./start.sh --check` only verifies dependencies and ports. `start.sh` never installs anything; it tells you the command to run.
Ports: backend 8765, frontend 5173; override with `AUTOTESTX_API_PORT` / `AUTOTESTX_UI_PORT`.

## Technology stack

| Layer | Technology | Role |
|---|---|---|
| Orchestration | Python 3 (argparse, subprocess, dataclasses, PyYAML) | CLI, config validation, process control, status mapping, reports |
| Simulation | Verilog + Icarus Verilog (`iverilog`, `vvp`) | Design under test (`rtl/counter.v`) and testbenches (`examples/*/tb.v`) |
| Glue | Bash (`scripts/run_simulation.sh`, `scripts/preflight.sh`) | Compile and run one test; probe tool versions |
| Log parsing | Perl (`scripts/parse_logs.pl`, core `JSON::PP`) | Regex scan of a log into JSON events with line numbers |
| Flow check | Tcl (`tcl/demo_tests.tcl`) | Lints testbenches (comments cannot satisfy markers). It does **not** drive the simulator |
| ML | scikit-learn (TF-IDF + Logistic Regression), joblib | Experimental text classifier of failure logs |
| API | FastAPI + Uvicorn (`src/autotestx/web/`) | Local-only JSON API over the engine |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router | Dashboard |
| Tests | pytest (Python), Vitest + Testing Library (frontend) | |

## Architecture

```
Browser (React)  --/api-->  FastAPI  --subprocess-->  python -m autotestx run --run-id X
                              |                              |
                              |                    bash run_simulation.sh -> iverilog/vvp
                              |                    perl parse_logs.pl  -> JSON events
                              |                    tclsh demo_tests.tcl (flow check)
                              +--- reads reports/runs/X/{status.json, results.json, logs/*} <---+
```

- **Engine** (`src/autotestx/`): `config` (strict validation), `preflight`, `runner` (argument-list subprocesses, own process
  group, timeouts with full process-tree kill, size-capped logs), `log_analysis` (Perl wrapper, rules, status), `ml_classifier`,
  `report`, `compare`, `cli`.
- **Status is deterministic:** exit code, timeout and explicit log markers only. ML never changes it.
- **Expectations:** each test has `expect: pass|fail|timeout|error`. The three negative demo tests are *meant* to fail; the run is
  "as expected" only if every test matches. An expected failure is never shown as a success.
- **Backend** (`src/autotestx/web/`): starts the same CLI as a subprocess (one run at a time) and reads the files it writes.
  Only allowlisted configs can run; the browser sends a config id, never a command or a path. See [docs/api.md](docs/api.md).
- **Frontend** (`frontend/`): Overview, Run, Results, Logs, ML analysis, Compare. All numbers come from the API.
- **Storage:** no database. `reports/runs/<run_id>/` holds `status.json` (live progress), `results.json`, `results.csv`,
  `report.html`, `config_snapshot.yaml` and `logs/<test>.log`. Runs survive restarts. `reports/ml_evaluation.json` and
  `models/log_classifier.joblib` come from `evaluate-ml`.
- More detail: [docs/architecture.md](docs/architecture.md).

## Installation details

Requirements: macOS with Python 3.9+ (3.11.7 tested), Perl, `tclsh`, Bash, `iverilog`/`vvp`, Node.js and npm (v25.9.0 / 11.12.1 tested).
Python packages are in `requirements.txt` (PyYAML, scikit-learn, joblib, pytest, fastapi, uvicorn, httpx). Run from the source
checkout (`PYTHONPATH=src`); `pip install -e .` also works, a regular `pip install .` does not (the helper scripts live outside the package).

## Using the dashboard

1. **Run:** pick the allowlisted config, *Validate configuration* (also checks tools), *Start regression run*, confirm. Progress
   updates every second; failures show the error and the CLI's console output.
2. **Results:** search and filter; click a test for its detail (expected vs actual, reason, rule category, ML guess, command).
3. **Logs:** open a log from a failed test (jumps to the first finding), search, load more, or jump to the end. Logs are served in
   64 KiB pieces; a banner appears if the engine truncated the log.
4. **ML analysis:** per-run rule-vs-ML table plus the saved evaluation (macro-F1, per-class precision/recall, confusion matrix).
5. **Compare:** pick two completed runs; regressions are judged against each test's own expectation.

## Using the CLI directly

```bash
export PYTHONPATH=src
python3 -m autotestx doctor                                   # tool check
python3 -m autotestx validate --config configs/demo.yaml      # validate only, runs nothing
python3 -m autotestx run --config configs/demo.yaml           # run the suite
python3 -m autotestx evaluate-ml --out reports/ml_evaluation.json   # ML evaluation; also saves models/log_classifier.joblib
python3 -m autotestx compare --before reports/runs/A/results.json --after reports/runs/B/results.json
```
`run` exit codes: 0 every test matched its `expect`; 1 some did not; 2 bad config; 3 tool missing; 4 cannot write output; 130 stopped.
Optional `--run-id <id>` sets the run id. Optional config setting `settings.max_log_bytes` (>= 1024) caps each log (default 5 MiB).

Sample output:
```
TEST                       STATUS   EXPECT   EXIT     TIME  CATEGORY
counter_basic              PASS     PASS     0       0.04s  -
counter_reset              PASS     PASS     0       0.04s  -
tcl_scenario_lint          PASS     PASS     0       0.02s  -
counter_fail_intentional   FAIL     FAIL     1       0.04s  assertion_failure
compile_error_intentional  FAIL     FAIL     2       0.02s  compile_error
hang_intentional           TIMEOUT  TIMEOUT  -       3.08s  timeout
Total 6: 3 passed, 2 failed, 0 errored, 1 timed out; 0 differ from expectation
```

## Inspecting logs

- **Dashboard:** Logs page (above).
- **Files:** `reports/runs/<run_id>/logs/<test>.log` is the raw combined stdout/stderr; `report.html` in the same folder links to every log.
- **Parsed events:** the Perl parser output is in `results.json` under each test's `rule_based.findings` (category, line, snippet).
  Run the parser by hand: `perl scripts/parse_logs.pl path/to/test.log`.
- **Truncated logs** contain a line `AUTOTESTX: LOG TRUNCATED: ...` where the middle was dropped.
- Example logs for each failure type: `data/sample_logs/`; a complete saved report: `docs/sample_run/`.

## Running the tests

```bash
export PYTHONPATH=src
python3 -m pytest -q                    # Python: unit, API and real-simulator integration tests
(cd frontend && npm test)               # Vitest
(cd frontend && npm run typecheck)      # TypeScript
(cd frontend && npm run build)          # type-check + production build
```
Integration tests need Icarus Verilog and run real simulations (about a minute in total). Their pass counts at the last verification are in `Updates.md`.

## ML evaluation and its limits

A TF-IDF + Logistic Regression model labels the *text* of a failure log (compile_error, assertion_failure, timeout,
runtime_error, unknown) and is compared with a keyword baseline. It does **not** detect hardware defects or find root causes;
its output is an experimental hint about which log to read first.

Measured (`reports/ml_evaluation.json`, seed 42, family-grouped 4-fold cross-validation): keyword rules macro-F1 **0.752**,
model macro-F1 **0.600**. Across other split seeds the model scored 0.44 to 0.60 and the rules stayed at 0.752, so **the rules are
currently the better classifier**. Limits: 151 synthetic, template-generated rows from only 40 template families (92 distinct texts after
normalisation); no real tool logs; the rule baseline was written by the same author as the templates, so it is probably optimistic;
low-confidence predictions are shown as `needs_review`. Details and per-class numbers: [docs/ml_evaluation.md](docs/ml_evaluation.md).
Model files are pickles: only load ones you created yourself, and only run configs you trust.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `start.sh` says a port is in use | Stop the other program, or `AUTOTESTX_API_PORT=8800 AUTOTESTX_UI_PORT=5200 ./start.sh` |
| `[missing] frontend dependencies` | `cd frontend && npm install` |
| `[missing] iverilog` | `brew install icarus-verilog` |
| Dashboard says "Cannot reach the backend" | Backend crashed: read `.run/backend.log` |
| Run shows `interrupted` | The run process was stopped (server stopped, Ctrl+C, or killed) before finishing; start a new run |
| Run fails immediately with "tools missing" | Run `python3 -m autotestx doctor` |
| ML page: "No saved evaluation" | `PYTHONPATH=src python3 -m autotestx evaluate-ml --out reports/ml_evaluation.json` |
| Runs show no ML labels | Train the model with the same `evaluate-ml` command (it saves `models/log_classifier.joblib`) |
| A leftover `vvp` process after killing the server with `kill -9` | `pkill vvp` (graceful stops clean up automatically) |
| "Bundled scripts not found" | You installed non-editable; run from the source folder or `pip install -e .` |

## Known limitations

- Tested on macOS (Apple silicon) with modern web browsers (Chrome, Safari, Firefox).
  **Linux, Windows, Verilator, and other Node/Python versions are untested.** The GitHub Actions file in
  `.github/workflows/ci.yml` has never been run and does not build the frontend.
- Only Icarus Verilog is supported, and `run_simulation.sh` is tied to the 4-bit counter in `rtl/counter.v`.
- Tcl does not control the simulator; it only lints testbenches (and cannot prove a testbench is meaningful).
- Sequential execution; one run at a time in the dashboard; no retries.
- The timeout kills the test's process tree found via `ps`; a process already orphaned before the timeout may survive.
  `kill -9` of the server can leave a hanging simulation behind.
- The web service has no authentication and must only be bound to 127.0.0.1.
- The ML data is small and synthetic (see above).
