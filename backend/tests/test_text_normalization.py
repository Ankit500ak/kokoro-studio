"""Unit tests for the TTS text-normalisation helpers in kokoro_service.

These cover the pure text -> spoken-words conversions that run on every
TTS request (preprocess_text -> _normalize_text_comprehensive ->
_normalize_numbers). No model or audio code is exercised.
"""

import pytest

from app.services.kokoro_service import _normalize_numbers, _number_to_words


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, "zero"),
        (5, "five"),
        (21, "twenty one"),
        (100, "one hundred"),
        (115, "one hundred fifteen"),
        (1000, "one thousand"),
        (2024, "two thousand twenty four"),
        (1000000, "one million"),
        (-3, "minus three"),
    ],
)
def test_number_to_words(n, expected):
    assert _number_to_words(n) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("He finished 1st in the race.", "He finished first in the race."),
        ("She came 2nd and 3rd.", "She came second and third."),
        (
            "They were 21st, 22nd and 23rd.",
            "They were twenty first, twenty second and twenty third.",
        ),
        (
            "It was the 4th of July, her 11th birthday.",
            "It was the fourth of July, her eleventh birthday.",
        ),
        (
            "The 12th day, the 13th hour, the 20th century.",
            "The twelfth day, the thirteenth hour, the twentieth century.",
        ),
    ],
)
def test_ordinals_are_spoken_correctly(text, expected):
    assert _normalize_numbers(text) == expected


def test_parenthesised_phone_number_does_not_crash():
    # Regression: int("(555)") used to raise ValueError and fail the
    # entire TTS request during preprocessing.
    result = _normalize_numbers("Call me at (555) 123-4567 tomorrow.")
    assert result == (
        "Call me at five hundred fifty five one hundred twenty three "
        "four thousand five hundred sixty seven tomorrow."
    )


def test_plain_phone_number():
    assert _normalize_numbers("Call 555-123-4567 now.") == (
        "Call five hundred fifty five one hundred twenty three "
        "four thousand five hundred sixty seven now."
    )


def test_money_with_cents():
    assert _normalize_numbers("It costs $5.50.") == (
        "It costs five dollars and fifty cents."
    )


def test_time_and_percentage():
    assert _normalize_numbers("The meeting is at 3:30.") == (
        "The meeting is at three thirty."
    )
    assert _normalize_numbers("About 50% agreed.") == "About fifty percent agreed."


@pytest.mark.parametrize(
    "text, expected",
    [
        ("He ate 3/4 of the pie.", "He ate three quarters of the pie."),
        ("He ate 1/12 of the cake.", "He ate a twelfth of the cake."),
        ("Only 1/2 remains.", "Only a half remains."),
        ("It is 5/6 done.", "It is five sixths done."),
    ],
)
def test_fractions(text, expected):
    assert _normalize_numbers(text) == expected
