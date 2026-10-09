// 《敢不敢走下坡》 renderer. Every frame is a pure function of t (seconds), so workers can render any frame in
// any order.  window.renderFrame(t) draws; window.TOTAL is the length; window.ready flips once data is in.
(async () => {
  const Q = new URLSearchParams(location.search)
  const W = +Q.get('w') || 1920, H = +Q.get('h') || 1080
  const cv = document.getElementById('cv')
  cv.width = W; cv.height = H
  const ctx = cv.getContext('2d')
  const SIM = await (await fetch('../data/sim.json')).json()
  const TL = await (await fetch('../data/timeline.json')).json()
  await Promise.all(['900 60px "Songti SC"', '600 30px "PingFang SC"', '500 30px "PingFang SC"', 'bold 60px "DIN Alternate"']
    .map((f) => document.fonts.load(f, '0123456789米岁敢')))

  // ------------------------------------------------------------------ helpers
  const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x)
  const lerp = (a, b, x) => a + (b - a) * x
  const eIO = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2 }
  const eOut = (x) => 1 - Math.pow(1 - clamp(x), 3)
  const eBack = (x) => { x = clamp(x); const c = 1.7; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2) }
  const prog = (t, t0, d) => (d > 0 ? clamp((t - t0) / d) : t >= t0 ? 1 : 0)
  const win = (t, t0, t1, fi = 0.3, fo = 0.3) => Math.min(prog(t, t0, fi), 1 - prog(t, t1 - fo, fo))
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`
  const hash = (i) => { const s = Math.sin(i * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s) }

  const C = { greedy: [104, 178, 255], anneal: [246, 196, 84], random: [255, 104, 88] }
  const NAME = { greedy: '求稳', anneal: '先闯后收', random: '一直折腾' }
  const KINDS = ['greedy', 'anneal', 'random']
  const INK = [243, 238, 228]
  const P = SIM.params, F = SIM.facts

  // ------------------------------------------------------------------ timeline
  const L = Object.fromEntries(TL.lines.map((l) => [l.id, l]))
  const charTimes = {}
  for (const l of TL.lines) {
    const tt = new Array(l.text.length).fill(null)
    let pos = 0
    for (const w of l.words) {
      const at = l.text.indexOf(w.w, pos)
      if (at < 0) continue
      for (let k = 0; k < w.w.length; k++) tt[at + k] = [lerp(w.t0, w.t1, k / w.w.length), lerp(w.t0, w.t1, (k + 1) / w.w.length)]
      pos = at + w.w.length
    }
    let last = [l.t0, l.t0]
    for (let i = 0; i < tt.length; i++) { if (tt[i]) last = tt[i]; else tt[i] = [last[1], last[1]] }
    charTimes[l.id] = tt
  }
  // time a phrase is spoken in a line (start, or end with end=true)
  const wt = (id, sub, end = false) => {
    const l = L[id], at = l.text.indexOf(sub)
    if (at < 0) { console.log('PHRASE NOT FOUND', id, sub); return l.t0 }
    return end ? charTimes[id][at + sub.length - 1][1] : charTimes[id][at][0]
  }
  const T_END = TL.total
  const S = {   // scene boundaries
    hook: 0, dip: L.hook3.t0 - 0.15, rewind: L.rewind.t0 - 0.1, three: L.three.t0 - 0.1, rule: L.rule.t0 - 0.1,
    lamps: L.lamps.t0 - 0.15, sim: L.fall.t0 - 0.1, crowd: L.crowd.t0 - 0.05, grid: L.rates.t0 - 0.35,
    temp: L.name.t0 - 0.15, path: L.moral.t0 - 0.2, ending: L.ask.t0 - 0.25,
  }

  // ------------------------------------------------------------------ terrain and tracks
  const TER = SIM.terrain, NT = TER.length
  const refl = (x) => { x = Math.abs(x); x = x > 1 ? 2 - x : x; return clamp(x) }
  const hAt = (x) => { const i = refl(x) * (NT - 1), a = Math.floor(i), b = Math.min(a + 1, NT - 1); return lerp(TER[a], TER[b], i - a) }
  const WW = 5600, HS = 0.6
  const X0 = P.x0, SUMMIT_X = F.summit_x
  const TR = SIM.tracks, SPYD = 30
  const trackAt = (k, age) => {
    const i = clamp((age - P.age0) * SPYD, 0, TR[k].length - 1), a = Math.floor(i), b = Math.min(a + 1, TR[k].length - 1)
    return lerp(TR[k][a], TR[k][b], i - a)
  }
  const trackAvg = (k, age, span) => { let s = 0; for (let j = -4; j <= 4; j++) s += trackAt(k, age + (j / 4) * span); return s / 9 }
  const END = Object.fromEntries(KINDS.map((k) => [k, TR[k][TR[k].length - 1]]))
  // cumulative walked distance, for the stride animation
  const DIST = Object.fromEntries(KINDS.map((k) => {
    const a = [0]; for (let i = 1; i < TR[k].length; i++) a.push(a[i - 1] + Math.abs(TR[k][i] - TR[k][i - 1])); return [k, a]
  }))
  const distAt = (k, age) => { const i = clamp((age - P.age0) * SPYD, 0, DIST[k].length - 1); return DIST[k][Math.floor(i)] }
  // display-track events (so callouts land exactly when the drawn walker gets there)
  const firstAge = (k, test, from = 18, to = 60) => { for (let a = from; a <= to; a += 1 / SPYD) if (test(hAt(trackAt(k, a)))) return a; return null }
  const goldTopAge = firstAge('anneal', (h) => h >= 990)
  const redTopAge = firstAge('random', (h) => h >= 990)
  let goldLowAge = 18.5, goldLowH = 1e9
  for (let a = 18.5; a <= 21; a += 1 / SPYD) { const h = hAt(trackAt('anneal', a)); if (h < goldLowH) { goldLowH = h; goldLowAge = a } }
  const temperature = (k, age) => (k === 'greedy' ? 0 : k === 'random' ? 1 : age >= P.t_floor_age ? 0 : Math.exp(-(age - P.age0) / P.tau))

  // ------------------------------------------------------------------ the age clock
  const simKeys = [
    [L.fall.t0, 18.0], [L.fall.t1, 19.6], [L.redtop.t0, 19.95], [L.redtop.t1, 20.5], [L.redoff.t0, 20.7], [L.redoff.t1, 24.1],
    [L.goldtop.t0, 24.4], [wt('goldtop', '登顶', true) + 0.15, Math.max(26.05, goldTopAge + 0.1)], [L.goldtop.t1 + 0.15, 35.3], [S.crowd, 36],
  ]
  const tAtAge = (age) => { for (let i = 1; i < simKeys.length; i++) if (simKeys[i][1] >= age) { const [ta, aa] = simKeys[i - 1], [tb, ab] = simKeys[i]; return lerp(ta, tb, (age - aa) / (ab - aa)) } return S.crowd }
  function ageAt(t) {
    if (t < S.rewind) return 60
    if (t < L.three.t0) return lerp(60, 18, eIO(prog(t, L.rewind.t0 - 0.05, L.rewind.t1 - L.rewind.t0 + 0.15)))
    if (t < L.fall.t0) return 18
    if (t < S.crowd) {
      for (let i = 1; i < simKeys.length; i++) if (t <= simKeys[i][0]) { const [ta, aa] = simKeys[i - 1], [tb, ab] = simKeys[i]; return lerp(aa, ab, (t - ta) / (tb - ta)) }
      return 36
    }
    return 60
  }

  // where each walker stands (x in 0..1) at time t; null = not drawn
  const OFF = { greedy: -0.0075, anneal: 0, random: 0.0075 }
  function posX(k, t) {
    if (t < S.rewind) return END[k]
    if (t < L.three.t0) return trackAvg(k, ageAt(t), 0.9)
    if (t < L.fall.t0) {
      const o = OFF[k] * eOut(prog(t, L.three.t0, 0.5))
      if (t > S.rule && t < S.lamps) {     // the demo: one step uphill, then a look downhill
        const up = 0.006 * Math.sin(Math.PI * prog(t, L.rule.t0 + 0.1, 1.0))
        const down = k === 'random' ? -0.009 * Math.sin(Math.PI * prog(t, wt('rule', '看你'), 1.1)) : 0
        return X0 + o + up + down
      }
      return X0 + o
    }
    if (t < S.crowd) return trackAt(k, ageAt(t)) + OFF[k] * (1 - eOut(prog(t, L.fall.t0, 0.8)))
    if (t < S.path) return null
    return END[k]
  }
  function facing(k, t) {
    const a = posX(k, t - 0.12), b = posX(k, t + 0.12)
    if (a == null || b == null || Math.abs(b - a) < 1e-5) return k === 'random' ? -1 : 1
    return b > a ? 1 : -1
  }

  // ------------------------------------------------------------------ camera
  function fit(x0, x1, h0, h1, zMin = 0.3, zMax = 2.4, exMax = 1) {
    const z = clamp(Math.min((W * 0.78) / ((x1 - x0) * WW), (H * 0.6) / ((h1 - h0) * HS)), zMin, zMax)
    const ex = clamp((H * 0.6) / ((h1 - h0) * HS * z), 1, exMax)
    return { cx: ((x0 + x1) / 2) * WW, cy: -((h0 + h1) / 2) * HS * ex, z, ex }
  }
  const around = (x, w, hLo, hHi) => fit(x - w, x + w, hLo, hHi)
  function camTarget(t) {
    if (t < L.hook2.t0 - 0.2) return around(END.greedy, 0.07, F.greedy_h - 300, F.greedy_h + 160)
    if (t < S.dip) return around(SUMMIT_X - 0.01, 0.085, 640, 1100)
    if (t < S.rewind + 0.2) return fit(END.greedy - 0.03, F.dip_x + 0.035, F.greedy_h - 260, F.greedy_h + 150)
    if (t < L.fall.t0 - 0.3) return around(X0 + 0.004, 0.05, F.start_h - 170, F.start_h + 210)
    if (t < S.crowd - 0.3) {
      const age = ageAt(t), g = trackAt('anneal', age), r = trackAt('random', age), b = trackAt('greedy', age)
      let xs
      if (t < L.redtop.t0 - 0.3) return fit(-0.03, 0.43, 0, 900, 0.55, 1.9)
      else if (t < L.goldtop.t0 - 0.2) xs = [r, SUMMIT_X]
      else if (age < 33) xs = [g, SUMMIT_X]
      else xs = [SUMMIT_X - 0.03, SUMMIT_X + 0.03]
      const lo = Math.min(...xs), hi = Math.max(...xs)
      const hs = xs.map(hAt)
      return fit(lo - 0.05, hi + 0.05, Math.min(...hs) - 160, Math.max(...hs) + 260, 0.55, 1.9)
    }
    if (t < S.path) return fit(-0.03, 1.03, -60, 1250, 0.2, 2.4, 2.3)
    if (t < S.ending) return fit(-0.02, 0.64, -60, 1250, 0.2, 2.4, 1.7)
    return fit(-0.04, 1.04, -60, 1300, 0.2, 2.4, 2.3)
  }
  function cam(t) {
    let sx = 0, sy = 0, sz = 0, se = 0, sw = 0
    for (let j = -6; j <= 6; j++) {
      const w = Math.exp(-(j * j) / 14), c = camTarget(clamp(t + j * 0.11, 0, T_END))
      sx += c.cx * w; sy += c.cy * w; sz += Math.log(c.z) * w; se += c.ex * w; sw += w
    }
    const c = { cx: sx / sw, cy: sy / sw, z: Math.exp(sz / sw), ex: se / sw }
    c.cx += Math.sin(t * 0.21) * 6 / c.z     // a slow drift so the frame is never dead still
    c.cy += Math.sin(t * 0.17 + 1) * 4 / c.z
    return c
  }
  const toS = (c, x, h) => [(x * WW - c.cx) * c.z + W / 2, (-h * HS * c.ex - c.cy) * c.z + H * 0.55]

  // ------------------------------------------------------------------ sky
  const STARS = Array.from({ length: 170 }, (_, i) => ({ x: hash(i) * W, y: hash(i + 500) * H * 0.62, r: 0.6 + hash(i + 900) * 1.3, p: hash(i + 1300) * 6.28 }))
  function sky(t, c) {
    const g = ctx.createLinearGradient(0, 0, 0, H)
    g.addColorStop(0, '#0c0f22'); g.addColorStop(0.55, '#1a1b36'); g.addColorStop(1, '#2a2442')
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
    for (const s of STARS) {
      ctx.fillStyle = `rgba(235,232,255,${0.25 + 0.35 * (0.5 + 0.5 * Math.sin(t * 1.3 + s.p))})`
      ctx.fillRect(s.x - (c.cx * 0.004) % W, s.y, s.r, s.r)
    }
    const mx = 1540, my = 180
    const halo = ctx.createRadialGradient(mx, my, 30, mx, my, 520)
    halo.addColorStop(0, 'rgba(245,232,200,0.30)'); halo.addColorStop(0.25, 'rgba(225,205,175,0.10)'); halo.addColorStop(1, 'rgba(200,180,160,0)')
    ctx.fillStyle = halo; ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = '#efe5c9'; ctx.beginPath(); ctx.arc(mx, my, 44, 0, 7); ctx.fill()
    ctx.fillStyle = 'rgba(200,185,150,0.25)'
    ;[[-12, -8, 9], [10, 6, 7], [-4, 14, 5]].forEach(([dx, dy, r]) => { ctx.beginPath(); ctx.arc(mx + dx, my + dy, r, 0, 7); ctx.fill() })
    // two far ranges with parallax
    ;[[0.18, 'rgba(66,66,112,0.55)', 610, 150, 1.0], [0.36, 'rgba(48,45,86,0.75)', 700, 110, 1.7]].forEach(([par, col, base, amp, fq]) => {
      ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(0, H)
      for (let sx = 0; sx <= W; sx += 12) {
        const u = (sx - W / 2) / 900 + (c.cx / WW) * par * 6
        const y = base - amp * (0.55 * Math.sin(u * 2.1 * fq + 1.3) + 0.3 * Math.sin(u * 5.3 * fq + 0.4) + 0.15 * Math.sin(u * 11.7 * fq))
        ctx.lineTo(sx, y + (c.cy * 0.05))
      }
      ctx.lineTo(W, H); ctx.fill()
    })
  }

  // ------------------------------------------------------------------ ground
  function ground(c, alpha = 1) {
    const xa = (c.cx - (W / 2) / c.z) / WW - 0.01, xb = (c.cx + (W / 2) / c.z) / WW + 0.01
    const n = Math.max(2, Math.ceil((xb - xa) * (NT - 1)))
    const pts = []
    for (let i = 0; i <= n; i++) { const x = lerp(xa, xb, i / n); pts.push(toS(c, x, hAt(x))) }
    ctx.save(); ctx.globalAlpha = alpha
    const top = Math.min(...pts.map((p) => p[1]))
    const g = ctx.createLinearGradient(0, top, 0, H)
    g.addColorStop(0, '#3d3759'); g.addColorStop(0.5, '#28233f'); g.addColorStop(1, '#16132a')
    ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(pts[0][0], H + 10)
    for (const p of pts) ctx.lineTo(p[0], p[1])
    ctx.lineTo(pts[pts.length - 1][0], H + 10); ctx.fill()
    ctx.strokeStyle = '#efe1c2'; ctx.lineWidth = 2.6; ctx.lineJoin = 'round'
    ctx.shadowColor = 'rgba(255,228,185,0.55)'; ctx.shadowBlur = 12
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.stroke()
    ctx.restore()
  }
  // a stretch of ridge between two x's, as a glowing stroke
  function ridgeSeg(c, xa, xb, col, a, width = 5) {
    const n = Math.max(2, Math.ceil(Math.abs(xb - xa) * (NT - 1) * 2))
    ctx.save(); ctx.strokeStyle = rgba(col, a); ctx.lineWidth = width; ctx.lineCap = 'round'
    ctx.shadowColor = rgba(col, 0.9); ctx.shadowBlur = 16
    ctx.beginPath()
    for (let i = 0; i <= n; i++) { const x = lerp(xa, xb, i / n), p = toS(c, x, hAt(x)); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]) }
    ctx.stroke(); ctx.restore()
  }

  // ------------------------------------------------------------------ the walker: wide-brim hat, pack, staff, lantern
  function walker(sx, sy, sc, col, face, phase, lamp, alpha = 1) {
    ctx.save(); ctx.translate(sx, sy); ctx.scale(sc * face, sc); ctx.globalAlpha = alpha
    // lantern light first, so the figure sits in it
    const lx = 15, ly = -74
    const R = 26 + 120 * lamp
    const glow = ctx.createRadialGradient(lx, ly, 2, lx, ly, R)
    glow.addColorStop(0, rgba(col, 0.55 * (0.25 + lamp))); glow.addColorStop(0.4, rgba(col, 0.18 * (0.2 + lamp))); glow.addColorStop(1, rgba(col, 0))
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(lx, ly, R, 0, 7); ctx.fill()
    const sw = Math.sin(phase), body = '#13121e'
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'
    ctx.shadowColor = rgba(col, 0.95); ctx.shadowBlur = 14
    ctx.strokeStyle = rgba(col, 1); ctx.fillStyle = body
    // legs
    ctx.lineWidth = 6.5
    const hip = [0, -30], leg = (a) => [hip[0] + Math.sin(a) * 30, hip[1] + Math.cos(a) * 30]
    for (const a of [sw * 0.45, -sw * 0.45]) {
      const f = leg(a); ctx.strokeStyle = rgba(col, 1); ctx.beginPath(); ctx.moveTo(...hip); ctx.lineTo(...f); ctx.stroke()
      ctx.strokeStyle = body; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(...hip); ctx.lineTo(...f); ctx.stroke(); ctx.lineWidth = 6.5
    }
    // pack
    ctx.lineWidth = 2.2; ctx.strokeStyle = rgba(col, 1)
    ctx.beginPath(); ctx.roundRect(-17, -62, 13, 25, 4); ctx.fill(); ctx.stroke()
    // torso
    ctx.beginPath(); ctx.roundRect(-6, -60, 12, 33, 6); ctx.fill(); ctx.stroke()
    // staff (front hand) with the lantern hanging from its tip
    ctx.beginPath(); ctx.moveTo(4, -50); ctx.lineTo(13, -44); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(17, 0 - Math.max(0, sw) * 2); ctx.lineTo(12, -84); ctx.lineTo(17, -86); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(17, -86); ctx.lineTo(16, -80); ctx.stroke()
    ctx.shadowBlur = 0
    ctx.fillStyle = rgba(col.map((v) => lerp(v * 0.35, 255, lamp * 0.6)), 1)
    ctx.beginPath(); ctx.roundRect(11.5, -80, 9, 12, 3); ctx.fill()
    ctx.strokeStyle = rgba(col, 1); ctx.lineWidth = 1.6; ctx.stroke()
    ctx.shadowBlur = 14; ctx.lineWidth = 2.2; ctx.fillStyle = body
    // head and hat
    ctx.beginPath(); ctx.arc(2, -68, 7.5, 0, 7); ctx.fill(); ctx.stroke()
    ctx.beginPath(); ctx.ellipse(2, -74, 14, 3.2, 0, 0, 7); ctx.fill(); ctx.stroke()
    ctx.beginPath(); ctx.roundRect(-4, -84, 12, 10, [5, 5, 1, 1]); ctx.fill(); ctx.stroke()
    ctx.restore()
  }
  function drawWalkers(t, c, opts = {}) {
    const age = ageAt(t)
    const order = ['greedy', 'random', 'anneal']
    for (const k of order) {
      const x = posX(k, t)
      if (x == null) continue
      const [sx, sy] = toS(c, x, hAt(x))
      if (sx < -200 || sx > W + 200) continue
      const sc = clamp(c.z * 1.05, 0.5, 1.9)
      const moving = t > S.rewind && t < S.crowd
      const ph = moving ? (t < L.fall.t0 ? (posX(k, t) - X0) * WW / 16 : distAt(k, age) * WW / 16) : 0
      const lamp = temperature(k, t < S.path ? age : 60)
      walker(sx, sy, sc, C[k], facing(k, t), ph, lamp, opts.alpha ?? 1)
    }
  }
  const headOf = (c, k, t, sc) => { const x = posX(k, t); const [sx, sy] = toS(c, x, hAt(x)); return [sx, sy - 92 * sc] }

  // ------------------------------------------------------------------ text
  function text(s, x, y, { size = 40, weight = 600, family = 'PingFang SC', color = INK, a = 1, align = 'left', base = 'alphabetic', shadow = 0 } = {}) {
    ctx.save(); ctx.font = `${weight} ${size}px "${family}"`; ctx.textAlign = align; ctx.textBaseline = base
    ctx.fillStyle = Array.isArray(color) ? rgba(color, a) : color
    if (shadow) { ctx.shadowColor = 'rgba(0,0,0,0.75)'; ctx.shadowBlur = shadow; ctx.shadowOffsetY = 2 }
    ctx.fillText(s, x, y); const w = ctx.measureText(s).width; ctx.restore(); return w
  }
  const measure = (s, size, weight = 600, family = 'PingFang SC') => { ctx.save(); ctx.font = `${weight} ${size}px "${family}"`; const w = ctx.measureText(s).width; ctx.restore(); return w }
  // number + unit, e.g. "696" + "米"
  function bigNum(num, unit, x, y, col, a, size = 70, align = 'left') {
    const wn = measure(num, size, 'bold', 'DIN Alternate'), wu = measure(unit, size * 0.56, 600)
    const total = wn + (unit ? 10 + wu : 0)
    let x0 = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x
    text(num, x0, y, { size, weight: 'bold', family: 'DIN Alternate', color: col, a, shadow: 14 })
    if (unit) text(unit, x0 + wn + 10, y, { size: size * 0.56, weight: 600, color: col, a, shadow: 14 })
    return total
  }
  // callout: leader line from an anchor to a big number and a caption chip
  function callout(t, t0, t1, anchor, { num, unit = '', cap, col, side = 1, dx = 150, dy = -120, size = 70 }) {
    const a = win(t, t0, t1, 0.35, 0.3)
    if (a <= 0) return
    const grow = eOut(prog(t, t0, 0.35))
    const [ax, ay] = anchor
    const ex = ax + side * dx * 0.55, ey = ay + dy
    const lx = ax + side * dx, ly = ey
    ctx.save(); ctx.globalAlpha = a
    ctx.strokeStyle = rgba(col, 0.9); ctx.lineWidth = 2; ctx.shadowColor = rgba(col, 0.8); ctx.shadowBlur = 8
    ctx.beginPath(); ctx.moveTo(ax, ay)
    const p1 = [lerp(ax, ex, clamp(grow * 2)), lerp(ay, ey, clamp(grow * 2))]
    ctx.lineTo(...p1)
    if (grow > 0.5) ctx.lineTo(lerp(ex, lx, (grow - 0.5) * 2), ey)
    ctx.stroke()
    ctx.fillStyle = rgba(col, 1); ctx.beginPath(); ctx.arc(ax, ay, 4, 0, 7); ctx.fill()
    ctx.restore()
    if (grow < 0.6) return
    const ta = a * eOut(prog(t, t0 + 0.2, 0.3)), slide = (1 - eOut(prog(t, t0 + 0.2, 0.35))) * 14
    const align = side > 0 ? 'left' : 'right'
    const tx = lx + side * 10
    let wnum = 0
    if (num) wnum = bigNum(num, unit, tx, ly - 14 + slide, col, ta, size, align)
    if (cap) {
      const cs = 32, cw = measure(cap, cs, 600) + 28
      const cx0 = side > 0 ? tx - 4 : tx - cw + 4
      ctx.save(); ctx.globalAlpha = ta; ctx.fillStyle = 'rgba(8,8,18,0.62)'
      ctx.beginPath(); ctx.roundRect(cx0, ly + 2 + slide, cw, cs + 18, 6); ctx.fill(); ctx.restore()
      text(cap, cx0 + 14, ly + cs + 6 + slide, { size: cs, weight: 600, color: INK, a: ta })
    }
  }
  function ring(t, t0, sx, sy, col, n = 2) {
    for (let i = 0; i < n; i++) {
      const p = prog(t, t0 + i * 0.25, 1.3)
      if (p <= 0 || p >= 1) continue
      ctx.save(); ctx.strokeStyle = rgba(col, 0.75 * (1 - p)); ctx.lineWidth = 3; ctx.shadowColor = rgba(col, 0.8); ctx.shadowBlur = 12
      ctx.beginPath(); ctx.arc(sx, sy, 30 + 220 * eOut(p), 0, 7); ctx.stroke(); ctx.restore()
    }
  }

  // ------------------------------------------------------------------ subtitles
  const SUBS = []
  for (const l of TL.lines) {
    const segs = []; let cur = '', start = 0
    for (let i = 0; i < l.text.length; i++) {
      cur += l.text[i]
      if ('，。；：？'.includes(l.text[i]) || i === l.text.length - 1) { segs.push([start, i, cur]); cur = ''; start = i + 1 }
    }
    const chunks = []; let acc = null
    for (const s of segs) {
      if (acc && (acc[2] + s[2]).replace(/[，。；：？\s]/g, '').length <= 19) acc = [acc[0], s[1], acc[2] + s[2]]
      else { if (acc) chunks.push(acc); acc = s }
    }
    chunks.push(acc)
    chunks.forEach((ch, j) => {
      const t0 = charTimes[l.id][ch[0]][0] - 0.06
      const t1 = j + 1 < chunks.length ? charTimes[l.id][chunks[j + 1][0]][0] - 0.06 : l.t1 + 0.22
      SUBS.push({ t0, t1, s: ch[2].replace(/[，。；]$/, ''), id: l.id })
    })
  }
  const NO_SUB = new Set(['rates', 'name'])
  function subtitles(t) {
    for (const s of SUBS) {
      if (t < s.t0 || t > s.t1 || NO_SUB.has(s.id)) continue
      const a = Math.min(prog(t, s.t0, 0.12), 1 - prog(t, s.t1 - 0.1, 0.1))
      // numbers glow warm, the rest is paper white
      const size = 66, parts = s.s.split(/(\d+(?:\.\d+)?%?)/)
      const total = parts.reduce((w, p) => w + measure(p, size, 900, 'Songti SC'), 0)
      let x = W / 2 - total / 2
      for (const p of parts) {
        const isNum = /^\d/.test(p)
        x += text(p, x, H - 92, { size, weight: 900, family: 'Songti SC', color: isNum ? [255, 214, 140] : INK, a, shadow: 18 })
      }
    }
  }

  // ------------------------------------------------------------------ age clock (top-left)
  function ageClock(t) {
    let a = 0
    if (t < S.rewind) a = win(t, 0.2, S.rewind + 0.1, 0.4, 0.2)
    else if (t >= L.three.t0 - 0.05 && t < S.crowd) a = Math.min(prog(t, L.three.t0 - 0.05, 0.3), 1 - prog(t, S.crowd - 0.25, 0.25))
    else if (t >= S.ending) a = prog(t, S.ending + 0.3, 0.5)
    if (S.lamps < t && t < S.sim) a *= 0.25
    if (a <= 0) return
    const age = Math.floor(ageAt(t) + 1e-6)
    const w = text(String(age), 84, 150, { size: 96, weight: 'bold', family: 'DIN Alternate', color: [236, 231, 222], a: a * 0.9, shadow: 12 })
    text('岁', 84 + w + 14, 150, { size: 54, weight: 600, color: [236, 231, 222], a: a * 0.9, shadow: 12 })
  }
  function footer(t) {
    const inPanel = (t > S.lamps + 0.2 && t < S.sim - 0.2) || (t > S.grid + 0.3 && t < S.path - 0.2)
    text('示意模拟 · 高度为相对单位', 46, H - 30, { size: 22, weight: 500, color: [255, 255, 255], a: inPanel ? 0.3 : 0.42 })
  }

  // ------------------------------------------------------------------ scenes
  function hookScene(t, c) {
    const sc = clamp(c.z * 1.05, 0.5, 1.9)
    callout(t, 0.55, L.hook2.t0 + 0.3, headOf(c, 'greedy', t, sc), { num: String(Math.round(F.greedy_h)), unit: '米', cap: '一步下坡都没走过', col: C.greedy, dx: 230, dy: -90 })
    callout(t, L.hook2.t0 + 0.35, S.dip + 0.2, headOf(c, 'anneal', t, sc), { num: '1000', unit: '米', cap: '同一个起点', col: C.anneal, side: -1, dx: 250, dy: -60 })
  }
  function dipScene(t, c) {
    const a = win(t, S.dip + 0.15, S.rewind + 0.25, 0.4, 0.3)
    if (a <= 0) return
    const gx = END.greedy, gh = hAt(gx)
    // the stretch he would have to go down
    let lo = gx, loH = gh
    for (let x = gx; x <= F.dip_x; x += 0.0005) if (hAt(x) < loH) { loH = hAt(x); lo = x }
    const draw = eOut(prog(t, S.dip + 0.2, 0.8))
    ridgeSeg(c, gx, lerp(gx, F.dip_x, draw), [255, 120, 100], 0.85 * a)
    const p0 = toS(c, gx, gh), p1 = toS(c, F.dip_x, gh), pl = toS(c, lo, loH)
    ctx.save(); ctx.globalAlpha = a; ctx.setLineDash([10, 9]); ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(lerp(p0[0], p1[0], draw), p0[1]); ctx.stroke()
    ctx.setLineDash([])
    const dd = eOut(prog(t, S.dip + 0.6, 0.5))
    ctx.strokeStyle = 'rgba(255,150,130,0.95)'; ctx.lineWidth = 3
    ctx.beginPath(); ctx.moveTo(pl[0], p0[1]); ctx.lineTo(pl[0], lerp(p0[1], pl[1], dd)); ctx.stroke()
    ;[p0[1], pl[1]].forEach((y) => { ctx.beginPath(); ctx.moveTo(pl[0] - 12, y); ctx.lineTo(pl[0] + 12, y); ctx.stroke() })
    ctx.restore()
    if (dd > 0.3) {
      const ta = a * eOut(prog(t, S.dip + 0.8, 0.3))
      bigNum(String(Math.round(F.dip)), '米', pl[0] + 26, (p0[1] + pl[1]) / 2 + 24, [255, 160, 140], ta, 74)
      text('过不去的那道沟', pl[0] + 28, (p0[1] + pl[1]) / 2 + 70, { size: 30, weight: 600, color: INK, a: ta * 0.9, shadow: 10 })
    }
  }
  function rewindScene(t) {
    const a = win(t, S.rewind, L.three.t0 + 0.25, 0.25, 0.35)
    if (a <= 0) return
    const age = Math.round(ageAt(t))
    ctx.save(); ctx.globalAlpha = a * 0.35
    for (let i = 0; i < 7; i++) { const y = (hash(Math.floor(t * 24) + i) * H); ctx.fillStyle = 'rgba(255,255,255,0.08)'; ctx.fillRect(0, y, W, 2 + hash(i) * 3) }
    ctx.restore()
    const w1 = measure('60', 150, 'bold', 'DIN Alternate'), w2 = measure(String(age), 150, 'bold', 'DIN Alternate')
    const total = w1 + 60 + 70 + w2 + 20 + measure('岁', 84)
    let x = W / 2 - total / 2
    text('60', x, 330, { size: 150, weight: 'bold', family: 'DIN Alternate', color: [236, 231, 222], a: a * 0.45, shadow: 16 })
    x += w1 + 30
    text('→', x, 315, { size: 80, weight: 500, color: [236, 231, 222], a: a * 0.6 })
    x += 100
    text(String(age), x, 330, { size: 150, weight: 'bold', family: 'DIN Alternate', color: [255, 255, 255], a, shadow: 16 })
    text('岁', x + w2 + 20, 330, { size: 84, weight: 600, color: [255, 255, 255], a, shadow: 16 })
    text('倒带回起点', W / 2, 395, { size: 34, weight: 600, color: INK, a: a * 0.7, align: 'center', shadow: 10 })
  }
  function threeScene(t, c) {
    const sc = clamp(c.z * 1.05, 0.5, 1.9)
    const t1 = S.rule + 0.4
    callout(t, wt('three', '求稳'), t1, headOf(c, 'greedy', t, sc), { num: '', cap: '求稳 · 只走上坡', col: C.greedy, side: -1, dx: 210, dy: -70 })
    callout(t, wt('three', '先闯后收'), t1, headOf(c, 'anneal', t, sc), { num: '', cap: '先闯，后收', col: C.anneal, side: 1, dx: 60, dy: -150 })
    callout(t, wt('three', '一直折腾'), t1, headOf(c, 'random', t, sc), { num: '', cap: '一直折腾', col: C.random, side: 1, dx: 220, dy: -40 })
  }
  function arrowAlong(c, xa, xb, col, a, label, labelSide = -1) {
    const n = 30, pts = []
    for (let i = 0; i <= n; i++) { const x = lerp(xa, xb, i / n); const p = toS(c, x, hAt(x)); pts.push([p[0], p[1] - 70]) }
    ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = rgba(col, 0.95); ctx.lineWidth = 4; ctx.lineCap = 'round'
    ctx.shadowColor = rgba(col, 0.9); ctx.shadowBlur = 10
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(...p) : ctx.moveTo(...p))); ctx.stroke()
    const [q, p] = [pts[n - 3], pts[n]], ang = Math.atan2(p[1] - q[1], p[0] - q[0])
    ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(p[0] - 22 * Math.cos(ang - 0.45), p[1] - 22 * Math.sin(ang - 0.45))
    ctx.moveTo(p[0], p[1]); ctx.lineTo(p[0] - 22 * Math.cos(ang + 0.45), p[1] - 22 * Math.sin(ang + 0.45)); ctx.stroke()
    ctx.restore()
    const m = pts[Math.floor(n * 0.55)]
    text(label, m[0], m[1] - 26, { size: 36, weight: 600, color: col, a, align: 'center', shadow: 12 })
  }
  function ruleScene(t, c) {
    const a0 = win(t, L.rule.t0, S.lamps + 0.1, 0.3, 0.3)
    if (a0 <= 0) return
    arrowAlong(c, X0 + 0.012, X0 + 0.05, [236, 231, 222], a0 * eOut(prog(t, L.rule.t0, 0.4)), '上坡：都走')
    const td = wt('rule', '碰到下坡')
    arrowAlong(c, X0 - 0.014, X0 - 0.052, [255, 170, 150], win(t, td, S.lamps + 0.1, 0.3, 0.3), '下坡：敢不敢？')
    const tb = wt('rule', '看你')
    const sc = clamp(c.z * 1.05, 0.5, 1.9)
    const bubble = (k, s, dt) => {
      const ba = win(t, tb + dt, S.lamps + 0.1, 0.25, 0.3)
      if (ba <= 0) return
      const [hx, hy] = headOf(c, k, t, sc), pop = eBack(prog(t, tb + dt, 0.35))
      const w = measure(s, 34, 700) + 30
      ctx.save(); ctx.globalAlpha = ba; ctx.translate(hx, hy - 30); ctx.scale(pop, pop)
      ctx.fillStyle = 'rgba(10,10,22,0.78)'; ctx.strokeStyle = rgba(C[k], 0.95); ctx.lineWidth = 2
      ctx.beginPath(); ctx.roundRect(-w / 2, -50, w, 50, 12); ctx.fill(); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(-8, 0); ctx.lineTo(0, 12); ctx.lineTo(8, 0); ctx.fill()
      ctx.restore()
      ctx.save(); ctx.globalAlpha = ba; ctx.translate(hx, hy - 30); ctx.scale(pop, pop)
      text(s, 0, -14, { size: 34, weight: 700, color: C[k], align: 'center' }); ctx.restore()
    }
    bubble('greedy', '不走', 0)
    bubble('anneal', '看年纪', 0.15)
    bubble('random', '走', 0.3)
  }
  function lantern(x, y, p, col, s = 1, a = 1) {
    ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.scale(s, s)
    const R = 22 + 100 * p
    const g = ctx.createRadialGradient(0, 0, 2, 0, 0, R)
    g.addColorStop(0, rgba(col, 0.7 * (0.15 + p))); g.addColorStop(0.45, rgba(col, 0.2 * (0.1 + p))); g.addColorStop(1, rgba(col, 0))
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, R, 0, 7); ctx.fill()
    ctx.strokeStyle = rgba(col, 0.9); ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(0, -36); ctx.lineTo(0, -24); ctx.stroke()
    ctx.beginPath(); ctx.arc(0, -36, 5, Math.PI, 0); ctx.stroke()
    ctx.fillStyle = rgba(col.map((v) => lerp(v * 0.25, 255, p * 0.8)), 1)
    ctx.beginPath(); ctx.roundRect(-13, -24, 26, 36, 6); ctx.fill(); ctx.stroke()
    ctx.fillStyle = 'rgba(20,18,30,0.9)'; ctx.fillRect(-15, -26, 30, 4); ctx.fillRect(-15, 10, 30, 4)
    ctx.restore()
  }
  function dim(t, t0, t1, amount = 0.74) {
    const a = win(t, t0, t1, 0.35, 0.35) * amount
    if (a <= 0) return 0
    ctx.fillStyle = `rgba(8,8,20,${a})`; ctx.fillRect(0, 0, W, H)
    return a / amount
  }
  function lampsScene(t) {
    const a = dim(t, S.lamps, S.sim + 0.05, 0.88)
    if (a <= 0) return
    text('碰到 50 米的下坡，肯走的概率', W / 2, 150, { size: 54, weight: 900, family: 'Songti SC', color: INK, a, align: 'center', shadow: 14 })
    const ages = [...SIM.pdown.map((d) => d.age), 35], cols = ages.map((_, i) => 560 + i * 168)
    ages.forEach((ag, i) => text(`${ag} 岁`, cols[i], 250, { size: 30, weight: 600, color: [200, 196, 210], a: a * 0.9, align: 'center' }))
    const rows = [
      { k: 'anneal', y: 420, p: [...SIM.pdown.map((d) => d.p), 0], t0: wt('lamps', '先闯后收'), sweep: [wt('lamps', '18'), wt('lamps', '一步不走', true)] },
      { k: 'random', y: 600, p: ages.map(() => SIM.pdown_random), t0: wt('lamps', '一直折腾'), sweep: [wt('lamps', '一直折腾'), wt('lamps', '一辈子', true)] },
      { k: 'greedy', y: 780, p: ages.map(() => 0), t0: wt('lamps', '一直折腾') + 0.9, sweep: [wt('lamps', '一直折腾') + 0.9, wt('lamps', '一直折腾') + 1.6] },
    ]
    for (const r of rows) {
      const ra = a * eOut(prog(t, r.t0 - 0.1, 0.35))
      if (ra <= 0) continue
      text(NAME[r.k], 420, r.y + 12, { size: 40, weight: 700, color: C[r.k], a: ra, align: 'right', shadow: 10 })
      r.p.forEach((p, i) => {
        const on = eOut(prog(t, lerp(r.sweep[0], r.sweep[1], i / (r.p.length - 1)), 0.35))
        lantern(cols[i], r.y, p * on, C[r.k], 1, ra)
        if (on > 0.05) text(`${Math.round(p * 100)}%`, cols[i], r.y + 66, { size: 32, weight: 'bold', family: 'DIN Alternate', color: p > 0 ? C[r.k] : [150, 150, 170], a: ra * on, align: 'center' })
      })
    }
  }
  function simScene(t, c) {
    const sc = clamp(c.z * 1.05, 0.5, 1.9)
    const tLow = tAtAge(goldLowAge), tRed = tAtAge(redTopAge), tGold = tAtAge(goldTopAge), t35 = tAtAge(35)
    const tOff = wt('redoff', '自己')
    callout(t, Math.max(tLow, L.fall.t0 + 0.6), L.redtop.t0 + 0.15, headOf(c, 'anneal', t, sc),
      { num: String(Math.round(goldLowH)), unit: '米', cap: '19 岁 · 跌进谷底', col: C.anneal, dx: 200, dy: -110 })
    if (t > tRed - 0.1 && t < tRed + 1.6) { const [hx, hy] = headOf(c, 'random', t, sc); ring(t, tRed, hx, hy + 50 * sc, C.random) }
    callout(t, tRed, L.redoff.t0 + 0.3, headOf(c, 'random', t, sc), { num: '20', unit: '岁', cap: '一直折腾的，最先登顶', col: C.random, side: -1, dx: 220, dy: -80 })
    if (t > tOff - 0.1 && t < tOff + 1.6) { const [hx, hy] = headOf(c, 'random', t, sc); ring(t, tOff, hx, hy + 50 * sc, C.random, 1) }
    callout(t, tOff, L.goldtop.t0 + 0.2, headOf(c, 'random', t, sc), { num: '不到 24', unit: '岁', cap: '自己走下了山顶', col: C.random, side: -1, dx: 220, dy: -60, size: 62 })
    if (t > tGold - 0.1 && t < tGold + 1.8) { const [hx, hy] = headOf(c, 'anneal', t, sc); ring(t, tGold, hx, hy + 50 * sc, C.anneal, 3) }
    callout(t, tGold, t35 - 0.05, headOf(c, 'anneal', t, sc), { num: '1000', unit: '米', cap: '25 岁 · 先闯后收 登顶', col: C.anneal, dx: 210, dy: -90 })
    callout(t, t35, S.crowd + 0.15, headOf(c, 'anneal', t, sc), { num: '35', unit: '岁起', cap: '不再下坡，守在山顶', col: C.anneal, dx: 210, dy: -90 })
  }
  function crowdScene(t, c) {
    const a = win(t, S.crowd, S.grid + 0.4, 0.3, 0.4)
    if (a <= 0) return
    text('同一座山 · 每种走法 4000 人', W / 2, 150, { size: 54, weight: 900, family: 'Songti SC', color: INK, a, align: 'center', shadow: 14 })
    const kOff = { greedy: 0, anneal: 0.12, random: 0.24 }
    for (const k of KINDS) {
      const xs = SIM.hero_final[k]
      ctx.fillStyle = rgba(C[k], 0.85)
      xs.forEach((x, i) => {
        const u1 = hash(i * 3 + kOff[k] * 100), u2 = hash(i * 5 + kOff[k] * 200)
        const jx = Math.sqrt(-2 * Math.log(u1 + 1e-6)) * Math.cos(6.283 * u2) * 0.009, jy = hash(i * 7 + kOff[k] * 300) * 16
        const ts = S.crowd + 0.1 + kOff[k] + (i / xs.length) * 0.65
        const p = eOut(prog(t, ts, 0.45))
        if (p <= 0) return
        const [sx, sy] = toS(c, clamp(x + jx), hAt(clamp(x + jx)))
        const y = lerp(-20, sy - 5 - jy, p)
        ctx.globalAlpha = a * (0.35 + 0.65 * p)
        ctx.fillRect(sx - 2.2, y - 2.2, 4.4, 4.4)
      })
    }
    ctx.globalAlpha = 1
    const la = a * eOut(prog(t, S.crowd + 1.0, 0.35))
    const lab = (k, x, dy, n, cap) => {
      const [sx, sy] = toS(c, x, hAt(x))
      bigNum(String(n), '', sx, sy - 70 + dy, C[k], la, 64, 'center')
      text(cap, sx, sy - 70 + dy + 40, { size: 28, weight: 600, color: C[k], a: la, align: 'center', shadow: 10 })
    }
    lab('anneal', SUMMIT_X, -40, SIM.hero_counts.anneal, '先闯后收 · 在山顶')
    lab('random', SUMMIT_X + 0.2, -10, SIM.hero_counts.random, '一直折腾 · 在山顶')
    lab('greedy', END.greedy - 0.1, -20, SIM.hero_counts.greedy, '求稳 · 在山顶')
  }
  function gridScene(t) {
    const a = dim(t, S.grid, S.temp + 0.05, 0.86)
    if (a <= 0) return
    text('再换 12 座随机的山', W / 2, 112, { size: 54, weight: 900, family: 'Songti SC', color: INK, a, align: 'center', shadow: 14 })
    const cw = 400, ch = 190, gx = 24, gy = 22, x0 = (W - (4 * cw + 3 * gx)) / 2, y0 = 160
    SIM.results.forEach((r, m) => {
      const ca = a * eOut(prog(t, S.grid + 0.15 + m * 0.05, 0.3))
      if (ca <= 0) return
      const cx = x0 + (m % 4) * (cw + gx), cy = y0 + Math.floor(m / 4) * (ch + gy)
      ctx.save(); ctx.globalAlpha = ca
      ctx.fillStyle = 'rgba(255,255,255,0.04)'; ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 1.5
      ctx.beginPath(); ctx.roundRect(cx, cy, cw, ch, 12); ctx.fill(); ctx.stroke()
      const th = SIM.thumbs[m], tw = cw * 0.66, tx = cx + 14, tb = cy + ch - 18, thh = ch * 0.62
      ctx.beginPath(); ctx.moveTo(tx, tb)
      th.forEach((v, i) => ctx.lineTo(tx + (i / (th.length - 1)) * tw, tb - (v / 1000) * thh))
      ctx.lineTo(tx + tw, tb); ctx.closePath()
      ctx.fillStyle = 'rgba(120,110,170,0.28)'; ctx.fill()
      ctx.strokeStyle = 'rgba(240,226,196,0.8)'; ctx.lineWidth = 1.6; ctx.stroke()
      const sx = tx + (P.x0) * tw, sy = tb - (th[Math.round(P.x0 * (th.length - 1))] / 1000) * thh
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(sx, sy, 3.5, 0, 7); ctx.fill()
      ctx.restore()
      text(m === 0 ? '#1 刚才那座' : `#${m + 1}`, cx + 14, cy + 32, { size: 22, weight: 600, color: [200, 196, 210], a: ca * 0.8 })
      const grow = eOut(prog(t, S.grid + 0.45 + m * 0.05, 0.6))
      const best = KINDS.reduce((b, k) => (r[k] > r[b] ? k : b), 'greedy')
      KINDS.forEach((k, j) => {
        const v = r[k] / P.n_people, bh = Math.max(2, v * 130 * grow)
        const bx = cx + cw * 0.72 + j * 34, by = cy + ch - 18
        ctx.save(); ctx.globalAlpha = ca; ctx.fillStyle = rgba(C[k], 0.95)
        if (k === best) { ctx.shadowColor = rgba(C[k], 0.9); ctx.shadowBlur = 12 }
        ctx.fillRect(bx, by - bh, 24, bh); ctx.restore()
        if (k === best && grow > 0.9) text('✓', bx + 12, by - bh - 10, { size: 30, weight: 700, color: C[k], a: ca, align: 'center' })
      })
    })
    const sumY = 900
    ;[['greedy', '求稳'], ['anneal', '先闯后收'], ['random', '一直折腾']].forEach(([k, phrase], i) => {
      const ta = a * eOut(prog(t, wt('rates', phrase) - 0.05, 0.3))
      if (ta <= 0) return
      const x = W / 2 + (i - 1) * 520
      text(NAME[k], x, sumY - 72, { size: 36, weight: 700, color: C[k], a: ta, align: 'center', shadow: 10 })
      bigNum((SIM.rate[k] * 100).toFixed(1), '%', x, sumY + 22, C[k], ta, 96, 'center')
    })
    const na = a * eOut(prog(t, wt('rates', '一直折腾', true) + 0.3, 0.4))
    text(`登顶率 = 60 岁时站在山顶的人 / 4000，12 座山取平均 · ${SIM.gold_best} 座山里先闯后收最高`, W / 2, 1010,
      { size: 26, weight: 500, color: [210, 206, 220], a: na * 0.85, align: 'center' })
  }
  function tempScene(t) {
    const a = dim(t, S.temp, S.path + 0.1, 0.84)
    if (a <= 0) return
    text('模拟退火', W / 2, 200, { size: 104, weight: 900, family: 'Songti SC', color: INK, a, align: 'center', shadow: 18 })
    text('Simulated Annealing · 先烧热，再慢慢冷下来', W / 2, 262, { size: 32, weight: 500, color: [210, 206, 220], a: a * 0.85, align: 'center' })
    const X0c = 480, X1c = 1500, Y0c = 820, Y1c = 380
    const ax = (age) => lerp(X0c, X1c, (age - 18) / (50 - 18)), ay = (T) => lerp(Y0c, Y1c, T)
    ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(X0c, Y1c - 20); ctx.lineTo(X0c, Y0c); ctx.lineTo(X1c + 20, Y0c); ctx.stroke(); ctx.restore()
    ;[18, 25, 35, 50].forEach((ag) => text(`${ag} 岁`, ax(ag), Y0c + 44, { size: 28, weight: 600, color: [200, 196, 210], a: a * 0.85, align: 'center' }))
    text('温度 = 敢走下坡的程度', X0c - 20, Y1c - 40, { size: 28, weight: 600, color: [200, 196, 210], a: a * 0.85 })
    const draw = eOut(prog(t, S.temp + 0.2, 1.0))
    const curve = (k, lw) => {
      ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = rgba(C[k], 1); ctx.lineWidth = lw; ctx.shadowColor = rgba(C[k], 0.9); ctx.shadowBlur = 12
      ctx.beginPath()
      for (let ag = 18; ag <= lerp(18, 50, draw); ag += 0.1) { const p = [ax(ag), ay(temperature(k, ag) * 0.92)]; ag === 18 ? ctx.moveTo(...p) : ctx.lineTo(...p) }
      ctx.stroke(); ctx.restore()
    }
    curve('random', 4); curve('greedy', 4); curve('anneal', 6)
    const la = a * eOut(prog(t, S.temp + 1.0, 0.4))
    text('一直折腾', ax(50) + 18, ay(0.92) + 10, { size: 30, weight: 700, color: C.random, a: la })
    text('求稳', ax(50) + 18, ay(0) - 12, { size: 30, weight: 700, color: C.greedy, a: la })
    text('先闯后收', ax(24) + 14, ay(temperature('anneal', 24) * 0.92) - 18, { size: 30, weight: 700, color: C.anneal, a: la })
  }
  function pathScene(t, c) {
    const a = win(t, S.path, S.ending + 0.6, 0.35, 0.6)
    if (a <= 0) return
    const reveal = eIO(prog(t, S.path + 0.15, 1.8))
    const ageEnd = lerp(18, 36, reveal)
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.strokeStyle = 'rgba(255,178,60,0.5)'; ctx.lineWidth = 6
    ctx.shadowColor = rgba(C.anneal, 0.9); ctx.shadowBlur = 14; ctx.lineJoin = 'round'
    ctx.beginPath()
    for (let ag = 18; ag <= ageEnd; ag += 1 / SPYD) {
      const x = trackAt('anneal', ag), p = toS(c, x, hAt(x))
      ag === 18 ? ctx.moveTo(p[0], p[1] - 7) : ctx.lineTo(p[0], p[1] - 7)
    }
    ctx.globalAlpha = a; ctx.stroke(); ctx.restore()
    const lowX = trackAt('anneal', goldLowAge)
    const [lx, ly] = toS(c, lowX, hAt(lowX))
    callout(t, S.path + 0.15 + 1.8 * ((goldLowAge - 18) / 18), S.ending + 0.4, [lx, ly - 8], { num: String(Math.round(goldLowH)), unit: '米', cap: '19 岁跌到这里', col: C.anneal, dx: 150, dy: -170, size: 58 })
  }
  function endingScene(t, c) {
    const a = prog(t, S.ending + 0.2, 0.5)
    if (a <= 0) return
    const sc = clamp(c.z * 1.05, 0.5, 1.9)
    const tag = (k, s, side, dy) => callout(t, S.ending + 0.3 + KINDS.indexOf(k) * 0.15, T_END + 5, headOf(c, k, t, sc), { num: '', cap: s, col: C[k], side, dx: 120, dy })
    tag('greedy', `求稳 · ${Math.round(F.greedy_h)} 米`, -1, -60)
    tag('anneal', '先闯后收 · 1000 米', 1, -150)
    tag('random', `一直折腾 · ${Math.round(F.random_end_h)} 米，灯还亮着`, -1, -40)
  }

  // ------------------------------------------------------------------ frame
  function renderFrame(t) {
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'
    const c = cam(t)
    sky(t, c)
    ground(c)
    if (t >= S.dip && t < S.three) dipScene(t, c)
    if (t >= S.path && t < T_END) pathScene(t, c)
    const inPanel = (t > S.lamps + 0.3 && t < S.sim - 0.3) || (t > S.grid + 0.3 && t < S.path - 0.3)
    if (!inPanel) drawWalkers(t, c)
    if (t < S.rewind + 0.3) hookScene(t, c)
    if (t >= S.three - 0.1 && t < S.lamps + 0.5) threeScene(t, c)
    if (t >= S.rule && t < S.lamps + 0.5) ruleScene(t, c)
    if (t >= S.sim - 0.1 && t < S.crowd + 0.4) simScene(t, c)
    if (t >= S.crowd - 0.1 && t < S.grid + 0.6) crowdScene(t, c)
    if (t >= S.ending) endingScene(t, c)
    if (t >= S.rewind - 0.1 && t < L.three.t0 + 0.4) rewindScene(t)
    if (t >= S.lamps - 0.1 && t < S.sim + 0.2) lampsScene(t)
    if (t >= S.grid - 0.1 && t < S.temp + 0.2) gridScene(t)
    if (t >= S.temp - 0.1 && t < S.path + 0.2) tempScene(t)
    ageClock(t)
    subtitles(t)
    footer(t)
    const fade = Math.max(1 - prog(t, 0, 0.35), prog(t, T_END - 0.7, 0.7))
    if (fade > 0) { ctx.fillStyle = `rgba(0,0,0,${fade})`; ctx.fillRect(0, 0, W, H) }
  }
  // sound cues for the mix (read by render.mjs --events)
  {
    const E = []
    const add = (t, k, extra = {}) => E.push({ t: +t.toFixed(3), k, ...extra })
    add(0.55, 'pop'); add(L.hook2.t0 + 0.35, 'pop'); add(S.dip + 0.6, 'low')
    add(L.rewind.t0 - 0.05, 'rewind', { d: +(L.rewind.t1 - L.rewind.t0 + 0.15).toFixed(3) })
    ;['求稳', '先闯后收', '一直折腾'].forEach((w) => add(wt('three', w), 'tick'))
    add(wt('rule', '碰到下坡'), 'tick'); [0, 0.15, 0.3].forEach((d) => add(wt('rule', '看你') + d, 'pop'))
    for (let i = 0; i < 8; i++) add(lerp(wt('lamps', '18'), wt('lamps', '一步不走', true), i / 7), 'lamp', { v: i < 7 ? SIM.pdown[i].p : 0 })
    for (let i = 0; i < 8; i++) add(lerp(wt('lamps', '一直折腾'), wt('lamps', '一辈子', true), i / 7), 'lamp', { v: SIM.pdown_random })
    add(tAtAge(goldLowAge), 'low'); add(tAtAge(redTopAge), 'ring'); add(wt('redoff', '自己'), 'pop')
    add(tAtAge(goldTopAge), 'summit'); add(tAtAge(35), 'tick')
    add(S.crowd + 0.1, 'patter', { d: 1.0 })
    for (let m = 0; m < 12; m++) add(S.grid + 0.15 + m * 0.05, 'tick', { quiet: 1 })
    ;['求稳', '先闯后收', '一直折腾'].forEach((w) => add(wt('rates', w) - 0.05, 'pop'))
    add(S.temp + 0.2, 'swell', { d: 1.2 }); add(S.path + 0.15, 'shimmer', { d: 1.8 })
    add(S.ending + 0.3, 'summit')
    window.__EVENTS = { events: E, scenes: S, total: T_END, lines: TL.lines.map((l) => ({ id: l.id, t0: l.t0, t1: l.t1, file: l.file })) }
  }
  // vertical cover: the summit and the small hill, two walkers, the title
  window.renderCover = () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    const c = fit(END.greedy - 0.05, SUMMIT_X + 0.06, 380, 1080, 0.2, 3, 1)
    c.cy += 140 / c.z
    sky(0.8, c); ground(c)
    ridgeSeg(c, END.greedy, F.dip_x, [255, 120, 100], 0.0)
    const sc = clamp(c.z * 1.45, 0.6, 2.4)
    for (const [k, lamp] of [['greedy', 0.0], ['anneal', 0.55]]) {
      const x = END[k], [sx, sy] = toS(c, x, hAt(x))
      walker(sx, sy, sc, C[k], k === 'greedy' ? 1 : -1, 0.6, lamp)
    }
    const [gx, gy] = toS(c, END.greedy, hAt(END.greedy)), [ax, ay] = toS(c, SUMMIT_X, hAt(SUMMIT_X))
    bigNum(String(Math.round(F.greedy_h)), '米', gx, gy - 150 * sc / 1.45 - 30, C.greedy, 0.95, 54, 'center')
    bigNum('1000', '米', ax, ay - 150 * sc / 1.45 - 30, C.anneal, 0.95, 54, 'center')
    const g = ctx.createLinearGradient(0, H * 0.58, 0, H); g.addColorStop(0, 'rgba(10,9,22,0)'); g.addColorStop(1, 'rgba(10,9,22,0.85)')
    ctx.fillStyle = g; ctx.fillRect(0, H * 0.58, W, H * 0.42)
    const line = (parts, y, size) => {
      const total = parts.reduce((w, [p]) => w + measure(p, size, 900, 'Songti SC'), 0)
      let x = W / 2 - total / 2
      for (const [p, col] of parts) x += text(p, x, y, { size, weight: 900, family: 'Songti SC', color: col, shadow: 22 })
    }
    line([['敢走', INK], ['下坡', C.anneal], ['的人，', INK]], H - 330, 112)
    line([['爬得更高？', INK]], H - 190, 112)
    text('三种走法 · 12 座山 × 每种 4000 人', W / 2, H - 100, { size: 36, weight: 600, color: [215, 210, 225], align: 'center', shadow: 12 })
  }
  window.renderFrame = renderFrame
  window.TOTAL = T_END
  window.__S = S
  window.ready = true
})()
