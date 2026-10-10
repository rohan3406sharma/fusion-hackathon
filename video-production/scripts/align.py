"""Word-level timings for the voiceover, one line at a time.

whisper.cpp snaps long-file segment starts to whole seconds, so each line clip is transcribed on its
own with DTW token timestamps (--dtw) and offset by the line's exact start from assets/timeline.json.
Writes assets/voice/words.json ([{text, start, end, line}]), then re-run build_timeline.py to attach
the words to the timeline.

Needs: ffmpeg, whisper-cli (whisper-cpp) and the ggml small.en model that `npx hyperframes transcribe`
downloads to ~/.cache/hyperframes/whisper/models/.
Run:   .venv-tts/bin/python scripts/align.py
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path(os.path.expanduser("~/.cache/hyperframes/whisper/models/ggml-small.en.bin"))


def transcribe(wav: Path, work: Path) -> list[dict]:
    pcm16 = work / (wav.stem + ".16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ar", "16000", "-ac", "1", str(pcm16)], check=True)
    base = work / wav.stem
    subprocess.run(["whisper-cli", "-m", str(MODEL), "-f", str(pcm16), "-l", "en", "--dtw", "small.en",
                    "-ojf", "-of", str(base), "-np"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = json.loads((work / (wav.stem + ".json")).read_text())
    words: list[dict] = []
    for seg in data.get("transcription", []):
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if not text or text.startswith("[_") or text.startswith("<|"):
                continue
            t = tok.get("t_dtw", -1)
            t = t / 100.0 if t is not None and t >= 0 else tok["offsets"]["from"] / 1000.0
            end = tok["offsets"]["to"] / 1000.0
            if text.startswith(" ") or not words:
                words.append({"text": text.strip(), "start": t, "end": max(end, t)})
            else:  # continuation of the previous word (sub-word token or punctuation)
                words[-1]["text"] += text
                words[-1]["end"] = max(words[-1]["end"], end)
    return [w for w in words if w["text"]]


def main() -> None:
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for sc in tl["scenes"]:
            for ln in sc["lines"]:
                ws = transcribe(ROOT / "assets" / "voice" / f"{ln['id']}.wav", work)
                for w in ws:
                    out.append({"text": w["text"], "start": round(ln["start"] + w["start"], 3),
                                "end": round(ln["start"] + w["end"], 3), "line": ln["id"]})
                print(ln["id"], " ".join(w["text"] for w in ws)[:90])
    (ROOT / "assets" / "voice" / "words.json").write_text(json.dumps(out, indent=0))
    print("words:", len(out))


if __name__ == "__main__":
    main()
