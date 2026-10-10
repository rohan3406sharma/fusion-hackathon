# Validation report

What was actually tested on the delivered file `renders/fin04-explainer.mp4` (render of 10 Oct 2026, HyperFrames 0.8.115,
`--quality delivery --fps 30 --video-frame-format png`). Raw results: `renders/review/validation.json`;
script: `scripts/validate.py`.

## File and streams (ffprobe)
| Check | Result |
|---|---|
| Container duration | 293.07 s (4:53) — target 4:50–5:10 ✔ |
| Video | H.264 High, 1920×1080, 30/1 fps, yuv420p, 8,792 frames ✔ |
| Audio | AAC, 48 kHz, stereo, 195 kb/s, 293.05 s ✔ |
| Size | 171 MB |

## Picture integrity
| Check | Result |
|---|---|
| Black frames (ffmpeg `blackdetect`, ≥ 0.25 s) | none ✔ |
| Frozen picture (`freezedetect`, ≥ 6 s) | none ✔ (first render had one 7 s hold at 1:57; a slow camera push-in was added) |
| Screen recordings play in the render | verified frame by frame around every recorded click (1:45–1:49, 2:36–2:43, 2:53–2:59) ✔ |
| Representative frames inspected (beginning, problem, idea, demo ×4, engine, impact, payoff, end card) | 26 frames, `renders/review/contact-sheet.png` ✔ — no clipping, legible text at 1080p, layouts as designed |
| Every scene cross-fade inspected (30 frames at −0.55 s, −0.25 s, +0.05 s of each boundary) | dissolves are clean; act changes dip briefly through the dark canvas by design ✔ |
| Full-resolution legibility spot check (2:17.6, zoomed UI table) | UI text crisp (2× captures), callouts legible ✔ |

## Audio
| Check | Result |
|---|---|
| Integrated loudness | −16.06 LUFS (target −16) ✔ |
| True peak | −1.47 dBTP (ceiling −1.5) ✔ |
| Loudness range | 3.0 LU (speech-led, consistent) |
| Silences ≥ 1.5 s at −50 dB | none ✔ |
| Narration alignment in the MP4 (cross-correlation with the voice stem at 0:01.6, 2:11.7, 4:43.9) | 0 ms offset at all three points ✔ |
| Voice vs music (stems) | music 17.5 dB under the voice while it speaks, ~10 dB under in pauses; lifted in the intro, long pauses and outro ✔ |
| SFX | 43 cues, 16–26 dB under voice peaks; no whooshes ✔ |
| Final audio is the final mix | correlation 0.9993 with `assets/audio/mix.wav`, identical levels in the swell regions ✔ |
| Spectrogram / waveform | `renders/review/audio-spectrogram.png`, `audio-waveform.png` — continuous speech, no dropouts or clipping ✔ |
| Voice intelligibility | every line re-transcribed with whisper small.en matched the script; one phrase ("A I copilot") was misheard, rewritten and re-synthesised ✔ |

## Composition checks (HyperFrames)
- `npx hyperframes lint`: 0 errors, 0 warnings.
- `npx hyperframes check --samples 24`: passed — lint, runtime, layout, motion and 31/31 WCAG AA contrast checks. Remaining "info" notes are intentional overflows (camera wrappers, drifting background glows).
- `npx hyperframes validate`: no runtime JavaScript errors.

## Factual checks
- Every number on screen in the demo was read from the running app and cross-checked against the texts captured in `captures/manifest.json` (see `research.md`, "Project numbers").
- One narration line was corrected after capture: the finder's runtime varies between runs (0.41–0.69 s observed), so "under half a second" became "under a second"; the screen shows the captured 0.69 s.
- External facts (Panama Canal advisory, two QJE papers, EBA guideline, ASC 280, JRC dataset) were checked against primary or near-primary sources on 9–10 Oct 2026 (`research.md`).

## Problems found and fixed during review
1. **Recordings frozen in the first full render** — videos created from JavaScript were invisible to the render compiler (`videoCount: 0`), so they showed their first frame only. Fixed by declaring each recording as a static `<video>` tag kept in sync by `scripts/sync_media.py`; second render reports `videoCount: 4`, 642 frames extracted.
2. Capture clips were ~1.3 s longer than real time (ffmpeg concat duplicated the final frame) — replaced with an exact constant-30 fps resampler; durations now match wall time.
3. GSAP `fromTo` pre-rendering made later effects visible at t=0 — replaced with seek-safe set+tween bursts.
4. Text overlap in scene 2 (layout check), letter-spacing tween stutter (lint), low-contrast "Live app" label (contrast check), cropped copilot provenance chips, and a word-lookup bug — all fixed.

## Not tested / limits
- Playback was verified by decoding and inspecting frames and audio programmatically, not by a person watching in real time; subjective qualities (voice naturalness, music taste) were judged from transcription accuracy, spectrograms and level measurements only.
- Local renders can differ slightly from Docker renders (fonts are bundled, so differences should be minimal).
