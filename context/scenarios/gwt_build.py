#!/usr/bin/env python3
"""gwt-view — render a hierarchical Given/When/Then scenario tree as an interactive diagram (single HTML).

Usage: gwt_build.py <scenarios.yaml> [output.html]

Input schema (YAML or JSON):
  meta: { title, description }            # optional
  journey (or tree/root):                 # root node
    id, title, given?[], note?, children?[], scenarios?[]
  scenario: { id, title, given?[], when, then[], refs?[] }

Semantics: a node's `given` is inherited by every descendant — in the diagram the
inheritance chain is the visible path from root to leaf.
"""
import json
import sys
from pathlib import Path

import yaml


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def normalize(node):
    node["given"] = as_list(node.get("given"))
    count = 0
    for s in node.get("scenarios", []) or []:
        s["given"] = as_list(s.get("given"))
        s["then"] = as_list(s.get("then"))
        s["refs"] = s.get("refs", [])
        count += 1
    for c in node.get("children", []) or []:
        count += normalize(c)
    node["subtree_count"] = count
    return count


def build(src: str, out: str) -> None:
    data = yaml.safe_load(open(src, encoding="utf-8"))
    root = data.get("journey") or data.get("tree") or data.get("root")
    if root is None:
        sys.exit("error: input needs a top-level `journey` (or `tree`/`root`) node")
    total = normalize(root)
    payload = json.dumps(
        {"meta": data.get("meta", {}), "root": root, "total": total},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    Path(out).write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    print(f"gwt-view: {out} ({total} scenarios)")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scenarios</title>
<style>
:root{
  --bg:#f4f5f7; --surface:#ffffff; --ink:#1a1d21; --muted:#697386; --line:#dfe3e8; --edge:#c4cad4;
  --given:#697386; --when:#175cd3; --then:#067647; --then-bg:#f0faf4;
  --accent:#175cd3; --chip:#eef1f4; --vp:rgba(23,92,211,.08);
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0b0d10; --surface:#171a1f; --ink:#e6e8eb; --muted:#8a94a6; --line:#272c34; --edge:#3a4250;
    --given:#8a94a6; --when:#6ea8ff; --then:#4ccb8f; --then-bg:#12271b; --accent:#6ea8ff; --chip:#212630; --vp:rgba(110,168,255,.12); }
}
:root[data-theme="light"]{
  --bg:#f4f5f7; --surface:#ffffff; --ink:#1a1d21; --muted:#697386; --line:#dfe3e8; --edge:#c4cad4;
  --given:#697386; --when:#175cd3; --then:#067647; --then-bg:#f0faf4; --accent:#175cd3; --chip:#eef1f4; --vp:rgba(23,92,211,.08);
}
:root[data-theme="dark"]{
  --bg:#0b0d10; --surface:#171a1f; --ink:#e6e8eb; --muted:#8a94a6; --line:#272c34; --edge:#3a4250;
  --given:#8a94a6; --when:#6ea8ff; --then:#4ccb8f; --then-bg:#12271b; --accent:#6ea8ff; --chip:#212630; --vp:rgba(110,168,255,.12);
}
*{box-sizing:border-box}
@media (prefers-reduced-motion: reduce){ *{transition:none !important} }
html,body{height:100%}
body{
  margin:0; background:var(--bg); color:var(--ink); display:flex; flex-direction:column; overflow:hidden;
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Noto Sans KR",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}

/* ── top bar ── */
.bar{
  flex:none; display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:9px 14px; background:var(--surface); border-bottom:1px solid var(--line); z-index:20;
}
.bar h1{font-size:14.5px; margin:0 4px 0 0; font-weight:700; letter-spacing:-.01em}
.bar .meta{font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums}
.search{
  display:flex; align-items:center; gap:7px; flex:0 1 280px; min-width:160px;
  background:var(--bg); border:1px solid var(--line); border-radius:7px; padding:5px 10px;
}
.search:focus-within{border-color:var(--accent)}
.search svg{flex:none; color:var(--muted)}
.search input{flex:1; min-width:50px; border:0; background:none; color:var(--ink); font:inherit; outline:none}
.search .hits{font-size:11.5px; color:var(--muted); white-space:nowrap; font-variant-numeric:tabular-nums}
.search .clear{display:none; border:0; background:none; color:var(--muted); cursor:pointer; padding:0 2px}
.search.active .clear{display:block}
button.ctl{
  font:inherit; font-size:12.5px; cursor:pointer; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); border-radius:7px; padding:5px 10px;
}
button.ctl:hover{background:var(--chip)}
button.ctl[aria-pressed="true"]{background:var(--chip); border-color:var(--muted)}
button.ctl:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.spacer{flex:1}
.legend{display:flex; gap:11px; font-size:11.5px; color:var(--muted)}
.legend span{display:inline-flex; gap:5px; align-items:center}
.dot{width:8px;height:8px;border-radius:2px}

/* ── canvas ── */
.canvas{flex:1; overflow:hidden; position:relative; touch-action:none}
.canvas.grab{cursor:grab}
.canvas.panning{cursor:grabbing}
.world{position:absolute; top:0; left:0; transform-origin:0 0; will-change:transform}
.stage{position:relative; width:max-content; padding:40px}
svg.edges{position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none}
svg.edges path{fill:none; stroke:var(--edge); stroke-width:1.5}

/* tree layout */
.branch{display:flex; align-items:center}
.kids{display:flex; flex-direction:column; gap:10px; margin-left:46px}
.branch.collapsed > .kids{display:none}

.nbox{
  flex:none; position:relative; background:var(--surface); border:1px solid var(--line); border-radius:9px;
  padding:7px 12px; max-width:240px; cursor:pointer; user-select:none;
}
.nbox:hover{border-color:var(--muted)}
.nbox:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.nbox .nid{font-size:10.5px; color:var(--muted)}
.nbox .ntitle{font-weight:650; font-size:13px; line-height:1.35; text-wrap:balance}
.nbox .count{
  position:absolute; top:-9px; right:-7px; font-size:10px; color:var(--muted);
  background:var(--chip); border:1px solid var(--line); border-radius:99px; padding:0 6px;
  font-variant-numeric:tabular-nums;
}
.branch.collapsed > .nbox{border-style:dashed}
.branch.collapsed > .nbox .count{color:var(--accent); border-color:var(--accent)}
.branch[data-depth="0"] > .nbox{border-width:1.5px; border-color:var(--ink); max-width:260px}
.nbox .ngiven{margin:4px 0 0; padding:4px 0 0; border-top:1px dashed var(--line); display:grid; gap:1px}
.nbox .ngiven div{font-size:11px; color:var(--muted); line-height:1.4}
.nbox .ngiven div::before{content:"G "; color:var(--given); font-weight:700; font-size:9.5px}
.detail-off .nbox .ngiven{display:none}
.detail-off .nbox{max-width:210px}

.card{
  position:relative; background:var(--surface); border:1px solid var(--line); border-radius:9px;
  padding:8px 12px; width:360px;
}
.card .chead{display:flex; gap:7px; align-items:baseline; flex-wrap:wrap}
.sid{flex:none; font-size:10.5px; color:var(--muted); background:var(--chip); border:0; border-radius:4px; padding:1px 6px; cursor:pointer}
.sid:hover{color:var(--ink)}
.sid:focus-visible{outline:2px solid var(--accent)}
.stitle{font-weight:650; font-size:13px; line-height:1.35}
.refs{display:flex; gap:4px; flex-wrap:wrap; margin-left:auto}
.ref{font-size:9.5px; color:var(--muted); border:1px solid var(--line); border-radius:99px; padding:0 5px}
.gwt{margin-top:7px; display:grid; gap:5px}
.glabel{font-size:9px; font-weight:800; letter-spacing:.08em; font-family:ui-monospace,monospace}
.gblock{padding:1px 0 1px 10px; border-left:2px dashed var(--line); display:grid; gap:1px}
.gblock .glabel{color:var(--given)}
.gblock div{font-size:11.5px; color:var(--muted); line-height:1.45}
.wblock{padding:2px 0 2px 10px; border-left:3px solid var(--when)}
.wblock .glabel{color:var(--when)}
.wblock p{margin:0; font-size:13px; font-weight:550; line-height:1.45}
.tblock{background:var(--then-bg); border-radius:7px; padding:5px 10px 6px; display:grid; gap:1px}
.tblock .glabel{color:var(--then)}
.tblock div{font-size:12.5px; line-height:1.5; display:flex; gap:7px}
.tblock div::before{content:"→"; color:var(--then); flex:none; font-weight:700}
.detail-off .gwt, .detail-off .refs{display:none}
.detail-off .card{width:280px}
.card.flash{border-color:var(--accent); box-shadow:0 0 0 1.5px var(--accent)}

.dimmable .dim{opacity:.13}
.card.hit{border-color:var(--accent)}
.nbox.onpath{border-color:var(--accent)}

/* ── floating controls (figma-style, bottom-right) ── */
.fab{
  position:absolute; right:14px; bottom:14px; z-index:20; display:flex; flex-direction:column; gap:8px; align-items:flex-end;
}
.minimap{
  width:190px; background:var(--surface); border:1px solid var(--line); border-radius:9px;
  position:relative; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.10); cursor:pointer;
}
.minimap canvas{display:block; width:100%}
.minimap .vp{position:absolute; border:1.5px solid var(--accent); background:var(--vp); pointer-events:none; border-radius:2px}
.zoombar{
  display:flex; align-items:center; background:var(--surface); border:1px solid var(--line);
  border-radius:9px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.10);
}
.zoombar button{border:0; background:none; color:var(--ink); font:inherit; font-size:14px; cursor:pointer; padding:6px 11px}
.zoombar button:hover{background:var(--chip)}
.zoombar .zv{font-size:11.5px; color:var(--muted); min-width:44px; text-align:center; font-variant-numeric:tabular-nums; cursor:pointer}
.zoombar .fit{font-size:11.5px; font-weight:600; border-left:1px solid var(--line)}

