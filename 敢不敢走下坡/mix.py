"""Score, sound cues and narration -> audio/final.wav (-14 LUFS).  All music is synthesized here
(felt piano, pads, soft pulses from the 《重估》 intro's music.py); nothing sampled."""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "extras" / "chonggu_intro"))
from music import SR, duck, echo, note_hz, pad, piano, place, room, sub_pulse, tick  # noqa: E402

EV = json.loads((ROOT / "data" / "events.json").read_text())
S, TOTAL = EV["scenes"], EV["total"]
N = int((TOTAL + 0.5) * SR)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        assert w.getframerate() == SR and w.getnchannels() == 1, path
    return x


def chord(names: str) -> list[float]:
    return [note_hz(n) for n in names.split()]


# ------------------------------------------------------------------------------------------- score
# D minor, slow.  Sections follow the picture: night hush -> rewind -> the rules -> the climb -> the count -> home.
PROG = [  # (start, chord for the pad, arpeggio notes)
    (0.0, "D3 A3 F4", "D4 A4 E5 F5"),
    (S["rewind"], "Bb2 F3 D4", "Bb3 F4 C5 D5"),
    (S["three"], "Bb2 F3 D4", "Bb3 F4 C5 D5"),
    (S["rule"] - 1.0, "F2 C4 A4", "F3 C4 G4 A4"),
    (S["lamps"], "G2 D4 Bb4", "G3 D4 A4 Bb4"),
    (S["lamps"] + 4.6, "C3 G3 E4", "C4 G4 D5 E5"),
    (S["sim"], "D3 A3 F4", "D4 A4 E5 F5"),
    (S["sim"] + 3.0, "Bb2 F3 D4", "Bb3 F4 C5 D5"),
    (S["sim"] + 6.0, "F2 C4 A4", "F3 C4 G4 A4"),
    (S["sim"] + 8.7, "C3 G3 E4", "C4 G4 D5 E5"),
    (S["crowd"], "F2 C4 A4", "F3 C4 A4 C5"),
    (S["grid"] + 1.6, "C3 G3 E4", "C4 G4 E5 G5"),
    (S["grid"] + 4.4, "D3 A3 F4", "D4 A4 F5 A5"),
    (S["temp"], "Bb2 F3 D4", "Bb3 F4 D5"),
    (S["path"], "F2 C4 A4", "F3 C4 A4 C5"),
    (S["ending"], "C3 G3 D4", "C4 G4 D5"),
    (S["ending"] + 2.4, "F2 C3 A3 G4", "F3 C4 G4 A4"),
]


def score() -> np.ndarray:
    mus = np.zeros(N)
    bounds = [p[0] for p in PROG] + [TOTAL + 0.5]
    for i, (t0, ch, arp) in enumerate(PROG):
        t1 = bounds[i + 1]
        if t1 - t0 < 0.3:
            continue
        place(mus, pad(chord(ch), t1 - t0 + 1.2, amp=0.075, attack=0.9, release=1.4), max(0, t0 - 0.3))
        # felt-piano arpeggio: sparse in the quiet parts, eighth notes while they climb and while we count
        busy = S["sim"] <= t0 < S["temp"]
        step = 0.32 if busy else 0.64
        notes = chord(arp)
        k, t = 0, t0
        if S["rewind"] <= t0 < S["three"] or S["temp"] <= t0 < S["path"]:
            t = t1  # rewind and the "模拟退火" card get the pad alone
        while t < t1 - 0.05:
            f = notes[k % len(notes)] if k % 8 != 7 else notes[0] * 2
            place(mus, piano(f, 1.8, amp=0.075 if busy else 0.085, decay=1.1 if busy else 1.8, bright=0.8), t)
            k += 1
            t += step
        if busy:  # a soft pulse on the bar
            for tb in np.arange(t0, t1 - 0.1, step * 4):
                place(mus, sub_pulse(note_hz(ch.split()[0]) / 2, 0.8, amp=0.12, decay=0.4), tb)
    # last chord rings out
    place(mus, piano(note_hz("F3"), 4.0, amp=0.09, decay=3.0), S["ending"] + 2.4)
    place(mus, piano(note_hz("A4"), 4.0, amp=0.06, decay=3.0), S["ending"] + 2.45)
    return room(mus, seconds=2.2, wet=0.28)


# ------------------------------------------------------------------------------------------- cues
def noise(dur: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(dur * SR))


