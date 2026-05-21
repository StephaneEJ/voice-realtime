"""Microphone capture — sounddevice InputStream → async byte chunks PCM16 mono."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import numpy as np
import sounddevice as sd


class MicrophoneStream:
    """Captures microphone audio as PCM16 mono chunks.

    Usage:
        async with MicrophoneStream(rate=24000) as mic:
            async for chunk in mic:
                # chunk: bytes (PCM16 little-endian)
                ...
    """

    def __init__(self, rate: int = 24000, chunk_ms: int = 200, channels: int = 1) -> None:
        self.rate = rate
        self.chunk_ms = chunk_ms
        self.channels = channels
        self.chunk_frames = int(rate * chunk_ms / 1000)
        # Larger queue (256 * 200ms = ~51s buffer) tolerates pikes. drop-oldest still safety net.
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
        self._stream: sd.InputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed: bool = False

    async def __aenter__(self) -> "MicrophoneStream":
        self._loop = asyncio.get_running_loop()
        self._stream = sd.InputStream(
            samplerate=self.rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.chunk_frames,
            callback=self._sd_callback,
        )
        self._stream.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._closed = True
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

    def _sd_callback(self, indata: "np.ndarray", _frames: int, _time, _status) -> None:
        # Called from PortAudio thread. Push bytes to asyncio queue via loop-safe call.
        if self._closed or self._loop is None:
            return
        pcm16_bytes = indata.tobytes()
        try:
            self._loop.call_soon_threadsafe(self._safe_put, pcm16_bytes)
        except RuntimeError:
            pass

    def _safe_put(self, data: bytes) -> None:
        # Drop oldest chunk if queue is full — keep latest audio to minimize lag.
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while not self._closed:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield chunk
            except asyncio.TimeoutError:
                if self._closed:
                    return
                continue


@asynccontextmanager
async def open_microphone(rate: int = 24000, chunk_ms: int = 100) -> AsyncIterator[MicrophoneStream]:
    async with MicrophoneStream(rate=rate, chunk_ms=chunk_ms) as mic:
        yield mic