.hint{
  position:absolute; left:14px; bottom:14px; z-index:20; font-size:11.5px; color:var(--muted);
  background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:5px 11px;
  box-shadow:0 4px 16px rgba(0,0,0,.08);
}
kbd{font-family:ui-monospace,monospace; font-size:10.5px; background:var(--chip); border:1px solid var(--line); border-radius:4px; padding:0 4px}
.empty{position:absolute; top:70px; left:50%; transform:translateX(-50%); color:var(--muted); display:none; z-index:20}
</style>
</head>
<body>
<div class="bar">
  <h1 id="title">Scenarios</h1>
  <span class="meta" id="stats"></span>
  <div class="search" id="searchbox">
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5.2" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l3.4 3.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
    <input id="q" type="search" placeholder="Search  /" aria-label="Search scenarios">
    <span class="hits" id="hits"></span>
    <button class="clear" id="clearq" aria-label="Clear">✕</button>
  </div>
  <button class="ctl" id="expandAll">Expand all</button>
  <button class="ctl" id="collapseAll">Collapse</button>
  <button class="ctl" id="detailToggle" aria-pressed="true">Details</button>
  <button class="ctl" id="copySvg" title="Copy the visible diagram as SVG — paste directly into Figma">Copy SVG</button>
  <span class="spacer"></span>
  <div class="legend" aria-hidden="true">
    <span><span class="dot" style="background:var(--given)"></span>given</span>
    <span><span class="dot" style="background:var(--when)"></span>when</span>
    <span><span class="dot" style="background:var(--then)"></span>then</span>
  </div>
