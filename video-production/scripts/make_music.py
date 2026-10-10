"""Original, procedurally synthesised score for the explainer (no samples, no third-party audio).

The arrangement follows assets/timeline.json so the harmony changes with the story:
  hook      D-minor drone + shimmer + slow pulse, swelling into the question, then a drop
  problem   Dm - Bb - Gm - A with sparse plucked notes
  idea      lift at the product reveal: Fmaj7 - C - Dm7 - Bbmaj7, soft arpeggio enters
  demo      steady light pulse: Dm9 - Bbmaj7 - Fmaj7 - C
  engine    brighter arpeggio: Gm9 - Bbmaj7 - Dm - C
  impact    warm build: Bb - F - C - Dm
  payoff    the hook drone returns, then resolves to D major on the title, long tail
Deterministic (seeded). Output: assets/music/score.wav (48 kHz stereo, peak-normalised stem).
Run: .venv-tts/bin/python scripts/make_music.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
rng = np.random.default_rng(20261009)

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}
NOTE.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})


def hz(name: str) -> float:
    """'D3' -> frequency (A4 = 440)."""
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + NOTE[pitch]
    return 440.0 * 2 ** ((midi - 69) / 12)


def smooth_env(n: int, attack: int, release: int) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    if attack > 0:
        a = min(attack, n)
        env[:a] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    if release > 0:
        r = min(release, n)
        env[n - r:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return env


class Track:
    def __init__(self, seconds: float):
        self.n = int(seconds * SR) + SR * 6
        self.buf = np.zeros((self.n, 2), dtype=np.float32)

    def add(self, start: float, mono_or_stereo: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
        i = int(start * SR)
        if i >= self.n:
            return
        x = mono_or_stereo
        if x.ndim == 1:
            left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            x = np.stack([x * left, x * right], axis=1)
        j = min(self.n, i + len(x))
        self.buf[i:j] += gain * x[: j - i]


def pad(freqs: list[float], dur: float, attack: float = 1.6, release: float = 2.2, bright: float = 1.0) -> np.ndarray:
    """Warm detuned additive pad (stereo)."""
    n = int((dur + release) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2), dtype=np.float32)
    for f in freqs:
        for v, (cents, pan) in enumerate([(-7, -0.6), (0, 0.0), (6, 0.6)]):
            fv = f * 2 ** (cents / 1200)
            wave = np.zeros(n, dtype=np.float32)
            for k in range(1, 9):
                if fv * k > 9000:
                    break
                amp = (1.0 / k ** (1.55 - 0.25 * bright))
                wave += amp * np.sin(2 * np.pi * fv * k * t + rng.uniform(0, 2 * np.pi)).astype(np.float32)
            # slow chorus-like amplitude drift per voice
            wave *= (1 + 0.12 * np.sin(2 * np.pi * (0.07 + 0.03 * v) * t + rng.uniform(0, 6))).astype(np.float32)
            left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            out[:, 0] += wave * left
            out[:, 1] += wave * right
    out *= smooth_env(n, int(attack * SR), int(release * SR))[:, None]
    return out / (len(freqs) * 3)


def pluck(f: float, dur: float = 2.2, decay: float = 0.55, bright: float = 1.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * t) + 0.32 * bright * np.sin(2 * np.pi * 2 * f * t + 0.3)
         + 0.11 * bright * np.sin(2 * np.pi * 3 * f * t + 1.1) + 0.05 * np.sin(2 * np.pi * 4.01 * f * t))
    env = np.exp(-t / decay) * (1 - np.exp(-t / 0.004))
    x = (x * env).astype(np.float32)
    x *= smooth_env(n, 0, int(0.08 * SR))
    return x


def drone(f: float, dur: float, attack: float = 3.0, release: float = 3.0) -> np.ndarray:
    n = int((dur + release) * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t + 0.7) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    x *= 1 + 0.18 * np.sin(2 * np.pi * 0.11 * t)
    return (x * smooth_env(n, int(attack * SR), int(release * SR))).astype(np.float32)


def shimmer(dur: float, base: str = "D6") -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2), dtype=np.float32)
    for i, name in enumerate([base, "A6", "E6", "F6"]):
        f = hz(name)
        am = 0.5 + 0.5 * np.sin(2 * np.pi * (0.13 + 0.05 * i) * t + rng.uniform(0, 6))
        x = (np.sin(2 * np.pi * f * t) * am ** 2).astype(np.float32)
        pan = [-0.7, 0.6, -0.3, 0.8][i]
        out[:, 0] += x * np.cos((pan + 1) * np.pi / 4)
        out[:, 1] += x * np.sin((pan + 1) * np.pi / 4)
    return out * smooth_env(n, int(2.5 * SR), int(2.5 * SR))[:, None] / 4


def thump() -> np.ndarray:
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    f = 42 + 38 * np.exp(-t / 0.06)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(phase) * np.exp(-t / 0.16) * (1 - np.exp(-t / 0.003))).astype(np.float32)


def chord(names: str, octave_shift: int = 0) -> list[float]:
    out = []
    for nm in names.split():
        p, o = nm[:-1], int(nm[-1]) + octave_shift
        out.append(hz(f"{p}{o}"))
    return out


def reverb(x: np.ndarray, seconds: float = 3.4, wet: float = 0.32) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2), dtype=np.float32)
    for ch in range(2):
        noise = rng.standard_normal(n).astype(np.float32)
        noise = signal.lfilter(*signal.butter(2, 5200 / (SR / 2)), noise).astype(np.float32)   # darker tail
        ir[:, ch] = noise * np.exp(-t * 6.9 / seconds)
    pre = int(0.022 * SR)
    ir = np.concatenate([np.zeros((pre, 2), dtype=np.float32), ir])
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    wet_sig = np.stack([signal.oaconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1)
    return (1 - wet) * x + wet * wet_sig.astype(np.float32)


def main() -> None:
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    S = {s["id"]: s for s in tl["scenes"]}
    L = {ln["id"]: ln for s in tl["scenes"] for ln in s["lines"]}
    total = tl["total"]
    pads = Track(total)      # sustained harmony
    keys = Track(total)      # plucks / arpeggios
    low = Track(total)       # drones / pulses
    air = Track(total)       # shimmer

    # ---------- hook: tension ----------
    hook_end = S["s01-hook"]["end"]
    low.add(0.0, drone(hz("D2"), hook_end - 0.8, attack=1.2, release=0.9), 0.34)
    low.add(0.0, drone(hz("A2"), hook_end - 0.8, attack=2.5, release=0.9), 0.16)
    air.add(0.2, shimmer(hook_end - 0.4), 0.55)
    pads.add(0.6, pad(chord("D3 F3 A3 E4"), hook_end - 2.0, attack=4.0, release=1.2, bright=0.6), 0.55)
    for k in range(int((hook_end - 3.2) / 1.5)):          # slow pulse like a held breath
        low.add(3.0 + k * 1.5, thump(), 0.55 + 0.03 * k)
    q = L["L04"]
    pads.add(q["start"] - 1.5, pad(chord("Bb2 D3 F3 A3 E4"), q["end"] - q["start"] + 1.2, attack=2.2, release=0.6, bright=1.1), 0.5)

    # ---------- problem: Dm - Bb - Gm - A ----------
    p0, p1 = S["s02-canal"]["start"] + 0.25, S["s03-evidence"]["end"]
    prog = ["D3 F3 A3 C4", "Bb2 D3 F3 A3", "G2 Bb2 D3 F3", "A2 C#3 E3 G3"]
    seg = (p1 - p0) / 8
    for i in range(8):
        pads.add(p0 + i * seg, pad(chord(prog[i % 4]), seg + 0.4, attack=1.4, release=1.8), 0.62)
        low.add(p0 + i * seg, drone(chord(prog[i % 4])[0] / 2, seg, attack=1.0, release=1.4), 0.15)
    melody = ["A4", "F4", "D5", "C5", "Bb4", "F4", "D5", "A4", "G4", "Bb4", "D5", "F4", "E4", "A4", "C#5", "E5"]
    for i, nm in enumerate(melody * 2):
        tt = p0 + 0.8 + i * (seg / 4)
        if tt < p1 - 1.0:
            keys.add(tt, pluck(hz(nm), decay=0.7), 0.16, pan=-0.3 + 0.6 * ((i * 7) % 5) / 4)

    # ---------- idea: lift ----------
    i0, i1 = S["s04-idea"]["start"], S["s04-idea"]["end"]
    prog = ["F2 A2 C3 E3 A3", "C3 E3 G3 D4", "D3 F3 A3 C4 E4", "Bb2 D3 F3 A3 C4"]
    seg = (i1 - i0) / 8
    for i in range(8):
        pads.add(i0 + i * seg, pad(chord(prog[i % 4]), seg + 0.4, attack=1.2, release=1.8, bright=1.15), 0.62)
        low.add(i0 + i * seg, drone(chord(prog[i % 4])[0] / 2, seg, attack=0.8, release=1.4), 0.17)
    beat = 60 / 84
    arp_start = L["L13"]["start"]
    k = 0
    while arp_start + k * beat / 2 < i1 - 0.5:
        tt = arp_start + k * beat / 2
        ci = min(7, int((tt - i0) / seg))
        notes = chord(prog[ci % 4], 1)
        keys.add(tt, pluck(notes[[0, 2, 1, 3, 2, 4 % len(notes)][k % 6] % len(notes)], decay=0.35), 0.075 + 0.02 * min(1, k / 16), pan=-0.4 + 0.8 * (k % 4) / 3)
        k += 1

    # ---------- demo: steady light pulse ----------
    d0, d1 = S["s05-search"]["start"], S["s08-optimise"]["end"]
    prog = ["D3 F3 A3 C4 E4", "Bb2 D3 F3 A3 C4", "F2 A2 C3 E3 G3", "C3 E3 G3 D4"]
    seg = (d1 - d0) / 16
    for i in range(16):
        pads.add(d0 + i * seg, pad(chord(prog[i % 4]), seg + 0.3, attack=1.0, release=1.6), 0.5)
        low.add(d0 + i * seg, drone(chord(prog[i % 4])[0] / 2, seg, attack=0.6, release=1.2), 0.15)
    k = 0
    while d0 + 0.3 + k * beat / 2 < d1 - 0.4:
        tt = d0 + 0.3 + k * beat / 2
        ci = min(15, int((tt - d0) / seg))
        notes = chord(prog[ci % 4], 1)
        keys.add(tt, pluck(notes[[0, 2, 3, 1][k % 4] % len(notes)], decay=0.3), 0.085, pan=-0.35 + 0.7 * (k % 3) / 2)
        if k % 4 == 0:
            low.add(tt, thump(), 0.22)
        k += 1

    # ---------- engine: brighter ----------
    e0, e1 = S["s09-engine"]["start"], S["s09-engine"]["end"]
    prog = ["G2 Bb2 D3 F3 A3", "Bb2 D3 F3 A3 C4", "D3 F3 A3 E4", "C3 E3 G3 B3 D4"]
    seg = (e1 - e0) / 8
    for i in range(8):
        pads.add(e0 + i * seg, pad(chord(prog[i % 4]), seg + 0.3, attack=1.1, release=1.6, bright=1.2), 0.5)
        low.add(e0 + i * seg, drone(chord(prog[i % 4])[0] / 2, seg, attack=0.6, release=1.2), 0.15)
    k = 0
    while e0 + 0.4 + k * beat / 4 < e1 - 0.4:
        tt = e0 + 0.4 + k * beat / 4
        ci = min(7, int((tt - e0) / seg))
        notes = chord(prog[ci % 4], 2)
        if k % 2 == 0 or k % 8 == 3:
            keys.add(tt, pluck(notes[[0, 1, 2, 3, 2, 1, 4, 2][k % 8] % len(notes)], decay=0.22, bright=0.7), 0.05, pan=-0.5 + (k % 5) / 4)
        k += 1

    # ---------- impact: warm build ----------
    m0, m1 = S["s10-impact"]["start"], S["s10-impact"]["end"]
    prog = ["Bb2 D3 F3 A3 C4", "F2 A2 C3 E3 A3", "C3 E3 G3 D4", "D3 F3 A3 C4 E4"]
    seg = (m1 - m0) / 8
    for i in range(8):
        pads.add(m0 + i * seg, pad(chord(prog[i % 4]), seg + 0.4, attack=1.3, release=1.8, bright=1.0 + 0.04 * i), 0.55 + 0.03 * i)
        low.add(m0 + i * seg, drone(chord(prog[i % 4])[0] / 2, seg, attack=0.8, release=1.4), 0.18)
    k = 0
    while m0 + 0.5 + k * beat < m1 - 0.6:
        tt = m0 + 0.5 + k * beat
        ci = min(7, int((tt - m0) / seg))
        notes = chord(prog[ci % 4], 1)
        keys.add(tt, pluck(notes[(k * 2) % len(notes)], decay=0.9), 0.09, pan=-0.3 + 0.6 * (k % 2))
        k += 1

    # ---------- payoff: callback, then resolve to D major ----------
    f0 = S["s11-payoff"]["start"]
    back, fence, title = L["L43"], L["L45"], L["L46"]
    low.add(f0, drone(hz("D2"), fence["start"] - f0, attack=1.5, release=1.0), 0.3)
    air.add(f0, shimmer(fence["start"] - f0 + 1.0), 0.45)
    pads.add(f0 + 0.2, pad(chord("D3 F3 A3 E4"), fence["start"] - f0 - 0.4, attack=2.0, release=1.2, bright=0.7), 0.55)
    pads.add(fence["start"] - 0.4, pad(chord("Bb2 D3 F3 A3 D4"), title["start"] - fence["start"] + 0.2, attack=1.0, release=1.0, bright=1.1), 0.62)
    end_len = total - title["start"] + 2.0
    pads.add(title["start"] - 0.2, pad(chord("D3 F#3 A3 E4 A4"), end_len - 3.5, attack=1.4, release=3.5, bright=1.25), 0.78)
    low.add(title["start"] - 0.2, drone(hz("D2"), end_len - 3.0, attack=0.8, release=3.0), 0.3)
    for i, nm in enumerate(["A4", "D5", "F#5", "A5", "E5"]):
        keys.add(title["start"] + 0.05 + i * 0.34, pluck(hz(nm), decay=1.6), 0.14, pan=-0.4 + 0.2 * i)

    mix = pads.buf * 0.9 + keys.buf * 1.0 + low.buf * 0.95 + air.buf * 0.8
    # keep the voice's presence band clear: gentle dip around 2.5 kHz, roll off the top
    b, a = signal.iirpeak(2500 / (SR / 2), 0.8)
    presence = np.stack([signal.lfilter(b, a, mix[:, c]) for c in range(2)], axis=1)
    mix = mix - 0.35 * presence
    b, a = signal.butter(2, 7500 / (SR / 2))
    mix = np.stack([signal.lfilter(b, a, mix[:, c]) for c in range(2)], axis=1).astype(np.float32)
    mix = reverb(mix)
    b, a = signal.butter(2, 35 / (SR / 2), btype="highpass")
    mix = np.stack([signal.lfilter(b, a, mix[:, c]) for c in range(2)], axis=1).astype(np.float32)
    mix = mix[: int(total * SR)]
    fade = int(2.5 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    mix = np.tanh(1.3 * mix / (np.max(np.abs(mix)) + 1e-9)) / np.tanh(1.3)
    mix *= 0.89 / (np.max(np.abs(mix)) + 1e-9)
    out = ROOT / "assets" / "music"
    out.mkdir(parents=True, exist_ok=True)
    sf.write(out / "score.wav", mix, SR, subtype="PCM_24")
    print(f"score.wav {len(mix) / SR:.2f}s")


if __name__ == "__main__":
    main()
