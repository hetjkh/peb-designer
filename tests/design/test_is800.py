"""IS 800 formula unit checks with documented expected behaviour."""

import math

from app.design.is800 import _chi_buckling


def test_chi_at_low_slenderness() -> None:
    assert _chi_buckling(0.1) == 1.0


def test_chi_decreases_with_slenderness() -> None:
    assert _chi_buckling(1.0) < _chi_buckling(0.5)
    assert _chi_buckling(1.5) < _chi_buckling(1.0)


def test_chi_bounded() -> None:
    chi = _chi_buckling(2.0)
    assert 0.0 < chi <= 1.0
