#!/usr/bin/env python3
"""Génère les enregistrements de test du mode chaîne (macOS : `say`).

Chaque fichier est un WAV PCM16 mono 16 kHz : un bruit de fond reproductible
(graine fixe), puis des phrases dites par la voix française « Thomas »
séparées de silences connus. Les bornes attendues sont écrites dans
`tests/fixtures/chain/enregistrements.json`.

    python3 scripts/generer_enregistrements_chaine.py

`jfk.wav` (discours de J. F. Kennedy, 1961, domaine public) est copié depuis
whisper.cpp pour disposer d'une vraie voix humaine enregistrée.
"""

from __future__ import annotations

import array
import json
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 16000
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "chain"
VOICE = "Thomas"
NOISE_RMS = 0.004  # ≈ -48 dBFS, une pièce calme
JFK_SRC = Path("/opt/homebrew/share/whisper.cpp/jfk.wav")

SCENES = {
    "deux_phrases": [
        ("silence", 600),
        ("phrase", "Liste mes sessions en cours."),
        ("silence", 1200),
        ("phrase", "Quel est le dernier retour de la session cockpit ?"),
        ("silence", 1000),
    ],
    "coupure": [
        ("silence", 400),
        ("phrase", "Attends, arrête-toi."),
        ("silence", 900),
    ],
    "killchat": [
        ("silence", 400),
        ("phrase", "Killchat."),
        ("silence", 900),
    ],
}


def say_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p.wav"
        subprocess.run(
            ["say", "-v", VOICE, "--file-format=WAVE", f"--data-format=LEI16@{RATE}", "-o", str(path), text],
            check=True,
        )
        with wave.open(str(path), "rb") as w:
            assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
            return w.readframes(w.getnframes())


def trim(pcm: bytes, level: int = 300) -> bytes:
    """Retire le silence numérique que `say` laisse autour de la phrase."""
    s = array.array("h")
    s.frombytes(pcm)
    idx = [i for i, v in enumerate(s) if abs(v) > level]
    if not idx:
        return pcm
    return s[idx[0] : idx[-1] + 1].tobytes()


def mix_noise(pcm: bytes, rng: random.Random) -> bytes:
    s = array.array("h")
    s.frombytes(pcm)
    amp = NOISE_RMS * 32768
    for i, v in enumerate(s):
        s[i] = max(-32768, min(32767, v + int(rng.gauss(0.0, amp))))
    return s.tobytes()


def main() -> int:
    if shutil.which("say") is None:
        print("say introuvable : macOS requis", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for name, scene in SCENES.items():
        rng = random.Random(12)
        pcm = bytearray()
        segments = []
        for kind, value in scene:
            if kind == "silence":
                pcm.extend(bytes(int(RATE * value / 1000) * 2))
            else:
                start_ms = len(pcm) * 1000 // (2 * RATE)
                pcm.extend(trim(say_pcm(value)))
                end_ms = len(pcm) * 1000 // (2 * RATE)
                segments.append({"texte": value, "debut_ms": start_ms, "fin_ms": end_ms})
        data = mix_noise(bytes(pcm), rng)
        with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(data)
        manifest[f"{name}.wav"] = {
            "source": f"say -v {VOICE}, bruit gaussien {NOISE_RMS} RMS graine 12",
            "duree_ms": len(data) * 1000 // (2 * RATE),
            "segments": segments,
        }
    if JFK_SRC.is_file():
        shutil.copyfile(JFK_SRC, OUT / "jfk.wav")
        manifest["jfk.wav"] = {
            "source": "whisper.cpp samples/jfk.wav — discours inaugural de J. F. Kennedy (1961), domaine public",
            "duree_ms": 11000,
            "segments": [{"texte": "And so my fellow Americans, ask not what your country can do for you, "
                                   "ask what you can do for your country.", "debut_ms": None, "fin_ms": None}],
        }
    (OUT / "enregistrements.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
