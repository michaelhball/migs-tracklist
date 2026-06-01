"""Orchestration: slide a window across the mix and collect Shazam detections."""

from __future__ import annotations

import sys

from .audioio import extract_window, ffprobe_duration, rms_level
from .models import Detection
from .recognize import Recognizer


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _skew(d: Detection) -> float:
    """How far Shazam had to stretch to match (smaller = cleaner match)."""
    return abs(d.frequency_skew or 0.0) + abs(d.time_skew or 0.0)


def _arbitrate(candidates: list[Detection]) -> Detection | None:
    """Pick the most-agreed track across several varispeed attempts.

    Different speeds can return different songs (a slowed track may match both
    a cover and the original at different speeds). We prefer the track that the
    most speeds agree on; ties break toward the cleanest match (smallest skew)
    and then the speed closest to 1.0.
    """
    if not candidates:
        return None

    groups: dict[str, list[Detection]] = {}
    for d in candidates:
        groups.setdefault(d.track_key, []).append(d)

    def group_rank(items: list[Detection]):
        best = min(items, key=lambda d: (_skew(d), abs(d.speed_factor - 1.0)))
        return (-len(items), _skew(best), abs(best.speed_factor - 1.0))

    winner = min(groups.values(), key=group_rank)
    # Representative detection for the winning track.
    return min(winner, key=lambda d: (_skew(d), abs(d.speed_factor - 1.0)))


async def scan_mix(
    path: str,
    recognizer: Recognizer,
    window_s: float = 12.0,
    hop_s: float = 30.0,
    grid: list[float] | None = None,
    sr: int = 16000,
    start_s: float = 0.0,
    end_s: float | None = None,
    grid_min_rms: float = 0.02,
) -> tuple[list[Detection], float]:
    """Recognize windows across the mix between start_s and end_s.

    For each hop position we recognize the plain window first; only if that
    misses do we try the varispeed `grid` — and we try *every* grid speed, then
    keep the track the most speeds agree on (see `_arbitrate`), rather than the
    first hit, which avoids locking onto a cover/remix at a wrong speed. We only
    spend the extra requests where the plain pass already missed.
    Returns (detections, mix_duration_s).
    """
    duration = ffprobe_duration(path)
    detections: list[Detection] = []
    grid = grid or []

    stop = duration if end_s is None else min(end_s, duration)
    t = max(0.0, start_s)
    n_windows = max(1, int((stop - t) // hop_s) + 1)
    idx = 0
    while t < stop:
        idx += 1
        plain = extract_window(path, t, window_s, speed=1.0, sr=sr)
        det = Recognizer.parse(await recognizer.recognize_bytes(plain), t, 1.0)

        gated = det is None and grid and rms_level(plain) < grid_min_rms
        if det is None and grid and not gated:
            candidates: list[Detection] = []
            for speed in grid:
                data = extract_window(path, t, window_s, speed=speed, sr=sr)
                d = Recognizer.parse(
                    await recognizer.recognize_bytes(data), t, speed
                )
                if d is not None:
                    candidates.append(d)
            det = _arbitrate(candidates)

        if det:
            tag = f"{det.artist} – {det.title}" + (
                f"  [varispeed {det.speed_factor:g}x]" if det.speed_factor != 1.0 else ""
            )
        else:
            tag = "—  (quiet, grid skipped)" if gated else "—"
        print(f"  [{idx}/{n_windows}] {_fmt(t)}  {tag}", file=sys.stderr)

        if det is not None:
            detections.append(det)
        t += hop_s

    return detections, duration
