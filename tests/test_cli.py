import pytest

from migshazam.cli import parse_time


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0.0),
        ("90", 90.0),
        ("0:05", 5.0),
        ("1:30", 90.0),
        ("10:00", 600.0),
        ("1:02:03", 3723.0),
    ],
)
def test_parse_time(value, expected):
    assert parse_time(value) == expected
