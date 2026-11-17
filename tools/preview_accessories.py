#!/usr/bin/env python3
"""配件審核頁：每個配件一張卡，疊在角色的動作上播放，可以逐個按 OK／需修改並匯出。

用法：python3 tools/preview_accessories.py characters/<id> [out.html] [配件id ...]
"""
import base64, hashlib, html, json, sys
from pathlib import Path

SLOTS = ["weapon", "outfit", "hands", "neck", "face", "eyes", "head"]     # 疊圖順序（同 desktop_pet.ACC_SLOTS）
SHOW = {"head": ["idle", "walk", "headpat", "read", "desk_sleep_r", "swing"],
        "neck": ["idle", "walk", "run", "read", "bed_sleep_r", "swing"],
        "hands": ["idle", "peace", "stretch", "read", "shy", "gift"],
        "face": ["idle", "walk", "sleepy", "read", "desk_sleep_r", "peek"],
        "weapon": ["swing", "walk_weapon", "run_weapon", "draw_weapon", "sheath", "idle"],
        "outfit": ["idle", "walk", "headpat", "read", "bed_sleep_r", "swing"]}


def b64(p):
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cdir = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else cdir / "accessories_review.html"
    char = json.loads((cdir / "character.json").read_text(encoding="utf-8"))
    anims = json.loads((cdir / "assets" / "anims.json").read_text(encoding="utf-8"))
    acc = cdir / "accessories"
    base = {n: dict(m, src=b64(cdir / "assets" / f"{n}.png")) for n, m in anims.items()}
    meta = json.loads((acc / "items.json").read_text(encoding="utf-8"))
    items = meta["items"] if isinstance(meta, dict) else meta
    defaults = meta.get("defaults", {}) if isinstance(meta, dict) else {}
    byid = {it["id"]: it for it in items}
    want = sys.argv[3:] or [it["id"] for it in items if it["id"] not in defaults.values()]   # 「a+b」表示疊在一起看
    cards = []
    for key in want:
        ids = key.split("+")
        worn = {byid[i]["slot"]: i for i in ids}
        order = [worn.get(s) or defaults.get(s) for s in SLOTS]
        order = [i for i in order if i]
        ov, h = {}, hashlib.sha1()
        for n in anims:                                   # 跟 desktop_pet.Sprites.set_worn 同樣的順序
            steps = [(i, k) for i in order for k in ("_erase", "") if (acc / i / f"{n}{k}.png").exists()]
            steps += [(i, "_top") for i in order if (acc / i / f"{n}_top.png").exists()]
            for i, k in steps:
                p = acc / i / f"{n}{k}.png"
                ov.setdefault(n, []).append([b64(p), k == "_erase"]); h.update(p.read_bytes())
        names = "＋".join(byid[i]["name"] for i in ids)
        cards.append(dict(id=key, name=names, slot=byid[ids[0]]["slot"], ov=ov, hash=h.hexdigest()[:10]))
    page = TEMPLATE.replace("__TITLE__", html.escape(char.get("name", cdir.name))) \
        .replace("__CID__", json.dumps(char.get("id", cdir.name))) \
        .replace("__BASE__", json.dumps(base)).replace("__CARDS__", json.dumps(cards, ensure_ascii=False)) \
        .replace("__SHOW__", json.dumps(SHOW))
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(cards)} accessories)")


