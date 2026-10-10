"""Validate the rendered MP4 itself (not the preview): streams, duration, resolution, fps, black and frozen
frames, silences, loudness, A/V alignment of the narration, and a contact sheet of representative frames.
Run: .venv-tts/bin/python scripts/validate.py [renders/fin04-explainer.mp4]
Writes renders/review/ (frames + contact sheet) and prints a JSON summary.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout + r.stderr


def main() -> None:
    mp4 = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "renders/fin04-explainer.mp4")
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    rep: dict = {"file": str(mp4.relative_to(ROOT)), "size_mb": round(mp4.stat().st_size / 1e6, 1)}

    probe = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(mp4)]))
    for s in probe["streams"]:
        if s["codec_type"] == "video":
            rep["video"] = {"codec": s["codec_name"], "profile": s.get("profile"), "w": s["width"], "h": s["height"], "fps": s["r_frame_rate"],
                            "pix_fmt": s["pix_fmt"], "frames": int(s.get("nb_frames", 0)), "duration": float(s.get("duration", 0))}
        if s["codec_type"] == "audio":
            rep["audio"] = {"codec": s["codec_name"], "sample_rate": int(s["sample_rate"]), "channels": s["channels"], "duration": float(s.get("duration", 0)),
                            "bit_rate_kbps": round(int(s.get("bit_rate", 0)) / 1000)}
    rep["container_duration"] = float(probe["format"]["duration"])
    rep["expected_duration"] = tl["total"]

    bd = run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-vf", "blackdetect=d=0.25:pix_th=0.06", "-an", "-f", "null", "-"])
    rep["black_segments"] = [{"start": float(a), "end": float(b)} for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)]
    fz = run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-vf", "freezedetect=n=0.0005:d=6", "-an", "-f", "null", "-"])
    rep["frozen_over_6s"] = re.findall(r"freeze_start: ([\d.]+)", fz)
    sd = run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-af", "silencedetect=n=-50dB:d=1.5", "-vn", "-f", "null", "-"])
    rep["silences_over_1_5s"] = [{"start": float(a), "end": float(b)} for a, b in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", sd)]
    ln = run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-af", "loudnorm=print_format=json", "-vn", "-f", "null", "-"])
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", ln, re.S).group(0))
    rep["loudness"] = {"integrated_lufs": float(m["input_i"]), "true_peak_dbtp": float(m["input_tp"]), "lra": float(m["input_lra"])}

    # narration alignment: cross-correlate the MP4's audio with the voice stem around three lines
    tmp = ROOT / "renders" / "review"
    tmp.mkdir(parents=True, exist_ok=True)
    wav = tmp / "_audio.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    a, sr = sf.read(wav, dtype="float32")
    v, vsr = sf.read(ROOT / "assets" / "voice" / "narration.wav", dtype="float32")
    v = np.interp(np.arange(int(len(v) * sr / vsr)) * vsr / sr, np.arange(len(v)), v)
    offs = []
    for lid in ["L01", "L24", "L46"]:
        line = next(l for s in tl["scenes"] for l in s["lines"] if l["id"] == lid)
        i0, i1 = int((line["start"] - 0.5) * sr), int((line["start"] + 2.5) * sr)
        ref, seg = v[i0:i1], a[i0 - int(0.5 * sr): i1 + int(0.5 * sr)]
        c = np.correlate(seg - seg.mean(), ref - ref.mean(), mode="valid")
        offs.append(round((int(np.argmax(c)) - int(0.5 * sr)) / sr * 1000, 1))
    rep["narration_offset_ms"] = dict(zip(["L01", "L24", "L46"], offs))
    wav.unlink()

    # representative frames: beginning, problem, idea, demo (x4), engine, impact, payoff, end card
    times = [3.0, 8.5, 16.8, 31.5, 55.0, 70.5, 86.0, 96.5, 108.0, 117.5, 136.4, 148.9, 162.2, 170.9, 176.6, 183.0, 189.8, 205.4, 217.6, 231.5, 244.8, 251.0, 260.5, 278.6, 282.0, 288.8]
    frames = []
    for t in times:
        f = tmp / f"t{t:06.1f}.png"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(mp4), "-frames:v", "1", str(f)])
        frames.append(f)
    sheet = tmp / "contact-sheet.png"
    inputs = []
    for f in frames:
        inputs += ["-i", str(f)]
    cols, n = 4, len(frames)
    rows = (n + cols - 1) // cols
    layout = "|".join(f"{(k % cols) * 480}_{(k // cols) * 270}" for k in range(n))
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
         "".join(f"[{k}:v]scale=480:270[s{k}];" for k in range(n)) + "".join(f"[s{k}]" for k in range(n)) + f"xstack=inputs={n}:layout={layout}:fill=black",
         str(sheet)])
    rep["review_frames"] = [str(f.relative_to(ROOT)) for f in frames]
    rep["contact_sheet"] = str(sheet.relative_to(ROOT))
    print(json.dumps(rep, indent=1))
    (tmp / "validation.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