</div>

<div class="canvas grab" id="canvas">
  <div class="world" id="world">
    <div class="stage" id="stage">
      <svg class="edges" id="edges" aria-hidden="true"></svg>
      <div id="tree"></div>
    </div>
  </div>
  <p class="empty" id="empty">No matching scenarios.</p>
  <div class="hint">drag = pan · wheel/pinch = zoom · click node = fold · <kbd>1</kbd> fit <kbd>0</kbd> 100%</div>
  <div class="fab">
    <div class="minimap" id="minimap"><canvas id="mmc"></canvas><div class="vp" id="mmvp"></div></div>
    <div class="zoombar">
      <button id="zoomOut" aria-label="Zoom out">−</button>
      <span class="zv" id="zoomVal" title="Reset to 100%">100%</span>
      <button id="zoomIn" aria-label="Zoom in">+</button>
      <button class="fit" id="zoomFit">Fit</button>
    </div>
  </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => [...el.querySelectorAll(s)];

document.title = DATA.meta.title || DATA.meta.project || 'Scenarios';
$('#title').textContent = document.title;
let nodeCount = 0;
(function walk(n){ nodeCount++; (n.children||[]).forEach(walk); })(DATA.root);
$('#stats').textContent = `${nodeCount} nodes · ${DATA.total} scenarios`;

