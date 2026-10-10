"""FastAPI application. Bind to 127.0.0.1 only; there is no authentication."""
from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..compare import compare_runs, format_comparison, load_results
from ..config import ConfigError, load_config
from ..log_analysis import LABELS
from ..preflight import check_tools, missing, missing_support_files
from . import store
from .jobs import Busy, JobManager
from .settings import DEFAULT_PORT, MAX_BODY_BYTES, MAX_LOG_CHUNK, MAX_SEARCH_MATCHES, Settings

log = logging.getLogger("autotestx.web")

ML_STATEMENT = ("The ML model classifies the TEXT of a failure log into five categories. It does not diagnose "
                "hardware defects and does not establish a verified root cause. Test status is decided only by "
                "exit code, timeout and explicit log markers; ML never changes it.")
ML_LIMITATIONS = [
    "Trained and evaluated on a small synthetic dataset (template-generated, no real tool logs).",
    "The 151 rows come from 40 template families, so the effective sample size is much smaller than it looks.",
    "Scores depend on the split seed; the keyword-rule baseline scored higher than the model in every seed tried.",
    "Predictions below the confidence threshold are shown as needs_review.",
]


class ConfigRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


def _config_summary(path, cid: str, settings: Settings) -> dict:
    try:
        cfg = load_config(path)
    except ConfigError as exc:
        return {"id": cid, "path": str(path.relative_to(settings.project_root)), "valid": False,
                "problems": exc.problems, "tests": [], "project": None}
    problems = []
    from ..config import resolve
    from pathlib import Path
    if Path(resolve(cfg, cfg.output_dir)).resolve() != settings.runs_root:
        problems.append(f"output_dir resolves outside the server's runs directory ({settings.runs_root})")
    return {"id": cid, "path": str(path.relative_to(settings.project_root)), "valid": not problems,
            "problems": problems, "project": cfg.project_name, "ml_enabled": cfg.enable_ml_classification,
            "max_log_bytes": cfg.max_log_bytes,
            "tests": [{"name": t.name, "description": t.description, "expect": t.expect,
                       "timeout_seconds": t.timeout_seconds, "tags": list(t.tags)} for t in cfg.tests]}


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    jobs = JobManager(settings)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()

    app = FastAPI(title="AutoTestX API", version=__version__, lifespan=lifespan,
                  description="Local-only API over the AutoTestX engine. No authentication; bind to 127.0.0.1.")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).hostname not in ("localhost", "127.0.0.1"):
                return JSONResponse({"error": "forbidden_origin", "message": "cross-site requests are refused"}, 403)
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                if request.method == "POST" and request.headers.get("transfer-encoding"):
                    return JSONResponse({"error": "length_required", "message": "Content-Length is required"}, 411)
            elif int(length) > MAX_BODY_BYTES:
                return JSONResponse({"error": "too_large", "message": f"request body over {MAX_BODY_BYTES} bytes"}, 413)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"error": "internal_error", "message": "unexpected server error (see server log)"}, 500)

    def err(status: int, code: str, message: str, **extra):
        return HTTPException(status_code=status, detail={"error": code, "message": message, **extra})

    def table() -> dict:
        return settings.config_table()

    def config_or_404(cid: str):
        path = table().get(cid)
        if path is None:
            raise err(404, "unknown_config", f"config {cid!r} is not in the allowlist")
        return path

    def require_run(run_id: str) -> None:
        if not store.valid_run_id(run_id):
            raise err(400, "bad_run_id", "run id has an invalid format")
        if not store.run_exists(settings.runs_root, run_id, jobs.active_run_id()):
            raise err(404, "unknown_run", f"no run {run_id!r}")

    def summary(run_id: str) -> dict:
        return store.summarise(settings.runs_root, run_id, jobs.active_run_id(), jobs.exit_code(run_id))

    # ---------------------------------------------------------------- health / configs
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "active_run": jobs.active_run_id(),
                "support_files_missing": missing_support_files()}

    @app.get("/api/configs")
    def configs():
        return {"configs": [_config_summary(p, cid, settings) for cid, p in table().items()]}

    @app.post("/api/configs/validate")
    def validate_config(ref: ConfigRef):
        path = config_or_404(ref.config_id)
        info = _config_summary(path, ref.config_id, settings)
        tools = []
        if info["valid"] or info["tests"]:
            cfg = load_config(path)
            statuses = check_tools(cfg.tools, cfg.enable_ml_classification)
            tools = [{"role": s.role, "executable": s.executable, "found": s.found, "path": s.path,
                      "version": s.version} for s in statuses]
            gone = missing(statuses)
            if gone:
                info["valid"] = False
                info["problems"] += [f"required tool missing: {s.role} ({s.executable})" for s in gone]
        info["tools"] = tools
        return info

    # ---------------------------------------------------------------- runs
    @app.post("/api/runs", status_code=202)
    def start_run(ref: ConfigRef):
        path = config_or_404(ref.config_id)
        info = _config_summary(path, ref.config_id, settings)
        if not info["valid"]:
            raise err(422, "invalid_config", "configuration is invalid", problems=info["problems"])
        cfg = load_config(path)
        gone = missing(check_tools(cfg.tools, cfg.enable_ml_classification))
        if gone:
            raise err(422, "tools_missing", "required tools are missing",
                      problems=[f"{s.role} ({s.executable})" for s in gone])
        if missing_support_files():
            raise err(503, "support_files_missing", "bundled scripts not found; use an editable install")
        try:
            run_id = jobs.start(path)
        except Busy as busy:
            raise err(409, "run_active", f"run {busy.run_id} is already in progress", active_run=busy.run_id)
        return {"run_id": run_id, "state": "starting", "config_id": ref.config_id}

    @app.get("/api/runs")
    def list_runs(limit: int = Query(50, ge=1, le=200)):
        ids = store.list_run_ids(settings.runs_root)[:limit]
        runs = [summary(r) for r in ids]
        return {"runs": runs, "latest": ids[0] if ids else None, "active_run": jobs.active_run_id()}

    @app.get("/api/runs/compare")
    def compare(before: str, after: str):
        loaded = []
        for rid in (before, after):
            require_run(rid)
            p = settings.runs_root / rid / "results.json"
            if not p.is_file():
                raise err(409, "run_not_complete", f"run {rid} has no results yet")
            try:
                loaded.append(load_results(p))
            except ValueError as exc:
                raise err(422, "bad_results", str(exc))
        result = compare_runs(loaded[0], loaded[1])
        return {"before": before, "after": after, **result, "text": format_comparison(result, before, after)}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        require_run(run_id)
        out = summary(run_id)
        st = store.run_state(settings.runs_root, run_id, jobs.active_run_id(), jobs.exit_code(run_id))
        status = st["status"] or {}
        out["progress"] = {"completed": status.get("completed", out["totals"]["total"] if out["totals"] else 0),
                           "total": status.get("total", out["totals"]["total"] if out["totals"] else 0),
                           "current": status.get("current"), "tests": status.get("tests", [])}
        out["environment"] = (st["results"] or {}).get("environment")
        out["console_tail"] = store.console_tail(settings.runs_root, run_id)
        out["exit_code"] = jobs.exit_code(run_id)
        return out

    @app.get("/api/runs/{run_id}/results")
    def run_results(run_id: str):
        require_run(run_id)
        run_dir = settings.runs_root / run_id
        st = store.run_state(settings.runs_root, run_id, jobs.active_run_id(), None)
        if st["results"] is not None:
            tests = [store.public_test(t, run_dir) for t in st["results"]["tests"]]
        else:  # partial results while running
            tests = [{"name": t["name"], "status": t.get("status"), "expected_status": t.get("expect", "PASS"),
                      "outcome": store.classify_test({"status": t.get("status"), "expected_status": t.get("expect", "PASS")})
                      if t.get("state") == "done" else t.get("state", "pending"),
                      "exit_code": t.get("exit_code"), "duration_seconds": t.get("duration_seconds"),
                      "rule_category": t.get("category"), "description": t.get("description", ""),
                      "log_available": (run_dir / "logs" / f"{t['name']}.log").is_file(), "findings": [],
                      "ml_prediction": None, "log_truncated": False}
                     for t in (st["status"] or {}).get("tests", [])]
        return {"run_id": run_id, "state": st["state"], "tests": tests}

    def test_names(run_id: str) -> set:
        st = store.run_state(settings.runs_root, run_id, jobs.active_run_id(), None)
        if st["results"] is not None:
            return {t["name"] for t in st["results"]["tests"]}
        return {t["name"] for t in (st["status"] or {}).get("tests", [])}

    def log_file(run_id: str, test_name: str):
        require_run(run_id)
        if test_name not in test_names(run_id):
            raise err(404, "unknown_test", f"run {run_id} has no test {test_name!r}")
        path = store.safe_log_path(settings.runs_root, run_id, test_name)
        if path is None:
            raise err(404, "log_missing", f"no log file for test {test_name!r} in run {run_id}")
        return path

    @app.get("/api/runs/{run_id}/logs/{test_name}")
    def run_log(run_id: str, test_name: str, offset: int = Query(0, ge=0),
                limit: int = Query(65536, ge=1, le=MAX_LOG_CHUNK), tail: bool = False,
                around_line: Optional[int] = Query(None, ge=1, le=10_000_000)):
        path = log_file(run_id, test_name)
        if around_line is not None:           # start a few lines before the requested one
            offset = store.offset_of_line(path, max(1, around_line - 5))
        chunk = store.read_log_chunk(path, offset, limit, tail)
        st = store.run_state(settings.runs_root, run_id, jobs.active_run_id(), None)
        rec = next((t for t in (st["results"] or {}).get("tests", []) if t["name"] == test_name), {})
        public = store.public_test(rec, settings.runs_root / run_id) if rec else {}
        return {**chunk, "test": test_name, "run_id": run_id, "max_chunk": MAX_LOG_CHUNK,
                "log_truncated": public.get("log_truncated", False), "log_bytes_total": public.get("log_bytes_total"),
                "findings": public.get("findings", [])}

    @app.get("/api/runs/{run_id}/logs/{test_name}/search")
    def run_log_search(run_id: str, test_name: str, q: str = Query(min_length=1, max_length=200)):
        return {**store.search_log(log_file(run_id, test_name), q, MAX_SEARCH_MATCHES), "test": test_name}

    # ---------------------------------------------------------------- ML
    @app.get("/api/ml/evaluation")
    def ml_evaluation():
        p = settings.ml_eval_path
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise err(404, "no_evaluation", "no saved evaluation; run `python -m autotestx evaluate-ml --out reports/ml_evaluation.json`")
        except (OSError, ValueError):
            raise err(500, "bad_evaluation", "saved evaluation file is unreadable")
        data.pop("dataset", None)             # local path
        return {"evaluation": data, "labels": list(LABELS), "statement": ML_STATEMENT, "limitations": ML_LIMITATIONS,
                "baseline_higher": data.get("rule_baseline", {}).get("macro_f1", 0) > data.get("ml_model", {}).get("macro_f1", 0),
                "model_file_present": settings.ml_model_path.is_file()}

    return app


def main() -> None:  # pragma: no cover - thin launcher
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")
