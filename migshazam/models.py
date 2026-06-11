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


# A real track plays through the mix, so catalog offsets of consecutive hits
# should advance at roughly mix speed. Allow generous slack: Shazam's offset is
# coarse, DJs nudge tempo, and loops/doubles rewind briefly.
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
        """Do the catalog-track offsets of consecutive hits advance like a
        track really playing through the mix?

        For windows Δt apart in the mix, the matched track's offset should
        advance by ~Δt (scaled by varispeed). Independent false matches land at
        arbitrary offsets and fail this. None = fewer than two hits carried an
        offset, so nothing can be said.

        Pairs are only formed between hits on the same catalog recording
        (track_key): a merged song can hold Shazam and AudD hits of different
        releases, whose offsets are not mutually comparable.
        """
        groups: dict[str, list[tuple[float, float, float]]] = {}
        for d in self.detections:
            if d.offset_s is not None:
                groups.setdefault(d.track_key, []).append(
                    (d.time_s, d.offset_s, d.speed_factor))
        pairs = []
        for pts in groups.values():
            pts.sort(key=lambda p: p[0])
            pairs += [(a, b) for a, b in zip(pts, pts[1:], strict=False) if b[0] > a[0]]
        if not pairs:
            return None
        ok = 0
        for (t1, o1, s1), (t2, o2, s2) in pairs:
            dt = t2 - t1
            # Window varispeeded by s to match the catalog ⇒ the mix plays the
            # catalog track at rate 1/s ⇒ expected offset advance is Δt/s.
            expected = dt / ((s1 + s2) / 2)
            if abs((o2 - o1) - expected) <= max(_OFFSET_TOL_S, _OFFSET_TOL_FRAC * dt):
                ok += 1
        return ok * 2 >= len(pairs)

    def label(self) -> str:
        artist = self.artist or "?"
        title = self.title or "?"
        return f"{artist} – {title}"
