"""Server settings: which configs may be run and where results live."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_ALLOWED = ("configs/demo.yaml",)
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 8 * 1024
MAX_LOG_CHUNK = 256 * 1024
MAX_SEARCH_MATCHES = 200


def default_project_root() -> Path:
    # src/autotestx/web/settings.py -> project root is three levels above the package dir
    return Path(__file__).resolve().parents[3]


@dataclass
class Settings:
    project_root: Path = field(default_factory=default_project_root)
    allowed_configs: tuple = DEFAULT_ALLOWED          # project-relative paths; the ONLY runnable configs
    runs_root: Optional[Path] = None                  # default: <root>/reports/runs
    ml_eval_path: Optional[Path] = None               # default: <root>/reports/ml_evaluation.json
    ml_model_path: Optional[Path] = None              # default: <root>/models/log_classifier.joblib

    def __post_init__(self):
        self.project_root = Path(self.project_root).resolve()
        self.runs_root = Path(self.runs_root or self.project_root / "reports" / "runs").resolve()
        self.ml_eval_path = Path(self.ml_eval_path or self.project_root / "reports" / "ml_evaluation.json")
        self.ml_model_path = Path(self.ml_model_path or self.project_root / "models" / "log_classifier.joblib")

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.environ.get("AUTOTESTX_ALLOWED_CONFIGS")
        allowed = tuple(p.strip() for p in raw.split(",") if p.strip()) if raw else DEFAULT_ALLOWED
        return cls(allowed_configs=allowed)

    def config_table(self) -> dict:
        """{config_id: absolute Path} for allowlisted configs that exist inside the project root.
        The id is the file stem. Paths that escape the project root or do not exist are skipped."""
        table: dict = {}
        for rel in self.allowed_configs:
            p = (self.project_root / rel).resolve()
            try:
                p.relative_to(self.project_root)
            except ValueError:
                continue
            if p.is_file() and p.stem not in table:
                table[p.stem] = p
        return table
