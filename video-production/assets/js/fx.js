/* FIN-04 explainer — shared helpers for every scene.
   Pure functions over window.TL (timeline + cues), window.CAP (capture manifest) and window.GEO.
   Nothing here measures the DOM or reads a clock, so every frame is a function of timeline time. */
(function () {
  const TL = window.TL
  const SC = {}, LN = {}
  TL.scenes.forEach((s) => { SC[s.id] = s; s.lines.forEach((l) => { LN[l.id] = Object.assign({ scene: s.id }, l) }) })
  const norm = (w) => String(w).toLowerCase().replace(/[^a-z0-9%$.]/g, '').replace(/\.$/, '')

  const FX = {
    TL, SC, LN,
    scene: (id) => SC[id],
    line: (id) => LN[id],
    /** absolute start (or end) time of the n-th word in a line that starts with `text` */
    word(id, text, n = 0, edge = 's') {
      const l = LN[id]; const want = norm(text); let k = 0
      for (const w of l.words) { if (norm(w.w).startsWith(want)) { if (k === n) return w[edge]; k++ } }
      throw new Error(`word "${text}" not found in ${id}`)
    },
    cue: (id) => { if (!(id in TL.cues)) throw new Error('cue ' + id); return TL.cues[id] },
    rec: (id) => TL.rec[id],
    /** converter from absolute time to a scene-local time */
    clock(sceneId) { const s0 = SC[sceneId].slot_start; return (t) => +(t - s0).toFixed(4) },

    h(tag, attrs, parent, html) {
      const el = document.createElement(tag)
      for (const [k, v] of Object.entries(attrs || {})) { if (k === 'style') Object.assign(el.style, v); else el.setAttribute(k, v) }
      if (html != null) el.innerHTML = html
      if (parent) parent.appendChild(el)
      return el
    },
    svg(tag, attrs, parent) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', tag)
      for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v)
      if (parent) parent.appendChild(el)
      return el
    },

    /** quadratic bezier between a and b with a perpendicular bend; returns path data, length and a sampler */
    curve(a, b, bend = 0.18) {
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y
      const c = { x: mx - dy * bend, y: my + dx * bend }
      const at = (t) => ({ x: (1 - t) ** 2 * a.x + 2 * (1 - t) * t * c.x + t * t * b.x, y: (1 - t) ** 2 * a.y + 2 * (1 - t) * t * c.y + t * t * b.y })
      let len = 0, p = a
      for (let i = 1; i <= 40; i++) { const q = at(i / 40); len += Math.hypot(q.x - p.x, q.y - p.y); p = q }
      return { d: `M${a.x.toFixed(1)} ${a.y.toFixed(1)}Q${c.x.toFixed(1)} ${c.y.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`, len, at }
    },

    /** count a number into el.textContent; fmt(v) formats the value */
    countTo(tl, el, from, to, at, dur, fmt) {
      const st = { v: from }
      el.textContent = fmt(from)
      tl.to(st, { v: to, duration: dur, ease: 'power2.out', onUpdate: () => { el.textContent = fmt(st.v) } }, at)
      tl.set(st, { v: to, onComplete: () => { el.textContent = fmt(to) } }, at + dur)
    },

    /** seek-safe one-shot effect: jump to `from` at t, then tween to `to` (no immediateRender leakage before t) */
    burst(tl, el, t, from, to) {
      tl.set(el, from, t)
      tl.to(el, to, t)
    },

    /** split an element's text into word spans (keeps inner markup of <em>/<span> words) */
    words(el) {
      const out = []
      const walk = (node) => {
        for (const child of Array.from(node.childNodes)) {
          if (child.nodeType === 3) {
            const frag = document.createDocumentFragment()
            for (const p of child.textContent.split(/(\s+)/)) {
              if (!p) continue
              if (/^\s+$/.test(p)) { frag.appendChild(document.createTextNode(p)); continue }
              const s = document.createElement('span'); s.className = 'fx-w'; s.style.display = 'inline-block'; s.textContent = p
              frag.appendChild(s); out.push(s)
            }
            node.replaceChild(frag, child)
          } else if (child.nodeType === 1) walk(child)
        }
      }
      walk(el)
      return out
    },

    /** standard scene envelope: fade the stage in over the cross-fade window and out at the slot end */
    envelope(tl, stage, sceneId, { fadeIn = true, fadeOut = true } = {}) {
      const s = SC[sceneId], dur = s.slot_duration, x = TL.xfade
      tl.fromTo(stage, { opacity: fadeIn && s.slot_start > 0 ? 0 : 1 }, { opacity: 1, duration: x + 0.05, ease: 'power1.out' }, 0)
      if (fadeOut && s.end < TL.total - 0.01) tl.to(stage, { opacity: 0, duration: x, ease: 'power1.in' }, dur - x)
    },

    chapter(parent, num, title) {
      return FX.h('div', { class: 'fx-chapter' }, parent, `<b>${num}</b><i></i><span>${title}</span>`)
    },

    // ---------- camera over a 1920x1080 capture ----------
    camRest: { s: 0.8, x: 192, y: 140 },
    /** camera that frames rect r (capture CSS px) with padding, clamped so the capture covers the screen when s>=1 */
    camFocus(r, { pad = 140, max = 2.2, min = 0.8, dy = 0, dx = 0 } = {}) {
      const s = Math.max(min, Math.min(max, (1920 - 2 * pad) / r.w, (1080 - 2 * pad) / r.h))
      let x = 960 + dx - s * (r.x + r.w / 2), y = 540 + dy - s * (r.y + r.h / 2)
      if (s >= 1) { x = Math.min(0, Math.max(1920 - 1920 * s, x)); y = Math.min(0, Math.max(1080 - 1080 * s, y)) }
      return { s: +s.toFixed(4), x: +x.toFixed(1), y: +y.toFixed(1) }
    },
    /** screen position of a capture-space point under a camera */
    toScreen(cam, p) { return { x: cam.x + cam.s * p.x, y: cam.y + cam.s * p.y } },
    camTo(tl, camEl, cam, at, dur = 1.2, ease = 'power3.inOut') {
      tl.to(camEl, { x: cam.x, y: cam.y, scale: cam.s, duration: dur, ease }, at)
    },
    camSet(tl, camEl, cam, at) { tl.set(camEl, { x: cam.x, y: cam.y, scale: cam.s }, at) },

    /** a browser frame holding a capture (img or video element supplied by the scene) */
    browser(parent, url, live) {
      const cam = FX.h('div', { class: 'fx-cam', 'data-layout-allow-overflow': '' }, parent)
      const frame = FX.h('div', { class: 'fx-browser' }, cam)
      FX.h('div', { class: 'bar', 'data-layout-allow-overflow': '' }, frame, `<i></i><i></i><i></i><div class="url">${url}</div>${live ? `<div class="live">${live}</div>` : ''}`)
      return { cam, frame }
    },
    rect(shot, key) {
      const r = window.CAP.stills[shot].rects[key]
      if (!r) throw new Error(`rect ${shot}.${key} missing`)
      return r
    },
    /** where a capture-space rect lands on screen under a camera */
    screenRect(cam, r) { return { x: cam.x + cam.s * r.x, y: cam.y + cam.s * r.y, w: cam.s * r.w, h: cam.s * r.h } },
    /** screen-space callout card: k = label, v = big value (html), s = sub line */
    callout(parent, { k = '', v = '', s = '', cls = '' }, x, y, width) {
      return FX.h('div', { class: 'fx-callout ' + cls, style: { left: x + 'px', top: y + 'px', width: width ? width + 'px' : 'auto', opacity: 0 } }, parent,
        `${k ? `<div class="k">${k}</div>` : ''}${v ? `<div class="v">${v}</div>` : ''}${s ? `<div class="s">${s}</div>` : ''}`)
    },
    /** chapter mark + "live" tag shared by the demo scenes */
    demoChrome(stage, tl) {
      const chap = FX.chapter(stage, '04', 'Live demo')
      const live = FX.h('div', { class: 'fx-tag fx-live' }, stage, '<span class="dot"></span>Running locally · synthetic data')
      tl.fromTo([chap, live], { opacity: 0 }, { opacity: 1, duration: 0.5 }, 0.1)
      return { chap, live }
    },

    /** highlight box positioned in capture space */
    hl(frame, r, { pad = 8, cls = '' } = {}) {
      return FX.h('div', { class: 'fx-hl ' + cls, style: { left: r.x - pad + 'px', top: r.y - pad + 'px', width: r.w + 2 * pad + 'px', height: r.h + 2 * pad + 'px', opacity: 0 } }, frame)
    },
  }
  window.FX = FX
})()
