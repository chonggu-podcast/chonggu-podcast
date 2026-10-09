"""Small frame renderer for the 《重估》 intro: layers, text, easing, audio sync, encoding.

Everything is drawn with PIL + numpy at 1920x1080 and piped to ffmpeg. Text layers are rendered once
and placed with sub-pixel affine resampling, so slow moves do not jitter at 60 fps.
"""
from __future__ import annotations

import glob
import math
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 60
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

# Colours sampled from 对谈 第 2 期 (1920x1080 frames).
PAPER = (236, 232, 224)
INK = (27, 25, 21)
GRAY = (142, 138, 131)
LIGHT_GRAY = (196, 191, 182)
RED = (196, 52, 44)
AMBER = (181, 140, 70)
AMBER_SOFT = (214, 190, 146)
TEAL = (43, 84, 89)
TEAL_SOFT = (148, 170, 168)
DARK = (23, 23, 19)
WHITE = (240, 236, 228)


def _pingfang() -> str:
    hits = glob.glob("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/PingFang.ttc")
    if not hits:
        raise SystemExit("PingFang.ttc not found (macOS downloads it on first use in Font Book)")
    return hits[0]


SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
FONT_FILES = {
    "serif_black": (SONGTI, 0),
    "serif_bold": (SONGTI, 1),
    "serif": (SONGTI, 6),
    "sans_semibold": (None, 11),
    "sans_medium": (None, 7),
    "sans": (None, 3),
    "sans_light": (None, 15),
}


@lru_cache(maxsize=None)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path, index = FONT_FILES[name]
    return ImageFont.truetype(path or _pingfang(), size, index=index)


# ---------------------------------------------------------------- easing

def clamp01(x: float) -> float:
    return 0.0 if x <= 0 else 1.0 if x >= 1 else x


def prog(t: float, start: float, dur: float) -> float:
    return clamp01((t - start) / dur) if dur > 0 else float(t >= start)


def ease_out_cubic(x): x = clamp01(x); return 1 - (1 - x) ** 3
def ease_in_cubic(x): x = clamp01(x); return x ** 3
def ease_in_out_cubic(x):
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
def ease_out_quint(x): x = clamp01(x); return 1 - (1 - x) ** 5
def ease_in_out_sine(x): x = clamp01(x); return -(math.cos(math.pi * x) - 1) / 2


def ease_out_back(x, s=1.4):
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def spring(x, damping=6.0, freq=2.2):
    """Settles from 0 to 1 with a small overshoot; x in [0, 1]."""
    x = clamp01(x)
    return 1 - math.exp(-damping * x) * math.cos(2 * math.pi * freq * x)


def lerp(a, b, x):
    return a + (b - a) * x


