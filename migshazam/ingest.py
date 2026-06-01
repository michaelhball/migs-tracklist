"""Audio acquisition: download a YouTube/SoundCloud URL to a local file via yt-dlp."""

from __future__ import annotations

import glob
import os
import subprocess
import sys


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def download_audio(
    url: str,
    out_dir: str,
    ytdlp_bin: str | None = None,
    extra_args: list[str] | None = None,
) -> str:
    """Download the best audio track of `url` into `out_dir`, return the file path.

    Downloads bestaudio without re-encoding (fast); ffmpeg in the pipeline reads
    whatever container yt-dlp produces. For YouTube this needs a JS runtime
    (Deno/Node) shipped via yt-dlp[default]; pass cookies / PO-token args through
    `extra_args` if a video is gated.
    """
    os.makedirs(out_dir, exist_ok=True)
    template = os.path.join(out_dir, "%(id)s.%(ext)s")
    # Invoke via the running interpreter's module so we always use the venv's
    # yt-dlp regardless of whether the venv is activated / on PATH.
    base = [ytdlp_bin] if ytdlp_bin else [sys.executable, "-m", "yt_dlp"]
    cmd = [
        *base,
        "-f", "bestaudio/best",
        "--no-playlist",
        "-o", template,
        *(extra_args or []),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"yt-dlp failed (exit {proc.returncode}).\n{proc.stderr.strip()}"
        )

    files = sorted(
        (f for f in glob.glob(os.path.join(out_dir, "*")) if os.path.isfile(f)),
        key=os.path.getmtime,
    )
    if not files:
        raise RuntimeError("yt-dlp reported success but produced no file.")
    return files[-1]
