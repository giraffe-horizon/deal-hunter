"""Tests for CLI verify output."""

from deal_hunter.cli.verify import format_breakdown_line


def test_format_keyword():
    line = format_breakdown_line(
        {"points": 10, "rule": "carbon", "source": "title", "type": "keyword"}
    )
    assert "+10" in line
    assert "carbon" in line


def test_format_budget():
    line = format_breakdown_line(
        {"points": 5, "rule": "budget", "source": "", "match": "in range", "type": "budget"}
    )
    assert "Budget" in line
    assert "in range" in line


def test_format_temperature():
    line = format_breakdown_line(
        {
            "points": 10,
            "rule": "temperature",
            "source": "",
            "match": "hot (150\u00b0)",
            "type": "temperature",
        }
    )
    assert "Temperature" in line


def test_format_excluded():
    line = format_breakdown_line(
        {"points": -100, "rule": "cheap", "source": "title", "match": "", "type": "excluded"}
    )
    assert "EXCLUDED" in line
    assert "-100" in line


def test_format_regex():
    line = format_breakdown_line(
        {"points": 10, "rule": "r/\\bxl\\b/", "source": "title", "match": "xl", "type": "regex"}
    )
    assert "regex" in line
    assert "xl" in line


def test_format_negative():
    line = format_breakdown_line(
        {"points": -5, "rule": "heavy", "source": "desc", "type": "penalty"}
    )
    assert "-5" in line
    assert "heavy" in line