def mix(c1, c2, x):
    return tuple(lerp(a, b, x) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- layers

class Layer:
    """Premultiplied RGBA float32 image with an anchor offset."""

    def __init__(self, rgba: np.ndarray):
        self.rgba = rgba  # H x W x 4, premultiplied, 0..1

    @property
    def w(self): return self.rgba.shape[1]

    @property
    def h(self): return self.rgba.shape[0]

    @staticmethod
    def from_pil(im: Image.Image) -> "Layer":
        a = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
        a[..., :3] *= a[..., 3:4]
        return Layer(a)


def text_layer(text: str, font_name: str, size: int, color, tracking: float = 0.0, pad: int = 8) -> tuple[Layer, dict]:
    """Render text (single line). tracking is extra space per character, in px.

    Returns the layer and metrics: ascent box (x of each glyph start, advance widths, baseline y).
    """
    f = font(font_name, size)
    ascent, descent = f.getmetrics()
    advs = [f.getlength(ch) for ch in text]
    width = sum(advs) + tracking * max(0, len(text) - 1)
    im = Image.new("RGBA", (int(math.ceil(width)) + 2 * pad, ascent + descent + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    xs, x = [], float(pad)
    for ch, adv in zip(text, advs):
        xs.append(x)
        d.text((x, pad), ch, font=f, fill=tuple(int(c) for c in color) + (255,))
        x += adv + tracking
    return Layer.from_pil(im), {"xs": xs, "advs": advs, "width": width, "pad": pad,
                                "ascent": ascent, "descent": descent, "height": ascent + descent}


def text_width(text: str, font_name: str, size: int, tracking: float = 0.0) -> float:
    f = font(font_name, size)
    return sum(f.getlength(ch) for ch in text) + tracking * max(0, len(text) - 1)


def ink_box(text: str, font_name: str, size: int) -> tuple[int, int, int, int]:
    """Tight ink bbox of text drawn at origin (top of the em box at y=0)."""
    return font(font_name, size).getbbox(text)


# ---------------------------------------------------------------- canvas

class Canvas:
    def __init__(self, base: np.ndarray):
        self.px = base.astype(np.float32).copy()  # H x W x 3, 0..1

    def blit(self, layer: Layer, x: float, y: float, alpha: float = 1.0, scale: float = 1.0,
             ox: float = 0.0, oy: float = 0.0, clip: tuple | None = None):
        """Composite layer so that layer-pixel (ox, oy) lands on canvas (x, y), scaled about that point."""
        if alpha <= 0.002 or scale <= 0.001:
            return
        lw, lh = layer.w, layer.h
        # canvas bbox
        x0 = math.floor(x - ox * scale) - 1
        y0 = math.floor(y - oy * scale) - 1
        x1 = math.ceil(x + (lw - ox) * scale) + 1
        y1 = math.ceil(y + (lh - oy) * scale) + 1
        cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if clip:
            cx0, cy0 = max(cx0, clip[0]), max(cy0, clip[1])
            cx1, cy1 = min(cx1, clip[2]), min(cy1, clip[3])
        if cx1 <= cx0 or cy1 <= cy0:
            return
        bw, bh = cx1 - cx0, cy1 - cy0
        # inverse affine: layer coord = (canvas - (x,y)) / scale + (ox, oy)
        inv = 1.0 / scale
        a, b_, c = inv, 0.0, (cx0 - x) * inv + ox
        d, e, f_ = 0.0, inv, (cy0 - y) * inv + oy
        integral = scale == 1.0 and abs(c - round(c)) < 1e-3 and abs(f_ - round(f_)) < 1e-3
        if integral:
            sx, sy = int(round(c)), int(round(f_))
            out = np.zeros((bh, bw, 4), np.float32)
            lx0, ly0 = max(sx, 0), max(sy, 0)
            lx1, ly1 = min(sx + bw, lw), min(sy + bh, lh)
            if lx1 > lx0 and ly1 > ly0:
                out[ly0 - sy:ly1 - sy, lx0 - sx:lx1 - sx] = layer.rgba[ly0:ly1, lx0:lx1]
        else:
            resample = Image.BICUBIC if scale > 0.6 else Image.BILINEAR
            chans = []
            for k in range(4):
                im = Image.fromarray(layer.rgba[..., k], mode="F")
                chans.append(np.asarray(im.transform((bw, bh), Image.AFFINE, (a, b_, c, d, e, f_), resample=resample)))
            out = np.clip(np.stack(chans, -1), 0.0, 1.0)
        out *= alpha
        dst = self.px[cy0:cy1, cx0:cx1]
        dst *= (1.0 - out[..., 3:4])
        dst += out[..., :3]

    def fill_rect(self, x0, y0, x1, y1, color, alpha=1.0):
        """Anti-aliased rectangle with fractional edges."""
        if alpha <= 0 or x1 <= x0 or y1 <= y0:
            return
        ix0, iy0 = max(int(math.floor(x0)), 0), max(int(math.floor(y0)), 0)
        ix1, iy1 = min(int(math.ceil(x1)), W), min(int(math.ceil(y1)), H)
        if ix1 <= ix0 or iy1 <= iy0:
            return
        xs = np.arange(ix0, ix1, dtype=np.float32)
        ys = np.arange(iy0, iy1, dtype=np.float32)
        cov_x = np.clip(np.minimum(xs + 1, x1) - np.maximum(xs, x0), 0, 1)
        cov_y = np.clip(np.minimum(ys + 1, y1) - np.maximum(ys, y0), 0, 1)
        cov = (cov_y[:, None] * cov_x[None, :])[..., None] * alpha
        col = np.array(color, np.float32) / 255.0
        dst = self.px[iy0:iy1, ix0:ix1]
        dst *= 1 - cov
        dst += cov * col

    def disc(self, cx, cy, r, color, alpha=1.0, ring: float = 0.0):
        """Anti-aliased filled disc, or a ring of the given width when ring > 0."""
        if alpha <= 0 or r <= 0:
            return
        ix0, iy0 = max(int(cx - r - 2), 0), max(int(cy - r - 2), 0)
        ix1, iy1 = min(int(cx + r + 3), W), min(int(cy + r + 3), H)
        ys, xs = np.mgrid[iy0:iy1, ix0:ix1].astype(np.float32)
        dist = np.sqrt((xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2)
        cov = np.clip(r - dist + 0.5, 0, 1)
        if ring > 0:
            cov = cov * np.clip(dist - (r - ring) + 0.5, 0, 1)
        cov = cov[..., None] * alpha
        col = np.array(color, np.float32) / 255.0
        dst = self.px[iy0:iy1, ix0:ix1]
        dst *= 1 - cov
        dst += cov * col

    def rounded_rect(self, x0, y0, x1, y1, r, color, alpha=1.0):
        """Anti-aliased rounded rectangle (signed-distance coverage)."""
        if alpha <= 0 or x1 <= x0 or y1 <= y0:
            return
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        ix0, iy0 = max(int(math.floor(x0)) - 1, 0), max(int(math.floor(y0)) - 1, 0)
        ix1, iy1 = min(int(math.ceil(x1)) + 1, W), min(int(math.ceil(y1)) + 1, H)
        ys, xs = np.mgrid[iy0:iy1, ix0:ix1].astype(np.float32) + 0.5
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hx, hy = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
        qx = np.abs(xs - cx) - hx
        qy = np.abs(ys - cy) - hy
        outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
        inside = np.minimum(np.maximum(qx, qy), 0)
        dist = outside + inside - r
        cov = np.clip(0.5 - dist, 0, 1)[..., None] * alpha
        col = np.array(color, np.float32) / 255.0
        dst = self.px[iy0:iy1, ix0:ix1]
        dst *= 1 - cov
        dst += cov * col

    def fade_to(self, base: np.ndarray, amount: float):
        if amount > 0:
            self.px += (base - self.px) * amount

    def to_bytes(self) -> bytes:
        return (np.clip(self.px, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()


def load_plate(name: str) -> np.ndarray:
    return np.asarray(Image.open(ASSETS / name).convert("RGB"), dtype=np.float32) / 255.0


def dark_plate() -> np.ndarray:
    """Near-black cold-open background with a faint vignette and the same static grain as the paper."""
    paper = load_plate("paper_plate.png")
    lum = paper.mean(-1, keepdims=True)
    low = np.asarray(Image.fromarray((lum[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(30)),
                     dtype=np.float32)[..., None] / 255.0
    grain = (lum - low)
    base = np.array(DARK, np.float32) / 255.0
    vign = (low - low.max()) * 0.35  # corners slightly darker
    return np.clip(base + vign + grain * 0.35, 0, 1)


# ---------------------------------------------------------------- audio

SR = 48000


def read_wav_mono(path: str | Path) -> np.ndarray:
    """Any audio file -> mono float32 at 48 kHz (via ffmpeg)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def write_wav(path: str | Path, stereo: np.ndarray):
    x = np.clip(stereo, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def speech_runs(voice: np.ndarray, min_gap: float = 0.12, min_run: float = 0.05) -> list[tuple[float, float]]:
    """Voiced runs (start, end) in seconds. Short isolated runs at either edge (clicks, taps, breaths) are dropped."""
    hop = int(SR * 0.01)
    frames = len(voice) // hop
    if frames < 5:
        return []
    rms = np.sqrt(np.mean(voice[: frames * hop].reshape(frames, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 10)
    peak = np.percentile(db, 98)
    if peak - floor < 12:
        return []
    thr = max(floor + 0.35 * (peak - floor), peak - 38)
    speech = db > thr
    runs, i = [], 0
    while i < frames:
        if speech[i]:
            j = i
            while j < frames and speech[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and (r[0] - merged[-1][1]) * 0.01 < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = [(a * 0.01, b * 0.01) for a, b in merged if (b - a) * 0.01 >= min_run]
    # drop stray edge noises: short runs far from the rest of the speech
    while len(out) > 1 and out[0][1] - out[0][0] < 0.25 and out[1][0] - out[0][1] > 0.3:
        out.pop(0)
    while len(out) > 1 and out[-1][1] - out[-1][0] < 0.25 and out[-1][0] - out[-2][1] > 0.3:
        out.pop()
    return out


def write_wav_float(path: str | Path, stereo: np.ndarray):
    """32-bit float WAV (no clipping before mastering)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_f32le", str(path)], input=np.ascontiguousarray(stereo, np.float32).tobytes(),
                   check=True)


def measure_loudness(path: str | Path) -> dict:
    """ffmpeg loudnorm first pass: integrated LUFS and true peak."""
    import json as _json
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "loudnorm=print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    blob = err[err.rindex("{"): err.rindex("}") + 1]
    d = _json.loads(blob)
    return {"I": float(d["input_i"]), "TP": float(d["input_tp"]), "LRA": float(d["input_lra"]),
            "thresh": float(d["input_thresh"])}


def detect_phrases(voice: np.ndarray, weights: list[float], min_gap: float = 0.12) -> list[tuple[float, float]]:
    """Split a recording into len(weights) phrases.

    weights are the expected relative lengths (syllable counts). Among the pauses between voiced runs, the cut set
    is chosen that best matches those proportions while preferring long pauses, so a long comma pause inside a line
    does not become a line break. Raises ValueError with a plain message when it cannot be done.
    """
    import itertools
    n = len(weights)
    runs = speech_runs(voice, min_gap=min_gap)
    if len(runs) < n:
        raise ValueError(f"只找到 {len(runs)} 段声音，需要 {n} 句：每句之间请停顿半秒左右")
    gaps = [runs[k + 1][0] - runs[k][1] for k in range(len(runs) - 1)]
    total_w = sum(weights)
    best, best_score, best_voiced = None, None, None
    cand = [k for k in range(len(gaps)) if gaps[k] >= 0.15]
    if len(cand) < n - 1:
        cand = list(range(len(gaps)))
    cand = sorted(sorted(cand, key=lambda k: gaps[k], reverse=True)[:12])  # keep the search small
    for cuts in itertools.combinations(cand, n - 1):
        bounds, start = [], 0
        for k in list(cuts) + [len(runs) - 1]:
            bounds.append((runs[start][0], runs[k][1]))
            start = k + 1
        voiced = [sum(min(b, r1) - max(a, r0) for r0, r1 in runs if r1 > a and r0 < b) for a, b in bounds]
        tv = sum(voiced)
        err = sum(math.log(max(v, 1e-3) / (w / total_w * tv)) ** 2 for v, w in zip(voiced, weights))
        pause = sum(math.log(gaps[k] + 0.05) for k in cuts)
        score = err - 0.35 * pause
        if best_score is None or score < best_score:
            best, best_score, best_voiced = bounds, score, voiced
    # plausibility: every line spoken at a human rate, and no line wildly faster than another
    rates = [w / max(v, 1e-3) for w, v in zip(weights, best_voiced)]
    if max(rates) / min(rates) > 2.6 or min(rates) < 1.6 or max(rates) > 9.5:
        detail = "、".join(f"第{i + 1}句 {a:.1f}–{b:.1f} 秒" for i, (a, b) in enumerate(best))
        raise ValueError(f"录音里好像少了一句、多了一句或有重录：检测到 {detail}。请确认只有这 {n} 句，每句之间停顿半秒")
    return best


def split_at_fraction(runs: list[tuple[float, float]], frac: float, window: float = 0.22, min_gap: float = 0.0):
    """Split runs into (A, B) at the pause (>= min_gap s) whose voiced-time position is closest to frac.

    None when no pause fits."""
    if len(runs) < 2:
        return None
    total = sum(b - a for a, b in runs)
    acc, best, best_d = 0.0, None, None
    for k in range(len(runs) - 1):
        acc += runs[k][1] - runs[k][0]
        d = abs(acc / total - frac)
        if runs[k + 1][0] - runs[k][1] >= min_gap and d <= window and (best_d is None or d < best_d):
            best, best_d = k, d
    if best is None:
        return None
    return (runs[0][0], runs[best][1]), (runs[best + 1][0], runs[-1][1])


def voiced_warp(runs: list[tuple[float, float]], start: float, end: float, fractions: list[float]) -> list[float]:
    """Map fractions of voiced time within [start, end] to wall-clock times (pauses do not advance the clock)."""
    segs = [(max(a, start), min(b, end)) for a, b in runs if b > start and a < end]
    total = sum(b - a for a, b in segs)
    if total <= 0:
        return [start + f * (end - start) for f in fractions]
    out = []
    for f in fractions:
        target, acc = f * total, 0.0
        for a, b in segs:
            if acc + (b - a) >= target:
                out.append(a + (target - acc))
                break
            acc += b - a
        else:
            out.append(segs[-1][1])
    return out


# ---------------------------------------------------------------- encoding

def open_encoder(out_path: str | Path, audio_wav: str | Path | None, crf: int = 14):
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if audio_wav:
        cmd += ["-i", str(audio_wav)]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,"
                   "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-video_track_timescale", "15360"]
    if audio_wav:
        cmd += ["-c:a", "aac", "-b:a", "256k", "-ar", str(SR), "-ac", "2", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out_path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
