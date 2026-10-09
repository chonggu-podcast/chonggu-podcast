"""Sound effects and music cues for 第 4 期 (朋友反馈 2026-10-05: 「开头要有音效，说到重点要有音乐元素」).

All sound is synthesized with the intro's own instrument (extras/chonggu_intro/music.py: felt piano, pad, sub pulse,
room), in D minor like the intro and the end chord, so nothing here needs a licence.

  cold open   a low hit with a piano ping as the dark plate comes up, a quiet drone under the three quotes,
              a soft note as each quote starts, and a riser into the intro.
  chapters    at every chapter change (the page turns sideways on screen): a page-turn swish panned right to left
              and a two-note piano motif.
  key lines   under the episode's key sentences (KEY below): a pad chord with an arpeggiated piano chord, fading in
              about a second before the line and out after it, ducked under the voice.

build(n, T, EP, voice) -> stereo float array (n, 2) at SR, to be added after the voice is mastered.
"""
import re
import numpy as np
from scipy.signal import butter, sosfilt
import music as mu

SR = 48000

# the sentences that carry the episode (spoken text, punctuation ignored); chord per cue cycles through CHORDS
KEY = [
    '它确实是一块敲门砖',
    '他们只在乎你掌握的知识',
    '错人家要的是你有能力',
    '完成一段教育并不意味着未来的问题被解决了',
    '就是保持饥饿保持求知欲',
    '就算我现在不知道做什么那我也要去做',
    '相信自己踏上那条改变自己的道路',
    '这份相遇呢很难用一份工资的薪水来衡量',
    '学历给我带来的是机会大学给我带来的是朋友',
    '其实我现在已经对学历其实已经祛魅了',
    '它只是一把尺子罢了',
    '原来不是一把尺子',
    '到底是不是可复利的资源还是一个不断贬值的资产',
    '排名回答不了我心里的那个问题',
    '好不好用当然是用的人说了算了',
    '学历也是一样它是工具不是答案',
    '除了学历我还能拿出来些什么东西',
]
CHORDS = [
    ['D3', 'A3', 'E4', 'F4'],      # Dm(add9)
    ['Bb2', 'F3', 'A3', 'D4'],     # Bbmaj7
    ['F3', 'C4', 'G4', 'A4'],      # F(add9)
    ['G2', 'D3', 'Bb3', 'F4'],     # Gm7
    ['A2', 'E3', 'G3', 'C4'],      # Am7
]
PUNCT = set('，。？！、；：,.?!;:“”"‘’（）() …—-《》「」')


def db(x):
    return 10 ** (x / 20)


