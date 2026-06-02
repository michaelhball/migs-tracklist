import pytest

from migshazam.models import Detection
from migshazam.scan import _arbitrate, _fmt, _skew, find_gaps


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


def test_find_gaps_between_songs_and_tail():
    dets = [Detection(t, "a", "T", "A") for t in (0, 30, 60)] + \
           [Detection(t, "b", "T", "A") for t in (200, 230, 260)]
    gaps = find_gaps(dets, duration=400, min_gap=60)
    assert (60.0, 200.0) in gaps                      # gap between the two songs
    assert any(s == 260.0 and e == 400.0 for s, e in gaps)  # tail after last
    # no spurious gap inside a song (windows 30s apart < min_gap)
    assert all(not (0 <= s < 60) for s, e in gaps)


def test_find_gaps_lead_in():
    dets = [Detection(t, "a", "T", "A") for t in (120, 150)]
    gaps = find_gaps(dets, duration=200, min_gap=60)
    assert (0.0, 120.0) in gaps   # silence/unidentified before the first hit
