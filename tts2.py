"""Narration v2 for 原同's version: paced on purpose, and picked for life.

Every line in script.json has a target speaking rate (`rate`, characters per second): key sentences slower, lists and
asides quicker.  F5-TTS gets the exact duration to fill (fix_duration), so the rate is set rather than left to chance;
one correction pass pulls it within ~7 %.  Each line is synthesized with two seeds; among the takes whisper hears
word for word, the one with the most pitch movement wins (the first version sounded flat).

    .venv-tts/bin/python tts2.py      # only lines whose text / reference / rate changed
    .venv-tts/bin/python tts2.py --redo b6,e3 --seeds 37,59,71   # more takes for these; the current one still competes
-> audio/line_XX.wav, data/asr.json, data/timeline.json  (helpers come from tts.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import tts as TT

ROOT = Path(__file__).parent
SEEDS = (11, 23)
TOL = 0.10


def pitch_sd(path: Path) -> float:
    y, sr = sf.read(str(path))
    y16 = librosa.resample(y, orig_sr=sr, target_sr=16000)
    f0, _, _ = librosa.pyin(y16, fmin=70, fmax=400, sr=16000, frame_length=1024)
    f = f0[~np.isnan(f0)]
    return float(np.std(12 * np.log2(f / np.median(f)))) if len(f) > 10 else 0.0


def drop_head(out: Path, said: str, a: dict) -> dict:
    """F5 sometimes starts with the tail of the reference clip (「行」 from 「…这一行」, 「明白」 from 「…没想明白」).
    If whisper hears syllables before the script's first two, cut at the quietest point before the real start."""
    from pypinyin import lazy_pinyin
    sp = lazy_pinyin(TT.norm(TT.plain(said))[:2])
    chars = [(c, w) for w in a["words"] for c in TT.norm(w["w"])]
    py = [lazy_pinyin(c)[0] for c, _ in chars]
    k = next((j for j in range(1, len(py) - 1) if py[j:j + 2] == sp), 0)
    if k == 0 or py[:2] == sp:
        return a
    w_prev, w_real = chars[k - 1][1], chars[k][1]
    y, sr = sf.read(str(out))
    lo, hi = int(w_prev["t1"] * sr), max(int(w_prev["t1"] * sr) + 1, int(w_real["t0"] * sr))
    hop = int(0.01 * sr)
    if hi - lo > 2 * hop:
        e = [np.sqrt(np.mean(y[i:i + hop] ** 2)) for i in range(lo, hi - hop, hop)]
        cut = lo + hop * int(np.argmin(e))
    else:
        cut = max(0, int((w_real["t0"] - 0.04) * sr))
    z = y[cut:].copy()
    f = min(len(z), int(0.015 * sr)); z[:f] *= np.linspace(0, 1, f)
    sf.write(str(out), z, sr)
    print(f"   dropped {''.join(c for c, _ in chars[:k])} ({cut / sr:.2f} s)", flush=True)
    return TT.asr(out)


TAIL_PROMPT = "这一句的结尾可能多了一个字，比如：清楚。看不见的楚。已经没了楚。"


def tail_extra(out: Path, said: str) -> int:
    """1 if whisper, hearing the last 0.9 s on its own, ends on something other than the script's last syllable
    (a reference clip cut mid-word made F5 add 「楚」 to the ends of lines).  The prompt nudges it to write extras down."""
    import mlx_whisper
    from pypinyin import lazy_pinyin
    y, sr = sf.read(str(out))
    seg = np.concatenate([np.zeros(int(0.3 * sr)), y[-int(0.9 * sr):], np.zeros(int(0.5 * sr))])
    tmp = out.with_name(out.stem + "_tail.wav"); sf.write(tmp, seg, sr)
    r = mlx_whisper.transcribe(str(tmp), path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language="zh",
                               condition_on_previous_text=False, initial_prompt=TAIL_PROMPT)
    tmp.unlink()
    h, last = TT.norm(r["text"]), TT.norm(TT.plain(said))[-1:]
    return int(bool(h) and lazy_pinyin(h[-1])[0] != lazy_pinyin(last)[0])


