"""Check that required external tools exist (delegates version probing to scripts/preflight.sh)."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "preflight.sh"


@dataclass
class ToolStatus:
    role: str
    executable: str
    path: Optional[str]
    version: str = ""

    @property
    def found(self) -> bool:
        return self.path is not None


def check_tools(tools: dict, ml_enabled: bool = False) -> list:
    """Return a ToolStatus per configured tool role. Roles never configured are skipped."""
    roles = dict(tools)
    out = {}
    exes = sorted(set(roles.values()))
    if shutil.which("bash") and SCRIPT.is_file():
        try:
            proc = subprocess.run(["bash", str(SCRIPT), *exes], capture_output=True,
                                  text=True, timeout=30)
            for line in proc.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    out[parts[0]] = (None if parts[1] == "MISSING" else parts[1],
                                     parts[2] if len(parts) > 2 else "")
        except (OSError, subprocess.TimeoutExpired):
            out = {}
    results = []
    for role, exe in roles.items():
        if exe in out:
            path, version = out[exe]
        else:  # shell helper unavailable: fall back to a plain PATH lookup
            path, version = shutil.which(exe), ""
        results.append(ToolStatus(role, exe, path, version))
    if ml_enabled:
        try:
            import sklearn  # noqa: F401
            results.append(ToolStatus("scikit-learn", "sklearn", "python-module", sklearn.__version__))
        except ImportError:
            results.append(ToolStatus("scikit-learn", "sklearn", None))
    return results


def missing_support_files() -> list:
    """Bundled helper scripts that must exist next to the package (they do not for a non-editable install)."""
    from .log_analysis import PARSER
    return [str(p) for p in (SCRIPT, PARSER) if not p.is_file()]


def missing(statuses: list) -> list:
    return [s for s in statuses if not s.found]
