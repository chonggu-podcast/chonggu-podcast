"""Three ways to climb a foggy mountain range: greedy (只走上坡), annealing (先折腾后收手), constant-temperature
random walk (一直折腾).  Writes data/sim.json for the renderer.

Every person only sees the ground under their feet: each step they try a random nearby spot and decide
whether to move there.  Uphill moves are always taken.  A downhill move of d metres is taken with
probability exp(-d / T(age)):  greedy T = 0, annealing T falls with age, random walk T stays at T0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

G = 1600                    # terrain samples across the range
AGE0, AGE1 = 18, 60
SPY = 120                   # steps per year
STEPS = (AGE1 - AGE0) * SPY
SIGMA = 0.015               # proposal step (fraction of the range width)
X0 = 0.25                   # everyone starts here
P50_YOUNG = 0.85            # chance of taking a 50 m downhill at 18 (annealer and random walker)
T0 = -50 / np.log(P50_YOUNG)
TAU = 5.0                   # annealing: T falls by e every TAU years
T_FLOOR_AGE = 35            # annealing: after this age T is 0 (never goes downhill)
SUMMIT = 970                # standing at >= 970 m counts as on the summit (max is 1000)
N_PEOPLE = 4000
N_MOUNTAINS = 12
SHOWN_UNTIL = 36            # the video follows the three of them up to this age
OUT = Path(__file__).parent / "data" / "sim.json"


def temp(strategy: str, age: np.ndarray | float) -> np.ndarray | float:
    if strategy == "greedy":
        return np.zeros_like(age, dtype=float) if isinstance(age, np.ndarray) else 0.0
    if strategy == "random":
        return np.full_like(age, T0, dtype=float) if isinstance(age, np.ndarray) else T0
    t = T0 * np.exp(-(np.asarray(age, dtype=float) - AGE0) / TAU)
    return np.where(np.asarray(age) >= T_FLOOR_AGE, 0.0, t)


def p_down(strategy: str, age: float, d: float = 50.0) -> float:
    T = float(temp(strategy, age))
    return 0.0 if T <= 0 else float(np.exp(-d / T))


# ------------------------------------------------------------------------------------------- terrain
def smooth(a: np.ndarray, k: int) -> np.ndarray:
    w = np.hanning(2 * k + 1)
    w /= w.sum()
    return np.convolve(np.pad(a, k, mode="edge"), w, mode="valid")


def gen_terrain(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, G)
    h = np.full(G, 80.0)
    for _ in range(rng.integers(6, 10)):
        c, w, a = rng.uniform(0.0, 1.0), rng.uniform(0.025, 0.11), rng.uniform(120, 700)
        h += a * np.exp(-(((x - c) / w) ** 2))
    for k in range(3, 22):  # ridgelines: small bumps on every slope
        h += rng.uniform(4, 26) / (1 + 0.08 * k) * np.sin(2 * np.pi * k * x + rng.uniform(0, 6.3))
    h = smooth(h, 6)
    h -= h.min() - 60
    h *= 1000 / h.max()
    return h


def local_ascent(h: np.ndarray, i: int) -> int:
    while True:
        j = i + (1 if i + 1 < G and h[i + 1] > h[i] else -1 if i > 0 and h[i - 1] > h[i] else 0)
        if j == i:
            return i
        i = j


def acceptable(h: np.ndarray, hero: bool = False) -> bool:
    """Every range: you start low and far from the top, and the top is one clear peak (so "on the summit" is
    well defined).  The hero range also needs the story's premise: the hill you start on is a small one."""
    i0 = int(X0 * (G - 1))
    ip = int(h.argmax())
    if abs(ip - i0) < 0.18 * G or not (180 < h[i0] < 480):
        return False
    if hero:
        il = local_ascent(h, i0)
        if not (520 < h[il] < 760) or (il - i0) * (ip - i0) <= 0:   # climbs toward the summit side, stops short
            return False
        step = 1 if ip > il else -1
        j, lo = il, h[il]
        while h[j] <= h[il] and j != ip:
            j += step
            lo = min(lo, h[j])
        if not (25 <= h[il] - lo <= 140):                           # what blocks him is only a shallow dip
            return False
    far = np.abs(np.arange(G) - ip) > 0.07 * G
    return h[far].max() < 900


