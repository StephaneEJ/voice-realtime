"""Audio playback — sounddevice OutputStream fed from asyncio queue of PCM16 bytes."""

from __future__ import annotations

import asyncio
import threading

import numpy as np
import sounddevice as sd


class AudioPlayer:
    """Async audio player. Feed PCM16 chunks via `enqueue()`, played by background OutputStream.

    Usage:
        player = AudioPlayer(rate=24000)
        player.start()
        await player.enqueue(pcm16_bytes)
        ...
        player.stop()
    """

    def __init__(self, rate: int = 24000, channels: int = 1) -> None:
        self.rate = rate
        self.channels = channels
        self._buffer: bytearray = bytearray()
        self._lock = threading.Lock()
        self._stream: sd.OutputStream | None = None
        self._started: bool = False

    def start(self) -> None:
        if self._started:
            return
        self._stream = sd.OutputStream(
            samplerate=self.rate,
            channels=self.channels,
            dtype="int16",
            callback=self._sd_callback,
        )
        self._stream.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

    def _sd_callback(self, outdata: "np.ndarray", frames: int, _time, _status) -> None:
        needed_bytes = frames * 2 * self.channels  # int16 = 2 bytes
        with self._lock:
            available = len(self._buffer)
            if available >= needed_bytes:
                chunk = bytes(self._buffer[:needed_bytes])
                del self._buffer[:needed_bytes]
                outdata[:] = np.frombuffer(chunk, dtype=np.int16).reshape(frames, self.channels)
            elif available > 0:
                chunk = bytes(self._buffer)
                self._buffer.clear()
                pad = needed_bytes - available
                padded = chunk + b"\x00" * pad
                outdata[:] = np.frombuffer(padded, dtype=np.int16).reshape(frames, self.channels)
            else:
                outdata.fill(0)

    async def enqueue(self, pcm16_bytes: bytes) -> None:
        # No await needed — lock is thread-safe, PortAudio drains in its own thread.
        # Removed `await asyncio.sleep(0)` (caused 50+ context switches/sec under load).
        with self._lock:
            self._buffer.extend(pcm16_bytes)

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait until buffer is empty or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            with self._lock:
                if not self._buffer:
                    return
            await asyncio.sleep(0.05)