def cues() -> np.ndarray:
    fx = np.zeros(N)
    for j, e in enumerate(EV["events"]):
        t, k = e["t"], e["k"]
        if k == "pop":
            place(fx, piano(note_hz("A5"), 0.5, amp=0.05, decay=0.18, bright=1.4), t)
            place(fx, tick(amp=0.05, freq=2600, seed=j), t)
        elif k == "tick":
            place(fx, tick(amp=0.035 if e.get("quiet") else 0.06, freq=3000, seed=j), t)
        elif k == "low":
            place(fx, sub_pulse(55, 1.2, amp=0.22, decay=0.5), t)
        elif k == "ring":
            for i, n in enumerate(("E5", "A5")):
                place(fx, piano(note_hz(n), 1.6, amp=0.05, decay=0.9, bright=1.2), t + i * 0.08)
        elif k == "summit":
            for i, n in enumerate(("F4", "A4", "C5", "F5")):
                place(fx, piano(note_hz(n), 2.6, amp=0.055, decay=1.6, bright=1.1), t + i * 0.07)
            place(fx, sub_pulse(43.6, 1.6, amp=0.16, decay=0.7), t)
        elif k == "lamp":
            v = e.get("v", 0)
            if v > 0.005:
                place(fx, piano(note_hz("C6") * (1 + 0.5 * v), 0.6, amp=0.02 + 0.03 * v, decay=0.25, bright=1.5), t)
        elif k == "rewind":  # tape running backwards: a falling, filtered whoosh
            d = e["d"]
            n = noise(d + 0.3, j)
            n = np.convolve(n, np.ones(40) / 40, mode="same")
            tt = np.arange(len(n)) / SR
            env = np.sin(np.pi * np.clip(tt / (d + 0.3), 0, 1)) ** 1.5
            sweep = np.sin(2 * np.pi * np.cumsum(900 * np.exp(-tt * 2.2) + 120) / SR)
            place(fx, 0.10 * n * env + 0.03 * sweep * env, t)
        elif k == "patter":  # many small feet landing
            rng = np.random.default_rng(j)
            for tt in np.sort(rng.uniform(0, e["d"], 70)):
                place(fx, tick(dur=0.03, amp=0.012 + 0.012 * rng.random(), freq=1800 + 2400 * rng.random(), seed=int(tt * 1e4)), t + tt)
        elif k == "swell":
            d = e["d"]
            n = np.convolve(noise(d, j), np.ones(120) / 120, mode="same")
            tt = np.arange(len(n)) / SR
            place(fx, 0.25 * n * (tt / d) ** 2 * np.exp(-((tt - d) ** 2) * 6), t)
        elif k == "shimmer":
            for i in range(9):
                place(fx, piano(note_hz(("C5", "F5", "A5", "C6")[i % 4]), 1.2, amp=0.022, decay=0.7, bright=1.3), t + i * e["d"] / 9)
    return echo(fx)


# ------------------------------------------------------------------------------------------- voice and mix
def voice() -> np.ndarray:
    v = np.zeros(N)
    for ln in EV["lines"]:
        place(v, read_wav(ROOT / "audio" / ln["file"]), ln["t0"])
    return v


def main():
    v, mus, fx = voice(), score(), cues()
    mus = duck(mus, v, depth_db=8.0)
    # levels relative to the voice (voice RMS while speaking ~ -20 dBFS before loudnorm)
    mix = v * 1.0 + mus * 0.11 + fx * 0.6
    fade = np.ones(N)
    k = int(0.6 * SR)
    fade[-k:] = np.linspace(1, 0, k)
    mix *= fade
    peak = np.abs(mix).max()
    mix *= 0.9 / peak
    raw = ROOT / "audio" / "mix_raw.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    # gentle voice-bus compression so -14 LUFS fits under a -1 dB true peak without a pumping limiter
    comp = ROOT / "audio" / "mix_comp.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    "acompressor=threshold=-20dB:ratio=3:attack=4:release=90:makeup=1,alimiter=limit=0.89:attack=2:release=40:level=false",
                    str(comp)], check=True)
    raw = comp
    out = ROOT / "audio" / "final.wav"
    # two-pass loudnorm to -14 LUFS, true peak -1 dB, stereo out
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
    af = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, "-ac", "2", str(out)], check=True)
    print("->", out)


if __name__ == "__main__":
    main()
