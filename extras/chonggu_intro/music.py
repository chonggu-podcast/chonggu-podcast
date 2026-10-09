"""Original synthesized sound for the 《重估》 intro (no samples, no third-party recordings)."""
from __future__ import annotations

import numpy as np

from engine import SR


def note_hz(name: str) -> float:
    """'A4' -> 440.0; supports sharps (C#4) and flats (Bb3)."""
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    base = names[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        base += 1
        rest = rest[1:]
    elif rest.startswith("b"):
        base -= 1
        rest = rest[1:]
    octave = int(rest)
    return 440.0 * 2 ** ((base + 12 * (octave - 4)) / 12)


def piano(freq: float, dur: float, amp: float = 0.2, decay: float = 1.8, bright: float = 1.0) -> np.ndarray:
    """Soft felt-piano-like tone: a few decaying partials, slight inharmonicity, quick hammer attack."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    partials = [(1, 1.0, 1.0), (2, 0.32 * bright, 0.55), (3, 0.12 * bright, 0.35), (4, 0.05 * bright, 0.25),
                (5, 0.025 * bright, 0.18)]
    B = 0.0004
    for k, a, dmul in partials:
        f = freq * k * np.sqrt(1 + B * k * k)
        if f > SR / 2.2:
            continue
        out += a * np.sin(2 * np.pi * f * t + 0.3 * k) * np.exp(-t / (decay * dmul))
    attack = 1 - np.exp(-t / 0.006)
    thump = 0.08 * np.sin(2 * np.pi * freq * 0.5 * t) * np.exp(-t / 0.05)
    release = np.cos(np.clip((t - (dur - 0.4)) / 0.4, 0, 1) * np.pi / 2) ** 2  # no hard stop at the end
    return amp * (out * attack + thump) * release


def sub_pulse(freq: float, dur: float, amp: float = 0.25, decay: float = 0.35) -> np.ndarray:
    """Low felt thump (a soft kick without the click)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    sweep = freq * (1 + 0.6 * np.exp(-t / 0.03))
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    return amp * np.sin(phase) * np.exp(-t / decay) * (1 - np.exp(-t / 0.004))


def tick(dur: float = 0.06, amp: float = 0.12, freq: float = 3200.0, seed: int = 0) -> np.ndarray:
    """Tiny mechanical tick: filtered noise burst plus a short sine ping."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same")  # soften
    env = np.exp(-t / 0.006)
    ping = np.sin(2 * np.pi * freq * t) * np.exp(-t / 0.012)
    return amp * (0.5 * noise * env + 0.6 * ping)


def pad(freqs: list[float], dur: float, amp: float = 0.05, attack: float = 1.2, release: float = 1.5) -> np.ndarray:
    """Very quiet sustained chord (detuned sines) for glue."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.7, 0.7):
            out += np.sin(2 * np.pi * (f + det) * t + det)
    env = np.clip(t / attack, 0, 1) * np.clip((dur - t) / release, 0, 1)
    return amp * out / max(1, 2 * len(freqs)) * env


def place(buf: np.ndarray, sig: np.ndarray, at: float, gain: float = 1.0):
    k = int(at * SR)
    if k >= len(buf):
        return
    m = min(len(sig), len(buf) - k)
    buf[k:k + m] += sig[:m] * gain


def echo(x: np.ndarray, taps=((0.13, 0.22), (0.27, 0.12), (0.41, 0.06))) -> np.ndarray:
    out = x.copy()
    for d, g in taps:
        k = int(d * SR)
        out[k:] += x[:-k] * g
    return out


def room(x: np.ndarray, seconds: float = 1.6, wet: float = 0.18, seed: int = 3) -> np.ndarray:
    """Cheap smooth reverb: convolution with exponentially decaying noise."""
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 6.9))
    ir = np.convolve(ir, np.ones(24) / 24, mode="same")
    ir /= np.sqrt((ir ** 2).sum())
    wet_sig = np.fft.irfft(np.fft.rfft(x, len(x) + n) * np.fft.rfft(ir, len(x) + n))[: len(x)]
    return x * (1 - wet) + wet_sig * wet * 2.2


def envelope_follow(x: np.ndarray, attack: float = 0.02, release: float = 0.25) -> np.ndarray:
    """Smoothed amplitude envelope for sidechain ducking."""
    hop = 240
    frames = len(x) // hop + 1
    padded = np.zeros(frames * hop)
    padded[: len(x)] = np.abs(x)
    env = padded.reshape(frames, hop).max(1)
    out = np.zeros(frames)
    a = np.exp(-hop / SR / attack)
    r = np.exp(-hop / SR / release)
    v = 0.0
    for i, e in enumerate(env):
        v = a * v + (1 - a) * e if e > v else r * v + (1 - r) * e
        out[i] = v
    return np.repeat(out, hop)[: len(x)]


def duck(music: np.ndarray, voice: np.ndarray, depth_db: float = 9.0) -> np.ndarray:
    env = envelope_follow(voice)
    level = np.clip(env / (np.percentile(env, 95) + 1e-9), 0, 1)
    gain = 10 ** (-depth_db * level / 20)
    return music * gain


def loudness_match(x: np.ndarray, target_rms_db: float) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2) + 1e-12)
    return x * 10 ** ((target_rms_db - 20 * np.log10(rms)) / 20)
