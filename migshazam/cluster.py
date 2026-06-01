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

    result = [s for s in songs.values() if s.count >= min_matches]
    result.sort(key=lambda s: s.first_s)
    return result
