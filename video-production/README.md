# FIN-04 Climate Exposure Graph — 5-minute explainer video

A narrated, 4:53 cinematic explainer of this repository, built with [HyperFrames](https://github.com/heygen-com/hyperframes) from **real captures of the running app**: screen recordings of genuine clicks, high-resolution stills, and annotations placed on the exact on-screen rectangles the app rendered. Nothing in the demo is mocked; every number on screen was read from the live UI.

| Deliverable | Path |
|---|---|
| Final video (1920×1080, 30 fps, H.264 + AAC) | `renders/fin04-explainer.mp4` |
| Captions | `renders/fin04-explainer.srt` |
| Narration script with exact timings | `narration.md` (source: `scripts/narration.json`) |
| Storyboard and scene timeline | `storyboard.md` |
| Research log (sources, dates, scenes) | `research.md` |
| Project understanding (internal) | `project-understanding.md` |
| Validation report | `validation-report.md` |
| Animation sources | `index.html` (generated), `compositions/*.html`, `assets/js/fx.js`, `assets/css/base.css` |
| Real app captures | `captures/stills/*.png`, `captures/rec/*.mp4`, `captures/manifest.json` |

## How it is built
```
scripts/narration.json ──tts.py──▶ assets/voice/L01…L46.wav (Kokoro-82M, local)
        │                                   │
        └────────────── build_timeline.py ◀─┘  exact line times + narration.wav
                         align.py  (whisper-cli --dtw per line) → word timings
                         build_timeline.py again → assets/timeline.json, assets/data/timeline.js
                         (+ scripts/cues.json: recordings aligned so each recorded click lands on its word; SFX cues)
                         sync_media.py → static <video> tags in the scenes get the resolved start/trim times
running app ──capture.mjs──▶ captures/ (recordings, stills, element rects + texts, graph node positions)
make_music.py  → assets/music/score.wav   (original score, arranged to the scene boundaries)
mix.py         → assets/audio/mix.wav     (voice + ducked score + SFX, −16 LUFS, ≤ −1.5 dBTP)
build_index.py → index.html               (11 overlapping scene slots + background + audio)
compositions/s01…s11.html                 (hand-written scenes; read window.TL, CAP, GEO via assets/js/fx.js)
hyperframes check / render → renders/fin04-explainer.mp4
validate.py    → renders/review/ (ffprobe, black/freeze/silence detection, loudness, A/V alignment, frames)
```
Every animation time is derived from the voice: scenes read word timestamps, so editing the script re-flows the whole video.

## Requirements
- Node 22+ (tested 25.2), FFmpeg (tested 9.0), Google Chrome (for capture), `whisper-cli` (whisper-cpp, Homebrew), Python 3.10–3.13 for the TTS venv (Kokoro does not support 3.14 yet).
- The app's own environment (`../.venv`, `../frontend/node_modules`) as described in the repository README.
- No API keys, no paid services. HyperFrames telemetry is turned off per command with `DO_NOT_TRACK=1`.

## Reproduce from scratch (exact commands, run from `video-production/`)
```bash
# 1. tooling (pinned: hyperframes 0.8.115, puppeteer-core 25.13.0)
npm install
python3.11 -m venv .venv-tts
.venv-tts/bin/pip install "kokoro-onnx==0.6.1" "soundfile==0.13.1" "scipy==1.16.2"
# Kokoro model files: the HyperFrames CLI downloads them to ~/.cache/hyperframes/tts/ on first use
#   (DO_NOT_TRACK=1 npx hyperframes tts "test"  — downloads kokoro-v1.0.onnx + voices-v1.0.bin)
# whisper model: DO_NOT_TRACK=1 npx hyperframes transcribe assets/voice/L01.wav --model small.en  (downloads ggml-small.en.bin)

# 2. run an ISOLATED copy of the app (separate ports and a throwaway database, so your own data is untouched)
(cd ../backend && FIN04_DATABASE_URL=sqlite:////tmp/fin04-capture.db FIN04_CORS_ORIGINS=http://localhost:5174 \
   ../.venv/bin/uvicorn app.main:app --port 8001) &
(cd ../frontend && VITE_BACKEND_URL=http://127.0.0.1:8001 npx vite --port 5174 --strictPort) &
#    optional: `ollama serve` with qwen3:8b for the live copilot shot (templates answer otherwise)

# 3. capture the real app (≈2 min): recordings, stills and the rects/texts of every annotated element
node scripts/capture.mjs
#    delete /tmp/fin04-capture.db before re-capturing so "Open as scenario" starts from a clean list

# 4. everything else: voice, timings, music, mix, compositions, check, render (≈10 min on an M4; render ≈5 min)
bash scripts/build_all.sh

# 5. verify the rendered file itself
.venv-tts/bin/python scripts/validate.py renders/fin04-explainer.mp4
```

## Editing
- **Change what is said:** edit `scripts/narration.json` (`say` is spoken, `gap` is the pause after the line), then `bash scripts/build_all.sh`. If a scene references a word you removed, its script throws a clear `word "…" not found in Lxx` error in `npx hyperframes validate`.
- **Change a visual:** edit `compositions/sNN-*.html` (times come from `FX.word(line, word)` / `FX.cue(name)`), preview with `DO_NOT_TRACK=1 npx hyperframes preview`, spot-check with `npx hyperframes snapshot --at <seconds>`, then render.
- **Change sync points or sound effects:** `scripts/cues.json` (named moments, SFX files and levels, recording alignment), then rerun from `build_timeline.py`.
- **Change the music:** `scripts/make_music.py` (deterministic; seeded).
- Re-capturing the app produces new runtime numbers (the finder's runtime varies run to run: 0.41–0.69 s observed); everything else is deterministic for the default data and seed 42.

## Notes and honest caveats
- The demo uses the app's **synthetic** dataset; the only real data is the JRC/Copernicus river-flood layer. The video says so on screen and in the narration.
- During capture a cursor overlay and hidden scrollbars are injected for legibility; the page itself is unchanged. All clicks are real.
- Recordings are real-time screen captures (Chrome DevTools screencast, resampled to constant 30 fps). One soft 0.25 s cross-fade joins two takes in scene 7.
- Kokoro TTS needed two workarounds on this machine: espeak-ng only reads its data via `ESPEAK_DATA_PATH`, and that path must not contain spaces (this project's path does), so `scripts/tts.py` links the data into the system temp folder.
- `npx hyperframes check` passes (lint, runtime, layout, motion, contrast). Remaining "info" notes are intentional overflows (camera wrappers, drifting background glows).
- Screen recordings must be **static** `<video>` tags in the scene HTML: the renderer only extracts frames for media it finds in the static markup (a JavaScript-created video renders as a frozen first frame). `scripts/sync_media.py` keeps their timing attributes in sync with the timeline.

## Credits and licences
- Fonts: Inter, Space Grotesk, Archivo Black, Instrument Serif, JetBrains Mono — SIL Open Font License (via the Motion Graphics starter kit; `assets/fonts/OFL.txt`).
- Sound effects: the starter kit's code-generated SFX (no licence restrictions per the kit).
- Music: original, generated by `scripts/make_music.py`.
- Voice: Kokoro-82M (Apache-2.0 weights) via `kokoro-onnx` (MIT), run locally.
- Map: Natural Earth land (public domain) via `world-atlas@2.0.2` (ISC).
- GSAP 3.14.2 (GreenSock standard no-charge licence), HyperFrames (Apache-2.0).
- River-flood hazard shown in the app: JRC / Copernicus CEMS, Baugh et al. (2024), CC BY 4.0, © European Union.
