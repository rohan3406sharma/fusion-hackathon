"""Write narration.md (full script with exact timings) and renders/fin04-explainer.srt from assets/timeline.json.
Run: .venv-tts/bin/python scripts/build_docs.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACTS = {
    "s01-hook": "Act 1 · The hook", "s02-canal": "Act 2 · The problem", "s03-evidence": "Act 2 · The problem (evidence)",
    "s04-idea": "Act 3 · The core idea", "s05-search": "Act 4 · Live demo: search", "s06-top-event": "Act 4 · Live demo: the top event",
    "s07-path": "Act 4 · Live demo: the path", "s08-optimise": "Act 4 · Live demo: protect", "s09-engine": "Act 5 · How it works",
    "s10-impact": "Act 6 · Impact and limits", "s11-payoff": "Act 7 · The payoff",
}
# spoken forms -> readable caption forms
CAPTION = [
    ("The Fin zero four", "The FIN-04"), ("the Fin zero four", "the FIN-04"), ("twenty twenty-three", "2023"), ("nineteen fifty", "1950"),
    ("twenty eleven", "2011"), ("E U's", "EU's"), ("Seven hundred and eighty", "780"), ("A hundred and sixty-five", "165"),
    ("one point one three percent", "1.13%"), ("two hundred", "200"), ("three million dollars", "$3 million"), ("ten worst", "10 worst"),
    ("about five percent", "about 5%"), ("a hundred and ninety-seven", "197"), ("A hundred and two companies, eighteen holdings", "102 companies, 18 holdings"),
    ("eighteen ships", "18 ships"),
]


def ts(t: float, srt: bool = False) -> str:
    m, s = divmod(t, 60)
    if srt:
        h, m = divmod(int(m), 60)
        return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
    return f"{int(m)}:{s:05.2f}"


def caption(text: str) -> str:
    for a, b in CAPTION:
        text = text.replace(a, b)
    return text


def main() -> None:
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    words = sum(len(l["say"].split()) for s in tl["scenes"] for l in s["lines"])
    speech = sum(l["end"] - l["start"] for s in tl["scenes"] for l in s["lines"])
    out = ["# Narration script", "",
           f"Final voiceover as rendered: {words} words, {speech:.1f} s of speech in a {ts(tl['total'])} video "
           f"({words / (tl['total'] / 60):.0f} words per minute overall). Voice: Kokoro-82M `af_heart`, speed 0.92, generated locally.",
           "Times are the exact start/end of each synthesised line in the final mix. Edit `scripts/narration.json`, then rerun the pipeline (see README).",
           "Numbers are spelled out for the voice; the captions file uses digits.", ""]
    for sc in tl["scenes"]:
        out += [f"## {ACTS[sc['id']]}  ({ts(sc['start'])}–{ts(sc['end'])})", ""]
        for ln in sc["lines"]:
            out.append(f"- `{ts(ln['start'])}` **{ln['id']}** — {ln['say']}")
        out.append("")
    (ROOT / "narration.md").write_text("\n".join(out))

    srt, n = [], 0
    for sc in tl["scenes"]:
        for ln in sc["lines"]:
            n += 1
            srt += [str(n), f"{ts(ln['start'], True)} --> {ts(ln['end'] + 0.15, True)}", caption(ln["say"]), ""]
    (ROOT / "renders").mkdir(exist_ok=True)
    (ROOT / "renders" / "fin04-explainer.srt").write_text("\n".join(srt))
    print(f"narration.md ({words} words) and renders/fin04-explainer.srt ({n} cues)")


if __name__ == "__main__":
    main()
