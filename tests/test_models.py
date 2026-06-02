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
