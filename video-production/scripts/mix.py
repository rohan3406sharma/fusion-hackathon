"""Final audio mix: narration + ducked original score + cued sound effects, loudness-normalised.

Inputs : assets/voice/narration.wav, assets/music/score.wav, assets/sfx/*.wav, assets/timeline.json (lines + sfx cues)
Output : assets/audio/mix.wav (48 kHz stereo, -16 LUFS integrated, true peak <= -1.5 dBTP)
         assets/audio/stems/{voice,music,sfx}.wav for review
Ducking: the bed sits ~17 dB under the voice while it speaks and opens to ~9 dB under between lines.
Run: .venv-tts/bin/python scripts/mix.py
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
DUCK_DB = -8.5          # extra attenuation of the bed while the voice speaks
MUSIC_DB = -15.5        # bed level relative to the stem (open, between lines)
VOICE_DB = 0.0
LIFT_DB = 3.5          # extra level for the score in pauses (x1.6 in the outro)


def db(x: float) -> float:
    return 10 ** (x / 20)


def load(path: Path, stereo: bool = True) -> np.ndarray:
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    if sr != SR:
        raise SystemExit(f"{path} is {sr} Hz; expected {SR}")
    if stereo and x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return x


def smooth_gate(active: np.ndarray, rate: int, attack: float, release: float) -> np.ndarray:
    """one-pole smoothing with separate attack (going active) and release (going idle) times"""
    out = np.zeros_like(active, dtype=np.float64)
    a_up, a_dn = np.exp(-1 / (attack * rate)), np.exp(-1 / (release * rate))
    y = 0.0
    for i, v in enumerate(active):
        a = a_up if v > y else a_dn
        y = a * y + (1 - a) * v
        out[i] = y
    return out


def loudnorm(src: Path, dst: Path, target: float = -16.0, tp: float = -1.5) -> dict:
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe, re.S).group(0))
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-ar", str(SR), "-c:a", "pcm_s24le", str(dst)], check=True)
    return m


def main() -> None:
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    n = int(np.ceil(tl["total"] * SR))
    voice = load(ROOT / "assets" / "voice" / "narration.wav")[:n]
    voice = np.pad(voice, ((0, n - len(voice)), (0, 0))) * db(VOICE_DB)
    music = load(ROOT / "assets" / "music" / "score.wav")[:n]
    music = np.pad(music, ((0, n - len(music)), (0, 0)))

    # ducking envelope at 1 kHz control rate from the exact line windows
    rate = 1000
    active = np.zeros(int(np.ceil(tl["total"] * rate)) + 1)
    for sc in tl["scenes"]:
        for ln in sc["lines"]:
            active[int((ln["start"] - 0.12) * rate): int((ln["end"] + 0.22) * rate)] = 1.0
    env = smooth_gate(active, rate, attack=0.09, release=0.55)
    # let the score breathe: lift it in the intro, in pauses of a second or more, and in the outro
    lines = sorted((ln["start"], ln["end"]) for sc in tl["scenes"] for ln in sc["lines"])
    lift = np.zeros_like(active)
    lift[: int(1.45 * rate)] = 1.0
    for (s0, e0), (s1, _) in zip(lines, lines[1:]):
        if s1 - e0 >= 1.0:
            lift[int((e0 + 0.25) * rate): int((s1 - 0.2) * rate)] = 1.0
    lift[int((lines[-1][1] + 0.2) * rate):] = 1.6
    lift = smooth_gate(lift, rate, attack=0.45, release=0.35)
    gain_db = MUSIC_DB + DUCK_DB * env + LIFT_DB * lift
    t_ctl = np.arange(len(gain_db)) / rate
    gain = db(np.interp(np.arange(n) / SR, t_ctl, gain_db))[:, None]
    music_ducked = music * gain

    sfx = np.zeros((n, 2), dtype=np.float32)
    cache: dict[str, np.ndarray] = {}
    for cue in tl["sfx"]:
        x = cache.setdefault(cue["file"], load(ROOT / "assets" / "sfx" / cue["file"]))
        i = int(round(cue["t"] * SR))
        j = min(n, i + len(x))
        if i < n:
            sfx[i:j] += x[: j - i] * db(cue["db"])

    mix = voice + music_ducked + sfx
    stems = ROOT / "assets" / "audio" / "stems"
    stems.mkdir(parents=True, exist_ok=True)
    for name, x in [("voice", voice), ("music", music_ducked), ("sfx", sfx)]:
        sf.write(stems / f"{name}.wav", x, SR, subtype="PCM_24")
    pre = ROOT / "assets" / "audio" / "mix_pre.wav"
    sf.write(pre, mix, SR, subtype="FLOAT")
    m = loudnorm(pre, ROOT / "assets" / "audio" / "mix.wav")
    pre.unlink()
    print(f"mix.wav written ({tl['total']:.2f}s); pre-normalisation I={m['input_i']} LUFS TP={m['input_tp']} dBTP; sfx cues={len(tl['sfx'])}")


if __name__ == "__main__":
    main()
