"""Keep the static <video data-rec="..."> tags in compositions/*.html in sync with assets/timeline.json.

HyperFrames pre-extracts frames only for media present in the static HTML, so each screen recording is
declared statically in its scene (the scene script then moves it into the browser frame). This rewrites
their data-start / data-duration / data-media-start / src from the resolved recording placements.
Run: .venv-tts/bin/python scripts/sync_media.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    tl = json.loads((ROOT / "assets" / "timeline.json").read_text())
    seen = set()
    for comp in sorted((ROOT / "compositions").glob("*.html")):
        html = comp.read_text()

        def fix(m: re.Match) -> str:
            tag = m.group(0)
            name = re.search(r'data-rec="([^"]+)"', tag).group(1)
            r = tl["rec"][name]
            seen.add(name)
            for attr, val in [("data-start", r["local"]), ("data-duration", r["duration"]), ("data-media-start", r["mediaStart"]), ("src", r["file"])]:
                tag = re.sub(rf'{attr}="[^"]*"', f'{attr}="{val}"', tag)
            return tag

        new = re.sub(r"<video\b[^>]*data-rec=\"[^\"]+\"[^>]*>", fix, html)
        if new != html:
            comp.write_text(new)
    missing = set(tl["rec"]) - seen
    print("synced:", ", ".join(sorted(seen)), "| missing:", ", ".join(sorted(missing)) or "none")


if __name__ == "__main__":
    main()
