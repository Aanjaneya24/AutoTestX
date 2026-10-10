"""Single-slot local job manager: launches the real CLI as a subprocess."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from ..runner import new_run_id
from .settings import Settings
from .store import CONSOLE_DIR, console_path


class Busy(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"run {run_id} is still active")


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._run_id: Optional[str] = None
        self._exit_codes: dict = {}

    def active_run_id(self) -> Optional[str]:
        with self._lock:
            return self._reap()

    def _reap(self) -> Optional[str]:
        if self._proc is not None and self._proc.poll() is not None:
            self._exit_codes[self._run_id] = self._proc.returncode
            if len(self._exit_codes) > 200:
                self._exit_codes.pop(next(iter(self._exit_codes)))
            self._proc = self._run_id = None
        return self._run_id

    def exit_code(self, run_id: str) -> Optional[int]:
        with self._lock:
            self._reap()
            return self._exit_codes.get(run_id)

    def start(self, config_path: Path) -> str:
        """Start `python -m autotestx run` for an already-allowlisted config. Raises Busy if one is active."""
        with self._lock:
            active = self._reap()
            if active:
                raise Busy(active)
            runs_root = self.settings.runs_root
            runs_root.mkdir(parents=True, exist_ok=True)
            (runs_root / CONSOLE_DIR).mkdir(exist_ok=True)
            run_id = new_run_id()
            while (runs_root / run_id).exists() or console_path(runs_root, run_id).exists():
                run_id = new_run_id()
            src_dir = str(Path(__file__).resolve().parents[2])
            env = {**os.environ, "PYTHONUNBUFFERED": "1",
                   "PYTHONPATH": src_dir + os.pathsep + os.environ.get("PYTHONPATH", "")}
            with open(console_path(runs_root, run_id), "wb") as console:
                # fixed argument list: only the allowlisted config path and a generated run id are variable
                self._proc = subprocess.Popen(
                    [sys.executable, "-u", "-m", "autotestx", "run", "--config", str(config_path), "--run-id", run_id],
                    cwd=str(self.settings.project_root), stdout=console, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)
            self._run_id = run_id
            return run_id

    def shutdown(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    os.killpg(self._proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
