"""Synthesise the voiceover line by line with Kokoro-82M (the local model `npx hyperframes tts` uses).

Reads scripts/narration.json, writes assets/voice/<line>.wav (24 kHz mono) and
assets/voice/manifest.json with each line's measured duration.

Run with the isolated TTS venv (Python 3.10-3.13):
    .venv-tts/bin/python scripts/tts.py            # all lines
    .venv-tts/bin/python scripts/tts.py L07 L25    # only these lines

Model files are the ones the HyperFrames CLI downloads to ~/.cache/hyperframes/tts/
(run `npx hyperframes tts "test"` once, or download kokoro-v1.0.onnx + voices-v1.0.bin there).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NARRATION = ROOT / "scripts" / "narration.json"
OUT = ROOT / "assets" / "voice"
CACHE = Path(os.path.expanduser("~/.cache/hyperframes/tts"))


def espeak_data_path() -> str:
    """espeak-ng (bundled by espeakng-loader) only finds its data via ESPEAK_DATA_PATH, and the path
    must not contain spaces. This project lives under a path with a space, so link the data dir
    into the system temp dir and point espeak there."""
    import espeakng_loader

    src = Path(espeakng_loader.get_data_path())
    link = Path(tempfile.gettempdir()) / "fin04-espeak-ng-data"
    if " " in str(link):
        raise SystemExit(f"temp dir contains a space: {link}")
    if link.is_symlink() or link.exists():
        if link.resolve() != src.resolve():
            link.unlink()
    if not link.exists():
        link.symlink_to(src, target_is_directory=True)
    return str(link)


def main(only: set[str]) -> None:
    os.environ["ESPEAK_DATA_PATH"] = espeak_data_path()
    import kokoro_onnx
    import numpy as np
    import soundfile as sf
    from kokoro_onnx.config import EspeakConfig

    spec = json.loads(NARRATION.read_text())
    model = kokoro_onnx.Kokoro(
        str(CACHE / "models" / "kokoro-v1.0.onnx"),
        str(CACHE / "voices" / "voices-v1.0.bin"),
        espeak_config=EspeakConfig(data_path=os.environ["ESPEAK_DATA_PATH"]),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for scene in spec["scenes"]:
        for line in scene["lines"]:
            lid = line["id"]
            if only and lid not in only:
                continue
            samples, sr = model.create(line["say"], voice=spec["voice"], speed=spec["speed"], lang=spec["lang"])
            samples = np.asarray(samples, dtype=np.float32)
            # trim leading/trailing near-silence so gaps in narration.json are the real pauses
            thresh = 0.01 * float(np.max(np.abs(samples)) or 1.0)
            loud = np.nonzero(np.abs(samples) > thresh)[0]
            if loud.size:
                pad = int(0.04 * sr)
                samples = samples[max(0, loud[0] - pad): min(len(samples), loud[-1] + pad)]
            path = OUT / f"{lid}.wav"
            sf.write(path, samples, sr)
            manifest[lid] = {"file": f"assets/voice/{lid}.wav", "duration": round(len(samples) / sr, 3),
                             "sample_rate": sr, "say": line["say"]}
            print(f"{lid}  {manifest[lid]['duration']:6.2f}s  {line['say'][:70]}")
    manifest_path.write_text(json.dumps(manifest, indent=1))
    total = sum(v["duration"] for v in manifest.values())
    print(f"lines: {len(manifest)}  speech: {total:.1f}s")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
