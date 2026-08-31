"""Shared fixtures: instances small enough to reason about by hand."""

from __future__ import annotations

import pytest

from dancepartner.model import Team

from .builders import roster


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
