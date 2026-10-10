import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
needs_sim = pytest.mark.skipif(not (shutil.which("iverilog") and shutil.which("vvp")),
                               reason="Icarus Verilog not installed")


@pytest.fixture
def project(tmp_path):
    """A copy of the repo's runnable parts so integration runs write under tmp_path.
    The path deliberately contains a space to exercise safe argument handling."""
    dest = tmp_path / "my project"
    dest.mkdir()
    for name in ("scripts", "tcl", "rtl", "examples", "configs", "data"):
        shutil.copytree(ROOT / name, dest / name)
    shutil.copy(ROOT / "pyproject.toml", dest / "pyproject.toml")
    return dest
