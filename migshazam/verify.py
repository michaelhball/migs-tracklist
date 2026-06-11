"""Acoustic verification: check that identified songs really occur in the mix.

Shazam/AudD matches are sometimes wrong (false positives on transitions, wrong
versions, gap-fill guesses). This stage fetches a short preview of the *claimed*
track — Apple/Deezer previews via URLs the backends already returned, falling
back to the iTunes/Deezer search APIs — and aligns it against the mix audio
around the claimed position with subsequence DTW over chroma features. Chroma
captures harmony, so the alignment survives what DJ mixes do to a track:
varispeed (the DTW path absorbs ±10%+ tempo drift), EQ filtering, and partial
crossfade overlap. Key shifts of ±1 semitone (nearly all real DJ key changes)
are handled by rotating the chroma.

A wrong identification simply fails to align, which is the safe direction: a
"rejected" verdict means "this audio is not where the tracklist claims", while
"unverifiable" (no preview obtainable) is reported distinctly rather than
counted against the track.

Requires librosa (install the `verify` extra). Network: Apple's CDN/iTunes
Search API and Deezer's public API, a few requests per song.
"""

from __future__ import annotations

import sys
import tempfile
import time

import numpy as np
import requests

from .audioio import decode_pcm
from .cluster import _norm
from .models import Song

# Calibrated on real iTunes previews embedded in synthetic mixes: true matches
# scored 0.004 (clean), 0.020 (transition-style EQ), 0.044 (entire preview
# overlapped 50% with another track — pathological); absent tracks scored
# 0.068–0.157 regardless of segment length. Cosine distance over L2-normalized
# CENS chroma, slope-constrained DTW, path-length normalized.
DEFAULT_THRESHOLD = 0.055

_SR = 22050
_HOP = 2048              # ~93 ms per chroma frame at 22050 Hz
_PAD_S = 75.0            # mix context around the claimed span
_MIN_PREVIEW_S = 5.0
_ITUNES_INTERVAL = 3.0   # iTunes Search API allows ~20 calls/min

_last_itunes = 0.0


def require_librosa():
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "--verify needs librosa; install it with: uv sync --extra verify"
        ) from exc
    return librosa


def _title_matches(want: str, got: str) -> bool:
    """Loose title equality: normalized containment either way, so version
    suffixes ('Remastered', 'feat. X') don't block a legitimate preview."""
    nw, ng = _norm(want), _norm(got)
    return bool(nw) and bool(ng) and (nw in ng or ng in nw)


def _artist_matches(want: str, got: str) -> bool:
    """Loose artist check: any normalized token in common. Lets credit variants
    through ('Otis Redding & Carla Thomas' vs 'Otis Redding') while screening
    out karaoke/tribute acts that share only the song title."""
    tw, tg = set(_norm(want).split()), set(_norm(got).split())
    return not tw or bool(tw & tg)


def _itunes_search(artist: str, title: str, timeout: float = 15) -> str | None:
    global _last_itunes
    wait = _ITUNES_INTERVAL - (time.monotonic() - _last_itunes)
    if wait > 0:
        time.sleep(wait)
    _last_itunes = time.monotonic()
    r = requests.get(
        "https://itunes.apple.com/search",
        params={"term": f"{artist} {title}", "media": "music", "limit": 5},
        timeout=timeout,
    )
    r.raise_for_status()
    for hit in r.json().get("results", []):
        if (hit.get("previewUrl")
                and _title_matches(title, hit.get("trackName", ""))
                and _artist_matches(artist, hit.get("artistName", ""))):
            return hit["previewUrl"]
    return None


def _deezer_search(artist: str, title: str, timeout: float = 15) -> str | None:
    r = requests.get(
        "https://api.deezer.com/search",
        params={"q": f"{artist} {title}"},
        timeout=timeout,
    )
    r.raise_for_status()
    for hit in r.json().get("data", []):
        if (hit.get("preview")
                and _title_matches(title, hit.get("title", ""))
                and _artist_matches(artist, (hit.get("artist") or {}).get("name", ""))):
            return hit["preview"]
    return None


def _preview_candidates(song: Song):
    """Yield (url, provenance) candidates, cheapest/most-authoritative first."""
    seen = set()
    for d in song.detections:
        if d.preview_url and d.preview_url not in seen:
            seen.add(d.preview_url)
            yield d.preview_url, f"{d.source} preview"
    yield None, "itunes search"
    yield None, "deezer search"


