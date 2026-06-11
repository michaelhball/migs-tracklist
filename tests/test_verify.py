"""Verifier tests, including a synthetic-audio calibration of the DTW threshold.

The synthetic 'songs' are distinct chord progressions rendered as sine stacks —
enough harmonic structure for chroma to discriminate, fully deterministic, and
no fixtures or network needed.
"""

import numpy as np
import pytest

librosa = pytest.importorskip("librosa")  # must run before importing migshazam.verify

from migshazam.models import Detection, Song  # noqa: E402
from migshazam.verify import (  # noqa: E402
    DEFAULT_THRESHOLD,
    _chroma,
    _preview_candidates,
    _title_matches,
    fetch_preview,
    match_cost,
)

SR = 22050


def _render(progression, dur_s=20.0, semitone_shift=0):
    """Render a chord progression (list of MIDI triads) as a sine-stack signal."""
    t = np.arange(int(dur_s * SR)) / SR
    y = np.zeros_like(t)
    beat_s = dur_s / len(progression)
    for i, chord in enumerate(progression):
        seg = (t >= i * beat_s) & (t < (i + 1) * beat_s)
        for k, midi in enumerate(chord):
            f = 440.0 * 2 ** ((midi - 69 + semitone_shift) / 12)
            y[seg] += (0.5 ** k) * np.sin(2 * np.pi * f * t[seg])
    return (y / np.abs(y).max()).astype(np.float32)


def _varispeed(y, factor):
    """Resample so the signal plays `factor`x faster (pitch+tempo, like a fader)."""
    idx = np.arange(0, len(y) - 1, factor)
    return np.interp(idx, np.arange(len(y)), y).astype(np.float32)


# Two clearly different progressions (Am-F-C-G vs a chromatic wander), looped.
SONG_A = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]] * 2
SONG_B = [[50, 54, 58], [51, 55, 59], [46, 50, 53], [58, 61, 65]] * 2
SONG_C = [[49, 53, 56], [56, 60, 63], [47, 51, 54], [52, 56, 59]] * 2


def _segment(inner, factor=1.0):
    """A 'mix segment': other music, then `inner` varispeed-shifted, then more
    other music — with noise so the verifier isn't matching silence."""
    rng = np.random.default_rng(42)
    parts = [_render(SONG_B), _varispeed(inner, factor), _render(SONG_C)]
    seg = np.concatenate(parts)
    return seg + rng.normal(0, 0.05, len(seg)).astype(np.float32)


def test_true_match_beats_threshold_even_varispeeded():
    preview = _render(SONG_A)
    for factor in (1.0, 1.06, 0.94):
        cost = match_cost(_chroma(librosa, preview),
                          _chroma(librosa, _segment(_render(SONG_A), factor)))
        assert cost < DEFAULT_THRESHOLD, f"true match failed at {factor}x: {cost:.3f}"


def test_true_match_survives_semitone_key_shift():
    preview = _render(SONG_A)
    shifted = _render(SONG_A, semitone_shift=1)
    cost = match_cost(_chroma(librosa, preview),
                      _chroma(librosa, _segment(shifted)))
    assert cost < DEFAULT_THRESHOLD, f"key-shifted match failed: {cost:.3f}"


def test_wrong_song_is_rejected():
    # SONG_A's preview against a mix that never plays SONG_A.
    preview = _render(SONG_A)
    rng = np.random.default_rng(7)
    seg = np.concatenate([_render(SONG_B), _render(SONG_C)])
    seg = seg + rng.normal(0, 0.05, len(seg)).astype(np.float32)
    cost = match_cost(_chroma(librosa, preview), _chroma(librosa, seg))
    assert cost > DEFAULT_THRESHOLD, f"wrong song accepted: {cost:.3f}"


def test_title_matches_is_loose_but_not_sloppy():
    assert _title_matches("Tramp", "Tramp (Remastered)")
    assert _title_matches("Love Serenade (feat. X)", "Love Serenade")
    assert not _title_matches("Tramp", "Completely Different")
    assert not _title_matches("", "Tramp")


def test_preview_candidates_prefer_backend_urls():
    s = Song(track_key="k", title="T", artist="A")
    s.detections += [
        Detection(0, "k", "T", "A", preview_url="https://x/p.m4a"),
        Detection(30, "k", "T", "A", preview_url="https://x/p.m4a"),  # dup skipped
        Detection(60, "k", "T", "A", source="audd", preview_url="https://y/q.mp3"),
    ]
    cands = list(_preview_candidates(s))
    assert cands[0] == ("https://x/p.m4a", "shazam preview")
    assert cands[1] == ("https://y/q.mp3", "audd preview")
    assert [c[1] for c in cands[2:]] == ["itunes search", "deezer search"]


def test_fetch_preview_falls_through_dead_urls(monkeypatch, tmp_path):
    import requests as _requests

    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise _requests.ConnectionError("dead")

    monkeypatch.setattr("migshazam.verify.requests.get", fake_get)
    monkeypatch.setattr("migshazam.verify._ITUNES_INTERVAL", 0.0)
    s = Song(track_key="k", title="T", artist="A")
    s.detections.append(Detection(0, "k", "T", "A", preview_url="https://x/p.m4a"))
    assert fetch_preview(s, str(tmp_path)) is None
    # tried the backend URL, then both search APIs
    assert len(calls) == 3


def test_artist_matches_screens_karaoke_but_allows_credit_variants():
    from migshazam.verify import _artist_matches

    assert _artist_matches("Otis Redding & Carla Thomas", "Otis Redding")
    assert _artist_matches("", "Anyone")  # no artist known: don't block
    assert not _artist_matches("Daft Punk", "Ameritz Karaoke Band")


def test_fetch_preview_skips_undecodable_download(monkeypatch, tmp_path):
    # First candidate returns HTTP 200 with a non-audio body; searches find
    # nothing — fetch_preview must fall through and return None, not blow up.
    class FakeResp:
        content = b"<html>expired link</html>"
        def raise_for_status(self):
            pass
        def json(self):
            return {"results": [], "data": []}

    monkeypatch.setattr("migshazam.verify.requests.get", lambda *a, **k: FakeResp())
    monkeypatch.setattr("migshazam.verify._ITUNES_INTERVAL", 0.0)
    s = Song(track_key="k", title="T", artist="A")
    s.detections.append(Detection(0, "k", "T", "A", preview_url="https://x/p.m4a"))
    assert fetch_preview(s, str(tmp_path)) is None
