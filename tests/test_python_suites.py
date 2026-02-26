import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SUITES = [
    ["services/orders/tests"],
    ["services/pos-integration/tests"],
    ["services/restaurants/tests"],
    ["services/users/tests"],
    ["infrastructure/tests"],
    ["tests/unit/test_admin_logic.py"],
]


def _run_pytest(paths: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *paths],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Suite failed: {' '.join(paths)}\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )


def test_all_python_suites_pass_in_isolation():
    for suite in SUITES:
        _run_pytest(suite)
