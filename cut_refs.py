"""Cut the reference clips listed in voice/*.json out of the episode-4 recording.

The clips are already in voice/; run this only after changing a clip's `src` (its place in the recording, seconds).

    python3 cut_refs.py ../work/src48.wav        # src48.wav = the episode recording, 48 kHz mono
-> voice/原同/*.wav, voice/顾东政/*.wav (24 kHz mono, what F5-TTS wants)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
src = sys.argv[1] if len(sys.argv) > 1 else str(ROOT.parent / "work" / "src48.wav")

for spk in sorted((ROOT / "voice").glob("*.json")):
    for mood, r in json.loads(spk.read_text()).items():
        out = ROOT / r["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        a, b = r["src"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", src, "-ac", "1", "-ar", "24000",
                        "-af", "afade=t=in:d=0.02,areverse,afade=t=in:d=0.04,areverse", str(out)], check=True)
        print(f"{spk.stem} {mood:9} {out.name:18} {b - a:5.2f} s  {r['text']}")
