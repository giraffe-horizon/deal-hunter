"""Tests for Source.extract_price() — shared price parser."""

import pytest

from deal_hunter.sources.base import Source


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 234 PLN", 1234),
        ("18.999 ZŁ", 18999),
        ("1234,50", 1234),
        ("1.234,50 zł", 1234),
        ("299,99 €", 299),
        ("brak ceny", 0),
        ("", 0),
        ("0 PLN", 0),
        ("1234", 1234),
        ("12\xa0345 zł", 12345),
        ("3.499,00 PLN", 3499),
        ("99", 99),
        ("1.234.567 zł", 1234567),
    ],
)
def test_extract_price(text: str, expected: int) -> None:
    assert Source.extract_price(text) == expected
