"""Narration: one edge-tts clip per line of script.json -> audio/line_*.wav, then data/timeline.json
(each line's start/end on the video clock, plus word timings for the subtitles)."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

ROOT = Path(__file__).parent
LEAD_IN = 0.5      # silence before the first line
TAIL = 2.6         # hold after the last line


async def synth(text: str, voice: str, rate: str, mp3: Path) -> list[dict]:
    words = []
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with mp3.open("wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"t0": chunk["offset"] / 1e7, "t1": (chunk["offset"] + chunk["duration"]) / 1e7, "w": chunk["text"]})
    return words


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def main():
    spec = json.loads((ROOT / "script.json").read_text())
    adir = ROOT / "audio"
    adir.mkdir(exist_ok=True)
    t = LEAD_IN
    lines = []
    for i, ln in enumerate(spec["lines"]):
        mp3, wav = adir / f"line_{i:02d}.mp3", adir / f"line_{i:02d}.wav"
        words = asyncio.run(synth(ln["text"], spec["voice"], spec["rate"], mp3))
        # trim edge-tts's leading/trailing silence so the gaps are ours
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "1", str(wav)], check=True)
        lead = words[0]["t0"] if words else 0.0
        d = duration(wav)
        lines.append({**ln, "i": i, "t0": round(t, 3), "t1": round(t + d, 3), "file": wav.name,
                      "words": [{"t0": round(t + w["t0"] - lead, 3), "t1": round(t + w["t1"] - lead, 3), "w": w["w"]} for w in words]})
        print(f"{i:02d} {t:6.2f}-{t + d:6.2f}  {ln['text']}")
        t += d + ln.get("gap", spec["gap"])
    total = lines[-1]["t1"] + TAIL
    (ROOT / "data" / "timeline.json").write_text(json.dumps({"total": round(total, 3), "lines": lines}, ensure_ascii=False, indent=1))
    print(f"total {total:.2f} s")


if __name__ == "__main__":
    main()
