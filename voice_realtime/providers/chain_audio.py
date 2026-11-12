"""Outils audio du mode chaîne : WAV en mémoire, niveau RMS, détection de parole.

Aucune dépendance native : `wave`, `array` et `math` de la bibliothèque
standard suffisent. Le détecteur de parole (`Endpointer`) découpe le flux
micro en énoncés ; il remplace la VAD serveur des fournisseurs temps réel.
"""

from __future__ import annotations

import array
import io
import math
import wave
from dataclasses import dataclass, field
from typing import Literal

SAMPLE_WIDTH = 2  # PCM16


def pcm16_to_wav(pcm16: bytes, sample_rate: int) -> bytes:
    """Encapsule du PCM16 mono dans un conteneur WAV en mémoire."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)
    return buf.getvalue()


def wav_to_pcm16(data: bytes) -> tuple[bytes, int]:
    """Lit un WAV PCM16 mono ; renvoie (pcm16, fréquence)."""
    with wave.open(io.BytesIO(data), "rb") as w:
        if w.getsampwidth() != SAMPLE_WIDTH or w.getnchannels() != 1:
            raise ValueError(
                f"WAV attendu PCM16 mono, reçu {w.getnchannels()} canal(aux), "
                f"{w.getsampwidth() * 8} bits"
            )
        return w.readframes(w.getnframes()), w.getframerate()


def rms(pcm16: bytes) -> float:
    """Niveau RMS normalisé (0..1) d'un bloc PCM16."""
    n = len(pcm16) // SAMPLE_WIDTH
    if n == 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm16[: n * SAMPLE_WIDTH])
    acc = 0
    for s in samples:
        acc += s * s
    return math.sqrt(acc / n) / 32768.0


def resample_pcm16(pcm16: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Rééchantillonnage linéaire, suffisant pour la voix (24 kHz ↔ 16 kHz)."""
    if src_rate == dst_rate or not pcm16:
        return pcm16
    src = array.array("h")
    src.frombytes(pcm16[: (len(pcm16) // SAMPLE_WIDTH) * SAMPLE_WIDTH])
    n_out = int(len(src) * dst_rate / src_rate)
    out = array.array("h", bytes(n_out * SAMPLE_WIDTH))
    ratio = src_rate / dst_rate
    last = len(src) - 1
    for i in range(n_out):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        a = src[j]
        b = src[j + 1] if j < last else a
        out[i] = int(a + (b - a) * frac)
    return out.tobytes()


# Silence de fin d'énoncé par préréglage, aligné sur `ProviderConfig.vad`.
SILENCE_MS_BY_VAD = {
    "reactive": 450,
    "balanced": 700,
    "patient": 1000,
    "very-patient": 1400,
}


@dataclass(frozen=True)
class EndpointEvent:
    kind: Literal["speech_start", "utterance"]
    pcm16: bytes = b""
    start_ms: int = 0
    end_ms: int = 0


@dataclass
class Endpointer:
    """Détecteur de parole par énergie, à seuil adaptatif.

    - trames de `frame_ms` ; une trame est « voisée » si son RMS dépasse
      `max(min_rms, plancher_de_bruit * noise_factor)` ;
    - début d'énoncé après `min_speech_ms` de trames voisées consécutives
      (événement `speech_start`, sert à la coupure de parole) ;
    - fin d'énoncé après `silence_ms` sans trame voisée (événement
      `utterance` avec l'audio, préroulage compris) ;
    - un énoncé plus long que `max_utterance_ms` est coupé de force.

    Le plancher de bruit suit une moyenne glissante des trames non voisées,
    pour tenir dans la rue comme au bureau.
    """

    sample_rate: int = 16000
    frame_ms: int = 20
    min_rms: float = 0.012
    noise_factor: float = 3.0
    min_speech_ms: int = 200
    silence_ms: int = 700
    preroll_ms: int = 300
    max_utterance_ms: int = 30_000
    noise_floor: float = 0.003
    _pending: bytearray = field(default_factory=bytearray)
    _preroll: list[bytes] = field(default_factory=list)
    _utterance: bytearray = field(default_factory=bytearray)
    _in_speech: bool = False
    _voiced_run: int = 0
    _silence_run: int = 0
    _candidate: list[bytes] = field(default_factory=list)
    _t_ms: int = 0
    _start_ms: int = 0

    @classmethod
    def for_vad(cls, vad: str | None, sample_rate: int = 16000) -> "Endpointer":
        return cls(sample_rate=sample_rate, silence_ms=SILENCE_MS_BY_VAD.get(vad or "balanced", 700))

    @property
    def frame_bytes(self) -> int:
        return int(self.sample_rate * self.frame_ms / 1000) * SAMPLE_WIDTH

    @property
    def threshold(self) -> float:
        return max(self.min_rms, self.noise_floor * self.noise_factor)

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def feed(self, pcm16: bytes) -> list[EndpointEvent]:
        """Ajoute un bloc micro ; renvoie les événements produits."""
        self._pending.extend(pcm16)
        events: list[EndpointEvent] = []
        fb = self.frame_bytes
        while len(self._pending) >= fb:
            frame = bytes(self._pending[:fb])
            del self._pending[:fb]
            ev = self._feed_frame(frame)
            if ev is not None:
                events.append(ev)
        return events

    def flush(self) -> list[EndpointEvent]:
        """Termine l'énoncé en cours (fin de flux)."""
        if self._in_speech and self._utterance:
            return [self._close_utterance()]
        return []

    def _feed_frame(self, frame: bytes) -> EndpointEvent | None:
        level = rms(frame)
        voiced = level > self.threshold
        self._t_ms += self.frame_ms
        min_speech_frames = max(1, self.min_speech_ms // self.frame_ms)
        silence_frames = max(1, self.silence_ms // self.frame_ms)
        preroll_frames = max(0, self.preroll_ms // self.frame_ms)

        if not self._in_speech:
            if voiced:
                self._voiced_run += 1
                self._candidate.append(frame)
                if self._voiced_run >= min_speech_frames:
                    self._in_speech = True
                    self._silence_run = 0
                    head = self._preroll + self._candidate
                    self._start_ms = self._t_ms - len(head) * self.frame_ms
                    self._utterance = bytearray(b"".join(head))
                    self._preroll = []
                    self._candidate = []
                    self._voiced_run = 0
                    return EndpointEvent(kind="speech_start", start_ms=self._start_ms)
                return None
            # Trame non voisée : le candidat retombe dans le préroulage.
            for f in self._candidate:
                self._push_preroll(f, preroll_frames)
            self._candidate = []
            self._voiced_run = 0
            self._push_preroll(frame, preroll_frames)
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * level
            return None

        self._utterance.extend(frame)
        if voiced:
            self._silence_run = 0
        else:
            self._silence_run += 1
        too_long = len(self._utterance) >= self.max_utterance_ms * self.sample_rate // 1000 * SAMPLE_WIDTH
        if self._silence_run >= silence_frames or too_long:
            return self._close_utterance()
        return None

    def _push_preroll(self, frame: bytes, preroll_frames: int) -> None:
        if preroll_frames == 0:
            return
        self._preroll.append(frame)
        if len(self._preroll) > preroll_frames:
            del self._preroll[0]

    def _close_utterance(self) -> EndpointEvent:
        ev = EndpointEvent(
            kind="utterance",
            pcm16=bytes(self._utterance),
            start_ms=self._start_ms,
            end_ms=self._t_ms,
        )
        self._utterance = bytearray()
        self._in_speech = False
        self._silence_run = 0
        return ev
