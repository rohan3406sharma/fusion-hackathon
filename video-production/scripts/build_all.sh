#!/usr/bin/env bash
# Rebuild everything after the app captures exist: voice -> timings -> music -> mix -> compositions -> check -> render.
# Usage (from video-production/):  bash scripts/build_all.sh            # full rebuild + render
#                                  SKIP_TTS=1 bash scripts/build_all.sh  # keep the current voice lines
set -euo pipefail
cd "$(dirname "$0")/.."
export DO_NOT_TRACK=1 HYPERFRAMES_SKIP_SKILLS=1
PY=.venv-tts/bin/python

if [ -z "${SKIP_TTS:-}" ]; then
  $PY scripts/tts.py                 # Kokoro-82M, one wav per line -> assets/voice/
fi
$PY scripts/build_timeline.py        # line times from measured durations (+ narration.wav)
$PY scripts/align.py                 # word timings per line (whisper-cli --dtw)
$PY scripts/build_timeline.py        # attach words, resolve cues, write assets/data/timeline.js + captures.js
$PY scripts/sync_media.py            # static <video> tags in the scenes follow the resolved recording placements
[ -f assets/data/geo.js ] || $PY scripts/build_geo.py
[ -f assets/img/grain.png ] || node scripts/make_grain.mjs
$PY scripts/make_music.py            # original score arranged to the scene boundaries
$PY scripts/mix.py                   # voice + ducked score + SFX -> assets/audio/mix.wav (-16 LUFS)
$PY scripts/build_index.py           # root composition from the timeline
$PY scripts/build_docs.py            # narration.md + renders/fin04-explainer.srt
npx hyperframes check
npx hyperframes render . -o renders/fin04-explainer.mp4 --quality delivery --fps 30 --video-frame-format png