def norm(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def bandnoise(n, lo, hi, seed):
    rng = np.random.default_rng(seed)
    return sosfilt(butter(2, [lo, hi], btype='band', fs=SR, output='sos'), rng.standard_normal(n))


def swish(dur=0.55, seed=11):
    """Page-turn air: a low band then a high band, rising and falling, about dur seconds."""
    n = int(dur * SR); t = np.arange(n) / SR
    lo = bandnoise(n, 250, 1400, seed) * np.sin(np.pi * np.clip(t / (dur * 0.75), 0, 1)) ** 2
    hi = bandnoise(n, 1800, 6500, seed + 1) * np.sin(np.pi * np.clip((t - dur * 0.2) / (dur * 0.8), 0, 1)) ** 2
    return norm(lo * 0.8 + hi * 0.5)


def riser(dur=1.6, seed=21):
    """Noise swell whose band climbs, ending on its loudest point."""
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros(n)
    bands = [(200, 900), (600, 2200), (1500, 5000), (3000, 9000)]
    for k, (lo, hi) in enumerate(bands):
        c = (k + 1) / len(bands)
        env = np.clip((t / dur - (c - 0.55)) / 0.55, 0, 1) ** 2
        out += bandnoise(n, lo, hi, seed + k) * env
    out *= (t / dur) ** 1.5
    f = int(0.03 * SR); out[-f:] *= np.linspace(1, 0, f)
    return norm(out)


def impact():
    """Low felt hit + a piano D with room: the first thing heard."""
    hit = mu.sub_pulse(mu.note_hz('D2'), 1.6, amp=1.0, decay=0.45)
    air = bandnoise(len(hit), 80, 900, 5) * np.exp(-np.arange(len(hit)) / SR / 0.08)
    ping = np.zeros(int(3.5 * SR))
    for k, nm in enumerate(['D4', 'A4', 'D5']):
        mu.place(ping, norm(mu.piano(mu.note_hz(nm), 3.0, amp=1.0, decay=1.6)) * db(-6 * k), 0.02 + k * 0.012)
    ping = mu.room(ping, 2.4, 0.35, seed=9)
    y = np.zeros(int(3.5 * SR))
    mu.place(y, norm(hit) * db(-9), 0.0)
    mu.place(y, norm(air) * db(-26), 0.0)
    mu.place(y, norm(ping) * db(-20), 0.0)
    return y


def motif(notes, gap=0.16, dur=2.4):
    y = np.zeros(int((dur + gap * len(notes)) * SR))
    for k, nm in enumerate(notes):
        mu.place(y, norm(mu.piano(mu.note_hz(nm), dur, amp=1.0, decay=1.5)), k * gap)
    return mu.room(y, 2.0, 0.3, seed=4)


def bed(chord, dur, hit_at):
    """A pad chord for dur seconds with a soft arpeggiated piano chord at hit_at (s into the bed)."""
    hz = [mu.note_hz(c) for c in chord]
    p = norm(mu.pad(hz, dur, amp=1.0, attack=1.1, release=1.8)) * db(-6)
    pn = np.zeros(int(dur * SR))
    for k, f in enumerate(hz):
        mu.place(pn, norm(mu.piano(f, min(dur - hit_at, 4.5), amp=1.0, decay=2.2 if f < 262 else 1.6)) * db(-3 * k), hit_at + k * 0.11)
    top = norm(mu.piano(hz[-1] * 2, 3.0, amp=1.0, decay=1.4)) * db(-10)
    mu.place(pn, top, max(hit_at + 0.6, dur - 3.2))   # a high note that answers near the end
    y = mu.room(p + pn, 2.2, 0.3, seed=6)
    fade = np.cos(np.clip((np.arange(len(y)) / SR - (dur - 1.2)) / 1.2, 0, 1) * np.pi / 2) ** 2
    return y * fade


def phrase_times(EP):
    """Normalised spoken text of the body and the time of every character."""
    txt, t0, t1 = [], [], []
    for c in EP['chars']:
        if c['c'] in PUNCT or c['c'].isspace():
            continue
        txt.append(c['c'].lower()); t0.append(c['t0']); t1.append(c['t1'])
    return ''.join(txt), t0, t1


def find_line(EP, phrase, cache={}):
    """(start, end) of the sentence that contains phrase: the phrase start and the next 。？！ after it."""
    if 'txt' not in cache:
        cache['txt'], cache['t0'], cache['t1'] = phrase_times(EP)
        stops, k = [], 0
        for c in EP['chars']:
            if c['c'] in PUNCT or c['c'].isspace():
                if c['c'] in '。？！?!' and k:
                    stops.append(k - 1)
                continue
            k += 1
        cache['stops'] = stops
    p = re.sub(r'[\s，。？！、,.?!“”「」]', '', phrase).lower()
    i = cache['txt'].find(p)
    if i < 0:
        return None          # not in this edit (4.1 / 4.2 each carry half of the key lines)
    j = i + len(p) - 1
    end = next((s for s in cache['stops'] if s >= j), j)
    end = min(end, j + 40)   # never more than ~40 characters past the phrase
    return cache['t0'][i], cache['t1'][end]


def pan(x, l, r):
    return np.stack([x * l, x * r], 1)


def build(n, T, EP, voice):
    mono = np.zeros(n)            # music: ducked under the voice
    st = np.zeros((n, 2))         # effects: not ducked, some panned
    cues = []

    # ---- cold open
    mu.place(st[:, 0], impact(), 0.0); mu.place(st[:, 1], impact(), 0.0)
    Tco = T['Tco']
    drone = mu.pad([mu.note_hz(x) for x in ('D2', 'A2', 'D3', 'F3')], Tco + 0.4, amp=1.0, attack=2.5, release=1.0)
    drone = norm(mu.room(drone, 2.0, 0.25, seed=2)) * db(-34)
    mu.place(mono, drone, 0.3)
    for k, q in enumerate(EP['coldopen']['quotes']):
        if k == 0:
            continue                                   # the first quote already has the hit
        nt = norm(mu.room(mu.piano(mu.note_hz(['A3', 'F3', 'D3'][k % 3]), 2.5, amp=1.0, decay=1.8), 1.8, 0.3)) * db(-27)
        mu.place(mono, nt, max(0, q['t0'] - 0.12))
    r = riser(1.6) * db(-23)
    mu.place(st[:, 0], r, Tco - 1.6); mu.place(st[:, 1], r, Tco - 1.6)
    cues.append(('cold open', 0.0, Tco))

    # ---- chapter changes (the first chapter follows the intro: no turn there)
    MOT = [['A3', 'D4'], ['F3', 'C4'], ['D4', 'A4'], ['C4', 'F4']]
    sc = EP['scenes']
    def first(s):   # same rule as render/engine.js: when the new page's first element appears (the turn is 0.4 s before)
        a = [e['at'] for e in s.get('els', []) if isinstance(e.get('at'), (int, float)) and e['at'] >= s['t0'] - 0.5]
        return max(s['t0'], min(min(a) if a else s['t0'], s['t0'] + 1.2))
    turns = [first(s) for i, s in enumerate(sc) if i and sc[i - 1].get('ch') != s.get('ch')]
    for k, tc in enumerate(turns):
        w = swish(0.6, seed=30 + k) * db(-25)
        g = np.linspace(0.85, 0.35, len(w))          # right -> left, like the page on screen
        mu.place(st[:, 0], w * (1.2 - g), tc - 0.5)
        mu.place(st[:, 1], w * g, tc - 0.5)
        m = norm(motif(MOT[k % len(MOT)])) * db(-23)
        mu.place(mono, m, tc - 0.15)
        cues.append(('chapter', tc - 0.5, tc + 2.0))

    # ---- key lines
    for k, ph in enumerate(KEY):
        if find_line(EP, ph) is None:
            continue
        a, b = find_line(EP, ph)
        start, dur = a - 1.3, (b - a) + 1.3 + 2.6
        y = norm(bed(CHORDS[k % len(CHORDS)], dur, 1.25)) * db(-15)
        mu.place(mono, y, start)
        cues.append((ph, start, start + dur))

    v = np.zeros(n); v[:min(n, len(voice))] = voice[:n]
    mono = mu.duck(mono, v, depth_db=8.0)
    return st + mono[:, None], cues
