"""Render the identified songs as console text, JSON, and Markdown."""

from __future__ import annotations

import json

from .models import Song


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def to_dict(songs: list[Song], duration: float, source: str) -> dict:
    return {
        "source": source,
        "duration_s": round(duration, 1),
        "n_songs": len(songs),
        "songs": [
            {
                "artist": s.artist,
                "title": s.title,
                "track_key": s.track_key,
                "first_s": round(s.first_s, 1),
                "last_s": round(s.last_s, 1),
                "detections": s.count,
                "confidence": s.confidence,
                "pitched": s.pitched,
                "source": s.source,
                "url": next((d.url for d in s.detections if d.url), None),
            }
            for s in songs
        ],
    }


def console(songs: list[Song], duration: float) -> str:
    lines = [
        "",
        f"Identified {len(songs)} distinct song(s) in {_fmt(duration)}:",
        "",
    ]
    for i, s in enumerate(songs, 1):
        extra = ""
        if s.pitched:
            extra += ", varispeed"
        if s.via_audd:
            extra += ", via AudD"
        lines.append(
            f"{i:>2}. [{_fmt(s.first_s)}] {s.label()}   ({s.count}x, {s.confidence}{extra})"
        )
    lines.append("")
    lines.append("  confidence = how many windows matched (high>=3, med=2, low=1)")
    if any(s.pitched for s in songs):
        lines.append("  varispeed  = only matched after speed correction")
    if any(s.via_audd for s in songs):
        lines.append("  via AudD   = found by the AudD fallback in a Shazam gap")
    return "\n".join(lines)


def markdown(songs: list[Song], duration: float, source: str) -> str:
    noun = "song" if len(songs) == 1 else "songs"
    out = [
        f"# Tracklist — {source}",
        "",
        f"_{len(songs)} {noun} identified · mix length {_fmt(duration)}_",
        "",
        "| # | Time | Artist – Title | Hits | Confidence |",
        "|---|------|----------------|------|------------|",
    ]
    for i, s in enumerate(songs, 1):
        notes = []
        if s.pitched:
            notes.append("_(varispeed)_")
        if s.via_audd:
            notes.append("_(via AudD)_")
        note = (" " + " ".join(notes)) if notes else ""
        link = next((d.url for d in s.detections if d.url), None)
        label = f"[{s.label()}]({link})" if link else s.label()
        out.append(
            f"| {i} | {_fmt(s.first_s)} | {label}{note} | {s.count} | {s.confidence} |"
        )
    return "\n".join(out) + "\n"


def write_outputs(songs, duration, source, prefix: str) -> list[str]:
    written = []
    with open(f"{prefix}.json", "w") as f:
        json.dump(to_dict(songs, duration, source), f, indent=2)
    written.append(f"{prefix}.json")
    with open(f"{prefix}.md", "w") as f:
        f.write(markdown(songs, duration, source))
    written.append(f"{prefix}.md")
    return written
