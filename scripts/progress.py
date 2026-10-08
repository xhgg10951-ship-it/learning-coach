#!/usr/bin/env python3
"""learning-coach 进度解析与可视化。

用法:
  python progress.py [--hub DIR] [--goal SLUG] [--today YYYY-MM-DD] [--html OUT.html] [--json]

- 默认在 stdout 输出文字摘要（包括过期未完成的周目标，供 Agent 做偏离检查）。
- --html 生成可内联嵌入对话的紧凑面板（<agent-embed>）。
- --json 输出结构化数据。
仅依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

DEFAULT_HUB = Path.home() / "learning-hub"

RE_STAGE = re.compile(r"^##\s+(.+?)\s*$")
RE_MODULE = re.compile(r"^###\s+\[(.)\]\s+(S\d+-M\d+)\s+(.+?)\s*$")
RE_HOURS = re.compile(r"预计耗时[:：]\s*([\d.]+)")
RE_MONTH = re.compile(r"^##\s+(\d{4})-(\d{2})\s*月")
RE_WEEK = re.compile(r"^###\s+(\d{4})-W(\d{1,2})")
RE_ITEM = re.compile(r"^\s*-\s+\[(.)\]\s+((?:W\d+-\d+)|(?:M\d+))[:：]\s*(.+?)\s*$")
RE_SECTION = re.compile(r"^##\s+")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig") if p.exists() else ""


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    out: dict = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.split("#", 1)[0].strip()
        out[k.strip()] = v
    return out


def parse_syllabus(text: str) -> list[dict]:
    modules, stage, cur = [], "", None
    for line in text.splitlines():
        mm = RE_MODULE.match(line)
        if mm:
            cur = {"status": mm.group(1), "id": mm.group(2), "name": mm.group(3), "stage": stage, "hours": 0.0}
            modules.append(cur)
            continue
        ms = RE_STAGE.match(line)
        if ms and not line.startswith("###"):
            stage, cur = ms.group(1), None
            continue
        if cur is not None:
            mh = RE_HOURS.search(line)
            if mh:
                try:
                    cur["hours"] = float(mh.group(1))
                except ValueError:
                    pass
    return modules


def parse_plan(text: str) -> dict:
    months: list[dict] = []
    weeks: list[dict] = []
    cur_month = cur_week = None
    for line in text.splitlines():
        m = RE_MONTH.match(line)
        if m:
            cur_month = {"month": f"{m.group(1)}-{m.group(2)}", "items": []}
            months.append(cur_month)
            cur_week = None
            continue
        w = RE_WEEK.match(line)
        if w:
            cur_week = {"year": int(w.group(1)), "week": int(w.group(2)), "label": line.lstrip("# ").strip(), "items": []}
            weeks.append(cur_week)
            continue
        if RE_SECTION.match(line):  # 其它二级标题（计划外学习/调整记录）
            cur_month = cur_week = None
            continue
        it = RE_ITEM.match(line)
        if it:
            item = {"status": it.group(1), "id": it.group(2), "text": it.group(3)}
            if cur_week is not None and item["id"].startswith("W"):
                cur_week["items"].append(item)
            elif cur_month is not None and item["id"].startswith("M"):
                cur_month["items"].append(item)
    return {"months": months, "weeks": weeks}


def parse_sessions(d: Path) -> list[dict]:
    out = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.md")):
        fm = frontmatter(read(f))
        date = fm.get("date") or f.name[:10]
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            continue
        try:
            minutes = int(float(fm.get("minutes", "0") or 0))
        except ValueError:
            minutes = 0
        out.append({"date": date, "topic": fm.get("topic", f.stem), "minutes": minutes, "file": f.name})
    return out


def analyze_goal(gdir: Path, today: dt.date) -> dict:
    fm = frontmatter(read(gdir / "goal.md"))
    modules = parse_syllabus(read(gdir / "syllabus.md"))
    plan = parse_plan(read(gdir / "plan.md"))
    sessions = parse_sessions(gdir / "sessions")
    iy, iw, _ = today.isocalendar()

    active = [m for m in modules if m["status"] != "-"]
    done = [m for m in active if m["status"] == "x"]
    doing = [m for m in active if m["status"] == "~"]
    tot_h = sum(m["hours"] for m in active)
    done_h = sum(m["hours"] for m in done)

    cur_week = next((w for w in plan["weeks"] if (w["year"], w["week"]) == (iy, iw)), None)
    overdue = []
    for w in plan["weeks"]:
        if (w["year"], w["week"]) < (iy, iw):
            for it in w["items"]:
                if it["status"] in (" ", "~"):
                    overdue.append({**it, "week": f"{w['year']}-W{w['week']:02d}"})
    cur_month = next((m for m in plan["months"] if m["month"] == today.strftime("%Y-%m")), None)
    month_has_weeks = any(
        dt.date.fromisocalendar(w["year"], w["week"], 1).strftime("%Y-%m") == today.strftime("%Y-%m")
        for w in plan["weeks"]
    )

    return {
        "slug": gdir.name,
        "title": fm.get("title", gdir.name),
        "deadline": fm.get("deadline", "none"),
        "status": fm.get("status", "active"),
        "weekly_hours": fm.get("weekly_hours", ""),
        "modules": modules,
        "module_total": len(active),
        "module_done": len(done),
        "module_doing": len(doing),
        "hours_total": tot_h,
        "hours_done": done_h,
        "current_week": cur_week,
        "current_month": cur_month,
        "current_month_needs_weeks": cur_month is not None and not month_has_weeks,
        "overdue": overdue,
        "sessions": sessions,
    }


def summary_text(goals: list[dict], today: dt.date) -> str:
    iy, iw, _ = today.isocalendar()
    lines = [f"今天 {today.isoformat()}（{iy}-W{iw:02d}）"]
    for g in goals:
        lines.append(f"\n## {g['title']} [{g['slug']}] status={g['status']} deadline={g['deadline']}")
        lines.append(f"模块：已掌握 {g['module_done']}/{g['module_total']}，进行中 {g['module_doing']}；"
                     f"学时 {g['hours_done']:.0f}/{g['hours_total']:.0f}h")
        recent = g["sessions"][-1] if g["sessions"] else None
        lines.append(f"学习次数：{len(g['sessions'])}；最近一次：{recent['date'] + ' ' + recent['topic'] if recent else '无'}")
        cw = g["current_week"]
        if cw:
            lines.append(f"本周目标（{cw['label']}）：")
            lines += [f"  [{i['status']}] {i['id']}: {i['text']}" for i in cw["items"]] or ["  （空）"]
        else:
            lines.append("本周目标：plan.md 中没有本周小节 → 需要细化本周/本月")
        if g["current_month_needs_weeks"]:
            lines.append("⚠ 本月有月目标，但还没有细化周目标")
        if g["current_month"] is None:
            lines.append("⚠ plan.md 中没有本月的月目标（可能需要跨月重排）")
        if g["overdue"]:
            lines.append(f"⚠ 过期未完成的周目标 {len(g['overdue'])} 条（需要顺延）：")
            lines += [f"  {o['week']} [{o['status']}] {o['id']}: {o['text']}" for o in g["overdue"]]
    return "\n".join(lines)


HTML_TMPL = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
<style>
.cell{width:12px;height:12px;border-radius:3px;background:var(--border)}
.bar{height:8px;border-radius:9999px;background:var(--border);overflow:hidden;display:flex}
</style></head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3">
<div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
  <div class="flex items-center justify-between gap-2 mb-3">
    <h2 class="font-semibold text-base">📊 学习进度 <span id="today" class="text-xs text-[var(--muted-foreground)] font-normal"></span></h2>
    <div id="tabs" class="flex gap-1 flex-wrap"></div>
  </div>
  <div id="body"></div>
</div>
<script>
const DATA = __DATA__;
const ICON = {" ":"⬜","~":"🟨","x":"✅",">":"↪️","-":"➖"};
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;};
document.getElementById('today').textContent = DATA.today + ' · ' + DATA.isoweek;
let cur = 0;
function tabs(){const t=document.getElementById('tabs');t.innerHTML='';
  if(DATA.goals.length<2)return;
  DATA.goals.forEach((g,i)=>{const b=el('button','text-xs px-2 py-1 rounded-md border border-[var(--border)] '+(i===cur?'bg-[var(--primary)] text-[var(--primary-foreground)]':'text-[var(--muted-foreground)]'),g.title);
    b.onclick=()=>{cur=i;render();};t.appendChild(b);});}
function render(){tabs();const b=document.getElementById('body');b.innerHTML='';
  const g=DATA.goals[cur]; if(!g){b.appendChild(el('p','text-sm text-[var(--muted-foreground)]','还没有学习目标。对我说“新建学习目标”开始吧。'));return;}
  // header
  const h=el('div','flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted-foreground)] mb-2');
  [['截止',g.deadline],['每周',g.weekly_hours?g.weekly_hours+'h':'—'],['学习次数',g.sessions.length],['累计',Math.round(g.sessions.reduce((a,s)=>a+s.minutes,0)/6)/10+'h']].forEach(([k,v])=>h.appendChild(el('span','',k+'：'+v)));
  b.appendChild(h);
  // module bar
  const t=g.module_total||1, pd=g.module_done/t*100, pg=g.module_doing/t*100;
  const row=el('div','mb-1 flex justify-between text-xs');row.appendChild(el('span','font-medium','大纲模块'));
  row.appendChild(el('span','text-[var(--muted-foreground)]',`已掌握 ${g.module_done} · 进行中 ${g.module_doing} · 共 ${g.module_total}`));b.appendChild(row);
  const bar=el('div','bar mb-2');const s1=el('div');s1.style.cssText=`width:${pd}%;background:var(--primary)`;const s2=el('div');s2.style.cssText=`width:${pg}%;background:var(--primary);opacity:.4`;bar.append(s1,s2);b.appendChild(bar);
  // module chips
  const chips=el('div','flex flex-wrap gap-1 mb-3');g.modules.forEach(m=>{const c=el('span','text-xs px-1.5 py-0.5 rounded border border-[var(--border)]',ICON[m.status]+' '+m.id);c.title=m.stage+' / '+m.name;if(m.status==='-')c.style.opacity=.5;chips.appendChild(c);});b.appendChild(chips);
  // grid: week + heatmap
  const grid=el('div','grid gap-4');grid.style.gridTemplateColumns='minmax(0,1fr) auto';
  const wk=el('div');wk.appendChild(el('div','text-xs font-medium mb-1','本周目标'+(g.current_week?'（'+g.current_week.label.replace(/^\d{4}-/,'')+'）':'')));
  const items=(g.current_week&&g.current_week.items)||[];
  if(!items.length)wk.appendChild(el('div','text-xs text-[var(--muted-foreground)]','本周还没有目标'));
  items.forEach(i=>{const r=el('div','text-xs flex gap-1 py-0.5');r.appendChild(el('span','',ICON[i.status]||'⬜'));const tx=el('span',i.status==='x'?'line-through text-[var(--muted-foreground)]':'',i.id+' '+i.text);r.appendChild(tx);wk.appendChild(r);});
  if(g.overdue.length)wk.appendChild(el('div','text-xs mt-1 text-[var(--muted-foreground)]',`↪️ ${g.overdue.length} 条过期未完成，待顺延`));
  grid.appendChild(wk);
  // heatmap 12 weeks
  const hm=el('div');hm.appendChild(el('div','text-xs font-medium mb-1','近 12 周'));
  const byDay={};g.sessions.forEach(s=>{byDay[s.date]=(byDay[s.date]||0)+Math.max(s.minutes,30);});
  const today=new Date(DATA.today+'T00:00:00');const dow=(today.getDay()+6)%7;const start=new Date(today);start.setDate(today.getDate()-dow-77);
  const cg=el('div');cg.style.cssText='display:grid;grid-template-rows:repeat(7,12px);grid-auto-flow:column;gap:3px';
  for(let i=0;i<84;i++){const d=new Date(start);d.setDate(start.getDate()+i);const key=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    const c=el('div','cell');const v=byDay[key]||0;if(d>today)c.style.opacity=.25;
    if(v){c.style.background='var(--primary)';c.style.opacity=Math.min(1,.35+v/120);}c.title=key+(v?` · ${v} 分钟`:'');cg.appendChild(c);}
  hm.appendChild(cg);grid.appendChild(hm);b.appendChild(grid);
  // recent sessions
  const rs=g.sessions.slice(-3).reverse();if(rs.length){const r=el('div','mt-3 text-xs text-[var(--muted-foreground)]');r.appendChild(el('span','font-medium text-[var(--foreground)]','最近：'));r.appendChild(document.createTextNode(rs.map(s=>s.date.slice(5)+' '+s.topic).join(' ｜ ')));b.appendChild(r);}
}
render();
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", default=str(DEFAULT_HUB))
    ap.add_argument("--goal")
    ap.add_argument("--today")
    ap.add_argument("--html")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    groot = Path(a.hub) / "goals"
    dirs = sorted(p for p in groot.glob("*") if p.is_dir()) if groot.exists() else []
    if a.goal:
        dirs = [d for d in dirs if d.name == a.goal]
    goals = [analyze_goal(d, today) for d in dirs]
    goals.sort(key=lambda g: g["status"] != "active")

    if a.json:
        print(json.dumps({"today": today.isoformat(), "goals": goals}, ensure_ascii=False, indent=2))
    else:
        print(summary_text(goals, today) if goals else f"未找到学习目标：{groot}")

    if a.html:
        iy, iw, _ = today.isocalendar()
        data = {"today": today.isoformat(), "isoweek": f"{iy}-W{iw:02d}", "goals": goals}
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        out = Path(a.html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(HTML_TMPL.replace("__DATA__", payload), encoding="utf-8")
        print(f"\nHTML 面板已生成：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
