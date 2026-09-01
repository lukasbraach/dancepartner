"""Shared fixtures: instances small enough to reason about by hand."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# The suite asserts English output, and Typer help texts resolve against DANCEPARTNER_LANG at
# import time -- so pin the variable before anything imports dancepartner.cli.
os.environ["DANCEPARTNER_LANG"] = "en"

import pytest  # noqa: E402

from dancepartner.i18n import Language, set_language  # noqa: E402
from dancepartner.model import Team  # noqa: E402
from dancepartner.solver import ENV_VAR as DP_BACKEND  # noqa: E402
from dancepartner.solver import resolve_backend  # noqa: E402

from .builders import roster  # noqa: E402


def active_backend() -> str:
    """Which solver the suite is currently exercising."""
    return resolve_backend()


# `streamlit run app/Home.py` puts the entry script's directory on sys.path, which is how the
# pages import `common`. AppTest loading a page file directly does not, so the UI tests would
# depend on a Home test having run first. Reproduce the runtime's own path here instead.
_APP = Path(__file__).resolve().parents[1] / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

# wasm/build_static.py is a script, not a package; tests/test_static_build.py imports it.
_WASM = Path(__file__).resolve().parents[1] / "wasm"
if str(_WASM) not in sys.path:
    sys.path.insert(0, str(_WASM))


def pytest_addoption(parser: pytest.Parser) -> None:
    """``--backend`` runs the whole suite against one solver.

    SPEC.md 8.1: the two backends must agree, and the way that is checked is by running the
    existing tests against both rather than by writing a second set. `tests/helpers.py`'s
    ``assert_result_valid`` re-derives every hard constraint and stage value independently of
    the solver, which is exactly the oracle that makes this worth doing.
    """
    parser.addoption(
        "--backend",
        action="store",
        default=None,
        choices=["cpsat", "highs"],
        help="solver backend to run the suite against (default: the project's own preference)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker for tests that can only mean anything on one backend."""
    config.addinivalue_line(
        "markers", "cpsat_only: measures something specific to the CP-SAT implementation"
    )


@pytest.fixture(scope="session", autouse=True)
def _backend(request: pytest.FixtureRequest) -> Iterator[None]:
    """Pin ``DANCEPARTNER_BACKEND`` for the session when ``--backend`` was given."""
    chosen = request.config.getoption("--backend")
    if chosen is None:
        yield
        return
    previous = os.environ.get(DP_BACKEND)
    os.environ[DP_BACKEND] = str(chosen)
    yield
    if previous is None:
        os.environ.pop(DP_BACKEND, None)
    else:
        os.environ[DP_BACKEND] = previous


@pytest.fixture(autouse=True)
def _skip_on_other_backends(request: pytest.FixtureRequest) -> None:
    """Honour ``@pytest.mark.cpsat_only``."""
    if request.node.get_closest_marker("cpsat_only") and active_backend() != "cpsat":
        pytest.skip("measures the CP-SAT implementation specifically")


@pytest.fixture(autouse=True)
def _english_default() -> Iterator[None]:
    """Reset the active language after every test, so a language switch cannot leak."""
    yield
    set_language(Language.EN)


@pytest.fixture
def german() -> Iterator[None]:
    """Run the test body in German."""
    set_language(Language.DE)
    yield
    set_language(Language.EN)


@pytest.fixture
def tiny() -> Team:
    """3 positions, 3 Herren, 3 Damen: every position is a single couple, no slack."""
    return Team(dancers=roster(3, 3), n_positions=3)


@pytest.fixture
def small() -> Team:
    """3 positions, 4 Herren, 4 Damen: exactly one position is a full Doppelbesetzung."""
    return Team(dancers=roster(4, 4), n_positions=3)


@pytest.fixture
def uneven() -> Team:
    """3 positions, 4 Herren, 5 Damen: one Herren-double, two Damen-doubles."""
    return Team(dancers=roster(4, 5), n_positions=3)


@pytest.fixture
def full() -> Team:
    """8 positions, 10 Herren, 12 Damen -- a realistic shape for the timing tests."""
    return Team(dancers=roster(10, 12), n_positions=8)
