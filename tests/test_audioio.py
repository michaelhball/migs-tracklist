import io
import shutil
import subprocess
import wave

import numpy as np
import pytest

from migshazam.audioio import rms_level


def _wav_bytes(samples: np.ndarray, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(samples.astype("<i2").tobytes())
    w.close()
    return buf.getvalue()


def test_rms_loud_passes_silence_fails_gate():
    loud = np.full(16000, 10000, dtype="<i2")
    silent = np.zeros(16000, dtype="<i2")
    assert rms_level(_wav_bytes(loud)) > 0.02
    assert rms_level(_wav_bytes(silent)) < 0.001


def test_rms_without_data_chunk_is_zero():
    assert rms_level(b"RIFF....WAVEfmt ") == 0.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_window_shape_and_varispeed(tmp_path):
    from migshazam.audioio import extract_window, ffprobe_duration

    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
         "-ac", "1", "-ar", "44100", str(src), "-y"],
        check=True,
    )
    assert ffprobe_duration(str(src)) == pytest.approx(20, abs=0.5)

    plain = extract_window(str(src), 2.0, 12.0, speed=1.0)
    fast = extract_window(str(src), 2.0, 12.0, speed=1.06)
    assert plain[:4] == b"RIFF" and fast[:4] == b"RIFF"
    assert plain != fast  # varispeed must alter the audio content
    assert rms_level(plain) > 0.02
