# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Speech-to-text: let JARVIS listen.

Captures microphone audio (via `sounddevice`) and transcribes it with the
OpenAI Whisper API. Both the mic library and the API key are optional: if
either is missing, ``available`` is False and the caller should fall back to
typed input.

Recording uses voice activity detection (VAD): it waits for you to start
talking, records while you speak, and stops after a short trailing silence — so
short and long utterances both work naturally, no fixed window. The VAD is a
simple energy (RMS) threshold, which is the lazy-but-correct approach: no extra
dependency beyond numpy (which sounddevice already needs). Known ceiling: a
pure energy threshold can be fooled by steady background noise; a spectral or
ML VAD (e.g. webrtcvad, silero) is the upgrade path. A fixed-window fallback
remains for when VAD can't get a clean read.
"""

from __future__ import annotations

import io
import wave
from typing import Any

# sounddevice is optional. Import lazily-ish so the module still loads without it.
try:
    import sounddevice as _sd  # type: ignore
except Exception:  # noqa: BLE001 - any import/portaudio error means "no mic"
    _sd = None

SAMPLE_RATE = 16_000  # Whisper is happy with 16 kHz mono.
DEFAULT_SECONDS = 5

# VAD tuning.
_FRAME_MS = 30  # analyse audio in 30 ms frames
_SILENCE_HANG_MS = 900  # stop this long after speech ends
_MAX_UTTERANCE_S = 15  # hard cap so a stuck mic can't record forever
_START_TIMEOUT_S = 6  # if no speech begins within this, give up
# Energy threshold (RMS of int16). Calibrated against ambient noise at start,
# but floored so a dead-silent room doesn't set an absurdly low bar.
_MIN_THRESHOLD = 500


class Listener:
    def __init__(self, client: Any | None = None, seconds: int = DEFAULT_SECONDS) -> None:
        self._client = client
        self._seconds = seconds

    @property
    def available(self) -> bool:
        """True only if we can both record audio and transcribe it."""
        return _sd is not None and self._client is not None

    def why_unavailable(self) -> str:
        reasons = []
        if _sd is None:
            reasons.append("microphone support not installed (pip install sounddevice)")
        if self._client is None:
            reasons.append("no API key for transcription")
        return "; ".join(reasons) or "unknown reason"

    def listen(self, vad: bool = True) -> str:
        """Record from the mic and return the transcribed text ("" on failure).

        With ``vad`` (default), records until you stop talking. Set vad=False to
        use the old fixed-window capture.
        """
        if not self.available:
            return ""
        try:
            audio = self._record_vad() if vad else self._record_fixed()
            if audio is None:
                return ""  # no speech detected
            return self._transcribe(audio)
        except Exception:  # noqa: BLE001 - never crash the loop on a bad capture
            return ""

    def _pack_wav(self, pcm_bytes: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)
        buf.seek(0)
        return buf.read()

    def _record_fixed(self) -> bytes:
        import numpy as np  # sounddevice pulls numpy in as a dependency

        frames = _sd.rec(
            int(self._seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
        )
        _sd.wait()
        return self._pack_wav(np.asarray(frames, dtype="int16").tobytes())

    def _record_vad(self) -> bytes | None:
        """Record until speech ends. Returns WAV bytes, or None if no speech.

        Reads the mic as a stream of short frames, measures each frame's RMS
        energy, and:
        - calibrates a noise floor from the first few frames,
        - starts collecting once a frame clears the threshold,
        - stops after _SILENCE_HANG_MS of sub-threshold frames,
        - gives up if nothing is said within _START_TIMEOUT_S,
        - caps total capture at _MAX_UTTERANCE_S.
        """
        import numpy as np

        frame_len = int(SAMPLE_RATE * _FRAME_MS / 1000)
        hang_frames = int(_SILENCE_HANG_MS / _FRAME_MS)
        start_timeout_frames = int(_START_TIMEOUT_S * 1000 / _FRAME_MS)
        max_frames = int(_MAX_UTTERANCE_S * 1000 / _FRAME_MS)

        collected: list[np.ndarray] = []
        started = False
        silence_run = 0
        idle_frames = 0
        threshold = float(_MIN_THRESHOLD)
        calib: list[float] = []

        def rms(block: "np.ndarray") -> float:
            if block.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))

        with _sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame_len
        ) as stream:
            frames_seen = 0
            while True:
                block, _ = stream.read(frame_len)
                block = np.asarray(block, dtype="int16").reshape(-1)
                energy = rms(block)
                frames_seen += 1

                # Calibrate threshold from the first ~10 frames of ambient noise.
                if len(calib) < 10:
                    calib.append(energy)
                    if len(calib) == 10:
                        noise = sum(calib) / len(calib)
                        threshold = max(_MIN_THRESHOLD, noise * 3.0)
                    continue

                if not started:
                    idle_frames += 1
                    if energy >= threshold:
                        started = True
                        collected.append(block)
                    elif idle_frames >= start_timeout_frames:
                        return None  # user never spoke
                    continue

                # Speaking: keep everything, watch for trailing silence.
                collected.append(block)
                if energy < threshold:
                    silence_run += 1
                    if silence_run >= hang_frames:
                        break
                else:
                    silence_run = 0
                if len(collected) >= max_frames:
                    break

        if not collected:
            return None
        pcm = np.concatenate(collected).astype("int16").tobytes()
        return self._pack_wav(pcm)

    def _transcribe(self, wav_bytes: bytes) -> str:
        file_obj = io.BytesIO(wav_bytes)
        file_obj.name = "speech.wav"  # the SDK infers format from the name
        result = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=file_obj,
        )
        return (getattr(result, "text", "") or "").strip()
