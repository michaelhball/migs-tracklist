"""Collapse raw detections into the distinct set of songs (the primary output)."""

from __future__ import annotations

import re

from .models import Detection, Song

_FEAT = re.compile(r"\s*[\(\[]?\s*(feat|ft|featuring|with)\.?\s.*$", re.I)
_PAREN = re.compile(r"\s*[\(\[].*?[\)\]]")
_NONWORD = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = _FEAT.sub("", s)
    s = _PAREN.sub("", s)
    return _NONWORD.sub(" ", s).strip()


def _identity(d: Detection) -> str:
    """Prefer Shazam's track key; fall back to a normalized title+artist."""
    if d.track_key:
        return f"key:{d.track_key}"
    return f"ta:{_norm(d.title)}|{_norm(d.artist)}"


# Consecutive hits of the same title within this many seconds are treated as
# one track (a song rarely recurs that fast).
_MERGE_GAP_S = 150.0


def _merge_same_title(songs: list[Song]) -> list[Song]:
    """Merge time-adjacent songs that share a normalized title.

    Handles the same track surfacing under slightly different artist strings
    (e.g. AudD returning "Charles" vs "Charlie" Mingus for "Cryin' Blues").
    Detections are combined, so the merged hit count is the sum.
    """
    merged: list[Song] = []
    for s in songs:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and _norm(s.title)
            and _norm(prev.title) == _norm(s.title)
            and s.first_s - prev.last_s <= _MERGE_GAP_S
        ):
            prev.detections.extend(s.detections)
        else:
            merged.append(s)
    return merged


def cluster_songs(detections: list[Detection], min_matches: int = 1) -> list[Song]:
    """Group detections into distinct Songs, sorted by first appearance."""
    songs: dict[str, Song] = {}
    for d in detections:
        key = _identity(d)
        song = songs.get(key)
        if song is None:
            song = Song(track_key=d.track_key, title=d.title, artist=d.artist)
            songs[key] = song
        song.detections.append(d)

    ordered = sorted(songs.values(), key=lambda s: s.first_s)
    ordered = _merge_same_title(ordered)

    # Keep a song if Shazam saw it enough times, OR the AudD fallback found it
    # (gap-fills are deliberately kept even on a single hit). Merging happens
    # first, so two single hits of one title combine to clear `min_matches`.
    return [s for s in ordered if s.count >= min_matches or s.via_audd]
