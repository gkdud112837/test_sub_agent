"""ax/demo/parts/*.csv + 원문을 합쳐 보기 좋은 HTML 뷰어(ax/demo/viewer.html)를 만든다.

사용: python -I -X utf8 tools/build_viewer.py
"""
import csv, glob, html, json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(BASE, "ax", "demo", "parts")
OUT = os.path.join(BASE, "ax", "demo", "viewer.html")

texts = {}
for p in glob.glob(os.path.join(BASE, "archive-*", "archive", "batch*", "r_*.md")):
    raw = open(p, encoding="utf-8").read()
    head, body = raw.split("---", 2)[1:]
    meta = dict(l.split(": ", 1) for l in head.strip().splitlines() if ": " in l)
    texts[meta.get("voc_id", os.path.basename(p)[:-3])] = {
        "text": body.strip(), "source": meta.get("source", ""), "date": meta.get("date", "")}

rows = []
for f in sorted(glob.glob(os.path.join(PARTS, "*.csv"))):
    name = os.path.basename(f)[:-4]
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        t = texts.get(r["voc_id"], {})
        rows.append({"file": name, **r, **t})

TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VOC 분류 뷰어</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--fg:#1f1f1f;--mute:#6b6b6b;--line:#e4e2dd;--hl:#fff3b0;
--P1:#d9480f;--P2:#1971c2;--P3:#2f9e44;--H1:#868e96;--H2:#868e96;--none:#adb5bd;--rev:#e8590c}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--card:#222225;--fg:#ececec;--mute:#9a9a9a;--line:#333;--hl:#5c4b00}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,"Malgun Gothic","Apple SD Gothic Neo",sans-serif}
header{position:sticky;top:0;background:var(--bg);padding:14px 16px 10px;border-bottom:1px solid var(--line);z-index:2}
h1{font-size:18px;margin:0 0 8px}.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
button,select,input{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 11px;cursor:pointer}
input{border-radius:8px;cursor:text;min-width:180px}button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.stat{color:var(--mute);margin-left:auto;font-size:13px}
main{padding:12px 16px 40px;max-width:1200px;margin:0 auto}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--mute);font-weight:600;background:var(--card);position:sticky;top:0}
td.id{white-space:nowrap;font-family:Consolas,monospace;font-size:13px}td.meta{white-space:nowrap;color:var(--mute);font-size:12px}
.tag{display:inline-block;min-width:54px;text-align:center;padding:2px 8px;border-radius:999px;color:#fff;font-weight:600;font-size:12px}
.ev{font-weight:600}mark{background:var(--hl);color:inherit;padding:0 1px;border-radius:2px}.note{color:var(--rev);font-size:13px}
@media (max-width:720px){td.meta,th.meta{display:none}}
</style></head><body>
<header><h1>VOC 분류 뷰어</h1>
<div class="bar" id="files"></div><div class="bar" id="tags" style="margin-top:6px"></div>
<div class="bar" style="margin-top:6px"><input id="q" placeholder="voc_id · 원문 · 근거 검색"><span class="stat" id="stat"></span></div></header>
<main><table><thead><tr><th>voc_id</th><th>파일</th><th>태그</th><th>원문 (근거 구절 강조)</th><th>근거 · note</th><th class="meta">출처 · 날짜</th></tr></thead><tbody id="tb"></tbody></table></main>
<script>
const ROWS=__DATA__;
const TAGS=["P1","P2","P3","H1","H2","해당없음","검토"];
const COLOR={P1:"var(--P1)",P2:"var(--P2)",P3:"var(--P3)",H1:"var(--H1)",H2:"var(--H2)","해당없음":"var(--none)","검토":"var(--rev)"};
const files=[...new Set(ROWS.map(r=>r.file))];let fSel="전체",tSel=new Set(),q="";
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function chips(){const fe=document.getElementById("files");fe.innerHTML="";["전체",...files].forEach(f=>{const b=document.createElement("button");b.textContent=f;b.className=f===fSel?"on":"";b.onclick=()=>{fSel=f;chips();draw()};fe.appendChild(b)});
const te=document.getElementById("tags");te.innerHTML="";TAGS.forEach(t=>{const b=document.createElement("button");b.textContent=t;b.className=tSel.has(t)?"on":"";b.onclick=()=>{tSel.has(t)?tSel.delete(t):tSel.add(t);chips();draw()};te.appendChild(b)})}
function draw(){const rs=ROWS.filter(r=>(fSel==="전체"||r.file===fSel)&&(!tSel.size||tSel.has(r.tag))&&(!q||(r.voc_id+r.text+r.evidence+r.note).includes(q)));
const cnt={};rs.forEach(r=>cnt[r.tag]=(cnt[r.tag]||0)+1);
document.getElementById("stat").textContent=rs.length+"건 · "+TAGS.filter(t=>cnt[t]).map(t=>t+" "+cnt[t]).join(" · ");
document.getElementById("tb").innerHTML=rs.map(r=>{let t=esc(r.text);const ev=esc(r.evidence);if(ev&&t.includes(ev))t=t.replace(ev,"<mark>"+ev+"</mark>");
return `<tr><td class="id">${esc(r.voc_id)}</td><td class="meta">${esc(r.file)}</td><td><span class="tag" style="background:${COLOR[r.tag]||"#000"}">${esc(r.tag)}</span></td><td>${t||"<i>원문 없음</i>"}</td><td><div class="ev">${ev}</div>${r.note?`<div class="note">${esc(r.note)}</div>`:""}</td><td class="meta">${esc(r.source)}<br>${esc(r.date)}</td></tr>`}).join("")}
document.getElementById("q").oninput=e=>{q=e.target.value.trim();draw()};chips();draw();
</script></body></html>"""

open(OUT, "w", encoding="utf-8").write(TEMPLATE.replace("__DATA__", json.dumps(rows, ensure_ascii=False)))
print(f"{len(rows)}행 → {OUT}")
