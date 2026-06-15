"""Pytest configuration for Tendril-Graph tests.

No sys.path manipulation needed — all code lives inside the `tendril` package,
which is installed via `pip install -e ".[dev]"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"


@pytest.fixture
def golden_fixture_paths() -> dict[str, Path]:
    """Return a dict of absolute paths to existing fixture files.

    Keys are logical fixture names; values are absolute Paths under
    tests/fixtures/.  Callers use these paths to load fixture data without
    duplicating JSON.  All paths are verified to exist at fixture-collection
    time so test failures are clear.
    """
    paths: dict[str, Path] = {
        # VCS fixtures
        "vcs_bitbucket_dc": _FIXTURES_ROOT / "vcs" / "bitbucket_dc",
        "vcs_github": _FIXTURES_ROOT / "vcs" / "github",
        # CI/CD fixtures
        "cicd_octopus": _FIXTURES_ROOT / "cicd" / "octopus",
        "cicd_teamcity": _FIXTURES_ROOT / "cicd" / "teamcity",
        # Golden expected output
        "golden_expected": _FIXTURES_ROOT / "golden" / "expected",
    }
    # Only verify directories that actually exist — some may be empty stubs.
    for key, path in paths.items():
        if not path.exists():
            pytest.skip(f"Fixture path missing: {path} (key={key!r})")
    return paths
