"""Shared fixtures: instances small enough to reason about by hand."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dancepartner.model import Team

from .builders import roster

# `streamlit run app/Home.py` puts the entry script's directory on sys.path, which is how the
# pages import `common`. AppTest loading a page file directly does not, so the UI tests would
# depend on a Home test having run first. Reproduce the runtime's own path here instead.
_APP = Path(__file__).resolve().parents[1] / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))


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
