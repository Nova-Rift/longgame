// Long Game player: draws the observation grid an agent gets and sends the same actions an agent sends.
// Keys work anywhere on the page (no need to click the board): arrows or WASD move, space / Enter / E interact
// (the USE action), R restarts.
// Typing in a form field, ctrl/cmd/alt shortcuts and space or Enter on a focused button or link keep their usual
// meaning. A held key moves once; its repeats are swallowed so the page does not scroll.
'use strict';
(() => {
  const TOKEN = document.querySelector('meta[name="longgame-token"]').content;
  const ACT = { RESET: 0, UP: 1, DOWN: 2, LEFT: 3, RIGHT: 4, USE: 5 };
  const KEYS = { ArrowUp: ACT.UP, KeyW: ACT.UP, ArrowDown: ACT.DOWN, KeyS: ACT.DOWN, ArrowLeft: ACT.LEFT, KeyA: ACT.LEFT,
    ArrowRight: ACT.RIGHT, KeyD: ACT.RIGHT, Space: ACT.USE, Enter: ACT.USE, KeyE: ACT.USE, KeyR: ACT.RESET };
  const $ = (id) => document.getElementById(id);
  const canvas = $('board'), ctx = canvas.getContext('2d');
  let state = null, pending = Promise.resolve(), queued = 0, confirmTimer = null;

  // ---- drawing: one rounded square per cell, with simple shapes so cell types are easy to tell apart ----
  const BG = '#0e0d13', FLOOR = '#1d1b25', HUD = '#2c2a36';
  function rr(x, y, w, h, r, fill) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); ctx.fillStyle = fill; ctx.fill(); }
  function ring(x, y, w, h, r, width, colour) {
    ctx.beginPath(); const o = width / 2;
    ctx.roundRect ? ctx.roundRect(x + o, y + o, w - width, h - width, r) : ctx.rect(x + o, y + o, w - width, h - width);
    ctx.lineWidth = width; ctx.strokeStyle = colour; ctx.stroke();
  }
  function circle(cx, cy, r, fill) { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill(); }
  function drawCell(c, x, y, s, hud) {
    const r = Math.max(2, s * 0.12), b = Math.max(2, s * 0.09), cx = x + s / 2, cy = y + s / 2;
    const base = { 1: hud ? HUD : '#5d5a6b', 3: '#1f9d55', 9: '#8a6a12', 10: '#a8e4f0', 12: '#7a4ad8' }[c] || FLOOR;
    rr(x, y, s, s, r, base);
    const inset = (f) => [x + s * f, y + s * f, s * (1 - 2 * f)];
    switch (c) {
      case 2: circle(cx, cy, s * 0.38, '#4c8ff7'); break;                       // player
      case 4: ring(x, y, s, s, r, b, '#1f6b3f'); break;                          // exit, closed
      case 5: { const [ix, iy, w] = inset(0.1); rr(ix, iy, w, w, r * 0.7, '#b8682a'); ring(ix, iy, w, w, r * 0.7, b, '#8a4b1c'); break; }
      case 6: ring(x, y, s, s, r, b, '#d29a35'); break;                          // pad
      case 7: { ring(x, y, s, s, r, b, '#d29a35'); const [ix, iy, w] = inset(0.1);  // crate on a pad
        rr(ix, iy, w, w, r * 0.7, '#f0b443'); ring(ix, iy, w, w, r * 0.7, b, '#b07a1d'); break; }
      case 8: { ctx.save(); ctx.translate(cx, cy); ctx.rotate(Math.PI / 4); const k = s * 0.32;  // key
        rr(-k / 2, -k / 2, k, k, 2, '#f5d02f'); ctx.restore(); break; }
      case 9: rr(x + s * 0.42, y + s * 0.36, s * 0.16, s * 0.28, s * 0.06, '#3a2d06'); break;  // door
      case 11: ctx.beginPath(); ctx.arc(cx, cy, s * 0.28, 0, Math.PI * 2); ctx.lineWidth = b; ctx.strokeStyle = '#e2559c'; ctx.stroke(); break;
      case 13: ring(x, y, s, s, r, Math.max(1.5, b * 0.7), '#4f3a7c'); break;   // gate, open
      case 14: circle(cx, cy, s * 0.38, '#e5484d'); break;                      // twin
      case 15: circle(cx, cy, s * 0.16, '#f3f3f3'); break;                      // coin
    }
  }
  function draw(grid) {
    const h = grid.length, w = grid[0].length, gap = 2, pad = 6;
    const avail = Math.min(canvas.parentElement.clientWidth, 640);
    const cell = Math.max(12, Math.floor(Math.min((avail - 2 * pad) / w, (window.innerHeight * 0.58 - 2 * pad) / h)));
    const cssW = w * cell + 2 * pad, cssH = h * cell + 2 * pad, dpr = window.devicePixelRatio || 1;
    canvas.style.width = cssW + 'px'; canvas.style.height = cssH + 'px';
    canvas.width = Math.round(cssW * dpr); canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = BG; ctx.fillRect(0, 0, cssW, cssH);
    grid.forEach((row, y) => row.forEach((c, x) =>
      drawCell(c, pad + x * cell + gap / 2, pad + y * cell + gap / 2, cell - gap, y === h - 1)));
  }

  // ---- text ----
  const pct = (x) => `${Math.round(100 * x)}%`;
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  function el(tag, text, cls) { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; }

  // Mouse clicks must not leave focus on a button: Space or Enter would then press that button again instead of
  // reaching the game (keyboard users who Tab to a button still get its normal behaviour).
  const noFocus = (b) => b.addEventListener('mousedown', (e) => e.preventDefault());

  function render(note) {
    if (confirmTimer) { clearTimeout(confirmTimer); confirmTimer = null; }  // a pending "click again" expires
    const o = state.observation, card = state.scorecard, lt = state.lifetime;
    $('lifetime-title').textContent = `${lt.title} · ${lt.visits} visits · ${card.total} levels`;
    const status = $('status'); status.replaceChildren();
    if (o.done) status.append(el('strong', 'Lifetime complete'));
    else status.append(el('strong', `World ${o.world}`), el('span', `level ${o.level + 1} of ${o.levels}`),
      el('span', cap(o.phase), 'lg-chip'), el('span', `${o.actions} / ${o.budget} actions`, 'lg-moves'));

    $('pad').hidden = o.done; canvas.hidden = o.done; $('keys-hint').hidden = o.done;
    const fin = $('final'); fin.hidden = !o.done; fin.replaceChildren();
    if (o.done) {
      const p = el('p'); p.append('Total score '); p.append(el('span', pct(card.overall), 'big')); fin.append(p);
      fin.append(el('p', lt.phases.map((ph) => `${cap(ph)} ${pct(card.phases[ph])}`).join(' · ')));
      const b = state.baselines || {};
      if (Object.keys(b).length) fin.append(el('p', 'For comparison: ' + Object.entries(b).map(([k, v]) => `${k} agent ${pct(v)}`).join(', ') + '.', 'lg-note'));
      if (state.recording) fin.append(el('p', `Your run is saved at ${state.recording}. Check it with: ${state.verify}`, 'lg-note'));
    } else draw(o.grid);

    const msg = $('message'); msg.replaceChildren();
    if (note) msg.append(el('span', note, 'lg-error'));
    else if (state.last) {
      const r = state.last;
      if (r.cleared) { msg.append(`World ${r.world} level ${r.level + 1} done in ${r.actions} actions (fewest possible ${r.par}): `); msg.append(el('strong', pct(r.score), 'good')); }
      else { msg.append(`Out of actions on world ${r.world} level ${r.level + 1}: `); msg.append(el('strong', '0%', 'bad')); }
    } else if (!o.done) msg.textContent = state.moves ? 'Every key press counts as an action, restarts too.'
      : 'No instructions: work out each world by playing.';

    const score = $('score'); score.replaceChildren(el('span', 'Your score so far', 'label'));
    lt.phases.forEach((ph) => { const s = el('span', `${cap(ph)} `); s.append(el('strong', state.phases_played.includes(ph) ? pct(card.phases[ph]) : '—')); score.append(s); });
    score.append(el('span', `${card.played} of ${card.total} levels`));
    const reset = el('button', 'Start over', 'lg-reset'); reset.type = 'button'; reset.onclick = startOver; noFocus(reset);
    score.append(reset);
  }

  // ---- talking to the local server; actions are sent one at a time, in order ----
  async function api(path, body) {
    const res = await fetch(path, { method: body ? 'POST' : 'GET', headers: { 'X-Longgame-Token': TOKEN, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }
  function act(action) {
    if (!state || state.observation.done || queued > 30) return;
    queued++;
    pending = pending.then(async () => {
      try { state = await api('/api/step', { action }); render(); }
      catch (e) { render(`Could not reach the game (${e.message}). Is "longgame play" still running?`); }
      finally { queued--; }
    });
  }
  function startOver(ev) {
    const btn = ev.currentTarget;
    if (!confirmTimer) { btn.textContent = 'Click again to start over'; confirmTimer = setTimeout(() => { confirmTimer = null; btn.textContent = 'Start over'; }, 4000); return; }
    clearTimeout(confirmTimer); confirmTimer = null;
    pending = pending.then(async () => {
      try { state = await api('/api/start-over', {}); render(); }
      catch (e) { render(`Could not start over (${e.message}).`); }
    });
  }

  // ---- keys ----
  function typing(t) { return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); }
  window.addEventListener('keydown', (e) => {
    const a = KEYS[e.code];
    if (a === undefined || e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
    if ((e.code === 'Space' || e.code === 'Enter') && e.target.closest && e.target.closest('button,a')) return;
    e.preventDefault();
    if (e.repeat) return;
    act(a);
  });
  document.querySelectorAll('[data-action]').forEach((b) => { noFocus(b); b.addEventListener('click', () => act(Number(b.dataset.action))); });
  window.addEventListener('resize', () => { if (state && !state.observation.done) draw(state.observation.grid); });

  api('/api/state').then((s) => { state = s; render(); })
    .catch((e) => { $('message').replaceChildren(el('span', `Could not load the game: ${e.message}`, 'lg-error')); });
})();
