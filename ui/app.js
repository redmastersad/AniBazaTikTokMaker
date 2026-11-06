'use strict';
/* AniBaza TikTok Studio UI. Talks to Python through window.pywebview.api (see app.py, class Api). */

const S = {
  screen: 'new', settings: null, presets: {}, builtin: [], fonts: [], logos: [], music: [], categories: [],
  channel: null, system: null, prog: { running: false, paused: false, jobs: [], uploads: { items: [] }, tiktok: { items: [] } },
  tt: null, ttFocus: false, ttKeys: false,
  log: [], logSeq: 0, clips: [], clipsDir: '', clipSel: new Set(), clipFilter: 'all', clipsDone: -1,
  layer: 'subs', safe: 'tiktok', loadedFonts: new Set(), logoUri: {}, upFocus: false,
};
const LAYERS = { subs: 'Субтитры', title: 'Заголовок', logo: 'Логотип' };
const STEPS = ['Расшифровка', 'Поиск моментов', 'Монтаж и субтитры'];
const MODELS = ['llama3.1', 'qwen2.5:14b', 'gemma2:9b', 'mistral'];
const SAMPLE = 'ты ещё не понял с кем связался?'.split(' ');
const SAFE = {
  tiktok: [[84, 36, 16, 44], [0, 85, 100, 15], [0, 0, 100, 7]],
  shorts: [[82, 46, 18, 40], [0, 87, 100, 13]],
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = () => window.pywebview.api;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmtT = s => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
const fmtSize = b => b > 1e9 ? (b / 1e9).toFixed(1) + ' ГБ' : Math.round(b / 1e6) + ' МБ';
const stars = n => n ? '★'.repeat(n) + '☆'.repeat(5 - n) : '';
const catLabel = id => (S.categories.find(c => c.id === id) || {}).label || '';
const plural = (n, a, b, c) => { const m10 = n % 10, m100 = n % 100; return m10 === 1 && m100 !== 11 ? a : (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? b : c); };
const epName = j => j.show + (j.episode ? ' — ' + j.episode : '');

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('on'), 2600);
}
function modal(html) {
  return new Promise(resolve => {
    $('#modalBody').innerHTML = html; $('#modal').classList.add('on');
    const inp = $('#modalBody textarea') || $('#modalBody input'); if (inp) setTimeout(() => inp.focus(), 30);
    const done = v => { const ai = $('#tcAi'); if (ai) editTimecodes._ai = ai.checked; $('#modal').classList.remove('on'); resolve(v); };
    $('#modalBody').onclick = e => {
      const b = e.target.closest('[data-m]'); if (!b) return;
      done(b.dataset.m === 'ok' ? (inp ? inp.value : true) : null);
    };
    $('#modalBody').onkeydown = e => {
      if (e.key === 'Enter' && (e.target.tagName !== 'TEXTAREA' || e.ctrlKey)) done(inp ? inp.value : true);
      if (e.key === 'Escape') done(null);
    };
  });
}
const confirmBox = (title, text, ok = 'Да') => modal(`<b style="font-size:16px">${esc(title)}</b><div class="mute">${esc(text)}</div>
  <div style="display:flex;gap:10px;justify-content:flex-end"><button class="btn" data-m="no">Отмена</button><button class="btn p" data-m="ok">${esc(ok)}</button></div>`);

/* ------------------------------------------------------------------ settings */
let saveTimer;
function save() { clearTimeout(saveTimer); saveTimer = setTimeout(() => api().save_settings(S.settings), 350); }
function set(key, val) { S.settings[key] = val; save(); }
function setStyle(layer, key, val, rerender = true) {
  S.settings.style[layer][key] = val;
  S.settings.preset = '';
  save();
  if (rerender) refreshPreviews();
}

/* ------------------------------------------------------------------ fonts & logo */
async function ensureFont(name) {
  if (S.loadedFonts.has(name)) return;
  const f = S.fonts.find(x => x.name === name); if (!f) return;
  S.loadedFonts.add(name);
  try {
    const uri = await api().font_data(f.file);
    if (!uri) return;
    const face = new FontFace(name, `url(${uri})`);
    await face.load(); document.fonts.add(face);
    refreshPreviews(); if (S.screen === 'style') renderFontList();
  } catch (e) { console.warn(e); }
}
async function logoUri(name) {
  const key = name || '';
  if (!(key in S.logoUri)) { S.logoUri[key] = null; S.logoUri[key] = await api().logo_data(key); refreshPreviews(); }
  return S.logoUri[key];
}
const ratio = name => (S.fonts.find(f => f.name === name) || {}).em_ratio || 0.82;

/* ------------------------------------------------------------------ preview */
function caseText(t, c) { return c === 'upper' ? t.toUpperCase() : c === 'lower' ? t.toLowerCase() : t; }
function textCss(L, k) {
  const sw = 2 * (+L.outline || 0) * k;
  return `font-family:'${L.font}';font-size:${(L.size * ratio(L.font) * k).toFixed(2)}px;color:${L.color};` +
    `letter-spacing:${(L.spacing * k).toFixed(2)}px;-webkit-text-stroke:${sw.toFixed(2)}px ${L.outline_color};` +
    (L.shadow ? `text-shadow:${(4 * k).toFixed(1)}px ${(4 * k).toFixed(1)}px 0 rgba(0,0,0,.5);` : '') +
    `left:${L.x}%;top:${L.y}%;max-width:${L.width}%;width:max-content;`;
}
function sampleTitle() {
  for (const j of [...S.prog.jobs].reverse()) if (j.moments && j.moments.length) return j.moments[0].title;
  return 'Годзё против всех';
}
function previewBg() {
  const j = S.prog.jobs.find(x => x.thumb);
  return j ? `url(${j.thumb})` : 'radial-gradient(circle at 60% 40%,#7cf7ff 0,#2b7fff 25%,#1a1f5c 55%,#07081a 90%)';
}
function previewHTML(H, edit) {
  const st = S.settings.style, k = H / 1920, W = Math.round(H * 9 / 16);
  const bg = previewBg();
  const cls = ['pv', edit ? 'edit' : '', S.settings.mirror ? 'mirror' : '', S.settings.filters ? 'fx' : ''].join(' ');
  let h = `<div class="${cls}" style="width:${W}px;height:${H}px;box-sizing:content-box" data-k="${k}">
    <div class="bgl" style="background-image:${bg}"></div><div class="fgl" style="background-image:${bg}"></div>`;
  if (edit && S.safe) for (const [x, y, w, hh] of SAFE[S.safe]) h += `<div class="safe" style="left:${x}%;top:${y}%;width:${w}%;height:${hh}%"></div>`;
  if (edit) h += `<div class="guide"></div>`;
  const L = st.logo, uri = S.logoUri[L.file || ''];
  if (L.visible) {
    if (uri === undefined) logoUri(L.file);
    h += `<div class="el logo ${S.layer === 'logo' ? 'sel' : ''}" data-layer="logo" style="left:${L.x}%;top:${L.y}%;width:${L.width}%">${uri ? `<img src="${uri}">` : ''}</div>`;
  }
  const T = st.title;
  if (T.visible) {
    ensureFont(T.font);
    h += `<div class="el ${S.layer === 'title' ? 'sel' : ''}" data-layer="title" style="${textCss(T, k)}">${esc(caseText(sampleTitle(), T.case))}</div>`;
  }
  const U = st.subs;
  if (U.visible) {
    ensureFont(U.font);
    const n = clamp(+U.words || 3, 1, SAMPLE.length), active = n > 1 ? 1 : 0;
    const words = SAMPLE.slice(0, n).map((w, i) => {
      const t = esc(caseText(w, U.case));
      return i === active && U.anim !== 'none' ? `<span style="color:${U.hl}">${t}</span>` : t;
    });
    h += `<div class="el ${S.layer === 'subs' ? 'sel' : ''}" data-layer="subs" style="${textCss(U, k)}">${words.join(' ')}</div>`;
  }
  if (edit) {
    const sel = st[S.layer];
    if (sel && sel.visible) h += `<div class="badge" style="left:${sel.x}%;top:${clamp(+sel.y + 7, 2, 95)}%">X ${Math.round(sel.x)}% · Y ${Math.round(sel.y)}%</div>`;
  }
  return h + '</div>';
}
function refreshPreviews() {
  const mini = $('#miniPv'); if (mini) mini.innerHTML = previewHTML(300, false);
  const big = $('#bigPv'); if (big) big.innerHTML = previewHTML(bigH(), true);
}
function bigH() {
  const stage = $('#stage'); if (!stage) return 540;
  const byW = (stage.clientWidth - 140 - 24 - 40) * 16 / 9;
  return Math.round(Math.max(300, Math.min(stage.clientHeight - 40, byW, 660)));
}

