"""Regression tests: explicit units are preserved, never silently relabeled."""

from normalize.units import normalize_dimension_list, split_value_uom


def test_explicit_metric_units_preserved():
    assert split_value_uom("600 mm") == ("600", "mm")
    assert split_value_uom("2.5 cm") == ("2.5", "cm")
    assert split_value_uom("10 ft") == ("10", "ft")


def test_bare_number_adopts_expected_uom_without_conversion():
    value, uom = split_value_uom("48", expected_uom="in")
    assert (value, uom) == ("48", "in")


def test_no_default_invention_without_expected():
    assert split_value_uom("48") == ("48", "")


def test_explicit_inch_still_normalized():
    value, uom = split_value_uom('24 in', expected_uom="in")
    assert (value, uom) == ("24", "in")


def test_voltage_and_amperage_unaffected():
    assert split_value_uom("120 V") == ("120", "V")
    assert split_value_uom("15 A", expected_uom="A") == ("15", "A")
