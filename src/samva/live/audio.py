"""
sounddevice-based audio I/O with a soft echo gate.

Why sounddevice over PyAudio
----------------------------
- Numpy-native callbacks (no bytes ↔ array conversion overhead)
- macOS uses the system audio stack which applies noise suppression on input
- Cleaner stream lifecycle (no pa.terminate())

Echo gate
---------
When the agent is playing audio through the speakers, the same sound reaches
the microphone and can trigger Gemini's VAD, causing the agent to interrupt
itself.  A hard mute (silence while speaking) prevents barge-in.  Instead we
apply a *soft gate*: mic gain is reduced to ``echo_attenuation`` (default 10%)
while the agent speaks, plus a ``cooldown_ms`` tail after playback ends to
absorb room reverberation.  A user speaking loudly enough will still break
through and trigger a barge-in.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

_DTYPE = "int16"
_INT16_MAX = 32767


class AudioCapture:
    """Capture microphone input as 16-bit PCM chunks with echo gating."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        chunk_size: int = 1024,
        echo_attenuation: float = 0.10,
        cooldown_ms: int = 300,
    ) -> None:
        """
        Parameters
        ----------
        echo_attenuation:
            Fraction of mic gain kept while agent is speaking (0.0 = hard mute,
            1.0 = no gating).  Default 0.10 means 10% — enough for loud barge-in
            but suppresses self-echo for normal speaker volume.
        cooldown_ms:
            How long to keep the gate active after playback stops, to absorb
            room reverberation before reopening the mic fully.
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self._echo_attenuation = echo_attenuation
        self._cooldown_s = cooldown_ms / 1000.0

        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self._stream: sd.InputStream | None = None
        self._running = False

        # Echo gate state — written by AudioPlayer, read by callback
        self._gate_lock = threading.Lock()
        self._playing = False          # agent currently writing audio
        self._last_play_time = 0.0     # epoch time of last write

    # ------------------------------------------------------------------
    # Echo gate control (called by AudioPlayer)
    # ------------------------------------------------------------------

    def notify_playing(self, playing: bool) -> None:
        """AudioPlayer calls this to open/close the echo gate."""
        with self._gate_lock:
            self._playing = playing
            if playing:
                self._last_play_time = time.monotonic()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=_DTYPE,
            blocksize=self.chunk_size,
            callback=self._callback,
        )
        self._stream.start()
        logger.debug("AudioCapture started (%d Hz, gate=%.0f%%)",
                     self.sample_rate, self._echo_attenuation * 100)

    def stop(self) -> None:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.debug("AudioCapture stopped")

    def close(self) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Internal callback (runs in sounddevice audio thread)
    # ------------------------------------------------------------------

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        if not self._running:
            return

        samples = indata[:, 0].astype(np.float32)

        with self._gate_lock:
            gate_active = self._playing or (
                time.monotonic() - self._last_play_time < self._cooldown_s
            )

        if gate_active:
            samples *= self._echo_attenuation

        pcm = np.clip(samples, -_INT16_MAX, _INT16_MAX).astype(np.int16).tobytes()
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            pass  # drop if consumer is too slow

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def read(self) -> bytes | None:
        """Return the next audio chunk, or None if nothing is available."""
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._queue.get(timeout=0.05)
            )
        except queue.Empty:
            return None


class AudioPlayer:
    """Play raw 16-bit PCM through the default speaker with echo gate feedback."""

    def __init__(
        self,
        sample_rate: int = 24_000,
        channels: int = 1,
        capture: AudioCapture | None = None,
    ) -> None:
        """
        Parameters
        ----------
        capture:
            If provided, the player notifies it via :meth:`AudioCapture.notify_playing`
            so the echo gate activates automatically during playback.
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self._capture = capture

        self._stream: sd.OutputStream | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=_DTYPE,
        )
        self._stream.start()
        logger.debug("AudioPlayer started (%d Hz)", self.sample_rate)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.debug("AudioPlayer stopped")

    def close(self) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def play(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write, data)

    def _write(self, data: bytes) -> None:
        with self._lock:
            if not self._stream:
                return
            if self._capture:
                self._capture.notify_playing(True)
            try:
                samples = np.frombuffer(data, dtype=np.int16)
                self._stream.write(samples)
            finally:
                if self._capture:
                    self._capture.notify_playing(False)
