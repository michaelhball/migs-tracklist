import pytest

from migshazam.models import Detection
from migshazam.scan import _arbitrate, _fmt, _skew


def D(key, speed, fs=0.0, ts=0.0):
    return Detection(60, key, "T", "A", speed_factor=speed, frequency_skew=fs, time_skew=ts)


def test_arbitrate_prefers_most_agreed_track():
    r = _arbitrate([D("a", 1.11), D("a", 1.05), D("b", 0.90)])
    assert r.track_key == "a"


def test_arbitrate_tie_breaks_on_cleanest_match():
    r = _arbitrate([D("a", 1.11, fs=0.0), D("b", 0.90, fs=0.05)])
    assert r.track_key == "a"


def test_arbitrate_tie_breaks_on_speed_closest_to_one():
    r = _arbitrate([D("x", 1.05), D("y", 0.90)])
    assert r.track_key == "x"


def test_arbitrate_returns_cleanest_representative_of_winning_track():
    r = _arbitrate([D("a", 1.11, fs=0.02), D("a", 1.05, fs=0.0), D("b", 0.90)])
    assert r.track_key == "a"
    assert r.speed_factor == pytest.approx(1.05)


def test_arbitrate_empty():
    assert _arbitrate([]) is None


def test_skew_handles_missing_values():
    assert _skew(Detection(0, "k", "T", "A", frequency_skew=None, time_skew=None)) == 0.0
    assert _skew(Detection(0, "k", "T", "A", frequency_skew=-0.02, time_skew=0.03)) == pytest.approx(0.05)


@pytest.mark.parametrize("secs,expected", [(0, "0:00"), (75, "1:15"), (3661, "1:01:01")])
def test_fmt(secs, expected):
    assert _fmt(secs) == expected