# ------------------------------------------------------------------------------------------- walkers
def walk(h: np.ndarray, strategy: str, n: int, rng: np.random.Generator, record: bool = False):
    """Vectorised walk of n people on one terrain. Returns final x (and per-step x if record)."""
    x = np.full(n, X0)
    hx = np.interp(x, np.linspace(0, 1, G), h)
    grid = np.linspace(0, 1, G)
    rec = np.empty((STEPS + 1, n)) if record else None
    if record:
        rec[0] = x
    for s in range(STEPS):
        age = AGE0 + s / SPY
        xn = x + rng.normal(0, SIGMA, n)
        xn = np.abs(xn)                       # reflect at the edges of the range
        xn = np.where(xn > 1, 2 - xn, xn)
        hn = np.interp(xn, grid, h)
        dh = hn - hx
        T = temp(strategy, age)
        if T > 0:
            ok = (dh >= 0) | (rng.random(n) < np.exp(np.minimum(dh, 0) / T))
        else:
            ok = dh >= 0
        x = np.where(ok, xn, x)
        hx = np.where(ok, hn, hx)
        if record:
            rec[s + 1] = x
    return (x, rec) if record else x


def heights(h: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.interp(x, np.linspace(0, 1, G), h)


# ------------------------------------------------------------------------------------------- the hero run
def story(h: np.ndarray, tg, ta, tr):
    """Check the three hero trajectories tell the story; return the key facts or None."""
    ages = AGE0 + np.arange(STEPS + 1) / SPY
    hg, ha, hr = heights(h, tg), heights(h, ta), heights(h, tr)
    if not (520 < hg[-1] < 760):                       # greedy parks on a hill well below the top
        return None
    on_a = np.nonzero(ha >= 995)[0]                    # annealer tops out and, once cooled, stays
    if len(on_a) == 0:
        return None
    a_top = ages[on_a[0]]
    if not (20.0 <= a_top <= 28) or ha[ages >= T_FLOOR_AGE - 2].min() < SUMMIT:
        return None
    on_r = np.nonzero(hr >= 995)[0]                    # random walker tops out first, walks off, ends low
    if len(on_r) == 0:
        return None
    r_top = ages[on_r[0]]
    if not (18.8 <= r_top <= a_top - 1.0):
        return None
    # "walked off": the last time (within what the video shows) he is anywhere near the top
    near = np.nonzero((hr >= 900) & (ages <= SHOWN_UNTIL))[0]
    r_left = ages[near[-1] + 1]
    if not (0.8 <= r_left - r_top <= 6) or r_left > SHOWN_UNTIL - 1.5 or hr[-1] > 650:
        return None
    early = (ages >= 18.6) & (ages <= a_top)           # annealer's stumble: drops well below where it started
    i_low = np.nonzero(early)[0][np.argmin(ha[early])]
    if ha[i_low] > h[int(X0 * (G - 1))] - 80:
        return None
    # greedy's blocking dip: from greedy's hill toward the summit, how far down before the ground is higher again
    ig = int(round(tg[-1] * (G - 1)))
    ip = int(h.argmax())
    step = 1 if ip > ig else -1
    j, lo = ig, h[ig]
    while h[j] <= h[ig] and j != ip:
        j += step
        lo = min(lo, h[j])
    da = np.diff(ha)                                   # last age the annealer took a real downhill step
    downs = np.nonzero(da < -3)[0]
    moved = np.nonzero(np.abs(np.diff(tg)) > 0)[0]
    return dict(greedy_h=float(hg[-1]), greedy_x=float(tg[-1]), greedy_stop_age=float(ages[moved[-1] + 1]),
                dip=float(h[ig] - lo), dip_x=float(j / (G - 1)),
                anneal_top_age=float(a_top), anneal_low_age=float(ages[i_low]), anneal_low_h=float(ha[i_low]),
                anneal_last_down_age=float(ages[downs[-1] + 1]) if len(downs) else float(AGE0),
                random_top_age=float(r_top), random_left_age=float(r_left), random_end_h=float(hr[-1]),
                start_h=float(h[int(X0 * (G - 1))]), summit_x=float(ip / (G - 1)))


def find_hero(max_terrains: int = 6000):
    """First range (in seed order) where one person of each kind tells the story; among the candidates there,
    prefer an annealer who tops out late and a random walker who tops out early and stays up a while."""
    ages = AGE0 + np.arange(STEPS + 1) / SPY
    for ts in range(max_terrains):
        h = gen_terrain(1000 + ts)
        if not acceptable(h, hero=True):
            continue
        rng = np.random.default_rng(ts)
        _, Rg = walk(h, "greedy", 1, rng, record=True)
        if not (520 < heights(h, Rg[-1, 0]) < 760):
            continue
        _, Ra = walk(h, "anneal", 300, rng, record=True)
        _, Rr = walk(h, "random", 300, rng, record=True)
        Ha, Hr = heights(h, Ra), heights(h, Rr)
        topa = Ha >= 995
        a_top = np.where(topa.any(0), topa.argmax(0), -1)
        a_ok = (a_top >= 0) & (Ha[ages >= T_FLOOR_AGE - 2].min(0) >= SUMMIT)
        a_ok &= (ages[a_top] >= 20.0) & (ages[a_top] <= 28)
        topr = Hr >= 995
        r_top = np.where(topr.any(0), topr.argmax(0), -1)
        r_ok = (r_top >= 0) & (Hr[-1] <= 650) & (ages[r_top] >= 18.8)
        best = None
        for ia in np.nonzero(a_ok)[0]:
            cand = np.nonzero(r_ok & (ages[r_top] <= ages[a_top[ia]] - 1.0))[0]
            for ir in cand:
                st = story(h, Rg[:, 0], Ra[:, ia], Rr[:, ir])
                if st:
                    score = st["anneal_top_age"] - st["random_top_age"] + 0.5 * (st["random_left_age"] - st["random_top_age"])
                    if best is None or score > best[0]:
                        best = (score, ia, ir, st)
        if best:
            _, ia, ir, st = best
            print(f"hero terrain seed {1000 + ts}: anneal#{ia} random#{ir}", st, file=sys.stderr)
            return 1000 + ts, h, Rg[:, 0], Ra[:, ia], Rr[:, ir], st
    raise SystemExit("no hero found")


def display_track(tr: np.ndarray, per_year: int = 30) -> list[float]:
    """Smooth the step-by-step x for drawing (people don't teleport), sampled per_year times a year."""
    a = 0.05                                    # forward then backward, so the drawn walker doesn't lag the sim
    y = tr.astype(float).copy()
    for idx in (range(1, len(y)), range(len(y) - 2, -1, -1)):
        prev = None
        for i in idx:
            prev = y[i - 1] if idx.step == 1 else y[i + 1]
            y[i] = prev + a * (y[i] - prev)
    idx = np.round(np.arange(0, STEPS + 1, SPY / per_year)).astype(int)
    return [round(float(v), 5) for v in y[idx]]


def main():
    seed, h, tg, ta, tr, facts = find_hero()
    terrains = [h]
    s = seed + 1
    while len(terrains) < N_MOUNTAINS:
        hh = gen_terrain(s)
        if acceptable(hh):
            terrains.append(hh)
        s += 1
    rng = np.random.default_rng(7)
    results = []
    hero_final = {}
    for m, hh in enumerate(terrains):
        row = {}
        for st in ("greedy", "anneal", "random"):
            xf = walk(hh, st, N_PEOPLE, rng)
            hf = heights(hh, xf)
            row[st] = int((hf >= SUMMIT).sum())
            if m == 0:
                hero_final[st] = [round(float(v), 4) for v in xf[:600]]
        results.append(row)
        print(f"mountain {m + 1}: " + "  ".join(f"{k} {v / N_PEOPLE:.1%}" for k, v in row.items()), file=sys.stderr)
    rate = {st: sum(r[st] for r in results) / (N_PEOPLE * N_MOUNTAINS) for st in ("greedy", "anneal", "random")}
    gold_best = sum(1 for r in results if r["anneal"] > max(r["greedy"], r["random"]))
    print("overall", {k: f"{v:.1%}" for k, v in rate.items()}, "anneal best on", gold_best, file=sys.stderr)
    out = dict(
        params=dict(G=G, age0=AGE0, age1=AGE1, spy=SPY, sigma=SIGMA, x0=X0, T0=T0, tau=TAU, t_floor_age=T_FLOOR_AGE,
                    summit=SUMMIT, n_people=N_PEOPLE, n_mountains=N_MOUNTAINS, hero_seed=seed),
        terrain=[round(float(v), 1) for v in h[::2]],
        thumbs=[[round(float(v), 1) for v in hh[::8]] for hh in terrains],
        tracks=dict(greedy=display_track(tg), anneal=display_track(ta), random=display_track(tr)),
        raw_end=dict(greedy=float(tg[-1]), anneal=float(ta[-1]), random=float(tr[-1])),
        facts=facts,
        pdown=[{"age": a, "p": round(p_down("anneal", a), 3)} for a in (18, 20, 22, 25, 28, 30, 33)],
        pdown_random=round(p_down("random", 18), 3),
        hero_counts=results[0],
        hero_final=hero_final,
        results=results,
        rate=rate,
        gold_best=gold_best,
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print("->", OUT, file=sys.stderr)


if __name__ == "__main__":
    main()