function el(tag, cls, text){
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/* ═══ render tree ═══ */
function renderScenario(s){
  const card = el('article','card');
  card.id = s.id;
  card.dataset.search = [s.id, s.title, s.when, ...(s.given||[]), ...(s.then||[]), ...(s.refs||[])].join(' ').toLowerCase();

  const head = el('div','chead');
  const idBtn = el('button','sid mono', s.id);
  idBtn.title = 'Copy link';
  idBtn.addEventListener('click', e => {
    e.stopPropagation();
    history.replaceState(null,'','#'+s.id);
    navigator.clipboard?.writeText(location.href).catch(()=>{});
    idBtn.textContent = 'copied';
    setTimeout(()=> idBtn.textContent = s.id, 900);
  });
  head.append(idBtn, el('span','stitle', s.title));
  if ((s.refs||[]).length){
    const refs = el('span','refs');
    s.refs.forEach(r => refs.append(el('span','ref mono', r)));
    head.append(refs);
  }
  card.append(head);

  const gwt = el('div','gwt');
  if ((s.given||[]).length){
    const gb = el('div','gblock');
    gb.append(el('span','glabel','GIVEN'));
    s.given.forEach(g => gb.append(el('div', null, g)));
    gwt.append(gb);
  }
  const wb = el('div','wblock');
  wb.append(el('span','glabel','WHEN'));
  wb.append(Object.assign(el('p'), {textContent: s.when}));
  gwt.append(wb);
  const tb = el('div','tblock');
  tb.append(el('span','glabel','THEN'));
  (s.then||[]).forEach(t => tb.append(el('div', null, t)));
  gwt.append(tb);
  card.append(gwt);

  card.addEventListener('mouseenter', () => tracePath(card, true));
  card.addEventListener('mouseleave', () => tracePath(card, false));
  return card;
}

function renderNode(node, depth){
  const branch = el('div','branch');
  branch.dataset.depth = depth;
  branch.dataset.id = node.id;

  const box = el('div','nbox');
  box.id = 'n-' + node.id;
  box.tabIndex = 0;
  box.dataset.search = [node.id, node.title, ...(node.given||[])].join(' ').toLowerCase();
  box.append(el('div','nid mono', node.id));
  box.append(el('div','ntitle', node.title));
  if ((node.given||[]).length){
    const g = el('div','ngiven');
    node.given.forEach(t => g.append(el('div', null, t)));
    box.append(g);
  }
  if (node.subtree_count) box.append(el('span','count', node.subtree_count));
  branch.append(box);

  const kids = el('div','kids');
  (node.scenarios||[]).forEach(s => kids.append(renderScenario(s)));
  (node.children||[]).forEach(c => kids.append(renderNode(c, depth+1)));
  if (kids.children.length) branch.append(kids);

  const toggle = () => { if (kids.children.length) foldToggle(branch, box); };
  box.addEventListener('click', e => { if (!dragMoved) toggle(); });
  box.addEventListener('keydown', e => { if (e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); } });
  return branch;
}

const canvas = $('#canvas'), world = $('#world'), stage = $('#stage'),
      tree = $('#tree'), edges = $('#edges');
tree.append(renderNode(DATA.root, 0));   /* default: fully expanded */

/* ═══ camera (pan/zoom via transform — figma-style) ═══ */
let cam = { x:0, y:0, s:1 };
function applyCam(){
  world.style.transform = `translate(${cam.x}px, ${cam.y}px) scale(${cam.s})`;
  $('#zoomVal').textContent = Math.round(cam.s * 100) + '%';
  updateViewportRect();
}
function zoomAt(factor, cx, cy){   /* cx,cy: client coords */
  const s2 = Math.min(2.5, Math.max(.15, cam.s * factor));
  const r = canvas.getBoundingClientRect();
  const px = cx - r.left, py = cy - r.top;
  cam.x = px - (px - cam.x) * (s2 / cam.s);
  cam.y = py - (py - cam.y) * (s2 / cam.s);
  cam.s = s2;
  applyCam();
}
function fit(){
  /* fit WIDTH — 세로로 긴 트리에서 전체-fit은 글자가 사라진다. 가로만 맞추고 위에서 시작 */
  const w = stage.offsetWidth;
  cam.s = Math.min(1, Math.max(.3, (canvas.clientWidth - 60) / w));
  cam.x = (canvas.clientWidth - w * cam.s) / 2;
  cam.y = 12;
  applyCam();
}
function fitAll(){
  const w = stage.offsetWidth, h = stage.offsetHeight;
  cam.s = Math.max(.1, Math.min(canvas.clientWidth / w, canvas.clientHeight / h) * .97);
  cam.x = (canvas.clientWidth - w * cam.s) / 2;
  cam.y = (canvas.clientHeight - h * cam.s) / 2;
  applyCam();
}
function centerOn(elm, targetScale){
  const r = elm.getBoundingClientRect();      /* current screen rect */
  const sx = (r.left + r.width/2 - canvas.getBoundingClientRect().left - cam.x) / cam.s;
  const sy = (r.top + r.height/2 - canvas.getBoundingClientRect().top - cam.y) / cam.s;
  if (targetScale) cam.s = targetScale;
  cam.x = canvas.clientWidth/2 - sx * cam.s;
  cam.y = canvas.clientHeight/2 - sy * cam.s;
  applyCam();
}

