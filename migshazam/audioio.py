"""ffmpeg/ffprobe helpers: probe duration and extract recognition windows."""

from __future__ import annotations

import json
import subprocess

import numpy as np


def rms_level(wav_bytes: bytes) -> float:
    """Normalized RMS loudness (0..1) of a PCM-16 WAV window.

    Used to gate the varispeed grid: there's no point spending extra requests
    trying to rescue a window that's basically silent (intro/breakdown/ambient).
    Locates the `data` chunk so it works on ffmpeg's streamed (pipe) headers.
    """
    i = wav_bytes.find(b"data")
    if i == -1 or len(wav_bytes) <= i + 8:
        return 0.0
    pcm = wav_bytes[i + 8:]
    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2)))


def ffprobe_duration(path: str) -> float:
    """Return the duration of an audio file in seconds."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def extract_window(
    path: str,
    start_s: float,
    dur_s: float,
    speed: float = 1.0,
    sr: int = 16000,
) -> bytes:
    """Extract a mono window as WAV bytes, optionally varispeed-shifted.

    Shazam fingerprints break under tempo/varispeed (a DJ's pitch fader), so
    `speed != 1.0` lets us re-query a missed window as if it were played at a
    different speed. asetrate+aresample is a true varispeed (pitch AND tempo
    move together), which mirrors what a turntable pitch fader does.

    `-ss` is placed before `-i` for fast (approximate) seeking — precise
    boundaries are not the goal, coverage is.
    """
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", f"{start_s:.3f}",
        "-i", path,
        "-t", f"{dur_s:.3f}",
        "-ac", "1",
    ]
    if abs(speed - 1.0) > 1e-6:
        # Normalize to `sr` FIRST so asetrate's relabel is relative to a known
        # rate, then relabel (varispeed: pitch+tempo together), then resample
        # back to `sr` for output.
        cmd += [
            "-af",
            f"aresample={sr},asetrate={int(round(sr * speed))},aresample={sr}",
        ]
    else:
        cmd += ["-ar", str(sr)]
    cmd += ["-f", "wav", "pipe:1"]

    out = subprocess.run(cmd, capture_output=True, check=True)
    return out.stdout
