"""Tests for the clean calculator fixture."""

from calculator import add, subtract


def test_add() -> None:
    """Addition returns the expected sum."""

    assert add(2, 3) == 5


def test_subtract() -> None:
    """Subtraction returns the expected difference."""

    assert subtract(5, 3) == 2
