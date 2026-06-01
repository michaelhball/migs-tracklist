"""Shazam recognition with rate limiting, retry/backoff, and varispeed grid-search.

ShazamIO is a thin wrapper: it builds a Shazam fingerprint locally (Rust) and
POSTs it to Shazam's unofficial endpoint. That endpoint is undocumented and
IP-rate-limited (~20 req/min before HTTP 429 per community reports), so we
self-throttle and back off on failure rather than hammering it.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time

from shazamio import Shazam

from .models import Detection


@contextlib.contextmanager
def _suppress_native_stderr():
    """Silence the bundled audio decoder's chatter ('skipping junk at N bytes',
    'invalid mpeg audio header') which it writes straight to fd 2, bypassing
    Python and RUST_LOG. We redirect fd 2 to /dev/null only around the decode.
    """
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stderr.flush()
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stderr.flush()
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)


class Recognizer:
    def __init__(self, rate_per_min: float = 12.0, max_retries: int = 4):
        self.shazam = Shazam()
        self.min_interval = 60.0 / rate_per_min
        self.max_retries = max_retries
        self._last = 0.0
        self.requests = 0

    async def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    async def recognize_bytes(self, data: bytes) -> dict | None:
        """Send one fingerprint request, retrying with exponential backoff."""
        for attempt in range(self.max_retries):
            await self._throttle()
            self.requests += 1
            try:
                with _suppress_native_stderr():
                    return await self.shazam.recognize(data)
            except Exception as exc:  # upstream raises many unrelated error types
                backoff = min(2 ** attempt, 30)
                print(
                    f"  ! recognize error ({type(exc).__name__}: {exc}); "
                    f"retry in {backoff}s",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff)
        return None

    @staticmethod
    def parse(out: dict | None, time_s: float, speed: float) -> Detection | None:
        track = (out or {}).get("track")
        if not track or not track.get("key"):
            return None
        matches = out.get("matches") or [{}]
        m = matches[0] if matches else {}
        return Detection(
            time_s=time_s,
            track_key=str(track["key"]),
            title=track.get("title", "") or "",
            artist=track.get("subtitle", "") or "",
            speed_factor=speed,
            frequency_skew=m.get("frequencyskew"),
            time_skew=m.get("timeskew"),
            url=track.get("url"),
        )
