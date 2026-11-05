"""Shared pytest setup for the Day 4 and Day 5 test suites.

The five fault-scenario databases (S1-S5) are generated locally and are
gitignored. On a fresh clone they do not exist, so any test that reads them
would fail with a database error. This session fixture builds them once, only
when at least one is missing or empty, using the same script documented in the
README. The baseline database is never modified by that script.

An empty (0-byte) file counts as missing: SQLite creates one when code opens a
database path that does not exist yet.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "alerting" / "scenarios" / "generated"
SCENARIO_DBS = [GENERATED_DIR / f"S{i}.db" for i in range(1, 6)]


def _is_built(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


@pytest.fixture(scope="session", autouse=True)
def ensure_scenario_databases():
    """Build S1-S5 if any scenario database is missing or empty."""
    if all(_is_built(path) for path in SCENARIO_DBS):
        return

    # Remove empty placeholder files so the build starts from a clean state.
    for path in SCENARIO_DBS:
        if path.exists() and path.stat().st_size == 0:
            path.unlink()

    result = subprocess.run(
        [sys.executable, "-m", "alerting.scenarios.build_scenarios"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    still_bad = [p.name for p in SCENARIO_DBS if not _is_built(p)]
    if result.returncode != 0 or still_bad:
        pytest.fail(
            "Could not build scenario databases.\n"
            f"Missing or empty: {still_bad}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )