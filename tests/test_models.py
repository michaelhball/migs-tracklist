from migshazam.models import Detection, Song


def _song(key="k", n=1, speeds=None):
    speeds = speeds or [1.0] * n
    s = Song(track_key=key, title="T", artist="A")
    for i, sp in enumerate(speeds):
        s.detections.append(Detection(i * 30, key, "T", "A", speed_factor=sp))
    return s


def test_counts_and_bounds():
    s = _song(n=3)
    assert s.count == 3
    assert s.first_s == 0
    assert s.last_s == 60


def test_confidence_tiers():
    assert _song(n=1).confidence == "low"
    assert _song(n=2).confidence == "medium"
    assert _song(n=5).confidence == "high"


def test_pitched_only_when_no_plain_hit():
    assert _song(speeds=[1.06]).pitched is True
    assert _song(speeds=[1.0]).pitched is False
    assert _song(speeds=[1.06, 1.0]).pitched is False  # one clean hit is enough


def test_label():
    s = Song(track_key="k", title="Tramp", artist="Otis Redding")
    assert s.label() == "Otis Redding – Tramp"
    assert Song(track_key="k", title="", artist="").label() == "? – ?"


def test_source_and_via_audd():
    mixed = Song(track_key="k", title="T", artist="A")
    mixed.detections += [Detection(0, "k", "T", "A"),
                         Detection(30, "k", "T", "A", source="audd")]
    assert mixed.via_audd is True
    assert mixed.source == "mixed"

    pure = Song(track_key="z", title="T", artist="A")
    pure.detections.append(Detection(0, "z", "T", "A", source="audd"))
    assert pure.source == "audd"

    shz = _song(n=2)
    assert shz.via_audd is False and shz.source == "shazam"


def _with_offsets(pairs, speeds=None):
    s = Song(track_key="k", title="T", artist="A")
    speeds = speeds or [1.0] * len(pairs)
    for (t, o), sp in zip(pairs, speeds, strict=True):
        s.detections.append(Detection(t, "k", "T", "A", offset_s=o, speed_factor=sp))
    return s


def test_offsets_consistent_when_advancing_like_playback():
    assert _with_offsets([(0, 30), (30, 61), (60, 88)]).offsets_consistent is True


def test_offsets_inconsistent_for_scattered_matches():
    assert _with_offsets([(0, 120), (30, 15), (60, 200)]).offsets_consistent is False


def test_offsets_unknown_without_two_offsets():
    assert _with_offsets([(0, 30)]).offsets_consistent is None
    assert _song(n=3).offsets_consistent is None  # detections carry no offsets


def test_offsets_consistent_scales_with_varispeed():
    # Matched at 1.06x speed-up ⇒ the mix plays the track slowed ⇒ catalog
    # offsets advance by Δt/1.06, not Δt.
    pairs = [(0, 10), (30, 10 + 30 / 1.06)]
    assert _with_offsets(pairs, speeds=[1.06, 1.06]).offsets_consistent is True


def test_offsets_tolerate_small_jitter_but_not_rewinds():
    assert _with_offsets([(0, 50), (30, 75)]).offsets_consistent is True   # -5s jitter
    assert _with_offsets([(0, 50), (30, 20)]).offsets_consistent is False  # rewind


def test_offsets_consistent_allows_forward_jumps_and_uneven_rate():
    # Regression: real groovy/looped tracks whose offsets jump FORWARD (Shazam
    # matching a similar bar elsewhere in the track) or advance at an uneven rate
    # must NOT be flagged — only backward rewinds are. These are the exact
    # offsets of DJ Darryn's "Act I" and "Millie Jackson", which the old
    # exact-rate check wrongly rejected despite both verifying acoustically.
    assert _with_offsets([(0, 45), (30, 39), (60, 110)]).offsets_consistent is True
    assert _with_offsets(
        [(0, 52), (30, 71), (60, 105), (90, 111)]).offsets_consistent is True


def test_offsets_not_compared_across_different_recordings():
    # A merged song holding Shazam + AudD hits of different releases: offsets
    # only pair up within one track_key, so the cross-backend "jump" is ignored.
    s = Song(track_key="k", title="T", artist="A")
    s.detections += [
        Detection(0, "k", "T", "A", offset_s=30),
        Detection(30, "k", "T", "A", offset_s=61),
        Detection(60, "audd:a|t", "T", "A", source="audd", offset_s=200),
    ]
    assert s.offsets_consistent is True