/* wheel: pinch/ctrl = zoom at cursor, otherwise pan (trackpad two-finger) */
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  if (e.ctrlKey || e.metaKey){
    zoomAt(Math.exp(-e.deltaY * .01), e.clientX, e.clientY);
  } else {
    cam.x -= e.deltaX; cam.y -= e.deltaY; applyCam();
  }
}, {passive:false});

/* drag pan (background or space+anywhere) */
let panning = null, dragMoved = false, spaceHeld = false;
canvas.addEventListener('pointerdown', e => {
  const onBg = e.target === canvas || e.target === world || e.target === stage ||
               e.target === tree || e.target.closest('svg.edges');
  if (!onBg && !spaceHeld && e.button !== 1) return;
  panning = { px:e.clientX, py:e.clientY, ox:cam.x, oy:cam.y };
  dragMoved = false;
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add('panning');
});
canvas.addEventListener('pointermove', e => {
  if (!panning) return;
  const dx = e.clientX - panning.px, dy = e.clientY - panning.py;
  if (Math.abs(dx) + Math.abs(dy) > 3) dragMoved = true;
  cam.x = panning.ox + dx; cam.y = panning.oy + dy;
  applyCam();
});
['pointerup','pointercancel'].forEach(ev => canvas.addEventListener(ev, () => {
  panning = null; canvas.classList.remove('panning');
  setTimeout(()=> dragMoved = false, 0);
}));
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT'){ spaceHeld = true; e.preventDefault(); }
});
document.addEventListener('keyup', e => { if (e.code === 'Space') spaceHeld = false; });

/* ═══ fold with position anchoring (no teleport) ═══ */
function foldToggle(branch, box){
  const before = box.getBoundingClientRect();
  branch.classList.toggle('collapsed');
  redraw();
  const after = box.getBoundingClientRect();
  cam.x += before.left - after.left;
  cam.y += before.top - after.top;
  applyCam();
  redraw();
}

