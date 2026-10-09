"""Natural-sounding cut of the recording by an edit list (replaces assemble.py's sentence-by-sentence cut).

python3 assemble2.py edl.json out_dir
  Writes out_dir/body.wav, out_dir/cold.wav (48 kHz mono float) and out_dir/timeline.json (same format as assemble.py).

What changed against assemble.py (which inserted digital silence between every sentence and shortened every pause):
  * Pieces that follow each other in the recording are played as ONE continuous take: the speaker's own pauses and
    breaths stay. Only removed content (retakes, cut sentences, single words) creates a splice.
  * A splice keeps the natural pause around it: up to 0.35 s after the last kept word and up to 0.5 s before the next
    one (the in-breath lives there), bounded by the removed words so none of them leaks in; equal-power crossfade.
  * Pauses longer than 0.9 s inside a take are shortened to about 0.65 s, keeping the breath before the next onset.
  * [2026-10-05, 朋友反馈「话与话链接有问题」] Every splice is measured: the non-speech run (pause + breath) at the end of
    what is already laid down plus the one at the head of the next take. If it is shorter than a natural pause it is
    padded with gated silence (the mix lays room tone under it): 0.5 s after 。？！, 0.3 s after a comma, 0.12 s inside
    a sentence. Splices inside a sentence get a 35 ms fade instead of 20 ms. A report goes to out_dir/joins.json.
  * Character times come from one whisper pass over the finished audio, aligned piece by piece (fallback: whisper on
    the piece alone), so subtitles follow the audio that is actually heard.
"""
import json, re, sys, difflib
from pathlib import Path
import numpy as np
from scipy.io import wavfile

SR = 48000
HERE = Path(__file__).resolve().parent
edl = json.load(open(sys.argv[1]))
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
sr, SRC = wavfile.read(HERE / 'src48.wav'); SRC = SRC.astype(np.float32)
assert sr == SR
GAIN = {'gu': 10 ** (2.0 / 20), 'wu': 1.0}
HOP = SR // 100
nfr = len(SRC) // HOP
DB = 20 * np.log10(np.sqrt((SRC[:nfr * HOP].reshape(nfr, HOP) ** 2).mean(1)) + 1e-9)
SPEECH = -30.0      # frames above this are speech (breaths sit around -35..-60 in this recording)
QUIET = -50.0       # frames below this are pause

WORDS = [(w['start'], w['end'], w['word'].strip()) for s in json.load(open(HERE / 'transcript.json'))['segments']
         for w in s.get('words', []) if w['word'].strip()]
W_START = np.array([w[0] for w in WORDS]); W_END = np.array([w[1] for w in WORDS])


def db_at(t):
    i = int(t * 100)
    return DB[i] if 0 <= i < nfr else -200.0


def prev_word_end(t):
    """End of the last word that ends before t (the word before a kept onset)."""
    k = np.searchsorted(W_END, t + 0.02) - 1
    while k >= 0 and W_START[k] >= t - 0.02:
        k -= 1
    return W_END[k] if k >= 0 else 0.0


def next_word_start(t):
    k = np.searchsorted(W_START, t - 0.02)
    while k < len(WORDS) and W_END[k] <= t + 0.02:
        k += 1
    return W_START[k] if k < len(WORDS) else len(SRC) / SR


def words_inside(a, b):
    """Words whose middle lies strictly inside (a, b): content that the edit removed."""
    mids = (W_START + W_END) / 2
    return int(((mids > a + 0.06) & (mids < b - 0.06)).sum())


def run_start(ra, inner=False):
    if inner:
        return ra
    pe = prev_word_end(ra)
    s0 = max(ra - 0.5, pe + 0.06, 0.0)
    # the removed word's tail may run past whisper's end: skip speech-level frames right after pe
    t = s0
    lim = min(ra - 0.12, pe + 0.3)
    while t < lim:
        if db_at(t) > SPEECH:
            s0 = t + 0.04
        t += 0.01
    # whisper often starts a word late: if the kept onset is already loud just before ra, reach back for it
    t = ra
    while t > s0 and db_at(t - 0.01) > QUIET:
        t -= 0.01
    return min(s0 if t > s0 + 0.001 else t, ra)