/* drag in the big preview */
let drag = null;
document.addEventListener('pointerdown', e => {
  const el = e.target.closest('#bigPv .el'); if (!el) return;
  const layer = el.dataset.layer;
  if (layer !== S.layer) { S.layer = layer; renderStyleSide(); renderLayers(); refreshPreviews(); }
  const pv = $('#bigPv .pv'), r = pv.getBoundingClientRect(), L = S.settings.style[layer];
  drag = { layer, r, dx: e.clientX - (r.left + r.width * L.x / 100), dy: e.clientY - (r.top + r.height * L.y / 100) };
  e.preventDefault();
});
document.addEventListener('pointermove', e => {
  if (!drag) return;
  const { r, layer } = drag, L = S.settings.style[layer];
  let x = (e.clientX - drag.dx - r.left) / r.width * 100, y = (e.clientY - drag.dy - r.top) / r.height * 100;
  x = clamp(x, 0, 100); y = clamp(y, 0, 100);
  const snap = Math.abs(x - 50) < 1.6; if (snap) x = 50;
  L.x = Math.round(x * 10) / 10; L.y = Math.round(y * 10) / 10;
  const el = $(`#bigPv .el[data-layer="${layer}"]`); if (el) { el.style.left = L.x + '%'; el.style.top = L.y + '%'; }
  const b = $('#bigPv .badge'); if (b) { b.style.left = L.x + '%'; b.style.top = clamp(L.y + 7, 2, 95) + '%'; b.textContent = `X ${Math.round(L.x)}% · Y ${Math.round(L.y)}%`; }
  const g = $('#bigPv .guide'); if (g) g.classList.toggle('on', snap);
});
document.addEventListener('pointerup', () => {
  if (!drag) return; drag = null;
  S.settings.preset = ''; save(); refreshPreviews(); renderStyleSide(); renderPresets();
});
document.addEventListener('keydown', e => {
  if (S.screen !== 'style' || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key]; if (!d) return;
  e.preventDefault();
  const L = S.settings.style[S.layer], step = e.shiftKey ? 2 : 0.5;
  L.x = clamp(Math.round((+L.x + d[0] * step) * 10) / 10, 0, 100); L.y = clamp(Math.round((+L.y + d[1] * step) * 10) / 10, 0, 100);
  S.settings.preset = ''; save(); refreshPreviews(); renderStyleSide(); renderPresets();
});

/* ------------------------------------------------------------------ navigation */
function go(screen) {
  S.screen = screen;
  $$('.nav').forEach(n => n.classList.toggle('on', n.dataset.s === screen));
  $$('.main').forEach(m => m.classList.toggle('on', m.id === 's-' + screen));
  ({ new: renderNew, style: renderStyle, run: renderRun, clips: loadClips, up: renderUp, tt: renderTT, settings: renderSettings })[screen]();
}
$$('.nav').forEach(n => n.onclick = () => go(n.dataset.s));

/* ------------------------------------------------------------------ sidebar */
function renderSys() {
  const s = S.system || {}, g = s.gpu, o = s.ollama || {};
  const model = S.settings.ollama_model, has = (o.models || []).some(m => m === model || m.startsWith(model + ':'));
  $('#sys').innerHTML = (g
    ? `<div class="t"><span><span class="dot"></span>${esc(g.name)}</span><span>${g.used.toFixed(1)}/${g.total.toFixed(0)} ГБ</span></div><div class="bar"><i style="width:${Math.round(g.used / g.total * 100)}%"></i></div>`
    : `<div class="t"><span><span class="dot off"></span>Видеокарта не найдена</span></div><div style="height:10px"></div>`) +
    `<div class="t"><span><span class="dot ${o.ok && has ? '' : 'off'}"></span>Ollama · ${esc(model)}</span><span>${!o.ok ? 'выкл' : has ? 'готов' : 'нет модели'}</span></div>`;
}
function renderBadges() {
  const jobs = S.prog.jobs, q = jobs.filter(j => j.status === 'queued').length;
  $('#bQueue').textContent = q && !S.prog.running ? q : '';
  $('#bRun').textContent = S.prog.running ? (S.prog.paused ? '❚❚' : jobs.filter(j => j.status === 'queued' || j.status === 'running').length) : '';
  $('#bClips').textContent = S.clips.length || '';
  const u = (S.prog.uploads.items || []).filter(x => x.status === 'queued' || x.status === 'running').length;
  $('#bUp').textContent = u || '';
  const tq = ((S.prog.tiktok || {}).items || []).filter(x => ['queued', 'running', 'download'].includes(x.status)).length;
  $('#bTT').textContent = tq || '';
}

