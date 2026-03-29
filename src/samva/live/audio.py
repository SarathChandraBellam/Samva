"""PyAudio-based microphone capture and speaker playback."""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import TYPE_CHECKING

import pyaudio

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FORMAT = pyaudio.paInt16


class AudioCapture:
    """Stream microphone audio as raw 16-bit PCM chunks."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        chunk_size: int = 1024,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

        self._pa = pyaudio.PyAudio()
        self._stream: pyaudio.Stream | None = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._stream = self._pa.open(
            format=_FORMAT,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._callback,
        )
        self._stream.start_stream()
        logger.debug("AudioCapture started (%d Hz)", self.sample_rate)

    def stop(self) -> None:
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        logger.debug("AudioCapture stopped")

    def close(self) -> None:
        self.stop()
        self._pa.terminate()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _callback(
        self,
        in_data: bytes,
        frame_count: int,
        time_info: dict,
        status: int,
    ) -> tuple[None, int]:
        if self._running:
            try:
                self._queue.put_nowait(in_data)
            except queue.Full:
                pass  # drop if consumer is too slow
        return (None, pyaudio.paContinue)

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
    """Play raw 16-bit PCM audio through the default speaker."""

    def __init__(self, sample_rate: int = 24_000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels

        self._pa = pyaudio.PyAudio()
        self._stream: pyaudio.Stream | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stream = self._pa.open(
            format=_FORMAT,
            channels=self.channels,
            rate=self.sample_rate,
            output=True,
        )
        logger.debug("AudioPlayer started (%d Hz)", self.sample_rate)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        logger.debug("AudioPlayer stopped")

    def close(self) -> None:
        self.stop()
        self._pa.terminate()

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def play(self, data: bytes) -> None:
        """Write PCM bytes to the output stream (non-blocking from caller)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write, data)

    def _write(self, data: bytes) -> None:
        with self._lock:
            if self._stream:
                self._stream.write(data)