def run_end(rb, inner=False):
    if inner:
        return rb
    ns = next_word_start(rb)
    e0 = min(rb + 0.38, ns - 0.06)
    t = e0
    lim = max(rb + 0.12, ns - 0.3)
    while t > lim:
        if db_at(t) > SPEECH:
            e0 = t - 0.04
        t -= 0.01
    # let a word tail that whisper ended early decay naturally
    t = rb
    while t < e0 and db_at(t) > QUIET:
        t += 0.01
    return max(min(e0, max(t + 0.12, rb + 0.08)), rb)


def shorten_pauses(a, b, max_gap=0.9, keep_after=0.3, keep_before=0.35):
    """Continuous source range -> list of source chunks, long pauses shortened (the breath before an onset stays)."""
    chunks, cur = [], a
    i, i1 = int(a * 100), int(b * 100)
    while i < i1:
        if DB[i] < QUIET:
            j = i
            while j < i1 and DB[j] < QUIET:
                j += 1
            L = (j - i) / 100
            if L > max_gap and i > int(a * 100) + 5 and j < i1 - 5:
                chunks.append((cur, i / 100 + keep_after))
                cur = j / 100 - keep_before
            i = j
        else:
            i += 1
    chunks.append((cur, b))
    return chunks


def eqp_join(out, x, fade):
    """Append x to out with an equal-power crossfade of `fade` seconds."""
    f = int(fade * SR)
    if not out or f <= 0 or len(out[-1]) < f or len(x) < f:
        out.append(x); return 0
    a = out[-1]
    w = np.linspace(0, 1, f, dtype=np.float32)
    a[-f:] = a[-f:] * np.cos(w * np.pi / 2) + x[:f] * np.sin(w * np.pi / 2)
    out.append(x[f:])
    return f


END_STOP = set('。？！?!…」』"')
GAP_MIN = {'stop': 0.50, 'comma': 0.30, 'inner': 0.12}


def ns_run(x, from_end):
    """Length (s) of the non-speech run (below SPEECH: pause, breath) at the end / head of x."""
    n = len(x) // HOP
    if n <= 0:
        return 0.0
    fr = x[len(x) - n * HOP:] if from_end else x[:n * HOP]
    d = 20 * np.log10(np.sqrt((fr.reshape(n, HOP) ** 2).mean(1)) + 1e-9)
    if from_end:
        d = d[::-1]
    k = 0
    while k < n and d[k] < SPEECH:
        k += 1
    return k / 100


JOINS = []


