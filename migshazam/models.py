"""Data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Detection:
    """A single Shazam hit on one window of the mix."""

    time_s: float          # window start offset within the mix (seconds)
    track_key: str         # Shazam track id — the identity we cluster on
    title: str
    artist: str
    speed_factor: float = 1.0          # which varispeed variant produced the hit
    frequency_skew: float | None = None  # Shazam's reported pitch deviation
    time_skew: float | None = None        # Shazam's reported tempo deviation
    url: str | None = None             # shazam.com link to the track


@dataclass
class Song:
    """A distinct song identified in the mix, with all of its detections."""

    track_key: str
    title: str
    artist: str
    detections: list[Detection] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def first_s(self) -> float:
        return min(d.time_s for d in self.detections)

    @property
    def last_s(self) -> float:
        return max(d.time_s for d in self.detections)

    @property
    def pitched(self) -> bool:
        """True if it only matched on a varispeed-corrected window."""
        return all(abs(d.speed_factor - 1.0) > 1e-6 for d in self.detections)

    @property
    def confidence(self) -> str:
        if self.count >= 3:
            return "high"
        if self.count == 2:
            return "medium"
        return "low"

    def label(self) -> str:
        artist = self.artist or "?"
        title = self.title or "?"
        return f"{artist} – {title}"
