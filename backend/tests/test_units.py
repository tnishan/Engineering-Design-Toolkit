"""Length parsing, including signed values for offsets/positions."""

import pytest

from core.units import UnitError, parse_length_mm


def test_bare_number_is_millimetres():
    assert parse_length_mm("235") == pytest.approx(235.0)
    assert parse_length_mm(235) == pytest.approx(235.0)


def test_unit_suffixes():
    assert parse_length_mm("3.5 m") == pytest.approx(3500.0)
    assert parse_length_mm("12 ft") == pytest.approx(3657.6)
    assert parse_length_mm('9 1/4"') == pytest.approx(9.25 * 25.4)
    assert parse_length_mm("18 in") == pytest.approx(457.2)


def test_feet_and_inches_combined():
    assert parse_length_mm("12'-6\"") == pytest.approx(3810.0)
    assert parse_length_mm("12 ft 6 in") == pytest.approx(3810.0)


# --------------------------------------------------------------------------
# Signed values - a machine offset or a position is a coordinate, not just a
# magnitude, and must accept a leading minus sign like any other length input.
# --------------------------------------------------------------------------

def test_negative_bare_number():
    assert parse_length_mm("-235") == pytest.approx(-235.0)
    assert parse_length_mm(-235) == pytest.approx(-235.0)


def test_negative_with_unit_suffix():
    assert parse_length_mm("-2.43 m") == pytest.approx(-2430.0)
    assert parse_length_mm("-1.09 m") == pytest.approx(-1090.0)
    assert parse_length_mm("-6 ft") == pytest.approx(-1828.8)


def test_negative_feet_inches_combined():
    assert parse_length_mm("-12'-6\"") == pytest.approx(-3810.0)


def test_negative_fraction():
    assert parse_length_mm('-9 1/4"') == pytest.approx(-9.25 * 25.4)


def test_unknown_unit_is_rejected():
    with pytest.raises(UnitError, match="Could not interpret"):
        parse_length_mm("5 furlongs")


def test_unparseable_text_is_rejected():
    with pytest.raises(UnitError, match="Could not interpret"):
        parse_length_mm("twelve metres")


def test_empty_string_is_rejected():
    with pytest.raises(UnitError, match="Empty length"):
        parse_length_mm("")
        parse_length_mm("   ")