def build(pieces, lead, between=None):
    """pieces -> (audio, rows). between(prev_piece, piece) -> extra silence (s) at a splice, or None."""
    # 1. flatten to intervals and group into continuous takes
    items = []
    for pi, p in enumerate(pieces):
        parts = p.get('parts') or [p['src']]
        for k, (a, b) in enumerate(parts):
            items.append({'pi': pi, 'a': float(a), 'b': float(b), 'spk': p['spk'],
                          'inner_l': k > 0, 'inner_r': k < len(parts) - 1})
    takes = []
    for it in items:
        if takes:
            T = takes[-1]; last = T['items'][-1]
            gap = it['a'] - last['b']
            same = last['spk'] == it['spk'] and not last['inner_r'] and not it['inner_l']
            if same and -0.05 <= gap <= 1.6 and words_inside(last['b'], it['a']) == 0 and not (between and between(pieces[last['pi']], pieces[it['pi']])):
                T['items'].append(it); continue
        takes.append({'items': [it], 'spk': it['spk']})
    # 2. render takes with their natural edges, join with crossfades
    out = [np.zeros(int(lead * SR), np.float32)]
    t_out = lead
    segmap = []          # (src_a, src_b, out_a)
    for ti, T in enumerate(takes):
        first, last = T['items'][0], T['items'][-1]
        a = run_start(first['a'], first['inner_l'])
        b = run_end(last['b'], last['inner_r'])
        if ti and between:
            extra = between(pieces[takes[ti - 1]['items'][-1]['pi']], pieces[first['pi']])
            if extra:
                out.append(np.zeros(int(extra * SR), np.float32)); t_out += extra
        for ci_, (ca, cb) in enumerate(shorten_pauses(a, b)):
            x = SRC[int(ca * SR):int(cb * SR)].copy() * GAIN[T['spk']]
            inner = first['inner_l'] or (ti and takes[ti - 1]['items'][-1]['inner_r'])
            fade = 0.035 if inner else 0.05
            if len(out) == 1:   # first chunk after the lead: fade in
                f = int(0.03 * SR); x[:f] *= np.linspace(0, 1, f)
                out.append(x); ov = 0
            else:
                if ci_ == 0 and ti:   # a splice: make sure a natural pause is heard
                    prev_txt = pieces[takes[ti - 1]['items'][-1]['pi']]['text'].rstrip()
                    kind = 'inner' if inner else ('stop' if prev_txt[-1:] in END_STOP else 'comma')
                    tail = ns_run(np.concatenate(out[-3:])[-int(1.5 * SR):], True)
                    head = ns_run(x[:int(1.5 * SR)], False)
                    gap = tail + head - fade
                    pad = max(0.0, GAP_MIN[kind] - gap)
                    JOINS.append({'at': round(t_out, 2), 'kind': kind, 'gap_before': round(gap, 2), 'pad': round(pad, 2),
                                  'prev': prev_txt[-12:], 'next': pieces[first['pi']]['text'][:12]})
                    if pad > 0:
                        f = int(0.015 * SR)
                        out[-1][-f:] *= np.linspace(1, 0, f, dtype=np.float32)
                        x[:f] *= np.linspace(0, 1, f, dtype=np.float32)
                        out.append(np.zeros(int(pad * SR), np.float32)); t_out += pad
                        out.append(x); ov = 0
                    else:
                        ov = eqp_join(out, x, fade)
                else:
                    ov = eqp_join(out, x, fade)
            segmap.append((ca, cb, t_out - ov / SR))
            t_out += (len(x) - ov) / SR
    y = np.concatenate(out)
    f = int(0.03 * SR); y[-f:] *= np.linspace(1, 0, f)

    def to_out(t):
        best = None
        for (sa, sb, oa) in segmap:
            if sa - 1e-3 <= t <= sb + 1e-3:
                best = oa + (t - sa)   # later chunks win (crossfade overlap)
        if best is None:   # inside removed audio: snap to the nearest chunk edge
            cands = [(abs(t - sa), oa) for sa, sb, oa in segmap] + [(abs(t - sb), oa + sb - sa) for sa, sb, oa in segmap]
            best = min(cands)[1]
        return best

    rows = []
    for pi, p in enumerate(pieces):
        parts = p.get('parts') or [p['src']]
        rows.append({**{k: v for k, v in p.items() if k != 'parts'}, 'cut': [round(float(parts[0][0]), 3), round(float(parts[-1][1]), 3)],
                     't0': round(to_out(float(parts[0][0])), 3), 't1': round(to_out(float(parts[-1][1])), 3),
                     '_parts': [[round(to_out(float(a)), 3), round(to_out(float(b)), 3)] for a, b in parts]})
    return y, rows, takes, to_out


# ---------------------------------------------------------------- character times from the finished audio
# ALIGN=map (2026-10-05, on the Air): no second whisper pass. The source transcript.json already holds large-v3 word
# times; each word inside a kept part is carried through the edit with to_out(), so the times follow the audio exactly.
import os
ALIGN = os.environ.get('ALIGN', 'asr')
if ALIGN == 'asr':
    import mlx_whisper
