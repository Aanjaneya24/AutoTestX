# Web API

Local-only FastAPI service over the AutoTestX engine. **No authentication. Bind to 127.0.0.1 only; not for public deployment.**
Interactive docs (Swagger) are served at `http://127.0.0.1:8765/docs` while it runs.

Start: `PYTHONPATH=src python3 -m autotestx.web [port]` (default port 8765).

Errors use `{"detail": {"error": "<code>", "message": "...", ...}}` (FastAPI validation errors use its standard list form).
Unhandled server errors return `{"error": "internal_error", "message": ...}` with no internals.

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /api/health` | Liveness, version, active run id | |
| `GET /api/configs` | Allowlisted configs with their tests | Ids are file stems; paths are project-relative |
| `POST /api/configs/validate` `{"config_id"}` | Validate config and probe required tools | 404 `unknown_config` if not allowlisted |
| `POST /api/runs` `{"config_id"}` | Start a run (`202`) | 409 `run_active` if one is in progress; 422 `invalid_config` / `tools_missing` |
| `GET /api/runs?limit=50` | Runs newest first, with `latest` and `active_run` | limit 1-200 |
| `GET /api/runs/{run_id}` | State, totals, progress per test, environment, console tail | states: starting, running, completed, failed, interrupted |
| `GET /api/runs/{run_id}/results` | Per-test results (no absolute paths) | `outcome`: passed, expected_failure, unexpected_failure, unexpected_pass |
| `GET /api/runs/{run_id}/logs/{test}` | A log chunk | query: `offset`, `limit` (max 262144), `tail=true`, `around_line` |
| `GET /api/runs/{run_id}/logs/{test}/search?q=` | Case-insensitive line search (max 200 matches) | |
| `GET /api/runs/compare?before=&after=` | Compare two completed runs | Uses `compare.compare_runs`; 409 if a run has no results |
| `GET /api/ml/evaluation` | Saved `reports/ml_evaluation.json` plus disclaimer and limitations | 404 `no_evaluation` if never generated |

## Safety design
- Only configs listed in `AUTOTESTX_ALLOWED_CONFIGS` (comma-separated, project-relative; default `configs/demo.yaml`) can run. Requests
  carry a config **id**, never a path or command; unknown JSON fields are rejected (422).
- Runs execute as a subprocess of the real CLI with a fixed argument list (`python -m autotestx run --config <path> --run-id <generated>`).
  One run at a time; a second launch gets 409.
- Run ids and test names are validated by regex, test names must exist in that run, and log paths are rebuilt from
  `<runs_dir>/<run_id>/logs/<test>.log` (symlinks refused). Paths stored inside `results.json` are never followed.
- Request bodies over 8 KiB are refused (413); non-local `Origin` on POST is refused (403); `Host` must be localhost/127.0.0.1.
- A config whose `output_dir` is not the server's runs directory is refused, so results always land where the API reads.
