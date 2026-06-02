"""Command-line entry point: a URL or local file in, a tracklist out."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

from .audd import AuddError, AuddRecognizer, load_token
from .cluster import cluster_songs
from .ingest import download_audio, is_url
from .output import console, write_outputs
from .recognize import Recognizer
from .scan import _fmt, find_gaps, scan_mix

DEFAULT_GRID = "0.94,0.97,1.03,1.06"


def parse_time(s: str) -> float:
    """Parse a time given as seconds (90) or clock form (1:30, 1:02:03)."""
    s = s.strip()
    if ":" not in s:
        return float(s)
    parts = [float(p) for p in s.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="migshazam",
        description="Identify the songs in a DJ mix (YouTube/SoundCloud link or audio file).",
    )
    p.add_argument("input", help="YouTube/SoundCloud URL or path to a local audio file")
    p.add_argument("--window", type=float, default=12.0,
                   help="recognition window length in seconds (<=12; default 12)")
    p.add_argument("--hop", type=float, default=30.0,
                   help="seconds between windows (default 30; smaller = more "
                        "coverage, more requests)")
    p.add_argument("--start", type=parse_time, default=0.0,
                   help="only scan from this offset (seconds or mm:ss / h:mm:ss)")
    p.add_argument("--end", type=parse_time, default=None,
                   help="stop scanning at this offset, e.g. --end 10:00 for the first 10 min")
    p.add_argument("--rate", type=float, default=12.0,
                   help="max Shazam requests per minute (default 12; raise carefully -> 429)")
    p.add_argument("--grid", action="store_true",
                   help="on a miss, retry the window at varispeed factors to rescue pitched tracks")
    p.add_argument("--grid-steps", default=DEFAULT_GRID,
                   help=f"comma-separated varispeed factors for --grid (default {DEFAULT_GRID})")
    p.add_argument("--grid-min-rms", type=float, default=0.02,
                   help="skip the grid on windows quieter than this RMS level 0..1 "
                        "(default 0.02; 0 disables the gate)")
    p.add_argument("--min-matches", type=int, default=2,
                   help="drop songs with fewer than N window hits (default 2; "
                        "single low-confidence hits are usually wrong)")
    p.add_argument("--audd", action="store_true",
                   help="fall back to AudD on unidentified gaps (needs AUDD_API_TOKEN "
                        "in env or a .env file); catches tracks not in Shazam's catalog")
    p.add_argument("--audd-gap-min", type=float, default=60.0,
                   help="only probe AudD on gaps at least this many seconds long (default 60)")
    p.add_argument("--audd-token", default=None,
                   help="AudD API token (overrides env/.env)")
    p.add_argument("--out", default=None,
                   help="output file prefix (default: derived from input)")
    p.add_argument("--keep-audio", action="store_true",
                   help="keep the downloaded audio file instead of deleting it")
    p.add_argument("--ytdlp-arg", action="append", default=[], dest="ytdlp_args",
                   help="extra arg passed through to yt-dlp (repeatable), e.g. "
                        "--ytdlp-arg=--cookies-from-browser=chrome")
    return p


async def _run(args) -> int:
    grid = None
    if args.grid:
        grid = [float(x) for x in args.grid_steps.split(",") if x.strip()]

    tmpdir = None
    cleanup_audio = False
    if is_url(args.input):
        tmpdir = tempfile.mkdtemp(prefix="migshazam_")
        print(f"Downloading audio from {args.input} ...", file=sys.stderr)
        try:
            audio_path = download_audio(args.input, tmpdir, extra_args=args.ytdlp_args)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        cleanup_audio = not args.keep_audio
        source = args.input
        default_prefix = os.path.splitext(os.path.basename(audio_path))[0]
    else:
        if not os.path.isfile(args.input):
            print(f"ERROR: no such file: {args.input}", file=sys.stderr)
            return 2
        audio_path = args.input
        source = os.path.basename(args.input)
        default_prefix = os.path.splitext(os.path.basename(args.input))[0]

    prefix = args.out or f"{default_prefix}.tracklist"

    print(f"Scanning (window={args.window}s, hop={args.hop}s, "
          f"rate={args.rate}/min, grid={'on' if grid else 'off'}) ...", file=sys.stderr)
    recognizer = Recognizer(rate_per_min=args.rate)
    detections, duration = await scan_mix(
        audio_path, recognizer,
        window_s=args.window, hop_s=args.hop, grid=grid,
        start_s=args.start, end_s=args.end,
        grid_min_rms=args.grid_min_rms,
    )

    # AudD fallback on unidentified gaps (needs the audio file, so before cleanup).
    if args.audd:
        token = load_token(args.audd_token)
        if not token:
            print("WARNING: --audd set but no AUDD_API_TOKEN found (env or .env); "
                  "continuing with Shazam only.", file=sys.stderr)
        else:
            audd = AuddRecognizer(token)
            scan_start = max(0.0, args.start)
            scan_end = duration if args.end is None else min(args.end, duration)
            gaps = [(s, e) for (s, e) in find_gaps(detections, scan_end, args.audd_gap_min)
                    if e > scan_start]
            print(f"AudD fallback: probing {len(gaps)} gap(s) >= {args.audd_gap_min:g}s ...",
                  file=sys.stderr)
            try:
                for gs, ge in gaps:
                    glen = ge - gs
                    n = max(2, min(6, round(glen / 150)))
                    for i in range(n):
                        off = gs + glen * (i + 1) / (n + 1)
                        det = audd.recognize_clip(audio_path, off)
                        label = f"{det.artist} – {det.title}" if det else "—"
                        print(f"  [AudD] {_fmt(off)}  {label}", file=sys.stderr)
                        if det:
                            detections.append(det)
            except AuddError as exc:
                # Token expired / quota exhausted / network: keep going Shazam-only.
                print(f"WARNING: AudD fallback unavailable ({exc}); "
                      f"continuing with Shazam results only.", file=sys.stderr)
            print(f"AudD used {audd.requests} request(s)", file=sys.stderr)

    if cleanup_audio:
        try:
            os.remove(audio_path)
            if tmpdir:
                os.rmdir(tmpdir)
        except OSError:
            pass

    songs = cluster_songs(detections, min_matches=args.min_matches)
    print(console(songs, duration))
    written = write_outputs(songs, duration, source, prefix)
    print(f"\nWrote: {', '.join(written)}", file=sys.stderr)
    print(f"({recognizer.requests} Shazam requests, "
          f"{len(detections)} window hits)", file=sys.stderr)
    return 0


def main() -> None:
    args = _build_parser().parse_args()
    try:
        sys.exit(asyncio.run(_run(args)))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