PUNCT = set('，。？！、；：,.?!;:“”"‘’（）() …—-《》')
EQ = str.maketrans('他她得地裡後個們這為說過來時間錢會麼經學實東', '它它的的里后个们这为说过来时间钱会么经学实东')
PROMPT = '普通话播客《重估》，重估学历。敲门砖，实习，博世，职高，国企央企，安全感，马来西亚，大学预科，UNSW，祛魅，复利，贬值，外部评价，Codex，Claude Code，AI。'


def asr_words(y, model='mlx-community/whisper-large-v3-mlx', prompt=PROMPT):
    from scipy.signal import resample_poly
    z16 = resample_poly(y, 1, 3).astype(np.float32)
    r = mlx_whisper.transcribe(z16, path_or_hf_repo=model, language='zh', word_timestamps=True,
                               initial_prompt=prompt, condition_on_previous_text=False)
    out = []
    for s in r['segments']:
        for w in s.get('words', []):
            cs = [c for c in w['word'].strip() if c not in PUNCT and not c.isspace()]
            if not cs:
                continue
            d = (w['end'] - w['start']) / len(cs)
            for k, c in enumerate(cs):
                out.append((c.lower().translate(EQ), w['start'] + k * d, w['start'] + (k + 1) * d))
    return out


def align(text, got, t0, t1, voiced):
    disp = list(text)
    core_idx = [i for i, c in enumerate(disp) if c not in PUNCT and not c.isspace()]
    core = [disp[i].lower().translate(EQ) for i in core_idx]
    sm = difflib.SequenceMatcher(a=core, b=[g[0] for g in got], autojunk=False)
    tt = [None] * len(core)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            tt[blk.a + k] = got[blk.b + k][1]
    q = sum(v is not None for v in tt) / max(len(core), 1)
    # anchor ends at the voiced edges of the piece, interpolate, keep monotone and inside the piece
    if tt and tt[0] is None:
        tt[0] = voiced[0]
    if tt and tt[-1] is None:
        tt[-1] = max(voiced[1] - 0.2, tt[0])
    idx = [i for i, v in enumerate(tt) if v is not None]
    for a, b in zip(idx, idx[1:]):
        for i in range(a + 1, b):
            tt[i] = tt[a] + (tt[b] - tt[a]) * (i - a) / (b - a)
    prev = t0 - 0.05
    for i in range(len(tt)):
        tt[i] = min(max(tt[i], prev + 0.03), t1 - 0.03)
        prev = tt[i]
    times = [None] * len(disp)
    for j, i in enumerate(core_idx):
        times[i] = round(tt[j], 3)
    for i in range(len(times)):
        if times[i] is None:
            times[i] = times[i - 1] if i else round(t0, 3)
    return times, q


def voiced_edges(y, t0, t1):
    a, b = int(t0 * 100), int(t1 * 100)
    seg = y[a * HOP:b * HOP]
    n = len(seg) // HOP
    if n <= 0:
        return t0, t1
    d = 20 * np.log10(np.sqrt((seg[:n * HOP].reshape(n, HOP) ** 2).mean(1)) + 1e-9)
    v = np.where(d > -38)[0]
    return (t0 + v[0] / 100, t0 + (v[-1] + 1) / 100) if len(v) else (t0, t1)


def mapped_words(p, to_out):
    """Source-transcript characters of piece p, placed on the output timeline."""
    got = []
    for a, b in (p.get('parts') or [p['src']]):
        for ws, we, w in WORDS:
            if not (a - 0.04 <= (ws + we) / 2 <= b + 0.04):
                continue
            cs = [c for c in w if c not in PUNCT and not c.isspace()]
            if not cs:
                continue
            d = (we - ws) / len(cs)
            for k, c in enumerate(cs):
                got.append((c.lower().translate(EQ), to_out(ws + k * d), to_out(ws + (k + 1) * d)))
    return got