/* ------------------------------------------------------------------ NEW */
function renderNew() {
  const st = S.settings;
  const presetNames = Object.keys(S.presets);
  const installed = (S.system && S.system.ollama && S.system.ollama.models) || [];
  const models = [...new Set([...installed, st.ollama_model, ...MODELS])];
  $('#s-new').innerHTML = `
  <div class="head"><div><h1>Новая нарезка</h1><div class="sub">Кидай серии — ИИ найдёт лучшие моменты и сам смонтирует шортсы</div></div></div>
  <div class="grid2">
    <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
      <div class="drop" id="drop"><div class="ic"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4M6 10l6-6 6 6M4 20h16"/></svg></div>
        <div style="flex:1"><b style="font-size:15px">${BRIDGE ? 'Выбери серии' : 'Перетащи серии сюда'}</b><div class="mute small">${BRIDGE ? 'Кнопка справа · можно сразу пачкой' : 'MP4, MKV, MOV, AVI, WEBM · можно сразу пачкой'}</div></div>
        <button class="btn" data-act="pick">Выбрать файлы</button></div>
      <div class="mute small" id="qInfo" style="display:flex;justify-content:space-between"></div>
      <div class="eplist scroll" id="eplist" style="flex:1"></div>
      <div class="card" style="padding:16px 18px;flex:none">
        <div class="sec">Что искать</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap" id="cats">${S.categories.map(c => `<span class="chip ${st.categories.includes(c.id) ? 'on' : ''}" data-cat="${c.id}">${esc(c.label)}</span>`).join('')}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;margin-top:14px">
          <div><div class="kv"><span>Клип от</span><b id="vMin">${st.clip_min} сек</b></div><input type="range" min="10" max="60" step="5" value="${st.clip_min}" data-num="clip_min"></div>
          <div><div class="kv"><span>Клип до</span><b id="vMax">${st.clip_max} сек</b></div><input type="range" min="20" max="180" step="5" value="${st.clip_max}" data-num="clip_max"></div>
          <div><div class="kv"><span>Клипов с серии</span><b id="vCnt">до ${st.max_clips}</b></div><input type="range" min="1" max="12" value="${st.max_clips}" data-num="max_clips"></div>
        </div>
      </div>
      <button class="btn p big" id="startBtn" data-act="start"></button>
    </div>
    <div class="card scroll" style="padding:18px;display:flex;flex-direction:column;gap:4px">
      <div class="sec" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">Стиль клипа <span class="btn sm ghost" data-act="gostyle" style="font-family:'Golos UI';letter-spacing:0;text-transform:none;font-size:12px">Настроить →</span></div>
      <div style="display:flex;gap:16px;align-items:flex-start">
        <div id="miniPv" style="cursor:pointer" data-act="gostyle"></div>
        <div style="flex:1;display:flex;flex-direction:column;gap:10px;font-size:12px;min-width:0">
          <div><div class="mute">Пресет</div><select data-set="preset" style="min-width:0;width:100%;margin-top:4px">${st.preset ? '' : '<option value="" selected>Свой</option>'}${presetNames.map(n => `<option ${n === st.preset ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
          <div><div class="mute">Субтитры</div><b>${esc(st.style.subs.font)}</b></div>
          <div><div class="mute">Слов на экране</div><b>${st.style.subs.words}</b></div>
        </div>
      </div>
      <div class="row" style="margin-top:10px"><span>Музыка</span><div style="display:flex;gap:6px"><select data-set="music" style="min-width:0;max-width:190px"><option value="">Без музыки</option>${S.music.map(m => `<option ${m === st.music ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select><button class="btn sm" data-act="pickmusic" title="Добавить свой трек">＋</button></div></div>
      <div class="row" style="gap:12px"><span class="mute small" style="white-space:nowrap">Громкость</span><input type="range" min="-40" max="0" step="1" value="${st.music_volume}" data-num="music_volume"><span class="small" id="vVol" style="white-space:nowrap">${st.music_volume} дБ</span></div>
      <div class="row"><span>Вырезать тишину <span class="mute small">&gt; ${st.silence_gap} сек</span></span><div class="tg ${st.remove_silence ? 'on' : ''}" data-tg="remove_silence"></div></div>
      <div class="row"><span>Зеркалить кадр <span class="mute small">против копирайта</span></span><div class="tg ${st.mirror ? 'on' : ''}" data-tg="mirror"></div></div>
      <div class="row"><span>Срезать вшитые сабы <span class="mute small">низ кадра ${st.hardsub_band}%</span></span><div class="tg ${st.cut_hardsubs ? 'on' : ''}" data-tg="cut_hardsubs"></div></div>
      <div class="row"><span>Цвет, зерно, виньетка</span><div class="tg ${st.filters ? 'on' : ''}" data-tg="filters"></div></div>
      <div class="row"><span>Нейросеть</span><select data-set="ollama_model" style="min-width:0;max-width:190px">${models.map(m => `<option value="${esc(m)}" ${m === st.ollama_model ? 'selected' : ''}>${esc(m)}${installed.length && !installed.includes(m) ? ' (не скачана)' : ''}</option>`).join('')}</select></div>
      <div class="row"><span>Папка для клипов</span><span class="btn sm" data-act="outdir" title="${esc(st.out_dir)}" style="max-width:190px;overflow:hidden;text-overflow:ellipsis">📁 ${esc(st.out_dir.split(/[\\/]/).pop() || st.out_dir)}</span></div>
    </div>
  </div>`;
  renderQueue(); refreshPreviews();
  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('hover'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove('hover')));
}
function renderQueue() {
  const box = $('#eplist'); if (!box) return;
  const jobs = S.prog.jobs.filter(j => j.status === 'queued');
  const dur = jobs.reduce((a, j) => a + (j.duration || 0), 0);
  $('#qInfo').innerHTML = jobs.length ? `<span>В очереди: ${jobs.length} ${plural(jobs.length, 'серия', 'серии', 'серий')} · ${fmtT(dur)} видео</span><span>${S.prog.running ? 'идёт обработка' : ''}</span>` : '';
  box.innerHTML = jobs.length ? jobs.map(j => `
    <div class="ep"><div class="th" style="${j.thumb ? `background-image:url(${j.thumb})` : ''}"><b>${j.duration ? fmtT(j.duration) : '…'}</b></div>
      <div style="min-width:0"><b>${esc(epName(j))}</b><div class="mute small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(j.path)} · ${fmtSize(j.size)}</div>
        <div class="epx">
          <span class="chip ${j.subs_file ? 'on' : ''}" data-subs="${j.id}" title="${j.subs_file ? esc(j.subs_file) : 'Готовые .ass / .srt вместо распознавания речи'}">💬 ${j.subs_file ? esc(j.subs_file.split(/[\\/]/).pop()) : 'Свои субтитры'}${j.subs_file ? `<i data-nosubs="${j.id}" title="Убрать, распознать речь">×</i>` : ''}</span>
          <span class="chip ${j.manual.length ? 'on' : ''}" data-tc="${j.id}" title="Свои моменты вместо выбора нейросетью">⏱ ${j.manual.length ? `Таймкоды: ${j.manual.length}` : 'Таймкоды вручную'}</span>
        </div></div>
      <span class="chip">${j.manual.length && !j.manual_plus_ai ? `${j.manual.length} ${plural(j.manual.length, 'клип', 'клипа', 'клипов')}` : j.manual.length ? `${j.manual.length} + до ${S.settings.max_clips} клипов` : `до ${S.settings.max_clips} клипов`}</span><span class="x" data-rm="${j.id}" title="Убрать">×</span></div>`).join('')
    : `<div class="empty" style="padding:20px"><div>Очередь пустая. Добавь серии кнопкой или перетаскиванием.</div></div>`;
  const b = $('#startBtn');
  if (b) {
    b.disabled = !jobs.length;
    b.textContent = S.prog.running ? (jobs.length ? `✦ Добавить ${jobs.length} в обработку` : 'Идёт обработка…') : jobs.length ? `✦ Нарезать ${jobs.length} ${plural(jobs.length, 'серию', 'серии', 'серий')}` : '✦ Нарезать';
  }
}

async function editTimecodes(id) {
  const j = S.prog.jobs.find(x => x.id === id); if (!j) return;
  let text = j.timecodes || '', errors = [], plusAi = j.manual.length ? j.manual_plus_ai : true;
  for (;;) {
    const v = await modal(`<b style="font-size:16px">Таймкоды · ${esc(epName(j))}</b>
      <div class="mute small">Один клип на строку: <b>начало - конец</b> и, если хочешь, название.</div>
      <textarea class="tcbox" spellcheck="false" placeholder="12:30 - 13:15 Годжо всех разносит&#10;18:02 - 18:40&#10;1:02:10 - 1:02:55 Финал">${esc(text)}</textarea>
      <label class="tcai"><input type="checkbox" id="tcAi" ${plusAi ? 'checked' : ''}> Нейросеть тоже ищет моменты в серии <span class="mute small">(выключи — будут только эти куски)</span></label>
      ${errors.length ? `<div class="tcerr">${errors.map(esc).join('<br>')}</div>` : ''}
      <div style="display:flex;gap:10px;justify-content:space-between;align-items:center"><span class="mute small">${j.duration ? 'Серия ' + fmtT(j.duration) + ' · ' : ''}Ctrl+Enter — сохранить</span>
      <span style="display:flex;gap:10px"><button class="btn" data-m="no">Отмена</button><button class="btn p" data-m="ok">Сохранить</button></span></div>`);
    if (v === null || v === true) return;
    text = v; plusAi = editTimecodes._ai;
    const r = await api().job_set_timecodes(id, text, plusAi);
    if (r && r.errors) { errors = r.errors; continue; }
    if (r && r.error) { toast(r.error); return; }
    toast(r.count ? `${r.count} ${plural(r.count, 'момент', 'момента', 'моментов')} вручную${plusAi ? ' + нейросеть' : ''}` : 'Моменты выберет нейросеть');
    return;
  }
}

/* ------------------------------------------------------------------ STYLE */
function renderStyle() {
  $('#s-style').innerHTML = `
  <div class="head"><div><h1>Стиль и шрифты</h1><div class="sub">Двигай субтитры, заголовок и лого мышкой прямо по превью или стрелками</div></div>
    <div class="presets" id="presets"></div></div>
  <div class="sgrid">
    <div class="card scroll" style="padding:16px;display:flex;flex-direction:column;gap:4px">
      <div class="sec">Слои</div><div id="layers"></div>
      <div class="sec" style="margin-top:14px" id="fontSec">Шрифт</div><div id="fontList"></div>
    </div>
    <div class="stage" id="stage">
      <div id="bigPv"></div>
      <div style="display:flex;flex-direction:column;gap:10px;font-size:12px;color:var(--mute);width:140px;flex:none">
        <div>Перетащи мышкой или двигай стрелками ←↑→↓ (Shift — шаг больше)</div>
        <div><span class="dot" style="background:var(--cyan);box-shadow:none"></span>липнет к центру</div>
        <div><span class="dot" style="background:#ff7a7a;box-shadow:none"></span>тут площадка закрывает видео кнопками</div>
        <div class="seg" id="safeSeg"><span data-safe="tiktok">TikTok</span><span data-safe="shorts">Shorts</span><span data-safe="">Нет</span></div>
      </div>
    </div>
    <div class="card scroll" style="padding:16px 18px;display:flex;flex-direction:column;gap:12px" id="styleSide"></div>
  </div>`;
  renderPresets(); renderLayers(); renderFontList(); renderStyleSide(); renderSafe();
  requestAnimationFrame(refreshPreviews);
}
function renderSafe() { $$('#safeSeg span').forEach(s => s.classList.toggle('on', s.dataset.safe === S.safe)); }
function renderPresets() {
  const box = $('#presets'); if (!box) return;
  const cur = S.settings.preset;
  box.innerHTML = `<div class="seg">${Object.keys(S.presets).map(n => `<span class="${n === cur ? 'on' : ''}" data-preset="${esc(n)}">${esc(n)}${S.builtin.includes(n) ? '' : `<b class="del" data-delpreset="${esc(n)}" title="Удалить">×</b>`}</span>`).join('')}${cur ? '' : '<span class="on">Свой*</span>'}</div>
    <button class="btn p" data-act="savepreset">Сохранить пресет</button>`;
}
function renderLayers() {
  const box = $('#layers'); if (!box) return;
  const st = S.settings.style, icons = { subs: 'Аа', title: 'T', logo: '◆' };
  box.innerHTML = Object.entries(LAYERS).map(([id, label]) => `<div class="lay ${S.layer === id ? 'on' : ''}" data-layer-pick="${id}"><i>${icons[id]}</i>${label}${id === 'title' ? ' <span class="mute small">от ИИ</span>' : ''}<span class="e ${st[id].visible ? '' : 'off'}" data-vis="${id}" title="Показать/скрыть">${st[id].visible ? '👁' : '⊘'}</span></div>`).join('');
}
function renderFontList() {
  const box = $('#fontList'); if (!box) return;
  if (S.layer === 'logo') {
    $('#fontSec').textContent = 'Логотип';
    const cur = S.settings.style.logo.file;
    box.innerHTML = S.logos.map((l, i) => `<div class="font ${(cur || S.logos[0]) === l ? 'on' : ''}" data-logo="${esc(l)}"><span style="font-size:13px">${esc(l.replace(/\.png$/i, ''))}</span></div>`).join('') +
      `<button class="btn" data-act="picklogo" style="width:100%;margin-top:4px">＋ Загрузить PNG</button><div class="hint" style="margin-top:6px">Лучше PNG с прозрачным фоном</div>`;
    return;
  }
  $('#fontSec').textContent = 'Шрифт';
  const L = S.settings.style[S.layer];
  const sample = esc(caseText(S.layer === 'title' ? 'Годзё' : 'Ты ещё', L.case));
  box.innerHTML = S.fonts.map(f => { ensureFont(f.name); return `<div class="font ${f.name === L.font ? 'on' : ''}" data-font="${esc(f.name)}"><span style="font-family:'${esc(f.name)}'">${sample}</span><span class="mute small">${esc(f.name)}${f.cyrillic ? '' : ' · без кириллицы'}</span></div>`; }).join('') +
    `<button class="btn" data-act="sysfonts" style="width:100%;margin-top:4px">🖥 Шрифты Windows</button>
     <button class="btn" data-act="pickfont" style="width:100%;margin-top:6px">＋ Загрузить свой .ttf / .otf</button>
     <div class="hint" style="margin-top:6px">Шрифт вшивается в ролик сам — ставить его в Windows не нужно</div>`;
}
function slider(label, key, val, min, max, step, unit = '') {
  return `<div><div class="kv"><span>${label}</span><b data-out="${key}">${val}${unit}</b></div><input type="range" min="${min}" max="${max}" step="${step}" value="${val}" data-sty="${key}" data-unit="${unit}"></div>`;
}
function renderStyleSide() {
  const box = $('#styleSide'); if (!box) return;
  const L = S.settings.style[S.layer], isText = S.layer !== 'logo';
  const pos9 = [[25, 12], [50, 12], [75, 12], [25, 50], [50, 50], [75, 50], [25, 80], [50, 80], [75, 80]];
  let h = `<div class="sec" style="margin:0">Положение · ${LAYERS[S.layer]}</div>
    <div style="display:flex;gap:16px;align-items:center"><div class="pos9">${pos9.map(([x, y]) => `<i class="${Math.abs(L.x - x) < 3 && Math.abs(L.y - y) < 3 ? 'on' : ''}" data-pos="${x},${y}"></i>`).join('')}</div>
      <div style="flex:1;display:flex;flex-direction:column;gap:6px">${slider('По высоте', 'y', L.y, 0, 100, 0.5, '%')}${slider(isText ? 'Ширина строки' : 'Ширина', 'width', L.width, 10, 100, 1, '%')}</div></div>`;
  if (isText) {
    h += `<div class="sec" style="margin:6px 0 0">Текст</div>
      ${slider('Размер', 'size', L.size, 20, 220, 1)}
      ${slider('Межбуквенный', 'spacing', L.spacing, -10, 30, 0.5)}
      <div class="row" style="padding:4px 0"><span>Регистр</span><div class="seg">${[['upper', 'АА'], ['as_is', 'Аа'], ['lower', 'аа']].map(([v, l]) => `<span class="${L.case === v ? 'on' : ''}" data-styseg="case" data-v="${v}">${l}</span>`).join('')}</div></div>
      <div class="row" style="padding:4px 0"><span>Цвет${S.layer === 'subs' ? ' / подсветка слова' : ''}</span><div style="display:flex;gap:8px"><input type="color" value="${L.color}" data-stycolor="color" title="Цвет текста">${S.layer === 'subs' ? `<input type="color" value="${L.hl}" data-stycolor="hl" title="Цвет активного слова">` : ''}</div></div>
      <div class="row" style="padding:4px 0;gap:12px"><span>Обводка</span><input type="range" min="0" max="12" step="0.5" value="${L.outline}" data-sty="outline" data-unit=" px" style="max-width:110px"><b class="small" data-out="outline" style="width:38px;text-align:right">${L.outline} px</b><input type="color" value="${L.outline_color}" data-stycolor="outline_color"></div>
      <div class="row" style="padding:4px 0"><span>Тень</span><div class="tg ${L.shadow ? 'on' : ''}" data-stytg="shadow"></div></div>`;
    if (S.layer === 'subs') {
      h += `<div class="row" style="padding:4px 0"><span>Анимация</span><div class="seg">${[['pop', 'Поп'], ['karaoke', 'Караоке'], ['none', 'Нет']].map(([v, l]) => `<span class="${L.anim === v ? 'on' : ''}" data-styseg="anim" data-v="${v}">${l}</span>`).join('')}</div></div>
        <div class="row" style="padding:4px 0"><span>Слов на экране</span><div class="seg">${[1, 2, 3, 4, 5].map(v => `<span class="${+L.words === v ? 'on' : ''}" data-styseg="words" data-v="${v}">${v}</span>`).join('')}</div></div>`;
    } else {
      h += `<div class="hint">Заголовок пишет ИИ для каждого клипа и висит весь ролик.</div>`;
    }
  } else {
    h += `<div class="hint">Логотип выбирается слева. Размер — ползунок «Ширина».</div>`;
  }
  box.innerHTML = h;
}

/* ------------------------------------------------------------------ RUN */
function renderRun() {
  const box = $('#s-run'); if (S.screen !== 'run') return;
  const jobs = S.prog.jobs, cur = jobs.find(j => j.status === 'running') || [...jobs].reverse().find(j => j.started);
  const waiting = jobs.filter(j => j.status === 'queued');
  const total = jobs.filter(j => j.status !== 'cancelled').length, idx = cur ? jobs.filter(j => j.status !== 'cancelled').indexOf(cur) + 1 : 0;
  let sub = 'Пока ничего не обрабатывается';
  if (S.prog.running && cur) sub = `Серия ${idx} из ${total}` + (cur.eta ? ` · осталось около ${Math.max(1, Math.round((cur.eta + waiting.reduce((a, j) => a + (j.duration || 1400) * 0.35, 0)) / 60))} мин` : '');
  else if (cur) sub = { done: 'Готово', empty: 'ИИ не нашёл моментов', error: 'Ошибка', cancelled: 'Отменено' }[cur.status] || '';
  const head = `<div class="head"><div><h1>Обработка</h1><div class="sub">${sub}${S.prog.paused ? ' · <span style="color:var(--amber)">пауза после текущего шага</span>' : ''}</div></div>
    <div style="display:flex;gap:10px">${S.prog.running ? `${S.prog.paused ? '<button class="btn" data-act="resume">▶ Продолжить</button>' : '<button class="btn" data-act="pause">❚❚ Пауза</button>'}<button class="btn danger" data-act="cancel">✕ Отменить</button>` : `<button class="btn" data-act="clearjobs">Очистить список</button><button class="btn p" data-act="go-new">＋ Новая нарезка</button>`}</div></div>`;
  if (!cur) { box.innerHTML = head + `<div class="card empty"><b>Очередь пуста</b><div>Добавь серии в «Новой нарезке» и нажми «Нарезать».</div></div>` + logHTML(); scrollLog(); return; }
  const pct = Math.round((cur.percent || 0) * 100);
  const steps = STEPS.map((n, i) => {
    const state = cur.status === 'done' || i < cur.step ? 'done' : i === cur.step && cur.status === 'running' ? 'run' : '';
    let b = '', d = '';
    if (i === 0) { b = 'Whisper ' + esc(S.settings.whisper_model); d = cur.words ? `${cur.words} слов` : state === 'run' ? Math.round(cur.step_progress * 100) + '%' : ''; }
    if (i === 1) { b = cur.moments.length ? `Найдено ${cur.moments.length} ${plural(cur.moments.length, 'момент', 'момента', 'моментов')}` : 'ИИ читает серию'; d = esc(S.settings.ollama_model); }
    if (i === 2) { b = cur.moments.length ? `Клип ${Math.max(1, Math.min(cur.clip_index + 1, cur.moments.length))} из ${cur.moments.length}` : 'Ждёт'; d = `${cur.clips} готово`; }
    return `<div class="st ${state}"><div class="n">${state === 'done' ? '✓' : state === 'run' ? '●' : '○'} ${n}</div><b>${b}</b><div class="mute small">${d}</div>${state === 'run' ? `<div class="bar" style="margin:6px 0 0"><i style="width:${Math.round(cur.step_progress * 100)}%"></i></div>` : ''}</div>`;
  }).join('');
  const moments = cur.moments.length ? cur.moments.map(m => `<div class="moment ${m.status === 'run' ? 'run' : ''}"><span class="time">${fmtT(m.start)}–${fmtT(m.end)}</span>
      <div style="min-width:0"><b>${esc(m.title)}</b><div class="mute small">${esc(catLabel(m.category))}${m.why ? ' · ' + esc(m.why) : ''}</div></div>
      ${m.status === 'done' ? '<span class="pill g">готов</span>' : m.status === 'run' ? `<span class="pill p">монтаж ${Math.round((m.progress || 0) * 100)}%</span>` : '<span class="pill m">в очереди</span>'}</div>`).join('')
    : `<div class="mute small">${cur.status === 'empty' ? 'ИИ не нашёл подходящих моментов. Попробуй другую модель или больше категорий.' : 'Моменты появятся после расшифровки.'}</div>`;
  box.innerHTML = head + `
  <div class="card job">
    <div style="display:flex;gap:14px;align-items:center"><div class="th" style="width:96px;${cur.thumb ? `background-image:url(${cur.thumb})` : ''}"><b>${cur.duration ? fmtT(cur.duration) : ''}</b></div>
      <div style="flex:1;min-width:0"><b style="font-size:16px">${esc(epName(cur))}</b><div class="mute small">${cur.status === 'error' ? `<span style="color:var(--red)">${esc(cur.error)}</span>` : esc(cur.file)}</div></div>
      <div style="font:800 28px 'Unbounded UI';color:var(--pink)">${pct}%</div></div>
    <div class="bar" style="height:8px;margin:14px 0 0"><i style="width:${pct}%"></i></div>
    <div class="steps">${steps}</div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;flex:1;min-height:0">
    <div class="card scroll" style="padding:16px 18px"><div class="sec">ИИ нашёл моменты</div>${moments}</div>
    <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
      ${waiting.length ? `<div class="card scroll" style="padding:16px 18px;max-height:45%"><div class="sec">Дальше в очереди</div>${waiting.map(j => `<div class="ep" style="margin-bottom:8px"><div class="th" style="${j.thumb ? `background-image:url(${j.thumb})` : ''}"><b>${j.duration ? fmtT(j.duration) : ''}</b></div><div><b>${esc(epName(j))}</b><div class="mute small">ждёт</div></div><span></span><span class="x" data-rm="${j.id}">×</span></div>`).join('')}</div>` : ''}
      ${logHTML()}
    </div>
  </div>`;
  scrollLog();
}
function logHTML() {
  return `<div class="log" id="log" style="flex:1"><div class="sec" style="margin-bottom:6px">Журнал</div>${S.log.slice(-200).map(l => {
    const c = /error|ошибк|failed|traceback/i.test(l.text) ? 'err' : /found highlight|найден/i.test(l.text) ? 'ai' : /saved|complete|done|готов/i.test(l.text) ? 'ok' : '';
    return `<div class="${c}"><span class="t">${l.t}</span>${esc(l.text)}</div>`;
  }).join('')}</div>`;
}
function scrollLog() { const l = $('#log'); if (l) l.scrollTop = l.scrollHeight; }

/* ------------------------------------------------------------------ CLIPS */
async function loadClips() {
  if (S.screen === 'clips' && !S.clips.length) $('#s-clips').innerHTML = `<div class="head"><div><h1>Готовые клипы</h1><div class="sub">Загружаю…</div></div></div>`;
  const r = await api().clips();
  S.clips = r.items; S.clipsDir = r.out_dir;
  const files = new Set(S.clips.map(c => c.file)); S.clipSel.forEach(f => files.has(f) || S.clipSel.delete(f));
  renderBadges(); if (S.screen === 'clips') renderClips();
}
function clipGroup(c) { return c.show ? c.show + (c.episode ? ' ' + c.episode : '') : 'Без серии'; }
function renderClips() {
  const groups = [...new Set(S.clips.map(clipGroup))];
  if (S.clipFilter !== 'all' && !groups.includes(S.clipFilter)) S.clipFilter = 'all';
  const list = S.clips.filter(c => S.clipFilter === 'all' || clipGroup(c) === S.clipFilter);
  const sel = S.clips.filter(c => S.clipSel.has(c.file)), selDur = sel.reduce((a, c) => a + (c.duration || 0), 0);
  $('#s-clips').innerHTML = `
  <div class="head"><div><h1>Готовые клипы</h1><div class="sub">${S.clips.length} ${plural(S.clips.length, 'клип', 'клипа', 'клипов')} в папке ${esc(S.clipsDir)} · отметь лучшие и отправь в публикацию</div></div>
    <div class="filters"><span class="${S.clipFilter === 'all' ? 'on' : ''}" data-cf="all">Все · ${S.clips.length}</span>${groups.length > 1 ? groups.map(g => `<span class="${S.clipFilter === g ? 'on' : ''}" data-cf="${esc(g)}">${esc(g)}</span>`).join('') : ''}</div></div>
  <div class="bulk"><b>${sel.length ? 'Выбрано ' + sel.length : 'Ничего не выбрано'}</b><span class="mute small">${sel.length ? '· ' + fmtT(selDur) : '· кликни по галочке на клипе'}</span><span style="flex:1"></span>
    <button class="btn sm" data-act="selall">${list.length && list.every(c => S.clipSel.has(c.file)) ? 'Снять все' : 'Выбрать все'}</button>
    <button class="btn sm" data-act="openfolder">📂 Открыть папку</button>
    <button class="btn sm danger" data-act="delclips" ${sel.length ? '' : 'disabled'}>🗑 Удалить</button>
    <button class="btn sm" data-act="totiktok" ${sel.length ? '' : 'disabled'}>♪ В TikTok ${sel.length || ''}</button>
    <button class="btn p sm" data-act="publish" ${sel.length ? '' : 'disabled'}>▲ YouTube ${sel.length || ''}</button></div>
  ${list.length ? `<div class="scroll" style="flex:1"><div class="clips">${list.map(c => `
    <div class="clip ${S.clipSel.has(c.file) ? 'sel' : ''}" data-clip="${esc(c.file)}">
      <div class="ph" style="${c.thumb ? `background-image:url(${c.thumb})` : ''}"><i class="ck ${S.clipSel.has(c.file) ? 'on' : ''}" data-ck="${esc(c.file)}"></i><span class="dur">${fmtT(c.duration)}</span>
        ${c.upload ? `<span class="upb pill ${c.upload === 'done' ? 'g' : c.upload === 'error' ? 'r' : 'p'}">${{ done: 'на YouTube', error: 'ошибка заливки', queued: 'в очереди', running: 'заливается' }[c.upload]}</span>` : ''}${c.tiktok ? `<span class="pill ${c.tiktok === 'done' ? 'g' : c.tiktok === 'error' ? 'r' : 'p'}" style="position:absolute;bottom:10px;right:10px;z-index:3">${{ done: 'в TikTok', error: 'TikTok: ошибка', queued: 'TikTok: очередь', running: 'TikTok…', download: 'TikTok…' }[c.tiktok]}</span>` : ''}<div class="play">▶</div></div>
      <div class="info"><b title="${esc(c.why || '')}">${esc(c.title)}</b><span class="score">${stars(c.score)} ${esc(catLabel(c.category))}</span></div></div>`).join('')}</div></div>`
    : `<div class="card empty"><b>Клипов пока нет</b><div>Готовые шортсы появятся здесь сразу после монтажа.</div></div>`}`;
}

/* ------------------------------------------------------------------ UPLOAD */
function renderUp(force) {
  if (S.screen !== 'up') return;
  if (!force && S.upFocus) return;
  const u = S.settings.upload, items = S.prog.uploads.items || [];
  const pill = it => it.status === 'done' ? `<span class="pill g">${it.link ? `<span data-link="${esc(it.link)}" style="cursor:pointer">опубликован ↗</span>` : 'опубликован'}</span>`
    : it.status === 'running' ? `<span class="pill p" title="${esc(it.detail)}">${esc(it.detail || 'загрузка')}</span>`
      : it.status === 'error' ? `<span class="pill r" title="${esc(it.detail)}">ошибка</span>` : '<span class="pill m">в очереди</span>';
  $('#s-up').innerHTML = `
  <div class="head"><div><h1>Публикация</h1><div class="sub">Робот сам заливает клипы в YouTube Shorts по очереди</div></div>
    <div style="display:flex;gap:10px"><button class="btn" data-act="clearup">Убрать опубликованные</button><button class="btn p" data-act="upstart" ${S.prog.uploads.running || !items.some(i => i.status === 'queued') ? 'disabled' : ''}>${S.prog.uploads.running ? 'Заливаю…' : '▲ Запустить очередь'}</button></div></div>
  <div style="display:grid;grid-template-columns:1fr 400px;gap:18px;flex:1;min-height:0">
    <div class="card scroll">
      <div class="up" style="padding:14px 16px"><span class="sec" style="margin:0">Название и описание</span><span class="sec" style="margin:0">Статус</span><span></span></div>
      ${items.length ? items.slice().reverse().map(it => `<div class="up">
        <div style="display:flex;flex-direction:column;gap:6px;min-width:0"><input class="inp" value="${esc(it.title)}" data-upf="title" data-id="${it.id}" ${it.status === 'running' || it.status === 'done' ? 'disabled' : ''} maxlength="100">
          <div class="mute small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(it.description)}">${esc(it.file)} · ${esc(it.description.split('\n')[0])}</div></div>
        <div>${pill(it)}</div>
        <div style="display:flex;gap:6px;justify-content:flex-end">${it.status === 'error' ? `<button class="btn sm" data-retry="${it.id}" title="${esc(it.detail)}">↻</button>` : ''}${it.status !== 'running' ? `<button class="btn sm ghost" data-uprm="${it.id}" title="Убрать">×</button>` : ''}</div>
      </div>`).join('') : `<div class="empty"><b>Очередь пустая</b><div>Отметь клипы в «Готовых клипах» и нажми «Опубликовать».</div></div>`}
    </div>
    <div style="display:flex;flex-direction:column;gap:14px;min-height:0">
      <div class="card" style="padding:18px"><div class="sec">Аккаунт YouTube</div>
        <div style="display:flex;align-items:center;gap:12px"><div class="acc">${esc((S.channel || '?')[0])}</div>
          <div style="flex:1;min-width:0"><b>${esc(S.channel || 'Не подключён')}</b><div class="mute small">${S.channel ? '<span class="dot"></span>вход выполнен' : 'войди один раз через Chrome'}</div></div>
          <button class="btn sm" data-act="ytlogin">${S.channel ? 'Сменить' : 'Войти'}</button></div></div>
      <div class="card scroll" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div class="sec">Шаблон для новых клипов</div>
        <div class="kv"><span>Название</span></div><input class="inp" value="${esc(u.title_tpl)}" data-tpl="title_tpl">
        <div class="kv"><span>Описание</span></div><textarea rows="5" data-tpl="desc_tpl">${esc(u.desc_tpl)}</textarea>
        <div class="hint">Подставляется само: <span class="var" data-var="{название}">{название}</span> — заголовок от ИИ, <span class="var" data-var="{тайтл}">{тайтл}</span> и <span class="var" data-var="{серия}">{серия}</span> — из имени файла серии</div>
        <div class="row"><span>Доступ</span><div class="seg">${[['PUBLIC', 'Публичный'], ['UNLISTED', 'По ссылке'], ['PRIVATE', 'Скрытый']].map(([v, l]) => `<span class="${u.visibility === v ? 'on' : ''}" data-vis2="${v}">${l}</span>`).join('')}</div></div>
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ TIKTOK */
const TT_PRIV = { PUBLIC_TO_EVERYONE: 'Все', MUTUAL_FOLLOW_FRIENDS: 'Друзья', FOLLOWER_OF_CREATOR: 'Подписчики', SELF_ONLY: 'Только я' };
async function loadTT(refresh) {
  S.tt = await api().tt_account(!!refresh);
  S.ttKeys = S.ttKeys && !S.tt.keys;
  if (S.screen === 'tt') renderTT(true);
}
function renderTT(force) {
  if (S.screen !== 'tt') return;
  if (!S.tt) { $('#s-tt').innerHTML = `<div class="head"><div><h1>TikTok</h1><div class="sub">Загружаю…</div></div></div>`; loadTT(); return; }
  if (!force && S.ttFocus) return;
  const q = S.prog.tiktok || { items: [] }, items = q.items || [], a = S.tt, ts = S.settings.tiktok;
  const active = items.filter(i => ['queued', 'running', 'download'].includes(i.status)).length;
  const pill = it => it.status === 'done' ? `<span class="pill g">${esc(it.detail || 'готово')}</span>`
    : it.status === 'running' || it.status === 'download' ? `<span class="pill p">${esc(it.detail || 'загрузка')}</span>`
      : it.status === 'error' ? `<span class="pill r" title="${esc(it.detail)}">ошибка</span>` : '<span class="pill m">в очереди</span>';
  const src = { gdrive: 'Google Диск', clips: 'клип', folder: 'файл' };
  const acc = !a.keys || S.ttKeys ? `
      <div class="hint" style="margin-bottom:8px">Вставь ключи приложения с developers.tiktok.com (Sandbox → App details). Они хранятся только на этом компьютере.</div>
      <input class="inp" id="ttKey" placeholder="Client key" style="margin-bottom:8px"><input class="inp" id="ttSecret" placeholder="Client secret" type="password" style="margin-bottom:10px">
      <div style="display:flex;gap:8px;justify-content:flex-end">${a.keys ? '<button class="btn sm" data-act="ttkeyscancel">Отмена</button>' : ''}<button class="btn p sm" data-act="ttkeys">Сохранить ключи</button></div>`
    : !a.logged ? `<div style="display:flex;align-items:center;gap:12px"><div class="acc">?</div><div style="flex:1"><b>Не подключён</b><div class="mute small">${esc(a.error || 'войди один раз через браузер')}</div></div><button class="btn p sm" data-act="ttlogin">Войти</button></div>`
      : `<div style="display:flex;align-items:center;gap:12px"><div class="acc" ${a.avatar ? `style="background:url(${esc(a.avatar)}) center/cover"` : ''}>${a.avatar ? '' : esc((a.nickname || '?')[0])}</div>
        <div style="flex:1;min-width:0"><b>${esc(a.nickname || 'TikTok')}</b><div class="mute small">${a.error ? esc(a.error) : `<span class="dot"></span>@${esc(a.username || '')}`}</div></div>
        <button class="btn sm" data-act="ttlogin">Сменить</button></div>
        <div style="display:flex;gap:12px;margin-top:10px"><span class="var small" data-act="ttkeysedit">ключи приложения</span><span class="var small" data-act="ttrefresh">обновить</span></div>`;
  const opts = a.privacy_options || [];
  $('#s-tt').innerHTML = `
  <div class="head"><div><h1>TikTok</h1><div class="sub">${esc(q.note || 'Видео заливаются в TikTok по очереди через официальный API')}</div></div>
    <div style="display:flex;gap:10px"><button class="btn" data-act="ttclear">Убрать готовые</button>
      ${q.running ? '<button class="btn" data-act="ttstop">❚❚ Стоп после текущего</button>' : `<button class="btn p" data-act="ttstart" ${active && a.logged && (ts.mode !== 'post' || ts.privacy) ? '' : 'disabled'}>▲ Запустить очередь</button>`}</div></div>
  <div style="display:grid;grid-template-columns:1fr 400px;gap:18px;flex:1;min-height:0">
    <div class="card scroll">
      <div class="up" style="padding:14px 16px"><span class="sec" style="margin:0">Подпись</span><span class="sec" style="margin:0">Статус</span><span></span></div>
      ${items.length ? items.map(it => `<div class="up">
        <div style="display:flex;flex-direction:column;gap:6px;min-width:0"><textarea rows="2" data-ttf="caption" data-id="${it.id}" ${['running', 'download', 'done'].includes(it.status) ? 'disabled' : ''} maxlength="2200">${esc(it.caption)}</textarea>
          <div class="mute small" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(it.path)}">${esc(src[it.source] || '')} · ${esc(it.file)}${it.status === 'error' ? ' · <span style="color:#ff7a7a">' + esc(it.detail) + '</span>' : ''}</div>
          ${it.status === 'running' ? `<div class="bar"><i style="width:${Math.round((it.progress || 0) * 100)}%"></i></div>` : ''}</div>
        <div>${pill(it)}</div>
        <div style="display:flex;gap:6px;justify-content:flex-end">${it.status === 'error' ? `<button class="btn sm" data-ttretry="${it.id}" title="${esc(it.detail)}">↻</button>` : ''}${!['running', 'download'].includes(it.status) ? `<button class="btn sm ghost" data-ttrm="${it.id}" title="Убрать">×</button>` : ''}</div>
      </div>`).join('') : `<div class="empty"><b>Очередь пустая</b><div>Добавь папку, ссылку на Google Диск или отметь клипы в «Готовых клипах» → «В TikTok».</div></div>`}
    </div>
    <div class="scroll" style="display:flex;flex-direction:column;gap:14px;min-height:0">
      <div class="card" style="padding:18px"><div class="sec">Аккаунт TikTok</div>${acc}</div>
      <div class="card" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div class="sec">Добавить видео</div>
        <div style="display:flex;gap:8px"><button class="btn sm" data-act="ttfolder" style="flex:1">📂 Папка</button><button class="btn sm" data-act="ttfiles" style="flex:1">🎞 Файлы</button><button class="btn sm" data-act="goclips" style="flex:1">Готовые клипы</button></div>
        <div class="kv" style="margin-top:4px"><span>Ссылка на папку Google Диска</span></div>
        <div style="display:flex;gap:8px"><input class="inp" id="ttGd" placeholder="https://drive.google.com/drive/folders/…"><button class="btn p sm" data-act="ttgdrive">Залить</button></div>
        <div class="hint">Папка должна быть открыта «всем, у кого есть ссылка». Видео пойдут по порядку имён: 01, 02, 03…</div></div>
      <div class="card" style="padding:18px;display:flex;flex-direction:column;gap:10px"><div class="sec">Как публиковать</div>
        <div class="seg">${[['draft', 'В черновики TikTok'], ['post', 'Сразу опубликовать']].map(([v, l]) => `<span class="${ts.mode === v ? 'on' : ''}" data-ttmode="${v}">${l}</span>`).join('')}</div>
        <div class="hint">${ts.mode === 'draft' ? 'Видео придёт в TikTok на телефоне (входящие), там добавишь звук и опубликуешь. TikTok держит не больше 5 неопубликованных черновиков за сутки.' : 'Пока TikTok не проверил приложение, можно только «Только я» и только с приватного аккаунта. Около 15 постов в день.'}</div>
        ${ts.mode === 'post' ? `<div class="kv"><span>Кто увидит</span></div>
          <div class="seg" style="flex-wrap:wrap">${(opts.length ? opts : ['SELF_ONLY']).map(o => `<span class="${ts.privacy === o ? 'on' : ''}" data-ttpriv="${o}">${TT_PRIV[o] || o}</span>`).join('')}</div>
          ${ts.privacy ? '' : '<div class="hint" style="color:#ff7a7a">Выбери, кто увидит видео</div>'}
          <div class="row"><span>Комментарии</span><i class="tg ${ts.allow_comments && !a.comment_disabled ? 'on' : ''}" data-act="ttcomments"></i></div>
          <div class="hint">Публикуя, ты соглашаешься с <span class="var" data-link="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en">Music Usage Confirmation</span> TikTok.</div>` : ''}
        <div class="kv" style="margin-top:4px"><span>Подпись для новых видео</span></div><textarea rows="3" data-tttpl="caption_tpl">${esc(ts.caption_tpl)}</textarea>
        <div class="hint">Подставляется: <span class="var" data-ttvar="{название}">{название}</span> (заголовок от ИИ или имя файла), <span class="var" data-ttvar="{тайтл}">{тайтл}</span>, <span class="var" data-ttvar="{серия}">{серия}</span>. Файл .txt рядом с видео заменяет подпись целиком.</div>
        <div class="row"><span>Пауза между видео</span><select data-ttpause>${[15, 20, 30, 60, 120, 300].map(v => `<option value="${v}" ${+ts.pause === v ? 'selected' : ''}>${v < 60 ? v + ' с' : v / 60 + ' мин'}</option>`).join('')}</select></div>
      </div>
    </div>
  </div>`;
}
async function ttAction(a) {
  if (a === 'ttkeys') {
    const k = $('#ttKey').value.trim(), s = $('#ttSecret').value.trim();
    const r = await api().tt_save_keys(k, s); if (r.error) return toast(r.error);
    S.tt = r; S.ttKeys = false; renderTT(true); toast('Ключи сохранены, теперь войди'); return true;
  }
  if (a === 'ttkeysedit') { S.ttKeys = true; renderTT(true); return true; }
  if (a === 'ttkeyscancel') { S.ttKeys = false; renderTT(true); return true; }
  if (a === 'ttrefresh') { await loadTT(true); return true; }
  if (a === 'ttlogin') {
    toast('Открываю браузер: войди в TikTok и разреши доступ');
    const r = await api().tt_login(); if (r.error) toast(r.error); else toast('TikTok подключён');
    S.tt = r.error ? await api().tt_account(true) : r; renderTT(true); poll(); return true;
  }
  if (a === 'ttfolder' || a === 'ttfiles') {
    const n = await (a === 'ttfolder' ? api().tt_add_folder(false) : api().tt_add_files(false));
    if (n === null) return true;
    toast(n ? `Добавлено ${n} ${plural(n, 'видео', 'видео', 'видео')}` : 'Новых видео нет (уже в очереди или залиты)'); await poll(); renderTT(true); return true;
  }
  if (a === 'goclips') { go('clips'); return true; }
  if (a === 'ttgdrive') {
    const url = $('#ttGd').value.trim(); if (!url) return toast('Вставь ссылку');
    const r = await api().tt_add_gdrive(url); toast(r.error || 'Читаю Google Диск…'); return true;
  }
  if (a === 'ttstart') { await api().tt_start(); await poll(); return true; }
  if (a === 'ttstop') { await api().tt_stop(); toast('Остановлю после текущего видео'); return true; }
  if (a === 'ttclear') { await api().tt_clear_done(); await poll(); renderTT(true); return true; }
  if (a === 'ttcomments') { S.settings.tiktok.allow_comments = !S.settings.tiktok.allow_comments; save(); renderTT(true); return true; }
  if (a === 'totiktok') {
    if (!S.tt) S.tt = await api().tt_account(false);
    const n = await api().tt_add_clips([...S.clipSel], !!S.tt.logged); S.clipSel.clear(); await poll();
    if (!S.tt.logged) toast('Клипы в очереди. Подключи TikTok и запусти'); else toast(n ? `В TikTok: ${n}` : 'Эти клипы уже в очереди');
    go('tt'); return true;
  }
  return false;
}

/* ------------------------------------------------------------------ SETTINGS */
function renderSettings() {
  const st = S.settings, o = (S.system && S.system.ollama) || {}, g = S.system && S.system.gpu;
  $('#s-settings').innerHTML = `
  <div class="head"><div><h1>Настройки</h1><div class="sub">Всё сохраняется само</div></div></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start">
    <div class="card" style="padding:18px 20px"><div class="sec">Файлы</div>
      <div class="row"><span>Папка для клипов</span><button class="btn sm" data-act="outdir" style="max-width:320px;overflow:hidden;text-overflow:ellipsis">📁 ${esc(st.out_dir)}</button></div>
      <div class="row"><span>Своя музыка</span><button class="btn sm" data-act="pickmusic">＋ Добавить трек</button></div>
      <div class="row"><span>Свой логотип</span><button class="btn sm" data-act="picklogo">＋ Загрузить PNG</button></div>
      <div class="row"><span>Свой шрифт</span><button class="btn sm" data-act="pickfont">＋ .ttf / .otf</button></div>
    </div>
    <div class="card" style="padding:18px 20px"><div class="sec">Нейросети</div>
      <div class="row"><span>Видеокарта</span><span class="${g ? '' : 'mute'}">${g ? esc(g.name) + ` · ${g.total.toFixed(0)} ГБ` : 'не найдена (будет медленно на процессоре)'}</span></div>
      <div class="row"><span>Распознавание речи</span><select data-set="whisper_model">${[['large-v3', 'large-v3 · точнее (6+ ГБ)'], ['medium', 'medium · быстрее'], ['small', 'small · для слабых ПК']].map(([v, l]) => `<option value="${v}" ${v === st.whisper_model ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      <div class="row"><span>Ollama</span><span>${o.ok ? `<span class="dot"></span>работает · ${(o.models || []).length} моделей` : '<span class="dot off"></span>не запущена — открой Ollama'}</span></div>
      <div class="row"><span>Срез вшитых сабов <span class="mute small">сколько отрезать снизу</span></span><div style="display:flex;gap:10px;align-items:center;width:200px"><input type="range" min="8" max="35" step="1" value="${st.hardsub_band}" data-num="hardsub_band"><b id="vBand" class="small" style="width:46px">${st.hardsub_band}%</b></div></div>
      <div class="row"><span>Порог тишины</span><div style="display:flex;gap:10px;align-items:center;width:200px"><input type="range" min="0.8" max="5" step="0.1" value="${st.silence_gap}" data-num="silence_gap"><b id="vGap" class="small" style="width:46px">${st.silence_gap} с</b></div></div>
    </div>
  </div>
  <div class="hint">Модель для ИИ выбирается в «Новой нарезке». Скачать новую: <code>ollama pull qwen2.5:14b</code> в командной строке.</div>`;
}

/* ------------------------------------------------------------------ events */
document.addEventListener('click', async e => {
  const t = e.target;
  const act = t.closest('[data-act]'); const a = act && act.dataset.act;
  if (a && a.startsWith('tt') || a === 'goclips' || a === 'totiktok') { if (await ttAction(a)) return; }
  if (a === 'pick') { const n = await api().pick_videos(); if (n) toast(`Добавлено: ${n}`); return poll(); }
  if (a === 'start') {
    const ok = await api().start(S.settings);
    if (ok || S.prog.running) go('run'); else toast('Нечего обрабатывать');
    return poll();
  }
  if (a === 'gostyle') return go('style');
  if (a === 'go-new') return go('new');
  if (a === 'pause') { await api().pause(); return poll(); }
  if (a === 'resume') { await api().resume(); return poll(); }
  if (a === 'cancel') { if (await confirmBox('Отменить обработку?', 'Текущий клип не сохранится, готовые останутся.', 'Отменить')) { await api().cancel(); poll(); } return; }
  if (a === 'clearjobs') { await api().queue_clear_finished(); return poll(); }
  if (a === 'outdir') { const d = await api().pick_out_dir(); if (d) { S.settings.out_dir = d; S.clips = []; go(S.screen); } return; }
  if (a === 'pickmusic') { const r = await api().pick_music(); if (r) { S.music = r.music; set('music', r.name); if (S.screen === 'new') renderNew(); toast('Трек добавлен'); } return; }
  if (a === 'picklogo') { const r = await api().pick_logo(); if (r) { S.logos = r.logos; setStyle('logo', 'file', r.name); renderFontList(); toast('Логотип добавлен'); } return; }
  if (a === 'pickfont') {
    const r = await api().pick_font(); if (!r) return;
    if (r.error) return toast(r.error);
    S.fonts = r.fonts; if (S.layer === 'logo') S.layer = 'subs';
    setStyle(S.layer, 'font', r.name); renderFontList(); toast(`Шрифт «${r.name}» добавлен`); return;
  }
  if (a === 'sysfonts') return openSystemFonts();
  if (a === 'savepreset') {
    const name = await modal(`<b style="font-size:16px">Сохранить пресет</b><input class="inp" placeholder="Например: Моя озвучка" maxlength="40">
      <div style="display:flex;gap:10px;justify-content:flex-end"><button class="btn" data-m="no">Отмена</button><button class="btn p" data-m="ok">Сохранить</button></div>`);
    if (!name || !name.trim()) return;
    const r = await api().save_preset(name.trim(), S.settings.style);
    if (r.error) return toast(r.error);
    S.presets = r.presets; S.settings.preset = name.trim(); save(); renderPresets(); toast('Пресет сохранён'); return;
  }
  if (a === 'selall') { const list = S.clips.filter(c => S.clipFilter === 'all' || clipGroup(c) === S.clipFilter); const all = list.every(c => S.clipSel.has(c.file)); list.forEach(c => all ? S.clipSel.delete(c.file) : S.clipSel.add(c.file)); return renderClips(); }
  if (a === 'openfolder') return api().open_folder();
  if (a === 'delclips') { const n = S.clipSel.size; if (await confirmBox(`Удалить ${n} ${plural(n, 'клип', 'клипа', 'клипов')}?`, 'Файлы удалятся с диска.', 'Удалить')) { await api().delete_clips([...S.clipSel]); S.clipSel.clear(); loadClips(); } return; }
  if (a === 'publish') {
    if (!S.channel) toast('Сначала войди в YouTube — кнопка справа');
    await api().upload_enqueue([...S.clipSel], !!S.channel); S.clipSel.clear(); await poll(); go('up'); return;
  }
  if (a === 'ytlogin') { toast('Открываю Chrome — войди в YouTube Studio'); const r = await api().yt_login(); if (r.channel) { S.channel = r.channel; renderUp(true); toast('Вход выполнен'); } else toast(r.error || 'Не вышло'); return; }
  if (a === 'upstart') { await api().upload_start(); return poll(); }
  if (a === 'clearup') { await api().upload_clear_done(); return poll(); }

  let el;
  if ((el = t.closest('[data-rm]'))) { await api().queue_remove(el.dataset.rm); return poll(); }
  if ((el = t.closest('[data-nosubs]'))) { await api().job_clear_subs(el.dataset.nosubs); lastJobsSig = ''; return poll(); }
  if ((el = t.closest('[data-subs]'))) {
    const r = await api().job_pick_subs(el.dataset.subs);
    if (r && r.error) toast(r.error); else if (r) toast(`Субтитры: ${r.file} · ${r.words} слов`);
    lastJobsSig = ''; return poll();
  }
  if ((el = t.closest('[data-tc]'))) { await editTimecodes(el.dataset.tc); lastJobsSig = ''; return poll(); }
  if ((el = t.closest('[data-cat]'))) {
    const c = el.dataset.cat, cats = S.settings.categories;
    S.settings.categories = cats.includes(c) ? cats.filter(x => x !== c) : [...cats, c];
    if (!S.settings.categories.length) S.settings.categories = [c];
    $$('#cats .chip').forEach(ch => ch.classList.toggle('on', S.settings.categories.includes(ch.dataset.cat))); return save();
  }
  if ((el = t.closest('[data-tg]'))) { const k = el.dataset.tg; set(k, !S.settings[k]); el.classList.toggle('on', S.settings[k]); return refreshPreviews(); }
  if ((el = t.closest('[data-delpreset]'))) {
    e.stopPropagation(); const n = el.dataset.delpreset;
    if (await confirmBox(`Удалить пресет «${n}»?`, '', 'Удалить')) { const r = await api().delete_preset(n); if (r.presets) { S.presets = r.presets; if (S.settings.preset === n) S.settings.preset = ''; renderPresets(); } }
    return;
  }
  if ((el = t.closest('[data-preset]'))) { applyPreset(el.dataset.preset); return; }
  if ((el = t.closest('[data-vis]'))) { e.stopPropagation(); const l = el.dataset.vis; setStyle(l, 'visible', !S.settings.style[l].visible); renderLayers(); return; }
  if ((el = t.closest('[data-layer-pick]'))) { S.layer = el.dataset.layerPick; renderLayers(); renderFontList(); renderStyleSide(); refreshPreviews(); return; }
  if ((el = t.closest('[data-font]'))) { setStyle(S.layer, 'font', el.dataset.font); renderFontList(); renderPresets(); return; }
  if ((el = t.closest('[data-logo]'))) { setStyle('logo', 'file', el.dataset.logo); renderFontList(); renderPresets(); return; }
  if ((el = t.closest('[data-pos]'))) { const [x, y] = el.dataset.pos.split(',').map(Number); const L = S.settings.style[S.layer]; L.x = x; L.y = y; setStyle(S.layer, 'x', x); renderStyleSide(); renderPresets(); return; }
  if ((el = t.closest('[data-styseg]'))) { const k = el.dataset.styseg, v = k === 'words' ? +el.dataset.v : el.dataset.v; setStyle(S.layer, k, v); renderStyleSide(); renderPresets(); if (k === 'case') renderFontList(); return; }
  if ((el = t.closest('[data-stytg]'))) { const k = el.dataset.stytg; setStyle(S.layer, k, !S.settings.style[S.layer][k]); el.classList.toggle('on'); renderPresets(); return; }
  if ((el = t.closest('[data-safe]'))) { S.safe = el.dataset.safe; renderSafe(); refreshPreviews(); return; }
  if ((el = t.closest('[data-ck]'))) { e.stopPropagation(); const f = el.dataset.ck; S.clipSel.has(f) ? S.clipSel.delete(f) : S.clipSel.add(f); return renderClips(); }
  if ((el = t.closest('[data-clip]'))) { return api().open_clip(el.dataset.clip); }
  if ((el = t.closest('[data-cf]'))) { S.clipFilter = el.dataset.cf; return renderClips(); }
  if ((el = t.closest('[data-link]'))) { e.stopPropagation(); return api().open_url(el.dataset.link); }
  if ((el = t.closest('[data-ttretry]'))) { await api().tt_update(el.dataset.ttretry, { retry: true }); return poll(); }
  if ((el = t.closest('[data-ttrm]'))) { await api().tt_remove(el.dataset.ttrm); await poll(); return renderTT(true); }
  if ((el = t.closest('[data-ttmode]'))) { S.settings.tiktok.mode = el.dataset.ttmode; save(); if (el.dataset.ttmode === 'post' && S.tt && S.tt.logged) loadTT(true); return renderTT(true); }
  if ((el = t.closest('[data-ttpriv]'))) { S.settings.tiktok.privacy = el.dataset.ttpriv; save(); return renderTT(true); }
  if ((el = t.closest('[data-ttvar]'))) { const ta = $('[data-tttpl]'); ta.value += ' ' + el.dataset.ttvar; S.settings.tiktok.caption_tpl = ta.value; return save(); }
  if ((el = t.closest('[data-retry]'))) { await api().upload_update(el.dataset.retry, { retry: true }); return poll(); }
  if ((el = t.closest('[data-uprm]'))) { await api().upload_remove(el.dataset.uprm); return poll(); }
  if ((el = t.closest('[data-vis2]'))) { S.settings.upload.visibility = el.dataset.vis2; save(); return renderUp(true); }
  if ((el = t.closest('[data-var]'))) { const ta = $('[data-tpl="desc_tpl"]'); ta.value += el.dataset.var; S.settings.upload.desc_tpl = ta.value; return save(); }
});
async function openSystemFonts() {
  const body = $('#modalBody');
  body.style.width = '560px';
  body.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:16px">Шрифты Windows</b><span class="x" data-sf-close>×</span></div>
    <input class="inp" id="sfSearch" placeholder="Поиск по названию…">
    <div class="scroll" id="sfList" style="max-height:52vh;display:flex;flex-direction:column;gap:6px"><div class="mute">Ищу шрифты…</div></div>
    <div class="hint">Выбранный шрифт скопируется в программу и будет вшиваться в ролики.</div>`;
  $('#modal').classList.add('on');
  const close = () => { $('#modal').classList.remove('on'); body.style.width = ''; body.onclick = null; };
  let fonts = [];
  const draw = () => {
    const q = $('#sfSearch').value.trim().toLowerCase();
    const list = fonts.filter(f => !q || f.name.toLowerCase().includes(q)).slice(0, 300);
    const sample = esc(caseText('Ты ещё не понял?', S.layer === 'logo' ? 'upper' : S.settings.style[S.layer].case));
    $('#sfList').innerHTML = list.length ? list.map(f => `<div class="font" data-sf="${esc(f.path)}"><span style="font-family:'${esc(f.name)}',sans-serif;font-size:18px">${sample}</span><span class="mute small">${esc(f.name)}${f.cyrillic ? '' : ' · без кириллицы'}</span></div>`).join('')
      : '<div class="mute">Ничего не нашлось</div>';
  };
  body.onclick = async e => {
    if (e.target.closest('[data-sf-close]')) return close();
    const el = e.target.closest('[data-sf]'); if (!el) return;
    el.style.opacity = .5;
    const r = await api().add_system_font(el.dataset.sf);
    if (r.error) { el.style.opacity = 1; return toast(r.error); }
    close();
    S.fonts = r.fonts; if (S.layer === 'logo') S.layer = 'subs';
    S.loadedFonts.delete(r.name);
    setStyle(S.layer, 'font', r.name); renderLayers(); renderFontList(); renderStyleSide(); renderPresets();
    toast(`Шрифт «${r.name}» добавлен`);
  };
  body.onkeydown = e => { if (e.key === 'Escape') close(); };
  $('#sfSearch').oninput = draw;
  setTimeout(() => $('#sfSearch').focus(), 30);
  fonts = await api().system_fonts();
  draw();
}
function applyPreset(name) {
  const p = S.presets[name]; if (!p) return;
  const keepLogo = S.settings.style.logo.file;
  S.settings.style = JSON.parse(JSON.stringify(p));
  if (!S.settings.style.logo.file) S.settings.style.logo.file = keepLogo;
  S.settings.preset = name; save();
  if (S.screen === 'style') { renderPresets(); renderLayers(); renderFontList(); renderStyleSide(); refreshPreviews(); } else renderNew();
}
document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset.num) {
    const k = t.dataset.num, v = +t.value; S.settings[k] = v;
    if (k === 'clip_min' && v > S.settings.clip_max - 5) { S.settings.clip_max = v + 5; const m = $('[data-num="clip_max"]'); if (m) m.value = v + 5; }
    if (k === 'clip_max' && v < S.settings.clip_min + 5) { S.settings.clip_min = Math.max(10, v - 5); const m = $('[data-num="clip_min"]'); if (m) m.value = S.settings.clip_min; }
    const out = { clip_min: '#vMin', clip_max: '#vMax', max_clips: '#vCnt', music_volume: '#vVol', silence_gap: '#vGap' };
    if ($('#vMin')) $('#vMin').textContent = S.settings.clip_min + ' сек';
    if ($('#vMax')) $('#vMax').textContent = S.settings.clip_max + ' сек';
    if (k === 'max_clips') { $('#vCnt').textContent = 'до ' + v; $$('.ep > .chip').forEach(c => { if (/^до /.test(c.textContent)) c.textContent = `до ${v} клипов`; }); }
    if (k === 'music_volume') $(out[k]).textContent = v + ' дБ';
    if (k === 'silence_gap') $(out[k]).textContent = v + ' с';
    if (k === 'hardsub_band' && $('#vBand')) $('#vBand').textContent = v + '%';
    return save();
  }
  if (t.dataset.sty) {
    const k = t.dataset.sty, v = +t.value; setStyle(S.layer, k, v);
    const o = $(`[data-out="${k}"]`); if (o) o.textContent = v + (t.dataset.unit || '');
    if (k === 'y') $$('.pos9 i').forEach(i => i.classList.remove('on'));
    return renderPresets();
  }
  if (t.dataset.stycolor) { setStyle(S.layer, t.dataset.stycolor, t.value); return renderPresets(); }
  if (t.dataset.tpl) { S.settings.upload[t.dataset.tpl] = t.value; return save(); }
  if (t.dataset.tttpl) { S.settings.tiktok.caption_tpl = t.value; return save(); }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.dataset.set === 'preset') { if (t.value) applyPreset(t.value); return; }
  if (t.dataset.set) { set(t.dataset.set, t.value); renderSys(); return; }
  if (t.dataset.upf) { api().upload_update(t.dataset.id, { [t.dataset.upf]: t.value }); }
  if (t.dataset.ttf) { api().tt_update(t.dataset.id, { [t.dataset.ttf]: t.value }); }
  if (t.hasAttribute('data-ttpause')) { S.settings.tiktok.pause = +t.value; save(); }
});
document.addEventListener('focusin', e => { if (e.target.closest('#s-up')) S.upFocus = true; if (e.target.closest('#s-tt')) S.ttFocus = true; });
document.addEventListener('focusout', e => { if (e.target.closest('#s-up')) { S.upFocus = false; } if (e.target.closest('#s-tt')) { S.ttFocus = false; } });
window.addEventListener('resize', () => { if (S.screen === 'style') refreshPreviews(); });
// let Python receive dropped files anywhere in the window
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => { e.preventDefault(); setTimeout(poll, 400); setTimeout(poll, 1500); });

/* ------------------------------------------------------------------ polling */
let lastJobsSig = '', lastUpSig = '', lastTTSig = '', lastTTStat = '';
async function poll() {
  try {
    const p = await api().progress(S.logSeq);
    S.prog = p;
    if (p.log.length) { S.log.push(...p.log); S.log = S.log.slice(-300); S.logSeq = p.log[p.log.length - 1].seq; }
    const doneClips = p.jobs.reduce((a, j) => a + (j.clips || 0), 0);
    if (doneClips !== S.clipsDone) { if (S.clipsDone >= 0 || !S.clips.length) loadClips(); S.clipsDone = doneClips; }
    const sig = JSON.stringify(p.jobs.map(j => [j.id, j.status, !!j.thumb, j.duration, j.subs_file, j.manual.length, j.manual_plus_ai]));
    if (sig !== lastJobsSig) { if (S.screen === 'new') renderQueue(); refreshPreviews(); }
    lastJobsSig = sig;
    if (S.screen === 'run') renderRun();
    const usig = JSON.stringify(p.uploads);
    if (S.screen === 'up' && usig !== lastUpSig) renderUp();
    lastUpSig = usig;
    const tsig = JSON.stringify(p.tiktok), tstat = JSON.stringify(((p.tiktok || {}).items || []).map(i => [i.path, i.status]));
    if (tsig !== lastTTSig && S.screen === 'tt') renderTT();
    if (tstat !== lastTTStat && lastTTStat && S.screen === 'clips' && S.clips.length) loadClips();
    lastTTSig = tsig; lastTTStat = tstat;
    renderBadges();
  } catch (e) { console.warn(e); }
}
async function pollSys() { try { S.system = await api().system(); renderSys(); } catch (e) { } }

async function boot() {
  const d = await api().init();
  Object.assign(S, { settings: d.settings, presets: d.presets, builtin: d.builtin_presets, fonts: d.fonts, logos: d.logos, music: d.music, categories: d.categories, channel: d.channel });
  logoUri(S.settings.style.logo.file).then(u => { if (u) $('#sideLogo').src = u; });
  await Promise.all([poll(), pollSys()]);
  go('new');
  setInterval(poll, 700); setInterval(pollSys, 4000);
}
const BRIDGE = new URLSearchParams(location.search).get('bridge');
if (BRIDGE && !window.pywebview) {
  // browser mode (no pywebview): same Api over HTTP on 127.0.0.1
  window.pywebview = {
    api: new Proxy({}, {
      get: (_, name) => (...args) => fetch('/api/' + name, {
        method: 'POST', headers: { 'X-Studio-Token': BRIDGE, 'Content-Type': 'application/json' }, body: JSON.stringify(args),
      }).then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))),
    }),
  };
  document.documentElement.classList.add('browser-mode');
}
if (window.pywebview && window.pywebview.api) boot(); else window.addEventListener('pywebviewready', boot);
