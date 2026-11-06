"""Unit tests for year handling in _normalize_numbers.

Years used to fall through to the cardinal pass because replace_year
was defined but never wired in: "in 2024" was spoken as "in two
thousand twenty four". The normaliser now speaks 4-digit years as
years ("twenty twenty four") in year contexts only - a temporal
preposition or a month name in front of the digits - so plain
quantities stay cardinal.
"""

from app.services.kokoro_service import _normalize_numbers


def test_year_after_temporal_preposition():
    assert _normalize_numbers(
        "The studio released its first video in 2024."
    ) == "The studio released its first video in twenty twenty four."


def test_year_1900s():
    assert _normalize_numbers("Back in 1999, nobody had a smartphone.") == (
        "Back in nineteen ninety nine, nobody had a smartphone."
    )


def test_year_with_oh_for_single_digit_tail():
    assert _normalize_numbers("A photograph from 1905 surfaced online.") == (
        "A photograph from nineteen oh five surfaced online."
    )


def test_year_round_century():
    assert _normalize_numbers("The tradition began in 2000.") == (
        "The tradition began in twenty hundred."
    )


def test_year_after_month_name():
    assert _normalize_numbers("June 2024 was unusually hot.") == (
        "June twenty twenty four was unusually hot."
    )


def test_plain_quantity_is_not_a_year():
    assert _normalize_numbers("She ordered 2000 items for the shoot.") == (
        "She ordered two thousand items for the shoot."
    )


def test_bare_four_digit_quantity_stays_cardinal():
    assert _normalize_numbers("He counted 2024 items in the warehouse.") == (
        "He counted two thousand twenty four items in the warehouse."
    )


def test_ordinal_and_phone_regressions_still_hold():
    # The year pass must not disturb the earlier ordinal/phone fixes.
    assert _normalize_numbers("He finished 1st in the race.") == (
        "He finished first in the race."
    )
    assert _normalize_numbers("Call me at (555) 123-4567 tomorrow.") == (
        "Call me at five hundred fifty five one hundred twenty three "
        "four thousand five hundred sixty seven tomorrow."
    )