TEMPLATE = r"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__ 配件審核</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#222;--mute:#777;--line:#ddd;--ok:#2e7d32;--fix:#c62828;--chk:#e9e7e1}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#26262a;--ink:#eee;--mute:#999;--line:#3a3a40;--ok:#66bb6a;--fix:#ef5350;--chk:#303036}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;z-index:2}
h1{font-size:18px;margin:0}
.wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr));gap:12px;padding:12px 16px}
.c{background:var(--card);border:2px solid var(--line);border-radius:10px;padding:10px}
.c.ok{border-color:var(--ok)}.c.fix{border-color:var(--fix)}
.row{display:flex;flex-wrap:wrap;gap:6px}
.stage{background:repeating-conic-gradient(var(--chk) 0 25%,transparent 0 50%) 0 0/12px 12px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;border-radius:6px;padding:4px}
.stage span{font-size:11px;color:var(--mute)}
canvas{image-rendering:pixelated}.meta{color:var(--mute);font-size:12px}.btns{display:flex;gap:6px;margin-top:6px}
button,select{font:inherit;padding:4px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.on.okb{background:var(--ok);color:#fff}button.on.fixb{background:var(--fix);color:#fff}
textarea{width:100%;box-sizing:border-box;margin-top:6px;font:inherit;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px}
pre{white-space:pre-wrap;margin:16px;padding:12px;background:var(--card);border-radius:8px}
</style></head><body>
<header><h1>__TITLE__ 配件審核</h1><span id="sum"></span>
<label>多看一個動作 <select id="pick"></select></label>
<label>速度 <select id="spd"><option value="1">1x</option><option value="0.5">0.5x</option></select></label>
<label><input type="checkbox" id="cmp"> 對照原圖</label>
<button id="exp">匯出審核結果</button></header>
<div class="wrap" id="root"></div><pre id="out" hidden></pre>
<script>
const CID=__CID__,BASE=__BASE__,CARDS=__CARDS__,SHOW=__SHOW__,S=3;
const KEY=c=>`acc:${CID}:${c.id}:${c.hash}`;
function load(c){try{return JSON.parse(localStorage.getItem(KEY(c)))||{}}catch(e){return {}}}
function save(c,v){try{localStorage.setItem(KEY(c),JSON.stringify(v))}catch(e){}}
let speed=1,extra=localStorage.getItem('acc:pick')||'sleepy',cmp=false;
const pick=document.getElementById('pick');
for(const n of Object.keys(BASE)){const o=document.createElement('option');o.value=o.textContent=n;pick.appendChild(o)}
pick.value=extra;pick.onchange=()=>{extra=pick.value;try{localStorage.setItem('acc:pick',extra)}catch(e){}};
document.getElementById('spd').onchange=e=>speed=+e.target.value;
document.getElementById('cmp').onchange=e=>cmp=e.target.checked;
const imgs={};const img=src=>imgs[src]||(imgs[src]=Object.assign(new Image(),{src}));
const players=[];
function player(card,getName){
  const st=document.createElement('div');st.className='stage';
  const cv=document.createElement('canvas'),lab=document.createElement('span');st.append(cv,lab);
  const x=cv.getContext('2d');let cur=null,f=0,t=0;
  players.push(now=>{const n=getName();const m=BASE[n];
    if(n!==cur){cur=n;f=0;t=now;cv.width=m.w*S;cv.height=m.h*S;lab.textContent=n}
    if(now-t>m.ms[f]/speed){t=now;f=(f+1)%m.frames}
    x.imageSmoothingEnabled=false;x.clearRect(0,0,cv.width,cv.height);
    x.drawImage(img(m.src),f*m.w,0,m.w,m.h,0,0,m.w*S,m.h*S);
    if(!cmp)for(const [o,er] of card.ov[n]||[]){x.globalCompositeOperation=er?'destination-out':'source-over';x.drawImage(img(o),f*m.w,0,m.w,m.h,0,0,m.w*S,m.h*S)}
    x.globalCompositeOperation='source-over'});
  return st}
const root=document.getElementById('root');
for(const c of CARDS){
  const el=document.createElement('div');el.className='c';root.appendChild(el);
  el.innerHTML=`<b>${c.name}</b> <code>${c.id}</code> <span class="meta">${c.slot}</span><div class="row"></div>
<div class="btns"><button class="okb">OK</button><button class="fixb">需修改</button></div><textarea rows="2" placeholder="修改意見（哪個動作、哪裡怪）"></textarea>`;
  const row=el.querySelector('.row');for(const n of (SHOW[c.slot]||SHOW.head))row.appendChild(player(c,()=>n));row.appendChild(player(c,()=>extra));
  const ok=el.querySelector('.okb'),fx=el.querySelector('.fixb'),ta=el.querySelector('textarea');ta.value=load(c).note||'';
  const paint=()=>{const s=load(c).s;el.classList.toggle('ok',s==='ok');el.classList.toggle('fix',s==='fix');ok.classList.toggle('on',s==='ok');fx.classList.toggle('on',s==='fix');summary()};
  const set=s=>{const v=load(c);v.s=v.s===s?null:s;v.note=ta.value;save(c,v);paint()};
  ok.onclick=()=>set('ok');fx.onclick=()=>set('fix');ta.oninput=()=>{const v=load(c);v.note=ta.value;if(ta.value&&!v.s)v.s='fix';save(c,v);paint()};paint()}
function summary(){let o=0,f=0;for(const c of CARDS){const s=load(c).s;if(s==='ok')o++;else if(s==='fix')f++}
  document.getElementById('sum').textContent=`OK ${o} · 需修改 ${f} · 未審 ${CARDS.length-o-f} / ${CARDS.length}`}
(function loop(now){for(const p of players)p(now);requestAnimationFrame(loop)})(0);
document.getElementById('exp').onclick=()=>{const L=[`# ${CID} 配件審核`];
  for(const c of CARDS){const v=load(c);L.push(`- ${c.id} (${c.name}): ${v.s==='ok'?'OK':v.s==='fix'?'需修改':'未審'}${v.note?' — '+v.note.replace(/\n/g,' '):''}`)}
  const t=L.join('\n'),p=document.getElementById('out');p.hidden=false;p.textContent=t;try{navigator.clipboard.writeText(t)}catch(e){}p.scrollIntoView()};
summary();
</script></body></html>"""

if __name__ == "__main__":
    main()
