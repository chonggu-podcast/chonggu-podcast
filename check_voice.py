"""How the cloned narration came out: likeness, pace, pitch movement, and endings.

    .venv-tts/bin/python check_voice.py voice/原同.json ../work/src48.wav

- likeness: resemblyzer similarity of every audio/line_XX.wav to the speaker's reference clips (1 = same voice;
  the same person's other speech scores ~0.95, the other host ~0.65; lines under 1 s are unreliable)
- pace (characters/second) against the target in script.json, and pitch movement (semitone sd) from data/asr.json
- endings: a line whose last 40 ms is louder than -32 dB was cut off mid-sound
"""
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from resemblyzer import VoiceEncoder, preprocess_wav

ROOT = Path(__file__).parent
refs_p, src_p = sys.argv[1], sys.argv[2]
refs = json.loads((ROOT / refs_p).read_text())
spec = json.loads((ROOT / "script.json").read_text())
asr = json.loads((ROOT / "data" / "asr.json").read_text())

enc = VoiceEncoder(verbose=False)
src, sr = sf.read(src_p)


def emb(y, s):
    return enc.embed_utterance(preprocess_wav(librosa.resample(y, orig_sr=s, target_sr=16000), source_sr=16000))


me = np.mean([emb(src[int(a * sr):int(b * sr)], sr) for a, b in (r["src"] for r in refs.values())], 0)
me /= np.linalg.norm(me)

print(f"{'id':4} {'mood':9} {'like':>5} {'rate':>5} {'goal':>5} {'pitch':>5}  end")
likes = []
for i, ln in enumerate(spec["lines"]):
    y, s = sf.read(ROOT / "audio" / f"line_{i:02d}.wav")
    like = float(np.dot(emb(y, s), me))
    likes.append(like)
    a = asr.get(ln["id"], {})
    end = 20 * np.log10(np.sqrt(np.mean(y[-int(0.04 * s):] ** 2)) + 1e-9)
    print(f"{ln['id']:4} {ln.get('mood', ''):9} {like:5.2f} {a.get('rate', 0):5.2f} {ln.get('rate', 0):5.1f} {a.get('pitch', 0):5.2f}  "
          f"{'CUT OFF' if end > -32 else ''}{'  cer ' + str(a['cer']) if a.get('cer') else ''}{'  EXTRA AT END' if a.get('tail_extra') else ''}")
print(f"\nlikeness mean {np.mean(likes):.2f}, min {min(likes):.2f}")
