"""Tests for spacing expression parser."""

from app.geometry.spacing import parse_spacing_list, spacing_total


def test_total() -> None:
    assert spacing_total(parse_spacing_list("2@30")) == 60.0