def fetch_preview(song: Song, tmpdir: str) -> tuple[np.ndarray, str] | None:
    """Download and decode a usable preview of the claimed track.

    Returns (mono PCM at _SR, provenance). A candidate that downloads but isn't
    decodable audio of useful length (expired CDN link serving an error page,
    truncated clip) falls through to the next source instead of giving up.
    """
    for url, provenance in _preview_candidates(song):
        try:
            if url is None:
                if not (song.artist or song.title):
                    continue
                search = _itunes_search if "itunes" in provenance else _deezer_search
                url = search(song.artist, song.title)
                if not url:
                    continue
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".audio",
                                             delete=False) as f:
                f.write(resp.content)
        except (requests.RequestException, ValueError, KeyError):
            continue  # bad candidate (network/JSON/shape) — try the next source
        try:
            pcm = decode_pcm(f.name, sr=_SR)
        except Exception:
            continue  # HTTP 200 but not decodable audio — try the next source
        if len(pcm) < _MIN_PREVIEW_S * _SR:
            continue  # truncated/stub body — try the next source
        return pcm, provenance
    return None


def _chroma(librosa, y):
    c = librosa.feature.chroma_cens(y=y, sr=_SR, hop_length=_HOP)
    # fill=True keeps silent frames from producing zero vectors (NaN cosine).
    return librosa.util.normalize(np.asarray(c), axis=0, fill=True)


def match_cost(preview_chroma, segment_chroma) -> float:
    """Best path-normalized subsequence-DTW cost of the preview within the
    segment, over ±1-semitone chroma rotations. Lower = better match."""
    librosa = require_librosa()
    # No horizontal/vertical steps: the path can't camp on one similar frame,
    # which is how an absent track fakes a cheap match. Slope stays in [0.5, 2],
    # ample for any real varispeed.
    steps = dict(step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
                 weights_add=np.array([0, 0, 0]),
                 weights_mul=np.array([1, 1, 1]))
    best = float("inf")
    for shift in (0, 1, -1):
        x = np.roll(preview_chroma, shift, axis=0)
        d, wp = librosa.sequence.dtw(X=x, Y=segment_chroma, metric="cosine",
                                     subseq=True, **steps)
        best = min(best, float(d[-1, :].min()) / len(wp))
    return best


def verify_song(
    song: Song,
    mix_path: str,
    duration: float,
    tmpdir: str,
    threshold: float = DEFAULT_THRESHOLD,
    window_s: float = 12.0,
    pad_s: float = _PAD_S,
) -> None:
    """Set song.verification / song.verify_note in place."""
    librosa = require_librosa()

    fetched = fetch_preview(song, tmpdir)
    if fetched is None:
        song.verification = "unverifiable"
        song.verify_note = "no usable preview found"
        return
    preview, provenance = fetched

    seg_start = max(0.0, song.first_s - pad_s)
    seg_end = min(duration, song.last_s + window_s + pad_s)
    segment = decode_pcm(mix_path, sr=_SR, start_s=seg_start,
                         dur_s=seg_end - seg_start)

    cost = match_cost(_chroma(librosa, preview), _chroma(librosa, segment))
    song.verification = "verified" if cost <= threshold else "rejected"
    song.verify_note = f"cost {cost:.3f} ({provenance})"


def verify_songs(
    songs: list[Song],
    mix_path: str,
    duration: float,
    threshold: float = DEFAULT_THRESHOLD,
    window_s: float = 12.0,
) -> None:
    """Verify every song in place, reporting progress on stderr."""
    require_librosa()  # fail fast (and clearly) before any network/decode work
    with tempfile.TemporaryDirectory(prefix="migshazam_verify_") as tmpdir:
        for i, song in enumerate(songs, 1):
            try:
                verify_song(song, mix_path, duration, tmpdir,
                            threshold=threshold, window_s=window_s)
            except Exception as exc:
                song.verification = "unverifiable"
                song.verify_note = f"error: {type(exc).__name__}: {exc}"
            mark = {"verified": "+", "rejected": "x"}.get(song.verification, "?")
            print(f"  [{i}/{len(songs)}] {mark} {song.label()}  "
                  f"({song.verification}: {song.verify_note})", file=sys.stderr)
