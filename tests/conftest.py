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

from .builders import roster  # noqa: E402

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