/* ═══ edges ═══ */
function stageRect(elm){
  const s = stage.getBoundingClientRect();
  const r = elm.getBoundingClientRect();
  return { x:(r.left - s.left)/cam.s, y:(r.top - s.top)/cam.s, w:r.width/cam.s, h:r.height/cam.s };
}
function drawEdges(){
  edges.innerHTML = '';
  const frag = document.createDocumentFragment();
  $$('.branch', tree).forEach(branch => {
    if (branch.classList.contains('collapsed')) return;
    const box = branch.querySelector(':scope > .nbox');
    const kids = branch.querySelector(':scope > .kids');
    if (!box || !kids) return;
    const b = stageRect(box);
    const x1 = b.x + b.w, y1 = b.y + b.h/2;
    [...kids.children].forEach(kid => {
      const target = kid.classList.contains('branch') ? kid.querySelector(':scope > .nbox') : kid;
      const k = stageRect(target);
      const x2 = k.x, y2 = k.y + k.h/2, mx = (x1 + x2)/2;
      const p = document.createElementNS('http://www.w3.org/2000/svg','path');
      p.setAttribute('d', `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      frag.append(p);
    });
  });
  edges.append(frag);
}

/* ═══ minimap ═══ */
const mm = $('#minimap'), mmc = $('#mmc'), mmvp = $('#mmvp');
let mmScale = 1;
let mmW = 190, mmH = 190;
function drawMinimap(){
  const W = stage.offsetWidth, H = stage.offsetHeight;
  mmScale = Math.min(190 / W, 240 / H);
  mmW = Math.max(40, W * mmScale); mmH = Math.max(40, H * mmScale);
  mm.style.width = mmW + 'px';
  const dpr = devicePixelRatio || 1;
  const cssW = mmW, cssH = mmH;
  mmc.width = cssW * dpr; mmc.height = cssH * dpr;
  mmc.style.width = cssW + 'px';
  mmc.style.height = cssH + 'px';
  const ctx = mmc.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, cssW, cssH);
  const styles = getComputedStyle(document.documentElement);
  const cLine = styles.getPropertyValue('--edge').trim();
  const cInk = styles.getPropertyValue('--muted').trim();
  const cAcc = styles.getPropertyValue('--accent').trim();
  $$('.card', tree).forEach(c => {
    if (c.offsetParent === null) return;
    const r = stageRect(c);
    ctx.fillStyle = c.classList.contains('hit') ? cAcc : cLine;
    ctx.fillRect(r.x * mmScale, r.y * mmScale, Math.max(2, r.w * mmScale), Math.max(1.5, r.h * mmScale));
  });
  $$('.nbox', tree).forEach(n => {
    if (n.offsetParent === null) return;
    const r = stageRect(n);
    ctx.fillStyle = cInk;
    ctx.fillRect(r.x * mmScale, r.y * mmScale, Math.max(2, r.w * mmScale), Math.max(1.5, r.h * mmScale));
  });
  updateViewportRect();
}
function updateViewportRect(){
  /* visible stage area in stage coords, clamped to the minimap box */
  const vx = (-cam.x) / cam.s, vy = (-cam.y) / cam.s;
  const vw = canvas.clientWidth / cam.s, vh = canvas.clientHeight / cam.s;
  const l = Math.max(0, Math.min(mmW - 4, vx * mmScale));
  const t = Math.max(0, Math.min(mmH - 4, vy * mmScale));
  mmvp.style.left = l + 'px';
  mmvp.style.top = t + 'px';
  mmvp.style.width = Math.max(4, Math.min(mmW - l, vw * mmScale)) + 'px';
  mmvp.style.height = Math.max(4, Math.min(mmH - t, vh * mmScale)) + 'px';
}
function mmNavigate(e){
  const r = mm.getBoundingClientRect();
  const sx = (e.clientX - r.left) / mmScale, sy = (e.clientY - r.top) / mmScale;
  cam.x = canvas.clientWidth/2 - sx * cam.s;
  cam.y = canvas.clientHeight/2 - sy * cam.s;
  applyCam();
}
mm.addEventListener('pointerdown', e => { mm.setPointerCapture(e.pointerId); mmNavigate(e); mm.dataset.drag = '1'; });
mm.addEventListener('pointermove', e => { if (mm.dataset.drag) mmNavigate(e); });
['pointerup','pointercancel'].forEach(ev => mm.addEventListener(ev, () => delete mm.dataset.drag));

function redraw(){ drawEdges(); drawMinimap(); }

/* ═══ hover path trace ═══ */
function tracePath(card, on){
  let b = card.closest('.branch');
  while (b){
    b.querySelector(':scope > .nbox')?.classList.toggle('onpath', on);
    b = b.parentElement.closest('.branch');
  }
}

/* ═══ toolbar ═══ */
$('#expandAll').addEventListener('click', () => {
  $$('.branch').forEach(b => b.classList.remove('collapsed'));
  redraw(); fit();
});
$('#collapseAll').addEventListener('click', () => {
  $$('.branch').forEach(b => { if (+b.dataset.depth >= 1) b.classList.add('collapsed'); });
  redraw(); fit();
});
const detailBtn = $('#detailToggle');
detailBtn.addEventListener('click', () => {
  const off = document.body.classList.toggle('detail-off');
  detailBtn.setAttribute('aria-pressed', String(!off));
  redraw();
});
$('#zoomIn').addEventListener('click', () => zoomAt(1.2, canvas.clientWidth/2, canvas.clientHeight/2 + canvas.getBoundingClientRect().top));
$('#zoomOut').addEventListener('click', () => zoomAt(1/1.2, canvas.clientWidth/2, canvas.clientHeight/2 + canvas.getBoundingClientRect().top));
$('#zoomFit').addEventListener('click', fit);
$('#zoomVal').addEventListener('click', () => { cam.s = 1; applyCam(); });
document.addEventListener('keydown', e => {
  if (document.activeElement.tagName === 'INPUT') return;
  if (e.key === '1') fit();
  if (e.key === '2') fitAll();
  if (e.key === '0'){ cam.s = 1; applyCam(); }
  if (e.key === '+' || e.key === '=') zoomAt(1.2, innerWidth/2, innerHeight/2);
  if (e.key === '-') zoomAt(1/1.2, innerWidth/2, innerHeight/2);
});

/* ═══ search (dim off-path) ═══ */
const q = $('#q'), hits = $('#hits'), sbox = $('#searchbox'), empty = $('#empty');
const allCards = $$('.card'), allBoxes = $$('.nbox');
function applyFilter(){
  const query = q.value.trim().toLowerCase();
  sbox.classList.toggle('active', !!query);
  document.body.classList.toggle('dimmable', !!query);
  allCards.forEach(c => c.classList.remove('dim','hit'));
  allBoxes.forEach(n => n.classList.remove('dim'));
  if (!query){ hits.textContent=''; empty.style.display='none'; drawMinimap(); return; }
  let shown = 0;
  const keep = new Set();
  allCards.forEach(c => {
    if (c.dataset.search.includes(query)){
      shown++; c.classList.add('hit');
      let b = c.closest('.branch');
      while (b){ keep.add(b.querySelector(':scope > .nbox')); b = b.parentElement.closest('.branch'); }
    } else c.classList.add('dim');
  });
  allBoxes.forEach(n => {
    if (n.dataset.search.includes(query)){
      keep.add(n);
      $$('.card', n.closest('.branch')).forEach(c => {
        if (c.classList.contains('dim')){ c.classList.remove('dim'); shown++; }
      });
      let b = n.closest('.branch').parentElement.closest('.branch');
      while (b){ keep.add(b.querySelector(':scope > .nbox')); b = b.parentElement.closest('.branch'); }
    }
  });
  allBoxes.forEach(n => { if (!keep.has(n)) n.classList.add('dim'); });
  hits.textContent = `${shown}/${DATA.total}`;
  empty.style.display = shown ? 'none' : 'block';
  drawMinimap();
}
let deb;
q.addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(applyFilter, 120); });
$('#clearq').addEventListener('click', () => { q.value=''; applyFilter(); q.focus(); });
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== q){ e.preventDefault(); q.focus(); }
  if (e.key === 'Escape' && document.activeElement === q){ q.value=''; applyFilter(); q.blur(); }
});

/* ═══ Copy as SVG (paste into Figma) ═══ */
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function colorOf(c){
  if (!c || c === 'transparent' || /rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0\s*\)/.test(c)) return null;
  return c;
}
function textLines(node){
  /* char-level rects grouped by line top → [{text,x,y,fontSize}] */
  const text = node.textContent;
  if (!text.trim()) return [];
  const range = document.createRange();
  const lines = [];
  let cur = null;
  for (let i = 0; i < text.length; i++){
    range.setStart(node, i); range.setEnd(node, i + 1);
    const r = range.getBoundingClientRect();
    if (!r.width && !r.height) continue;
    const top = Math.round(r.top);
    if (!cur || Math.abs(top - cur.top) > 2){
      cur = { top, left: r.left, bottom: r.bottom, chars: [] };
      lines.push(cur);
    }
    cur.chars.push(text[i]);
    cur.bottom = Math.max(cur.bottom, r.bottom);
  }
  return lines.map(l => ({ text: l.chars.join(''), left: l.left, top: l.top, bottom: l.bottom }));
}
function exportSVG(){
  const sr = stage.getBoundingClientRect();
  const X = v => ((v - sr.left) / cam.s).toFixed(1);
  const Y = v => ((v - sr.top) / cam.s).toFixed(1);

  function rectFor(elm){
    const cs = getComputedStyle(elm);
    const r = elm.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return '';
    const bg = colorOf(cs.backgroundColor);
    const bw = parseFloat(cs.borderTopWidth) || 0;
    const bc = bw ? colorOf(cs.borderTopColor) : null;
    if (!bg && !bc) return '';
    const rx = (parseFloat(cs.borderTopLeftRadius) || 0).toFixed(1);
    return `<rect x="${X(r.left)}" y="${Y(r.top)}" width="${(r.width/cam.s).toFixed(1)}" height="${(r.height/cam.s).toFixed(1)}" rx="${rx}"`
      + ` fill="${bg || 'none'}"`
      + (bc ? ` stroke="${bc}" stroke-width="${(bw/cam.s).toFixed(1)}"` : '')
      + (bc && cs.borderTopStyle === 'dashed' ? ' stroke-dasharray="4 3"' : '')
      + '/>';
  }
  function textsFor(scope){
    const parts = [];
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    let tn;
    while ((tn = walker.nextNode())){
      const parent = tn.parentElement;
      if (!parent || parent.offsetParent === null) continue;
      const cs = getComputedStyle(parent);
      const fs = parseFloat(cs.fontSize);
      const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '');
      textLines(tn).forEach(l => {
        if (!l.text.trim()) return;
        const baseline = ((l.top + l.bottom) / 2 - sr.top) / cam.s + fs * 0.35;
        parts.push(`<text x="${X(l.left)}" y="${baseline.toFixed(1)}" font-family="${esc(fam)}, sans-serif"`
          + ` font-size="${(fs/cam.s).toFixed(1)}" font-weight="${cs.fontWeight}" fill="${cs.color}"`
          + ` letter-spacing="${cs.letterSpacing === 'normal' ? '0' : cs.letterSpacing}">${esc(l.text)}</text>`);
      });
    }
    return parts;
  }
  /* 요소 서브트리 하나(카드/노드박스) → 도형+텍스트를 담은 그룹 */
  function groupFor(elm, name){
    const parts = [rectFor(elm)];
    $$(':scope *', elm).forEach(e => { if (e.offsetParent !== null) parts.push(rectFor(e)); });
    parts.push(...textsFor(elm));
    return `<g id="${esc(name)}">${parts.filter(Boolean).join('')}</g>`;
  }
  /* branch → 피그마 그룹 트리로 재귀 직렬화 */
  function groupForBranch(branch){
    const id = branch.dataset.id;
    const box = branch.querySelector(':scope > .nbox');
    const kids = branch.querySelector(':scope > .kids');
    const title = box?.querySelector('.ntitle')?.textContent || '';
    const parts = [groupFor(box, `${id} node`)];
    if (kids && !branch.classList.contains('collapsed')){
      [...kids.children].forEach(kid => {
        if (kid.classList.contains('branch')) parts.push(groupForBranch(kid));
        else {
          const sTitle = kid.querySelector('.stitle')?.textContent || '';
          parts.push(groupFor(kid, `${kid.id} ${sTitle}`));
        }
      });
    }
    return `<g id="${esc(id + ' ' + title)}">${parts.join('\n')}</g>`;
  }

  const edgeParts = $$('svg.edges path').map(p =>
    `<path d="${p.getAttribute('d')}" fill="none" stroke="${getComputedStyle(p).stroke}" stroke-width="1.5"/>`);
  const rootBranch = tree.querySelector(':scope > .branch');
  const w = (sr.width / cam.s).toFixed(0), h = (sr.height / cam.s).toFixed(0);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">\n`
    + `<g id="edges">${edgeParts.join('')}</g>\n`
    + groupForBranch(rootBranch)
    + `\n</svg>`;
}
const copyBtn = $('#copySvg');
copyBtn.addEventListener('click', async () => {
  copyBtn.textContent = '…';
  await new Promise(r => setTimeout(r, 20));   /* let label paint */
  const svg = exportSVG();
  let ok = false;
  try { await navigator.clipboard.writeText(svg); ok = true; } catch(e){}
  if (!ok){
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([svg], {type:'image/svg+xml'}));
    a.download = (document.title || 'scenarios') + '.svg';
    a.click();
  }
  copyBtn.textContent = ok ? 'Copied — paste in Figma' : 'Downloaded .svg';
  setTimeout(() => copyBtn.textContent = 'Copy SVG', 2200);
});

/* ═══ boot ═══ */
addEventListener('resize', () => { updateViewportRect(); });
if (document.fonts?.ready) document.fonts.ready.then(() => { redraw(); fit(); });
requestAnimationFrame(() => { redraw(); fit();
  if (location.hash){
    const t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (t){
      let b = t.closest('.branch');
      while (b){ b.classList.remove('collapsed'); b = b.parentElement.closest('.branch'); }
      redraw();
      centerOn(t, 1);
      t.classList.add('flash');
      setTimeout(()=> t.classList.remove('flash'), 1500);
    }
  }
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else Path(src).with_suffix(".html").name
    build(src, out)
