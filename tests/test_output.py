from migshazam.models import Detection, Song
from migshazam.output import console, markdown, to_dict


def _song(verification=None, offsets=None):
    s = Song(track_key="k", title="T", artist="A", verification=verification)
    for i, off in enumerate(offsets or [None, None]):
        s.detections.append(Detection(i * 30.0, "k", "T", "A", offset_s=off))
    return s


def test_json_carries_consistency_and_verification_fields():
    d = to_dict([_song()], 120.0, "mix")
    row = d["songs"][0]
    assert row["offsets_consistent"] is None
    assert row["verification"] is None

    d = to_dict([_song(verification="verified", offsets=[10, 40])], 120.0, "mix")
    row = d["songs"][0]
    assert row["offsets_consistent"] is True
    assert row["verification"] == "verified"


def test_markdown_verified_column_only_when_verification_ran():
    plain = markdown([_song()], 120.0, "mix")
    assert "Verified" not in plain

    md = markdown([_song(verification="rejected")], 120.0, "mix")
    assert "| Verified |" in md
    assert "✗" in md


def test_markdown_flags_offset_mismatch():
    md = markdown([_song(offsets=[100, 15])], 120.0, "mix")
    assert "_(offset mismatch)_" in md


def test_console_marks_inconsistent_offsets_and_verification():
    text = console([_song(verification="rejected", offsets=[100, 15])], 120.0)
    assert "offsets!" in text
    assert "rejected" in text