def main():
    args = sys.argv[1:]
    redo = set(args[args.index("--redo") + 1].split(",")) if "--redo" in args else set()
    seeds = tuple(int(x) for x in args[args.index("--seeds") + 1].split(",")) if "--seeds" in args else SEEDS
    spec = json.loads((ROOT / "script.json").read_text())
    REFS = json.loads((ROOT / spec["refs"]).read_text())
    adir, ddir = ROOT / "audio", ROOT / "data"
    cache_p = ddir / "asr.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    tts = None
    eff = {}
    for i, ln in enumerate(spec["lines"]):
        said = ln.get("tts", ln["text"])
        ref = REFS[ln["mood"]]
        ref_f, ref_t, rate = str(ROOT / ref["file"]), ref["text"], ln["rate"]
        key = json.dumps(["v2", said, ref_f, ref_t, rate], ensure_ascii=False)
        wav = adir / f"line_{i:02d}.wav"
        old = cache.get(ln["id"], {})
        if old.get("key") == key and wav.exists() and ln["id"] not in redo:
            continue
        if tts is None:
            from f5_tts.api import F5TTS
            from f5_tts.infer.utils_infer import preprocess_ref_audio_text
            TT.patch_frontend()
            tts = F5TTS()
        if ref_f not in eff:
            pf, _ = preprocess_ref_audio_text(ref_f, ref_t, show_info=lambda *a: None)
            eff[ref_f] = sf.info(pf).duration
        n = len(TT.norm(TT.plain(said)))
        takes = []
        if ln["id"] in redo and old.get("key") == key and wav.exists():
            keep = adir / f"_try_{i:02d}_old.wav"; keep.write_bytes(wav.read_bytes())
            takes.append({"e": old["cer"], "err": abs(old["rate"] / rate - 1), "sd": old["pitch"], "out": keep, "seed": old["seed"],
                          "got": old["rate"], "a": {"text": old["heard"], "words": old["words"]}, "x": tail_extra(keep, said)})
        for seed in (seeds if ln["id"] in redo else SEEDS):
            gen = n / (rate * 0.8) + 0.15
            for attempt in range(2):
                y, sr, _ = tts.infer(ref_f, ref_t, said, seed=seed, nfe_step=32, cfg_strength=2.0, fix_duration=eff[ref_f] + gen, show_info=lambda *a: None)
                raw = adir / f"_raw_{i:02d}.wav"; sf.write(raw, y, sr)
                out = adir / f"_try_{i:02d}_{seed}.wav"; TT.trim(raw, out); raw.unlink()
                a = drop_head(out, said, TT.asr(out))
                got = n / TT.duration(out)
                if abs(got / rate - 1) <= TOL or attempt == 1:
                    break
                gen *= got / rate          # too fast -> give it more time, and the other way round
            e = TT.cer(said, a["text"])
            sd = pitch_sd(out)
            x = tail_extra(out, said)
            print(f"{i:02d} {ln['id']} seed {seed}: {got:.2f} c/s (target {rate})  pitch {sd:.2f}  cer {e:.2f}{'  EXTRA AT END' if x else ''}  {a['text']}", flush=True)
            takes.append({"e": e, "err": abs(got / rate - 1), "sd": sd, "out": out, "a": a, "seed": seed, "got": got, "x": x})
        best_e = min(t["e"] for t in takes)
        pool = [t for t in takes if t["e"] == best_e]
        pool = [t for t in pool if not t["x"]] or pool
        near = [t for t in pool if t["err"] <= 0.1] or [min(pool, key=lambda t: t["err"])]   # none on pace: the closest
        best = max(near, key=lambda t: t["sd"])
        best["out"].replace(wav)
        for f in adir.glob(f"_try_{i:02d}_*.wav"):
            f.unlink()
        print(f"{i:02d} {ln['id']} -> seed {best['seed']}  {best['got']:.2f} c/s  pitch {best['sd']:.2f}  cer {best['e']:.2f}", flush=True)
        cache[ln["id"]] = {"key": key, "cer": round(best["e"], 3), "seed": best["seed"], "heard": best["a"]["text"], "words": best["a"]["words"], "pitch": round(best["sd"], 2), "rate": round(best["got"], 2), "tail_extra": best["x"]}
        cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    # timeline (same as tts.py)
    t = TT.LEAD_IN
    lines = []
    for i, ln in enumerate(spec["lines"]):
        wav = adir / f"line_{i:02d}.wav"
        d = TT.duration(wav)
        ct = TT.char_times(ln["text"], TT.plain(ln.get("tts", ln["text"])), cache[ln["id"]], d)
        lines.append({"id": ln["id"], "scene": ln["scene"], "text": ln["text"], "i": i, "file": wav.name,
                      "t0": round(t, 3), "t1": round(t + d, 3), "chars": [round(t + x, 3) for x in ct], "cer": cache[ln["id"]]["cer"]})
        t += d + ln.get("gap", spec["gap"])
    total = lines[-1]["t1"] + TT.TAIL
    (ddir / "timeline.json").write_text(json.dumps({"total": round(total, 3), "lead": TT.LEAD_IN, "lines": lines}, ensure_ascii=False, indent=1))
    print(f"total {total:.2f} s")


if __name__ == "__main__":
    main()