def time_rows(y, rows, label, pieces=None, to_out=None):
    if ALIGN == 'map':
        low = []
        for r, p in zip(rows, pieces):
            ve = voiced_edges(y, r['t0'], r['t1'])
            times, q = align(r['text'], mapped_words(p, to_out), r['t0'], r['t1'], ve)
            r['char_t'] = times
            r['match'] = round(q, 2)
            if q < 0.6:
                low.append((round(q, 2), r['text'][:30]))
        print(f'{label}: {len(rows)} rows (mapped), {len(low)} below 0.6', low[:8], flush=True)
        return
    got = asr_words(y)
    low = []
    for r in rows:
        w = [g for g in got if r['t0'] - 0.6 <= g[1] <= r['t1'] + 0.6]
        ve = voiced_edges(y, r['t0'], r['t1'])
        times, q = align(r['text'], w, r['t0'], r['t1'], ve)
        if q < 0.6:   # fall back to whisper on this piece alone (often recovers short or English-heavy lines)
            a, b = max(0, int((r['t0'] - 0.3) * SR)), int((r['t1'] + 0.3) * SR)
            for pr in (r['text'], None):
                w2 = [(c, s + a / SR, e + a / SR) for c, s, e in asr_words(y[a:b], prompt=pr)]
                t2, q2 = align(r['text'], w2, r['t0'], r['t1'], ve)
                if q2 > q:
                    times, q = t2, q2
                if q >= 0.6:
                    break
        r['char_t'] = times
        r['match'] = round(q, 2)
        if q < 0.6:
            low.append((round(q, 2), r['text'][:30]))
    print(f'{label}: {len(rows)} rows, {len(low)} below 0.6', low[:8], flush=True)


# ---------------------------------------------------------------- body
pieces = []
for ch in edl['chapters']:
    for k, p in enumerate(ch['pieces']):
        pieces.append({**p, 'chapter': ch['no'], 'chapter_start': k == 0 and ch['no'] != edl['chapters'][0]['no']})
body, rows, takes, body_to_out = build(pieces, lead=0.25, between=lambda a, b: 0.35 if a['spk'] != b['spk'] else 0)
print(f'{len(pieces)} pieces -> {len(takes)} continuous takes; body {len(body) / SR:.2f} s', flush=True)
time_rows(body, rows, 'body', pieces, body_to_out)
SPL = []
for i in range(1, len(takes)):
    A_, B_ = takes[i - 1]['items'][-1], takes[i]['items'][0]
    rem = ''.join(w[2] for w in WORDS if A_['b'] - 0.02 < (w[0] + w[1]) / 2 < B_['a'] + 0.02)
    SPL.append({'src_end': round(A_['b'], 2), 'src_next': round(B_['a'], 2), 'removed': rem,
                'out_at': rows[B_['pi']]['t0'], 'inner': A_['inner_r']})
json.dump(SPL, open(OUT / 'splices.json', 'w'), ensure_ascii=False, indent=1)
json.dump(JOINS, open(OUT / 'joins.json', 'w'), ensure_ascii=False, indent=1)
_pd = [j for j in JOINS if j['pad'] > 0]
print(f'joins: {len(JOINS)} splices, {len(_pd)} padded (total {sum(j["pad"] for j in _pd):.1f} s)', flush=True)
wavfile.write(OUT / 'body.wav', SR, body.astype(np.float32))

co_rows = []
if edl.get('cold_open'):
    cold, co_rows, _, cold_to_out = build(edl['cold_open'], lead=0.7, between=lambda a, b: 1.0)
    time_rows(cold, co_rows, 'cold open', edl['cold_open'], cold_to_out)
    wavfile.write(OUT / 'cold.wav', SR, cold.astype(np.float32))
    print(f'cold open {len(cold) / SR:.2f} s', flush=True)

for r in rows + co_rows:
    r.pop('_parts', None)
chapters = [{'no': c['no'], 'name': c['name']} for c in edl['chapters']]
json.dump({'body': rows, 'cold_open': co_rows, 'body_seconds': round(len(body) / SR, 3), 'chapters': chapters},
          open(OUT / 'timeline.json', 'w'), ensure_ascii=False, indent=1)
print(f'body {len(body) / SR:.2f} s -> {OUT}')
