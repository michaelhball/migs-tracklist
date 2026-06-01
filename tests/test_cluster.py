from migshazam.cluster import _identity, _norm, cluster_songs
from migshazam.models import Detection


def D(t, key, title="T", artist="A", speed=1.0):
    return Detection(t, key, title, artist, speed_factor=speed)


def test_groups_by_track_key_and_orders_by_first_appearance():
    songs = cluster_songs([D(60, "b"), D(0, "a"), D(30, "a")], min_matches=1)
    assert [s.track_key for s in songs] == ["a", "b"]
    assert songs[0].count == 2


def test_min_matches_drops_single_hits():
    songs = cluster_songs([D(0, "a"), D(30, "a"), D(90, "b")], min_matches=2)
    assert [s.track_key for s in songs] == ["a"]


def test_identity_falls_back_to_normalized_title_artist_without_key():
    d1 = Detection(0, "", "Take On Me", "a-ha")
    d2 = Detection(30, "", "take on me (feat. x)", "A-ha")
    songs = cluster_songs([d1, d2], min_matches=1)
    assert len(songs) == 1
    assert songs[0].count == 2


def test_track_key_takes_priority_over_title():
    # same key, different display titles -> one song
    songs = cluster_songs([D(0, "k", title="A"), D(30, "k", title="B")], min_matches=1)
    assert len(songs) == 1


def test_norm_strips_features_and_parentheticals():
    assert _norm("Take On Me (Live)") == "take on me"
    assert _norm("Song feat. Someone") == "song"
    assert _identity(Detection(0, "357027", "x", "y")) == "key:357027"
