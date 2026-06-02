"""AudD fallback backend.

Shazam misses some tracks that simply aren't in its catalog (different
pressings/versions, obscure artists). AudD's catalog differs, so we use it ONLY
to fill the gaps Shazam left — a few short clips per unidentified stretch, which
keeps it cheap (AudD's free tier is 300 requests; paid is ~$2/1000).
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import requests

from .models import Detection

ENDPOINT = "https://api.audd.io/"


def load_token(explicit: str | None = None) -> str | None:
    """Resolve the AudD token: explicit arg > env var > project .env file."""
    if explicit:
        return explicit
    if os.environ.get("AUDD_API_TOKEN"):
        return os.environ["AUDD_API_TOKEN"]
    for p in (pathlib.Path(".env"), pathlib.Path.home() / ".config" / "migshazam" / "env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip().startswith("AUDD_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _clip(path: str, start_s: float, dur_s: float, sr: int = 44100) -> bytes:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start_s:.3f}", "-i", path, "-t", f"{dur_s:.3f}",
           "-ac", "1", "-ar", str(sr), "-f", "wav", "pipe:1"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


class AuddRecognizer:
    def __init__(self, token: str, clip_s: float = 18.0):
        self.token = token
        self.clip_s = clip_s
        self.requests = 0

    def recognize_clip(self, path: str, start_s: float) -> Detection | None:
        """Identify a single clip via AudD; returns a Detection or None."""
        self.requests += 1
        try:
            resp = requests.post(
                ENDPOINT,
                data={"api_token": self.token},
                files={"file": ("clip.wav", _clip(path, start_s, self.clip_s), "audio/wav")},
                timeout=90,
            ).json()
        except Exception:
            return None
        if resp.get("status") != "success":
            return None
        res = resp.get("result")
        if not res:
            return None
        artist = (res.get("artist") or "").strip()
        title = (res.get("title") or "").strip()
        return Detection(
            time_s=start_s,
            track_key=f"audd:{artist}|{title}".lower(),
            title=title,
            artist=artist,
            url=res.get("song_link"),
            source="audd",
        )
