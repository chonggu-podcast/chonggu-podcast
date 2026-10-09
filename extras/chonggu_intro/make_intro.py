"""《重估》 fixed intro: 落点 / The Re-mark.

The waveform settles into a ruler and 重估 rises out of it. On 默认 a dark mark lands on the ruler; on the spoken
重估 it lifts, turns red and moves along, writing the episode topic. The old reading stays as a gray ghost labelled
默认, the new one carries the recording date. The ruler then rises to the top as the episode's timeline.

    python3 make_intro.py --topic 青年交流 --episode 2                       # no voice: music + picture
    python3 make_intro.py --topic 青年交流 --episode 2 --voice 片头.m4a        # one file with all four lines
    python3 make_intro.py --topic 财富 --episode 3 --voice-fixed 前三句.m4a --voice-topic 第四句.m4a
    python3 make_intro.py --topic 青年交流 --episode 2 --lines 3 --voice 片头.m4a --p3-speaker wu --p4-speaker wu \
        --total-frames 700                                                # three lines, no name lines
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import music as mu
from engine import (ASSETS, FPS, GRAY, H, INK, RED, SR, W, Canvas, Layer, clamp01, detect_phrases,
                    ease_in_out_cubic, ease_in_out_sine, ease_out_back, ease_out_cubic, ease_out_quint, font, lerp,
                    measure_loudness, mix, open_encoder, prog, read_wav_mono, speech_runs, split_at_fraction,
                    text_layer, voiced_warp, write_wav_float)

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- palette
DARK = (23, 23, 20)
SECOND = (78, 74, 66)
LIGHT_GRAY = (196, 191, 182)
MINOR_TICK = (179, 173, 162)
GHOST = (163, 158, 149)
TIMELINE = (194, 186, 172)
CH_TICK = (85, 77, 63)
WAVE = (237, 233, 225)
BULLET = (122, 118, 110)
BAR_AMBER = (165, 109, 27)
BAR_TEAL = (43, 84, 89)
BAR_IDLE = (163, 158, 149)   # flat meter when nobody speaks (music-only intro)
DOT_AMBER = (166, 110, 29)
DOT_TEAL = (44, 82, 91)
RING_AMBER = (186, 164, 124)
RING_TEAL = (135, 146, 139)
IDLE_AMBER = (214, 190, 146)
IDLE_TEAL = (161, 173, 170)
CHIP_FILL = (224, 221, 210)

# ---------------------------------------------------------------- geometry
X0, X1 = 96, 1824
Y_R = 596.0            # stage ruler centre
Y_T = 101.0            # timeline centre
BASELINE = 509
TITLE_SIZE = 192
X_OLD = 536.0          # centre of 默认 in the P3 sentence
SENT = "我们重新审视那些被默认接受的答案"
SENT_SIZE = 44
SENT_Y = 626
KICKER = "今天我们"
TOPIC_BUDGET = 1172     # keeps the new mark at x <= 1748 so the date stays centred under it
TOPIC_FLOOR = 116
TEXT_BAND = (255, 540)  # kicker + headline rows; the rising ruler is faint here

# syllables per line (for splitting a recording and placing word anchors)
SYL_P1, SYL_P2, SYL_P3 = 9, 5, 16          # 这里是重估我是原同 / 我是顾东政 / 我们重新审视那些被默认接受的答案
SYL_P1_SHORT = 5                           # three-line script (--lines 3): 这里是重估, no name lines
NO_VOICE_PHRASES = [(0.600, 2.900), (3.100, 4.300), (4.600, 7.800), (8.000, 10.200)]
PAD_BEFORE, PAD_AFTER = 0.040, 0.120
GAPS = [0.200, 0.300, 0.200]
GAP_RANGE_3 = (0.300, 0.800)  # --lines 3: the speaker's own pauses are kept, clamped to this range
ANCHOR_KEYS = {"t1g", "t1n", "t2n", "t3", "t3d", "t4t", "t4w", "t4v", "t_topic", "t_topic_end", "phrases"}
ANCHOR_ORDER = ["t1g", "t1n", "t2n", "t3d", "t4t", "t4w", "t4v", "t_topic", "t_topic_end"]
KARAOKE_LEAD = 0.050     # ink a character slightly before its syllable (picture should not trail sound)


# ---------------------------------------------------------------- timing

@dataclass
class Timing:
    phrases: list            # 4 x (start, end) on the intro timeline
    n: int                   # topic syllables
    topic_w: float           # topic advance width in px
    runs: list | None        # per phrase: voiced runs on the intro timeline (None = no voice)
    overrides: dict
    lines: int = 4           # 3: no name lines; phrase 2 is an empty slot at the end of phrase 1

    def __post_init__(self):
        (p1s, p1e), (p2s, p2e), (p3s, p3e), (p4s, p4e) = self.phrases
        self.P1s, self.P1e, self.P2s, self.P2e = p1s, p1e, p2s, p2e
        self.P3s, self.P3e, self.P4s, self.P4e = p3s, p3e, p4s, p4e
        n = self.n
        sp4 = 6 + n  # 今天我们重估 + topic
        if self.runs:
            r1, r2, r3, r4 = self.runs
            # word onsets by syllable position in voiced time (pauses do not advance the clock)
            if self.lines == 3:  # 这里是重估: the chrome comes in as the line ends
                (self.t1g,) = voiced_warp(r1, p1s, p1e, [3 / SYL_P1_SHORT])
                self.t1n = self.t2n = p1e
            else:
                self.t1g, self.t1n = voiced_warp(r1, p1s, p1e, [3 / SYL_P1, 7 / SYL_P1])
                (self.t2n,) = voiced_warp(r2, p2s, p2e, [2 / SYL_P2])
            self.t3 = voiced_warp(r3, p3s, p3e, [i / SYL_P3 for i in range(SYL_P3)])
            self.t4t, self.t4w, self.t4v, self.t_topic = voiced_warp(r4, p4s, p4e, [1 / sp4, 2 / sp4, 4 / sp4, 6 / sp4])
            self.t_topic_end = p4e
            # a real pause near a word boundary wins over syllable counting (今天，我们… / 重估……<topic>)
            for key, frac in (("t4w", 2 / sp4), ("t_topic", 6 / sp4)):
                ab = split_at_fraction(r4, frac, window=1 / sp4, min_gap=0.15)
                if ab:
                    setattr(self, key, ab[1][0])
            self.t4v = min(max(self.t4v, self.t4w + 0.12), self.t_topic - 0.12)
        else:
            self.t1g, self.t1n, self.t2n = 1.150, 2.250, 3.580
            step = (p3e - p3s - 0.150) / SYL_P3
            self.t3 = [p3s + i * step for i in range(SYL_P3)]
            self.t4t = p4s + 0.060
            self.t4w, self.t4v, self.t_topic = 8.550, 8.860, 9.250
            self.t_topic_end = min(p4e - 0.100, self.t_topic + 0.150 + 0.170 * n)
        self.t3d = self.t3[9]
        ov = self.overrides
        for k in ("t1g", "t1n", "t2n", "t4t", "t4w", "t4v", "t_topic", "t_topic_end"):
            if k in ov:
                setattr(self, k, ov[k])
        if self.lines == 3 and "t2n" not in ov:
            self.t2n = max(self.t2n, self.t1n)  # no line 2: t2n is unused, it only has to keep the order
        if "t3" in ov:
            self.t3 = list(ov["t3"])
            self.t3d = self.t3[9]
        if "t3d" in ov:  # keep the highlighted 默认 with the mark, and the karaoke in order around it
            shift = ov["t3d"] - self.t3[9]
            self.t3[9] += shift
            self.t3[10] += shift
            self.t3d = ov["t3d"]
            for i in range(11, SYL_P3):
                self.t3[i] = max(self.t3[i], self.t3[i - 1] + 0.06)
            for i in range(8, -1, -1):
                self.t3[i] = min(self.t3[i], self.t3[i + 1] - 0.06)
        seq = [getattr(self, k) for k in ANCHOR_ORDER]
        if any(b < a for a, b in zip(seq, seq[1:])) or any(b < a for a, b in zip(self.t3, self.t3[1:])):
            got = "，".join(f"{k}={getattr(self, k):.2f}" for k in ANCHOR_ORDER)
            sys.exit(f"时间点顺序不对（应当逐个变大）：{got}。请检查 anchors 文件")
        # the re-mark
        self.d = self.topic_w + 40
        D = min(max(self.d / 1.1, 600), 1150) / 1000
        self.T0 = max(self.t_topic - 0.200, self.t4v + 0.150)
        self.T1 = min(max(self.T0 + D, self.t_topic_end - 0.350), self.T0 + 1.400)
        self.L = self.T1 + 0.120
        self.R0 = self.L + 0.100
        self.R1 = self.R0 + 0.500
        self.END = max(self.P4e + 0.500, self.R1 + 0.350)

    def fast_windows(self):
        """(start, end, samples) of fast motion; these frames get a 180-degree shutter."""
        return [(0.0, 1.0, 5), (self.t1g - 0.160, self.t1g + 0.400, 8), (self.t4v - 0.110, self.L + 0.050, 8),
                (self.R0 - 0.02, self.R1 + 0.02, 6)]


def _seconds(key: str, x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        sys.exit(f"anchors 里 {key} 要写成数字（秒），现在是：{x!r}")
    if x > 100:  # written in ms
        print(f"  注意：{key}={x:g} 看起来是毫秒，按 {x / 1000:.3f} 秒处理", file=sys.stderr)
        x /= 1000
    return x


def load_overrides(path: str | None) -> dict:
    if not path:
        return {}
    try:
        raw = json.loads(Path(path).read_text())
    except OSError:
        sys.exit(f"找不到 anchors 文件：{path}")
    except json.JSONDecodeError as e:
        sys.exit(f"anchors 不是合法的 JSON（第 {e.lineno} 行第 {e.colno} 列）")
    if not isinstance(raw, dict):
        sys.exit("anchors 文件应该是一个 {…} 对象，例如 {\"t4v\": 8.9}")
    if "anchors" in raw and "out" in raw:
        sys.exit("这是生成时输出的 .json，不能直接当 anchors 用：新建一个文件，只写要改的键，例如 {\"t4v\": 8.9}")
    bad = set(raw) - ANCHOR_KEYS
    if bad:
        sys.exit(f"anchors 文件里有不认识的键：{sorted(bad)}；可用：{sorted(ANCHOR_KEYS)}")
    out = {}
    for k, v in raw.items():
        if k == "phrases":
            if not isinstance(v, list) or not all(isinstance(p, list) and len(p) == 2 for p in v):
                sys.exit("anchors 里 phrases 要写成 [[开始, 结束], …]（秒，录音文件里的时间）")
            pairs = [[_seconds("phrases", a), _seconds("phrases", b)] for a, b in v]
            for i, (a, b) in enumerate(pairs):
                if not 0 <= a < b <= 60:
                    sys.exit(f"anchors 里第 {i + 1} 句的 phrases [{a}, {b}] 不对：开始要小于结束，且在 0–60 秒内")
            out[k] = pairs
            continue
        vals = [_seconds(k, x) for x in (v if isinstance(v, list) else [v])]
        for x in vals:
            if not 0 <= x <= 20:
                sys.exit(f"anchors 里 {k}={x:g} 不在 0–20 秒之间")
        if k == "t3" and len(vals) != SYL_P3:
            sys.exit(f"anchors 里 t3 需要 {SYL_P3} 个时间（每个字一个）")
        out[k] = vals if isinstance(v, list) else vals[0]
    if out:
        print(f"  使用 anchors：{json.dumps(out, ensure_ascii=False)}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- voice

def cut_clip(x: np.ndarray, s: float, e: float) -> np.ndarray:
    """Phrase with 40 ms before and 120 ms after, 10 ms fades; pads are exact so the timeline maths hold."""
    a = int(round((s - PAD_BEFORE) * SR))
    b = int(round((e + PAD_AFTER) * SR))
    out = np.zeros(b - a)
    lo, hi = max(a, 0), min(b, len(x))
    out[lo - a:hi - a] = x[lo:hi]
    f = int(0.010 * SR)
    ramp = np.linspace(0, 1, f)
    out[:f] *= ramp
    out[-f:] *= ramp[::-1]
    return out


def respace(clips: list[np.ndarray], gaps: list[float] = GAPS):
    starts, phrases, t = [], [], NO_VOICE_PHRASES[0][0]
    for i, c in enumerate(clips):
        speech = len(c) / SR - PAD_BEFORE - PAD_AFTER
        phrases.append((t, t + speech))
        starts.append(t - PAD_BEFORE)
        t = t + speech + (gaps[i] if i < len(gaps) else 0)
    track = np.zeros(int((phrases[-1][1] + 4.0) * SR))
    for s, c in zip(starts, clips):
        mu.place(track, c, s)
    return track, phrases, starts


def rate_spread(x: np.ndarray, bounds, weights) -> float:
    """Fastest over slowest speaking rate (syllables per voiced second) of a split; 1.0 = perfectly even."""
    runs = speech_runs(x)
    voiced = [sum(min(b, r1) - max(a, r0) for r0, r1 in runs if r1 > a and r0 < b) for a, b in bounds]
    rates = [w / max(v, 1e-3) for w, v in zip(weights, voiced)]
    return max(rates) / min(rates)


def load_voice(args, n: int, overrides: dict):
    """Returns (voice track on the intro timeline, phrases, per-phrase runs, raw phrase bounds) or Nones."""
    if not (args.voice or args.voice_fixed or args.voice_topic):
        return None, list(NO_VOICE_PHRASES), None, None
    if args.voice and (args.voice_fixed or args.voice_topic):
        sys.exit("--voice 和 --voice-fixed/--voice-topic 只能二选一")
    if bool(args.voice_fixed) != bool(args.voice_topic):
        sys.exit("--voice-fixed 和 --voice-topic 要一起给")

    def read(path):
        if not Path(path).is_file():
            sys.exit(f"找不到录音文件：{path}")
        try:
            x = read_wav_mono(path)
        except subprocess.CalledProcessError:
            sys.exit(f"读不了录音文件（格式不对？）：{path}")
        if len(x) / SR > 60:
            sys.exit(f"录音有 {len(x) / SR:.0f} 秒长：请只给片头这几句（约 10 秒）的录音：{path}")
        return x

    w_fixed = [SYL_P1, SYL_P2, SYL_P3] if args.lines == 4 else [SYL_P1_SHORT, SYL_P3]
    nf = len(w_fixed)
    try:
        if args.voice:
            v = read(args.voice)
            raw = overrides.get("phrases") or detect_phrases(v, w_fixed + [6 + n])
            if len(raw) != nf + 1:
                sys.exit(f"anchors 里的 phrases 需要 {nf + 1} 句")
            clips = [cut_clip(v, s, e) for s, e in raw]
        else:
            v1 = read(args.voice_fixed)
            v4 = read(args.voice_topic)
            given = overrides.get("phrases")
            if given and len(given) not in (nf, nf + 1):
                sys.exit(f"用 --voice-fixed 时，anchors 里的 phrases 写前 {nf} 句"
                         f"（可再加最后一句在 --voice-topic 文件里的时间）")
            raw = list(given[:nf]) if given else detect_phrases(v1, w_fixed)
            if given and len(given) == nf + 1:
                raw.append(tuple(given[nf]))
            else:
                runs4 = speech_runs(v4)
                if not runs4:
                    sys.exit(f"{args.voice_topic} 里没找到人声")
                raw.append((runs4[0][0], runs4[-1][1]))
                rate = (6 + n) / max(sum(b - a for a, b in runs4), 1e-3)
                if not 1.6 <= rate <= 9.5:
                    sys.exit(f"第 {nf + 1} 句的录音长度和主题字数对不上（{runs4[-1][1] - runs4[0][0]:.1f} 秒，"
                             f"{6 + n} 个字）：请检查文件")
            clips = [cut_clip(v1, s, e) for s, e in raw[:nf]] + [cut_clip(v4, *raw[nf])]
        if args.lines == 3 and not overrides.get("phrases"):  # an old four-line file would split "fine" but wrong
            x = v if args.voice else v1
            w3 = w_fixed + ([6 + n] if args.voice else [])
            w4 = [SYL_P1, SYL_P2, SYL_P3] + ([6 + n] if args.voice else [])
            try:
                alt = detect_phrases(x, w4)
            except ValueError:
                alt = None
            if alt and rate_spread(x, alt, w4) < 0.75 * rate_spread(x, raw[:len(w3)], w3):
                sys.exit("这段录音像是四句版（带「我是原同」「我是顾东政」）：去掉 --lines 3，或换成只有三句的录音")
    except ValueError as e:
        hint = ""
        if args.lines == 4 and args.voice:
            try:
                detect_phrases(read(args.voice), [SYL_P1_SHORT, SYL_P3, 6 + n])
                hint = "。如果只录了三句（没有「我是原同」「我是顾东政」），加 --lines 3"
            except ValueError:
                pass
        sys.exit(f"切句失败：{e}{hint}")
    gaps = GAPS
    if args.lines == 3:  # fewer lines: keep the speaker's own pauses (the seam between two files gets the middle)
        lo, hi = GAP_RANGE_3
        gaps = [raw[i + 1][0] - raw[i][1] for i in range(len(raw) - 1)]
        if not args.voice:
            gaps[-1] = (lo + hi) / 2
        gaps = [min(max(g, lo), hi) for g in gaps]
    track, phrases, starts = respace(clips, gaps)
    runs = []
    for c, off in zip(clips, starts):
        rr = speech_runs(c, min_gap=0.04, min_run=0.03)
        runs.append([(a + off, b + off) for a, b in rr] or [(off + PAD_BEFORE, off + len(c) / SR - PAD_AFTER)])
    if args.lines == 3:  # no name lines: line 2 is an empty slot at the end of line 1
        phrases.insert(1, (phrases[0][1], phrases[0][1]))
        runs.insert(1, [])
    return track, phrases, runs, raw


# ---------------------------------------------------------------- topic

SENTENCE_PUNCT = set("？！。，、；：…—「」『』“”‘’《》〈〉【】（）()?!,;:\"'`~")


def normalise_topic(topic: str) -> str:
    """Drop sentence punctuation only (keeps in-word marks such as 2.0, C++, A/B, 7%)."""
    topic = unicodedata.normalize("NFKC", topic).replace("\u3000", " ")
    out = []
    for i, ch in enumerate(topic):
        if ch in SENTENCE_PUNCT:
            continue
        if unicodedata.category(ch).startswith("P") and not (
                0 < i < len(topic) - 1 and topic[i - 1].isalnum() and topic[i + 1].isalnum()):
            continue
        out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def topic_syllables(topic: str) -> int:
    n = 0
    for tok in re.findall(r"[A-Za-z]+|[0-9]|[\u3400-\u9fff]", topic):
        if tok.isdigit() or re.match(r"[\u3400-\u9fff]", tok):
            n += 1
            continue
        for part in re.findall(r"[A-Z]{2,}(?![a-z])|[A-Z]?[a-z]+|[A-Z]", tok):
            n += len(part) if part.isupper() else max(1, len(re.findall(r"[aeiouy]+", part.lower())))
    return max(n, 1)


def check_glyphs(topic: str):
    f = font("serif_black", 100)
    missing = [ch for ch in topic if ch != " " and f.getmask(ch).getbbox() is None]
    if missing:
        sys.exit(f"主题里有字体显示不了的字符：{''.join(missing)}")


def topic_advance(topic: str, size: int) -> float:
    f = font("serif_black", size)
    return sum(0.25 * size if ch == " " else f.getlength(ch) for ch in topic)


def topic_size(topic: str) -> int:
    s = min(TITLE_SIZE, math.floor(TOPIC_BUDGET / (topic_advance(topic, 100) / 100)))
    if s < TOPIC_FLOOR:
        sys.exit(f"主题太长，放不下（需要缩到 {s}px，下限 {TOPIC_FLOOR}px）：请缩短屏幕上的主题，念的时候可以长一些")
    return s


def topic_layer(topic: str, size: int):
    f = font("serif_black", size)
    pad = 12
    ascent, descent = f.getmetrics()
    width = topic_advance(topic, size)
    im = Image.new("RGBA", (int(math.ceil(width)) + 2 * pad, ascent + descent + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = float(pad)
    for ch in topic:
        if ch == " ":
            x += 0.25 * size
            continue
        d.text((x, pad), ch, font=f, fill=RED + (255,))
        x += f.getlength(ch)
    return Layer.from_pil(im), pad, width, ascent


# ---------------------------------------------------------------- easing helpers

def ease_in_out_quart(x):
    x = clamp01(x)
    return 8 * x ** 4 if x < 0.5 else 1 - (-2 * x + 2) ** 4 / 2


def ease_in_sine(x):
    return 1 - math.cos(math.pi * clamp01(x) / 2)


def ease_out_sine(x):
    return math.sin(math.pi * clamp01(x) / 2)


# ---------------------------------------------------------------- scene

class Scene:
    def __init__(self, args, T: Timing, topic: str, tsize: int, voice_env: np.ndarray | None):
        self.a, self.T, self.topic = args, T, topic
        self.paper = np.asarray(Image.open(ASSETS / "paper_plate.png").convert("RGB"), np.float32) / 255
        self.dark = np.asarray(Image.open(ASSETS / "dark_plate.png").convert("RGB"), np.float32) / 255
        # waveform at rest (bar positions of the show's cold-open meter; heights and alphas at rest)
        bars = json.loads((ASSETS / "coldopen_bars.json").read_text())
        cxs = [(b["x0"] + b["x1"]) / 2 for b in bars]
        self.bars = []
        for i, b in enumerate(bars):
            frac = (cxs[i] - cxs[0]) / (cxs[-1] - cxs[0])
            alpha = 0.25 + 0.40 * frac
            self.bars.append({"x0": b["x0"], "x1": b["x1"], "y0": 856, "y1": 863, "color": mix(DARK, WAVE, alpha),
                              "L": (cxs[i - 1] + cxs[i]) / 2 if i else cxs[0] - 6,
                              "R": (cxs[i] + cxs[i + 1]) / 2 if i + 1 < len(cxs) else cxs[-1] + 6})
        self.voice_env = voice_env
        self.p1 = args.p1_speaker or "wu"
        pad = self.pad = 8
        self.title = [text_layer(ch, "serif_black", TITLE_SIZE, INK, pad=pad)[0] for ch in "重估"]
        self.title_oy = BASELINE - font("serif_black", TITLE_SIZE).getmetrics()[0]
        self.sent_gray = [text_layer(ch, "sans_semibold", SENT_SIZE, GRAY, pad=pad)[0] for ch in SENT]
        self.sent_ink = [text_layer(ch, "sans_semibold", SENT_SIZE, INK, pad=pad)[0] for ch in SENT]
        self.moren_ink = text_layer("默认", "sans_semibold", SENT_SIZE, INK, pad=pad)[0]
        self.moren_gray = text_layer("默认", "sans_semibold", SENT_SIZE, GRAY, pad=pad)[0]
        self.moren_32 = text_layer("默认", "sans_semibold", 32, GRAY, pad=pad)[0]
        self.kick_light = [text_layer(ch, "sans_semibold", 34, LIGHT_GRAY, pad=pad)[0] for ch in KICKER]
        self.kick_dark = [text_layer(ch, "sans_semibold", 34, SECOND, pad=pad)[0] for ch in KICKER]
        self.kick_x0 = 96 - font("sans_semibold", 34).getbbox(KICKER[0])[0]
        self.topic_layer, self.topic_pad, self.topic_w, t_asc = topic_layer(topic, tsize)
        self.topic_oy = BASELINE - t_asc
        self.x_new = X_OLD + self.topic_w + 40
        self.date_layers = self._date_layers(args.date) if args.date else None
        # chrome (sizes measured on the episode body)
        self.names = {}
        for who, text in (("gu", "顾东政"), ("wu", "吴原同")):
            self.names[who] = (text_layer(text, "sans_semibold", 22, INK, tracking=1.5, pad=pad)[0],
                               text_layer(text, "sans_semibold", 22, GRAY, tracking=1.5, pad=pad)[0])
        self.name_bb = font("sans_semibold", 22).getbbox("顾东政")
        self.brand = text_layer("重估", "serif_black", 28, INK, pad=pad)[0]
        self.issue = text_layer(args.label or f"第 {args.episode} 期", "sans", 22, SECOND, pad=pad)[0]
        self.chapter = None
        if args.chapter:
            parts = args.chapter.replace("\u3000", " ").split(None, 1)
            num, title = (parts[0], parts[1]) if len(parts) == 2 and parts[0].isdigit() else ("", " ".join(parts))
            self.chapter = (text_layer(num, "sans_semibold", 22, RED, tracking=1, pad=pad) if num else None,
                            text_layer(title, "sans", 22, SECOND, pad=pad), title)
        self.chapter_ticks = args.chapter_ticks
        rng = np.random.default_rng(7)
        self.bar_phase = rng.uniform(0, 2 * np.pi, (7, 2))
        self.bar_freq = rng.uniform(3.0, 8.5, (7, 2))

    def _date_layers(self, date: str):
        f = font("sans_semibold", 28)
        cells = [(text_layer(ch, "sans_semibold", 28, GRAY, pad=self.pad)[0], 8 if ch == "." else 17, f.getlength(ch))
                 for ch in date]
        bb = f.getbbox("2026")
        return cells, sum(w for _, w, _ in cells), (bb[1] + bb[3]) / 2

    # ------------------------------------------------------------ state helpers
    def speaker_at(self, t):
        if self.voice_env is None:  # music-only intro: nobody speaks, so no speaker chip lights up
            return "none", "none", -10.0
        T = self.T
        seq = list(zip([T.P1s, T.P2s, T.P3s, T.P4s], [self.p1, "gu", self.a.p3_speaker, self.a.p4_speaker]))
        if T.lines == 3:
            del seq[1]
        cur, prev, since = seq[0][1], seq[0][1], -10.0
        for s, k in seq:
            if t >= s:
                prev, cur, since = cur, k, s
        return cur, prev, since

    def envelope(self, t):
        if self.voice_env is None:
            return 0.0
        k = int(t * FPS)
        return float(self.voice_env[k]) if 0 <= k < len(self.voice_env) else 0.0

    def line_y(self, t):
        T = self.T
        if t >= T.R0:
            return lerp(Y_R, Y_T, ease_in_out_cubic(prog(t, T.R0, T.R1 - T.R0)))
        return lerp(859.5, Y_R, ease_in_out_cubic(prog(t, 0.350, 0.500)))

    def dot_x(self, t):
        T = self.T
        if t < T.T0:
            return X_OLD
        return X_OLD + T.d * ease_in_out_sine(prog(t, T.T0, T.T1 - T.T0))

    # ------------------------------------------------------------ frame
    def band(self, t):
        e = ease_in_out_quart(prog(t, 0.480, 0.520))
        yc = self.line_y(t)
        return yc * (1 - e), yc + (H - yc) * e, e

    def frame(self, t: float, span: float = 0.0) -> Canvas:
        """span: shutter time this sample stands for; the paper wipe edges are integrated over it analytically."""
        c = Canvas(self.dark)
        if t + span / 2 >= 0.480:
            self._paste_band(c, t, span)
        self.draw_line_and_ticks(c, t)
        self.draw_measure(c, t)
        self.draw_text(c, t)
        self.draw_dots(c, t)
        self.draw_chrome(c, t)
        return c

    def _paste_band(self, c, t, span):
        top0, bot0, e0 = self.band(t - span / 2)
        top1, bot1, e1 = self.band(t + span / 2)
        if max(e0, e1) <= 0:
            return
        t_lo, t_hi = min(top0, top1), max(top0, top1)
        b_lo, b_hi = min(bot0, bot1), max(bot0, bot1)
        i0, i1 = max(int(math.floor(t_lo)), 0), min(int(math.ceil(b_hi)) + 1, H)
        if i1 <= i0:
            return
        y = np.arange(i0, i1, dtype=np.float32)
        if t_hi - t_lo > 1:   # fraction of the shutter during which the row is inside the band
            ct = np.clip(((y + 0.5) - t_lo) / (t_hi - t_lo), 0, 1)
        else:
            ct = np.clip(y + 1 - (t_lo + t_hi) / 2, 0, 1)
        if b_hi - b_lo > 1:
            cb = np.clip(((y + 0.5) - b_lo) / (b_hi - b_lo), 0, 1)
            cb = 1 - cb
        else:
            cb = np.clip((b_lo + b_hi) / 2 - y, 0, 1)
        cov = np.minimum(ct, cb)[:, None, None]
        if e0 <= 0 or e1 <= 0:  # the band is born inside this shutter
            cov = cov * (max(e0, e1) > 0)
        c.px[i0:i1] = self.dark[i0:i1] * (1 - cov) + self.paper[i0:i1] * cov

    def draw_line_and_ticks(self, c, t):
        T = self.T
        y = self.line_y(t)
        line_col = mix(mix(DARK, WAVE, 0.75), SECOND, ease_in_out_cubic(prog(t, 0.480, 0.250)))
        line_a = 1.0
        if t >= T.R0:
            line_col = mix(SECOND, TIMELINE, ease_in_out_cubic(prog(t, T.R0, T.R1 - T.R0)))
            # passes faintly behind the kicker and headline (smooth in and out of the band)
            dist = max(TEXT_BAND[0] - y, y - TEXT_BAND[1], 0.0)
            line_a = 1 - 0.7 * (1 - clamp01(dist / 24))
        if t < 0.400:
            flat = ease_out_cubic(prog(t, 0.0, 0.250))
            widen = ease_in_out_sine(prog(t, 0.150, 0.250))
            for b in self.bars:
                hh = lerp(b["y1"] + 1 - b["y0"], 2.0, flat)
                col = mix(b["color"], mix(DARK, WAVE, 0.75), flat)
                c.fill_rect(lerp(b["x0"], b["L"], widen), y - hh / 2, lerp(b["x1"], b["R"], widen), y + hh / 2, col)
        else:
            s = ease_in_out_cubic(prog(t, 0.350, 0.500))
            c.fill_rect(lerp(self.bars[0]["L"], X0, s), y - 1, lerp(self.bars[-1]["R"], X1, s), y + 1, line_col,
                        alpha=line_a)
        if t >= T.P3s:
            fade = 1.0 if t < T.R0 else 1 - ease_in_sine(prog(t, T.R0, 0.3 * (T.R1 - T.R0)))
            if fade > 0:
                for j in range(40):
                    x = 96 + 44 * j
                    g = ease_out_cubic(prog(t, T.P3s + 0.100 + (x - 96) / 1728 * 0.600, 0.160))
                    if g <= 0:
                        continue
                    if j % 5 == 0:
                        c.fill_rect(x - 1, y - 7 * g, x + 1, y + 7 * g, SECOND, alpha=fade)
                    else:
                        c.fill_rect(x, y - 4 * g, x + 1, y + 4 * g, MINOR_TICK, alpha=fade)
        if t >= T.R0 and self.chapter_ticks:
            a = ease_out_sine(prog(t, T.R0 + 0.65 * (T.R1 - T.R0), 0.35 * (T.R1 - T.R0)))
            for x in self.chapter_ticks:
                c.fill_rect(x, y - 6, x + 2, y + 6, CH_TICK, alpha=a)

    def draw_measure(self, c, t):
        T = self.T
        if t >= T.T0:
            x = self.dot_x(t)
            if x > X_OLD + 14:
                c.fill_rect(X_OLD + 14, Y_R - 2, x, Y_R + 2, RED)
        if t >= T.t4v:
            a = prog(t, T.t4v, 0.200)
            self._paper_disc(c, X_OLD, Y_R, 9.5, a)
            c.disc(X_OLD, Y_R, 11, GHOST, alpha=a, ring=2)

    def _paper_disc(self, c, cx, cy, r, alpha):
        ix0, iy0, ix1, iy1 = int(cx - r - 2), int(cy - r - 2), int(cx + r + 3), int(cy + r + 3)
        ys, xs = np.mgrid[iy0:iy1, ix0:ix1].astype(np.float32)
        cov = np.clip(r - np.sqrt((xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2) + 0.5, 0, 1)[..., None] * alpha
        c.px[iy0:iy1, ix0:ix1] = c.px[iy0:iy1, ix0:ix1] * (1 - cov) + self.paper[iy0:iy1, ix0:ix1] * cov

    def _two_tone(self, c, lo, hi, x, y, a, k):
        """Karaoke without a coverage dip: base colour at full alpha, target colour over it at alpha k."""
        pad = self.pad
        if a <= 0:
            return
        if k < 1:
            c.blit(lo, x, y, alpha=a, ox=pad, oy=pad)
        if k > 0:
            c.blit(hi, x, y, alpha=a * k, ox=pad, oy=pad)

    def draw_text(self, c, t):
        T, pad = self.T, self.pad
        # 重估 rises out of the ruler (2 px feather into the line)
        x = 96.0
        for L, st in zip(self.title, [T.t1g - 0.150, T.t1g - 0.070]):
            if t >= st:
                y = self.title_oy + 250 * (1 - ease_out_quint(prog(t, st, 0.850)))
                c.blit(L, x, y, ox=pad, oy=pad, clip=(0, 0, W, 593))
                c.blit(L, x, y, alpha=0.66, ox=pad, oy=pad, clip=(0, 593, W, 594))
                c.blit(L, x, y, alpha=0.33, ox=pad, oy=pad, clip=(0, 594, W, 595))
            x += TITLE_SIZE
        # P3 sentence with karaoke
        if t >= T.P3s - 0.100:
            appear = prog(t, T.P3s - 0.100, 0.200)
            gone = prog(t, T.P3e + 0.050, 0.200)
            for i in range(SYL_P3):
                if i in (9, 10):
                    continue
                self._two_tone(c, self.sent_gray[i], self.sent_ink[i], 96 + 44 * i, SENT_Y, appear * (1 - gone),
                               prog(t, T.t3[i] - KARAOKE_LEAD, 0.120))
            self.draw_moren(c, t, appear)
        # kicker 今 天 我 们
        if t >= T.P4s - 0.120:
            a = ease_out_cubic(prog(t, T.P4s - 0.120, 0.150))
            f34 = font("sans_semibold", 34)
            x = self.kick_x0
            for i, ch in enumerate(KICKER):
                on = ((T.P4s, T.t4t)[i] if i < 2 else T.t4w + 0.060 * (i - 2)) - KARAOKE_LEAD
                self._two_tone(c, self.kick_light[i], self.kick_dark[i], x, 255 + 6 * (1 - a), a, prog(t, on, 0.080))
                x += f34.getlength(ch) + 11
        # topic, written by the travelling dot
        if t >= T.T0:
            E = self.dot_x(t) - 10
            L, ox = self.topic_layer, self.topic_pad
            cols = np.arange(L.w, dtype=np.float32) - ox + X_OLD
            ramp = np.clip((E - cols) / 24.0, 0, 1)
            if ramp.max() > 0:
                c.blit(Layer(L.rgba * ramp[None, :, None]), X_OLD, self.topic_oy, ox=ox, oy=ox)
        # recording date under the new mark, centred on the 默认 label's line
        if self.date_layers and t >= T.L:
            a = ease_out_cubic(prog(t, T.L, 0.250))
            cells, total, mid = self.date_layers
            x = min(self.x_new, 1748) - total / 2
            y = 633.5 - mid + 6 * (1 - a)
            for L, w, adv in cells:
                c.blit(L, x + (w - adv) / 2, y, alpha=a, ox=pad, oy=pad)
                x += w

    def draw_moren(self, c, t, appear):
        T, pad = self.T, self.pad
        g = ease_in_out_cubic(prog(t, T.P3e + 0.050, 0.400))
        if g <= 0:
            for idx in (9, 10):
                self._two_tone(c, self.sent_gray[idx], self.sent_ink[idx], 96 + 44 * idx, SENT_Y, appear,
                               prog(t, T.t3[idx] - KARAOKE_LEAD, 0.120))
            return
        f44, f32 = font("sans_semibold", 44), font("sans_semibold", 32)
        b44, b32 = f44.getbbox("默认"), f32.getbbox("默认")
        s = lerp(1.0, 32 / 44, g)
        cx = lerp(492 + (b44[0] + b44[2]) / 2, X_OLD, g)
        top = lerp(SENT_Y + b44[1], 618, g)
        ox, oy = pad + (b44[0] + b44[2]) / 2, pad + b44[1]
        native = prog(t, T.P3e + 0.370, 0.080)
        if native < 1:  # ink -> gray without a dip: gray underneath at full alpha, ink over it fading out
            c.blit(self.moren_gray, cx, top, scale=s, ox=ox, oy=oy)
            c.blit(self.moren_ink, cx, top, alpha=1 - g, scale=s, ox=ox, oy=oy)
        if native > 0:
            c.blit(self.moren_32, cx, top, alpha=native, ox=pad + (b32[0] + b32[2]) / 2, oy=pad + b32[1])

    def draw_dots(self, c, t):
        T = self.T
        st = T.t3d - 0.040
        if t < st:
            return
        y = lerp(Y_R - 28, Y_R, ease_out_back(prog(t, st, 0.240), 1.2))
        a = prog(t, st, 0.100)
        lift = ease_out_cubic(prog(t, T.t4v - 0.100, 0.250))
        if lift > 0:
            y = Y_R - 22 * lift
        scale = 1 + 0.15 * lift
        if t >= T.T1:
            sd = prog(t, T.T1, 0.120)
            y = lerp(Y_R - 22, Y_R, sd * sd)
            scale = lerp(1.15, 1.0, sd)
        x = self.dot_x(t)
        if lift > 0:
            c.disc(x, y, 19 * scale, RED, alpha=0.22 * lift)
        c.disc(x, y, 11 * scale, mix(INK, RED, lift), alpha=a)
        if t >= T.L:
            p = ease_out_cubic(prog(t, T.L, 0.420))
            if p < 1:
                c.disc(x, Y_R, lerp(11, 32, p), RED, alpha=0.45 * (1 - p), ring=2)

    def draw_chrome(self, c, t):
        T, pad = self.T, self.pad
        a = ease_out_cubic(prog(t, T.t1n - 0.200, 0.250))
        if a > 0:
            self.draw_chips(c, t, a)
            self.draw_voice_bars(c, t, a)
        if t >= T.R1 - 0.040:
            p = prog(t, T.R1 - 0.040, 0.200)
            sc = lerp(0.6, 1.0, ease_out_back(p, 1.2))
            on = min(1.0, p * 3)
            c.fill_rect(96, Y_T - 6 * sc, 98, Y_T + 6 * sc, RED, alpha=on)
            hp = prog(t, T.R1 + 0.160, 0.350)
            if 0 < hp < 1:
                c.disc(104, Y_T, lerp(15, 26, ease_out_cubic(hp)), RED, alpha=0.30 * (1 - hp))
            c.disc(104, Y_T, 15 * sc, RED, alpha=0.18 * on)
            c.disc(104, Y_T, 9 * sc, RED, alpha=on)
        if t >= T.R1 - 0.150:
            p = ease_out_cubic(prog(t, T.R1 - 0.150, 0.250))
            dx = -10 * (1 - p)
            b = font("serif_black", 28).getbbox("重估")
            c.blit(self.brand, 97 - b[0] + dx, 53 - b[1], alpha=p, ox=pad, oy=pad)
            c.disc(182 + dx, 66.5, 2.6, BULLET, alpha=p)
            bi = font("sans", 22).getbbox("第")
            c.blit(self.issue, 211 - bi[0] + dx, 58 - bi[1], alpha=p, ox=pad, oy=pad)
            if self.chapter:
                num, (Lt, mt), title = self.chapter
                bt = font("sans", 22).getbbox(title)
                xt = 1821 - dx - bt[2]
                c.blit(Lt, xt, 54 - bt[1], alpha=p, ox=pad, oy=pad)
                if num:
                    Ln, mn = num
                    c.blit(Ln, xt - 14 - mn["width"], 54 - bt[1], alpha=p, ox=pad, oy=pad)

    def draw_chips(self, c, t, a):
        cur, prev, since = self.speaker_at(t)
        k = prog(t, since, 0.200)
        grow_k = ease_out_cubic(prog(t, since, 0.220))
        on = lambda who, state: 1.0 if state in (who, "both") else 0.0
        for who, cx, dot, ring, idle, nx in (("gu", 101, DOT_TEAL, RING_TEAL, IDLE_TEAL, 120),
                                             ("wu", 232, DOT_AMBER, RING_AMBER, IDLE_AMBER, 250)):
            now, before = on(who, cur), on(who, prev)
            act = lerp(before, now, k)
            grow = lerp(0.7, 1.0, grow_k) if now > before else 1.0
            if act > 0:
                c.disc(cx, 1025, 16 * grow, CHIP_FILL, alpha=a * act * 0.85)
                c.disc(cx, 1025, 17.5 * grow, ring, alpha=a * act, ring=2.4)
            c.disc(cx, 1025, lerp(5, 7, act), mix(idle, dot, act), alpha=a)
            ink, gray = self.names[who]
            y = 1025 - (self.name_bb[1] + self.name_bb[3]) / 2
            x = nx - self.name_bb[0]
            self._two_tone(c, gray, ink, x, y, a, act)

    def draw_voice_bars(self, c, t, a):
        cur, prev, since = self.speaker_at(t)
        k = prog(t, since, 0.150)
        env = self.envelope(t)

        def col_for(state, i):
            if state == "none":
                return BAR_IDLE
            if state == "both":
                return BAR_AMBER if i % 2 == 0 else BAR_TEAL
            return BAR_AMBER if state == "wu" else BAR_TEAL

        for i in range(7):
            w = 0.5 + 0.25 * sum(math.sin(2 * math.pi * self.bar_freq[i, j] * t + self.bar_phase[i, j])
                                 for j in range(2))
            hh = 4 + 30 * env * (0.15 + 0.85 * w)
            x = 1746 + 12 * i
            c.rounded_rect(x, 1025 - hh / 2, x + 6, 1025 + hh / 2, 3, mix(col_for(prev, i), col_for(cur, i), k),
                           alpha=a)


# ---------------------------------------------------------------- music

HZ = {k: mu.note_hz(k) for k in ["C2", "G2", "C3", "E3", "G3", "D4", "E4", "Eb3", "Bb3", "F4", "Bb4", "D5", "E5",
                                  "G5", "Eb2"]}


def db(x):
    return 10 ** (x / 20)


def onepole(x, hz):
    from scipy.signal import lfilter
    a = math.exp(-2 * math.pi * hz / SR)
    return lfilter([1 - a], [1, -a], x)


def build_music(T: Timing, total: float, hold: float = 0.5) -> np.ndarray:
    """Original bed: Csus2 -> C (the default) -> Eb add9 (re-valued), never resolving back."""
    n = int(total * SR)
    t = np.arange(n) / SR
    chords = {"A": [HZ["C3"], HZ["G3"], HZ["D4"]], "B": [HZ["C3"], HZ["G3"], HZ["E4"]],
              "C": [HZ["Eb3"], HZ["G3"], HZ["Bb3"], HZ["F4"]]}

    def pad_voice(freqs):
        out = np.zeros(n)
        for f in freqs:
            for d in (-0.7, 0.7):
                out += np.sin(2 * np.pi * (f + d) * t + d)
        return out / (2 * len(freqs))

    x1, x2 = T.t3d, T.t4v - 0.250
    wA = np.cos(np.clip((t - x1) / 0.4, 0, 1) * np.pi / 2)
    wB = np.sin(np.clip((t - x1) / 0.4, 0, 1) * np.pi / 2) * np.cos(np.clip((t - x2) / 0.4, 0, 1) * np.pi / 2)
    wC = np.sin(np.clip((t - x2) / 0.4, 0, 1) * np.pi / 2)
    pad = wA * pad_voice(chords["A"]) + wB * pad_voice(chords["B"]) + wC * pad_voice(chords["C"])
    env = np.clip(t / 0.8, 0, 1) ** 1.5
    env *= 1 + (db(3) - 1) * np.clip((t - T.P4e) / max(T.R1 - T.P4e, 0.05), 0, 1)
    tail = max(0.0, hold - 0.5)  # a longer hold on the last frame keeps the bed under it
    fade = np.cos(np.clip((t - (T.END + tail - 0.300)) / 0.650, 0, 1) * np.pi / 2) ** 2
    pad = onepole(pad * env * fade, 1500)
    pad *= db(-30) / (np.max(np.abs(pad)) + 1e-9)

    pn = np.zeros(n)

    def pno(name, at, dbfs, dur=3.2):
        f = HZ[name]
        sig = mu.piano(f, dur, amp=1.0, decay=2.4 if f < 261 else 1.6)
        mu.place(pn, sig / (np.max(np.abs(sig)) + 1e-9) * db(dbfs), at)

    pno("C2", 0.480, -26, 5.0)
    pno("G2", 0.480, -27, 5.0)
    pno("G5", T.t1g, -22)
    pno("E4", T.t1g, -32)
    if T.lines == 4:  # one note per spoken name
        pno("E5", T.t1n, -28)
        pno("D5", T.t2n, -28)
    pno("C3", T.t3d, -30, 4.0)
    pno("G3", T.t3d, -31, 4.0)
    pno("E4", T.t3d, -31)
    eb = mu.piano(HZ["Eb2"], 4.0, amp=1.0, decay=2.4)
    mu.place(pn, onepole(eb / np.max(np.abs(eb)), 800) * db(-34), T.t4v - 0.250)
    pno("G5", T.t4v - 0.100, -22)        # the same value note, now over Eb (struck at the lift)
    pno("Bb4", T.L, -28)
    pn = onepole(pn, 3500) * fade

    sub = np.zeros(n)
    k = T.P3s
    while k < T.t4v - 0.300:
        s = mu.sub_pulse(HZ["C2"], 0.4, amp=1.0, decay=0.09)
        s *= np.cos(np.clip((np.arange(len(s)) / SR - 0.3) / 0.1, 0, 1) * np.pi / 2)
        mu.place(sub, s / np.max(np.abs(s)) * db(-30), k)
        k += 0.750

    tl, tr = np.zeros(n), np.zeros(n)
    for j in range(0, 40, 5):
        x = 96 + 44 * j
        st = T.P3s + 0.100 + (x - 96) / 1728 * 0.600
        s = mu.tick(0.06, amp=1.0, freq=2637, seed=j)
        tt = np.arange(len(s)) / SR
        s = s + 0.5 * np.sin(2 * np.pi * 1319 * tt) * np.exp(-tt / 0.02)
        s = s / np.max(np.abs(s)) * db(-42)
        pan = (x - 960) / 864 * 0.6
        mu.place(tl, s * math.cos((pan + 1) * math.pi / 4), st)
        mu.place(tr, s * math.sin((pan + 1) * math.pi / 4), st)

    bus = pad + pn
    wet = np.stack([mu.room(bus, 1.6, 0.18, seed=3), mu.room(bus, 1.6, 0.18, seed=4)])
    return wet + np.stack([sub, sub]) + np.stack([tl, tr])


def duck(music: np.ndarray, voice: np.ndarray, depth_db: float = 10.0, bridge_until: float | None = None) -> np.ndarray:
    """Sidechain with a 350 ms hold and slow release, so short gaps between lines do not make the bed breathe.

    bridge_until (end of the last line): before it the hold is 850 ms, longer than any kept pause, so pauses between
    and inside lines stay ducked; after it the held level releases smoothly and the bed comes back."""
    from scipy.ndimage import maximum_filter1d
    raw = mu.envelope_follow(voice, attack=0.02, release=0.6)
    hold = int(0.35 * SR)
    env = maximum_filter1d(raw, size=hold, origin=(hold - 1) // 2)  # holds the last 350 ms
    if bridge_until is not None:
        hl = int(0.85 * SR)
        long = maximum_filter1d(raw, size=hl, origin=(hl - 1) // 2)
        k = min(max(int(bridge_until * SR), 1), len(env))
        env[:k] = long[:k]
        env[k:] = np.maximum(env[k:], long[k - 1] * np.exp(-np.arange(len(env) - k) / (0.25 * SR)))
    voiced = env[env > np.max(env) * 0.05]
    ref = np.median(voiced) if len(voiced) else 1.0
    level = np.clip(env / (ref + 1e-9), 0, 1)
    return music * 10 ** (-depth_db * level / 20)


def master(mixdown: np.ndarray, target_lufs: float, tmp: Path) -> Path:
    """Linear gain to the target loudness, then a gentle true-peak limit to -1.5 dBTP."""
    raw = tmp / "mix.wav"
    write_wav_float(raw, mixdown.T)
    m = measure_loudness(raw)
    out = tmp / "master.wav"
    gain = target_lufs - m["I"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    f"volume={gain:.2f}dB,alimiter=limit=0.84:attack=2:release=60:level=disabled",
                    "-c:a", "pcm_f32le", str(out)], check=True)
    return out


# ---------------------------------------------------------------- main

def check_tools():
    import shutil
    if not shutil.which("ffmpeg"):
        sys.exit("需要先安装 ffmpeg：brew install ffmpeg")
    try:
        import scipy  # noqa: F401
    except ImportError:
        sys.exit("需要先安装 Python 库：pip3 install numpy scipy pillow")


class ChineseArgs(argparse.ArgumentParser):
    def error(self, message):
        sys.exit(f"参数有误：{message}\n例子：python3 make_intro.py --topic 青年交流 --episode 2 --voice 片头录音.m4a")


def main():
    check_tools()
    ap = ChineseArgs(description="Render the 《重估》 intro.")
    ap.add_argument("--topic", required=True, help="on-screen topic, e.g. 青年交流")
    ap.add_argument("--topic-syllables", type=int, default=None, help="how many syllables the spoken topic has")
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--label", default=None, help='optional issue label shown instead of "第 N 期", e.g. 3.1 for the first half of episode 3')
    ap.add_argument("--date", default=None, help="recording date YYYY.MM.DD under the new mark (optional)")
    ap.add_argument("--chapter", default=None, help='optional first chapter label for the top bar, e.g. "01 不谈不行"')
    ap.add_argument("--chapter-ticks", default="", help="optional chapter tick x positions, comma-separated")
    ap.add_argument("--voice", help="one recording with all lines (4, or 3 with --lines 3)")
    ap.add_argument("--voice-fixed", help="the fixed lines (1-3, or 1-2 with --lines 3), reused every episode")
    ap.add_argument("--voice-topic", help="the last line (per episode)")
    ap.add_argument("--anchors", help="JSON overriding anchors (seconds on the intro timeline); "
                                      "'phrases' = raw line bounds in the recording")
    ap.add_argument("--lines", type=int, default=4, choices=[3, 4],
                    help="4: 这里是《重估》，我是原同。/ 我是顾东政。/ … ; 3: 这里是《重估》。/ … (no name lines)")
    ap.add_argument("--p1-speaker", default=None, choices=["wu", "gu", "both"], help="who says line 1 (--lines 3)")
    ap.add_argument("--p3-speaker", default="both", choices=["wu", "gu", "both"])
    ap.add_argument("--p4-speaker", default="both", choices=["wu", "gu", "both"])
    ap.add_argument("--handoff", default="fade", choices=["fade", "hold"],
                    help="fade: end on bare paper (default); hold: end on the finished frame")
    ap.add_argument("--hold", type=float, default=0.5, help="seconds on the finished frame before the end/fade")
    ap.add_argument("--total-frames", type=int, default=None,
                    help="exact length in frames (sets --hold), e.g. 704 to keep the episode edit unchanged")
    ap.add_argument("--out", default=None)
    ap.add_argument("--frames", default=None, help="render only these times (s) as PNG stills into ./stills")
    args = ap.parse_args()
    try:
        args.chapter_ticks = [float(v) for v in args.chapter_ticks.split(",") if v.strip()]
        frame_times = [float(v) for v in args.frames.split(",")] if args.frames else None
    except ValueError:
        sys.exit("--chapter-ticks / --frames 要写成用逗号隔开的数字")
    if args.date:
        import datetime
        try:
            datetime.datetime.strptime(args.date, "%Y.%m.%d")
        except ValueError:
            sys.exit("--date 格式是 YYYY.MM.DD，例如 2026.09.27")
    if args.episode < 1:
        sys.exit("--episode 要大于 0")
    if args.total_frames is None and not 0 <= args.hold <= 5:
        sys.exit("--hold 在 0–5 秒之间")
    if args.lines == 3 and not (args.voice or args.voice_fixed or args.voice_topic):
        sys.exit("--lines 3 要配录音（--voice，或 --voice-fixed 加 --voice-topic）")
    if args.p1_speaker and args.lines == 4:
        sys.exit("--p1-speaker 只用于 --lines 3（四句版第 1 句是「我是原同」）")
    if args.out and Path(args.out).suffix.lower() not in (".mp4", ".mov"):
        sys.exit("--out 要以 .mp4 或 .mov 结尾")

    topic = normalise_topic(args.topic)
    if not topic:
        sys.exit("主题是空的")
    if topic != args.topic.strip():
        print(f"  屏幕上会显示：{topic}", file=sys.stderr)
    check_glyphs(topic)
    n = args.topic_syllables or topic_syllables(topic)
    tsize = topic_size(topic)
    overrides = load_overrides(args.anchors)
    voice_track, phrases, runs, raw = load_voice(args, n, overrides)
    T = Timing(phrases, n, topic_advance(topic, tsize), runs, overrides, args.lines)

    fade_len = 0.350 if args.handoff == "fade" else 0.0
    if args.total_frames is not None:  # replaces --hold
        extra = 1 if fade_len else 0
        least = int(math.ceil((T.END + fade_len) * FPS - 1e-6)) + extra
        most = int(math.floor((T.END + 5 + fade_len) * FPS + 1e-6)) + extra
        if not least <= args.total_frames <= most:
            sys.exit(f"--total-frames {args.total_frames} 不行：这段录音要在 {least}–{most} 帧之间（结尾停留 0–5 秒）")
        args.hold = max(0.0, (args.total_frames - extra) / FPS - T.END - fade_len)
    nframes = args.total_frames if args.total_frames is not None else \
        int(math.ceil((T.END + args.hold + fade_len) * FPS)) + (1 if fade_len else 0)
    total = nframes / FPS
    fade_start = T.END + args.hold

    env = None
    if voice_track is not None:
        hop = SR // FPS
        vv = np.pad(voice_track, (0, max(0, nframes * hop - len(voice_track))))[: nframes * hop]
        rms = np.sqrt((vv.reshape(nframes, hop) ** 2).mean(1))
        ref = np.percentile(rms[rms > rms.max() * 0.05], 90) if (rms > 0).any() else 1.0
        env = np.clip(rms / (ref + 1e-9), 0, 1)
        sm, v_ = np.zeros_like(env), 0.0
        for i, e in enumerate(env):
            v_ = e if e > v_ else v_ * 0.80 + e * 0.20
            sm[i] = v_
        env = sm

    scene = Scene(args, T, topic, tsize, env)
    windows = T.fast_windows()
    shutter = 0.5 / FPS  # 180 degrees

    def render(ts: float) -> np.ndarray:
        samples = max([k for a, b, k in windows if a <= ts <= b], default=1)
        if samples > 1:
            acc = None
            for i in range(samples):
                sub = ts + ((i + 0.5) / samples - 0.5) * shutter
                px = scene.frame(sub, span=shutter / samples).px
                acc = px if acc is None else acc + px
            px = acc / samples
        else:
            px = scene.frame(ts).px
        if fade_len and ts > fade_start:
            k = clamp01((ts - fade_start) / (total - 1 / FPS - fade_start))
            k = k * k * (3 - 2 * k)
            px = px + (scene.paper - px) * k
        return px

    if frame_times:
        d = HERE / "stills"
        d.mkdir(exist_ok=True)
        for ts in frame_times:
            Image.fromarray((np.clip(render(ts), 0, 1) * 255 + .5).astype(np.uint8)).save(d / f"intro_{ts:06.3f}.png")
        print(json.dumps({"stills": str(d)}, ensure_ascii=False))
        return

    # audio
    music = build_music(T, total + 2.0, args.hold)[:, : int(round(total * SR))]
    tmp = Path(tempfile.mkdtemp())
    if voice_track is not None:
        vt = np.zeros(music.shape[1])
        m = min(len(vt), len(voice_track))
        vt[:m] = voice_track[:m]
        vt = mu.loudness_match(vt, -20.0)
        music = np.stack([duck(music[0], vt, bridge_until=T.P4e), duck(music[1], vt, bridge_until=T.P4e)])
        mixdown = music + np.stack([vt, vt])
        target = -14.0
    else:
        mixdown = music
        target = -18.0
    end_fade = np.cos(np.clip((np.arange(mixdown.shape[1]) / SR - (total - 0.200)) / 0.180, 0, 1) * np.pi / 2) ** 2
    mixdown = mixdown * end_fade
    wav = master(mixdown, target, tmp)

    slug = re.sub(r"[\s/\\:*?\"<>|]+", "", topic)
    out = Path(args.out) if args.out else HERE.parent / "outputs" / (
        f"重估_片头_{args.label or f'第{args.episode}期'}_{slug}{'' if voice_track is not None else '_无人声'}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = open_encoder(out, wav)
    t0 = time.time()
    try:
        for k in range(nframes):
            enc.stdin.write((np.clip(render(k / FPS), 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
            if k % 120 == 0:
                print(f"  frame {k}/{nframes}  {time.time() - t0:.0f}s", file=sys.stderr)
        enc.stdin.close()
    except BrokenPipeError:
        pass
    if enc.wait() != 0:
        sys.exit(f"ffmpeg 编码失败（输出路径能写吗？{out}）")
    info = {"out": str(out), "seconds": round(total, 3), "frames": nframes, "topic": topic, "topic_px": tsize,
            "voice": bool(voice_track is not None), "lines": args.lines, "hold": round(args.hold, 3),
            "phrases_in_recording": [[round(a, 3), round(b, 3)] for a, b in raw] if raw else None,
            "phrases": [[round(a, 3), round(b, 3)] for a, b in T.phrases],
            "anchors": {k: round(getattr(T, k), 3) for k in ANCHOR_ORDER},
            "t3": [round(x, 3) for x in T.t3],
            "derived": {k: round(getattr(T, k), 3) for k in ["T0", "T1", "L", "R0", "R1", "END"]},
            "voiced_runs": [[[round(a, 3), round(b, 3)] for a, b in r] for r in runs] if runs else None,
            "loudness": measure_loudness(wav)}
    out.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
