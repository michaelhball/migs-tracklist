from migshazam.cluster import _identity, _norm, cluster_songs
from migshazam.models import Detection


def D(t, key, title="T", artist="A", speed=1.0):
    return Detection(t, key, title, artist, speed_factor=speed)


def test_groups_by_track_key_and_orders_by_first_appearance():
    songs = cluster_songs(
        [D(60, "b", title="Beta"), D(0, "a", title="Alpha"), D(30, "a", title="Alpha")],
        min_matches=1,
    )
    assert [s.track_key for s in songs] == ["a", "b"]
    assert songs[0].count == 2


def test_min_matches_drops_single_hits():
    songs = cluster_songs(
        [D(0, "a", title="Alpha"), D(30, "a", title="Alpha"), D(90, "b", title="Beta")],
        min_matches=2,
    )
    assert [s.track_key for s in songs] == ["a"]


def test_adjacent_same_title_merges_and_sums_hits():
    # Same track, different artist spelling, found ~100s apart -> one song, 2 hits.
    dets = [
        Detection(6010, "audd:charles mingus|cryin blues", "Cryin' Blues", "Charles Mingus", source="audd"),
        Detection(6110, "audd:charlie mingus|cryin blues", "Cryin' Blues", "Charlie Mingus", source="audd"),
    ]
    songs = cluster_songs(dets, min_matches=2)
    assert len(songs) == 1
    assert songs[0].count == 2          # 1 + 1 summed
    assert songs[0].confidence == "medium"


def test_two_single_title_hits_merge_to_clear_min_matches():
    # Same title under different keys, adjacent -> merged 2 hits clears min_matches.
    songs = cluster_songs(
        [D(100, "k1", title="Same Song", artist="Artist A"),
         D(130, "k2", title="Same Song", artist="Artist B")],
        min_matches=2,
    )
    assert len(songs) == 1 and songs[0].count == 2


def test_distinct_titles_are_not_merged():
    songs = cluster_songs([D(0, "a", title="Alpha"), D(100, "b", title="Beta")], min_matches=1)
    assert len(songs) == 2


def test_same_title_far_apart_not_merged():
    songs = cluster_songs(
        [D(0, "a", title="Reprise"), D(900, "b", title="Reprise")], min_matches=1
    )
    assert len(songs) == 2  # 15 min apart -> distinct plays, not merged


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


def test_audd_gap_fill_survives_min_matches():
    # A single Shazam hit is dropped, but a single AudD gap-fill is kept.
    dets = [Detection(0, "shz", "T", "A")]
    audd = [Detection(300, "audd:x|y", "Y", "X", source="audd")]
    songs = cluster_songs(dets + audd, min_matches=2)
    keys = [s.track_key for s in songs]
    assert "shz" not in keys
    assert "audd:x|y" in keys


def test_norm_strips_features_and_parentheticals():
    assert _norm("Take On Me (Live)") == "take on me"
    assert _norm("Song feat. Someone") == "song"
    assert _identity(Detection(0, "357027", "x", "y")) == "key:357027"
