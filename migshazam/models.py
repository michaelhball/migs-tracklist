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
    url: str | None = None             # link to the track
    source: str = "shazam"             # which backend identified it: "shazam" | "audd"
    offset_s: float | None = None      # position in the *catalog track* where the window matched
    preview_url: str | None = None     # ~30s audio preview (Apple/Deezer), if the backend gave one


# A real track plays forward through the mix; only a backward rewind in its
# catalog offset marks a scattered/false match. These bound the rewind forgiven
# as jitter — Shazam's offset is coarse and DJs briefly loop/re-cue.
_OFFSET_TOL_S = 8.0
_OFFSET_TOL_FRAC = 0.25


@dataclass
class Song:
    """A distinct song identified in the mix, with all of its detections."""

    track_key: str
    title: str
    artist: str
    detections: list[Detection] = field(default_factory=list)
    verification: str | None = None   # "verified" | "rejected" | "unverifiable" (None = not run)
    verify_note: str | None = None    # short detail, e.g. the DTW match cost

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
    def via_audd(self) -> bool:
        """True if any detection came from the AudD fallback."""
        return any(d.source == "audd" for d in self.detections)

    @property
    def source(self) -> str:
        srcs = {d.source for d in self.detections}
        if srcs == {"audd"}:
            return "audd"
        return "mixed" if "audd" in srcs else "shazam"

    @property
    def confidence(self) -> str:
        if self.count >= 3:
            return "high"
        if self.count == 2:
            return "medium"
        return "low"

    @property
    def offsets_consistent(self) -> bool | None:
        """Do the catalog-track offsets of consecutive hits move forward, like a
        track really playing through the mix?

        A real track only advances through its own timeline, so we flag a
        *rewind* — a hit landing at an earlier catalog position as the mix moves
        on, beyond a jitter tolerance — which is what scattered/false matches do.
        We deliberately do NOT check the advance *rate*: DJ loops and re-cues,
        self-similar grooves (Shazam matches a similar bar elsewhere in the same
        track) and the grid's quantized varispeed make the rate jump around even
        for correct IDs, so an exact-rate test over-flags them. Forward jumps,
        however large, are fine.

        Pairs only form within one catalog recording (track_key): a merged song
        can hold Shazam and AudD hits of different releases whose offsets are not
        comparable. None = fewer than two hits on a recording carried an offset.
        """
        groups: dict[str, list[tuple[float, float]]] = {}
        for d in self.detections:
            if d.offset_s is not None:
                groups.setdefault(d.track_key, []).append((d.time_s, d.offset_s))
        pairs = []
        for pts in groups.values():
            pts.sort()
            pairs += [(a, b) for a, b in zip(pts, pts[1:], strict=False) if b[0] > a[0]]
        if not pairs:
            return None
        for (t1, o1), (t2, o2) in pairs:
            rewind = o1 - o2  # positive ⇒ the catalog position moved backward
            if rewind > max(_OFFSET_TOL_S, _OFFSET_TOL_FRAC * (t2 - t1)):
                return False
        return True

    def label(self) -> str:
        artist = self.artist or "?"
        title = self.title or "?"
        return f"{artist} – {title}"
