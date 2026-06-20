"""
Coach Availability — dashboard generator.

Two data sources, one renderer:
  - build_data(xlsx)            : read the output workbook (static/offline path)
  - build_data_from_engine(...) : build the same dict straight from engine outputs
                                  (used by the live FastAPI endpoint — no Excel round-trip)
  - render_html(data, live)     : static snapshot (live=False) OR live page with a
                                  Refresh button that re-fetches /api/data (live=True)

Operational-first: open-slot finder is the hero; capacity/utilisation collapsed below.

Created 18-Jun-2026 IST. Live mode added 18-Jun-2026 IST.

Run (static):
    python dashboard.py                       # coach_availability.xlsx -> coach_availability_dashboard.html
    python dashboard.py in.xlsx out.html
"""
import sys, json, re
from datetime import datetime
import pandas as pd
import tzutil

SUMMARY_SHEET = "Coach Availability"
OPEN_SHEET    = "Open Slots (next 7d)"
META_SHEET    = "Method & Notes"


def _i(v):
    return int(v) if pd.notna(v) else 0


def _fmt_dt(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%d-%b %H:%M")
    return str(v)


# ----------------------------------------------------------------------------- static path
def _read_meta(xlsx):
    try:
        mn = pd.read_excel(xlsx, sheet_name=META_SHEET, header=None)
    except Exception:
        return {}
    meta = {}
    for _, row in mn.iterrows():
        k = str(row[0]).strip()
        v = str(row[1]).strip() if len(row) > 1 and pd.notna(row[1]) else ""
        if k and k.lower() != "nan":
            meta[k] = v
    return meta


def _parse_slot(cell, coach, year):
    m = re.match(r"\s*(\d{1,2})-([A-Za-z]{3})\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", str(cell))
    if not m:
        return None
    day, mon, start, end = m.groups()
    try:
        dt = datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
    except ValueError:
        return None
    return {"coach": coach, "date": dt.strftime("%Y-%m-%d"),
            "day": dt.strftime("%a"), "start": start, "end": end,
            "reserved": "(R)" in str(cell)}


def _assemble(coaches, open_slots, window, statuses, n0=None, n1=None):
    open_slots = sorted(open_slots, key=lambda x: (x["date"], x["start"], x["coach"]))
    dates = sorted({s["date"] for s in open_slots})
    totals = {
        "total": sum(c["total"] for c in coaches),
        "blocked": sum(c["blocked"] for c in coaches),
        "booked": sum(c["booked"] for c in coaches),
        "avail": sum(c["avail"] for c in coaches),
        "open": sum(c["open"] for c in coaches),
        "open7": len(open_slots),
        "coaches": len(coaches),
        "coaches_with_open7": len({s["coach"] for s in open_slots}),
    }
    nf = n0.strftime("%Y-%m-%d") if n0 is not None else (dates[0] if dates else "")
    nt = n1.strftime("%Y-%m-%d") if n1 is not None else (dates[-1] if dates else "")
    return {
        "generated": tzutil.now_ist().strftime("%d-%b-%Y %H:%M") + " IST",
        "window": window, "statuses": statuses,
        "next7": {"from": nf, "to": nt},
        "totals": totals, "coaches": coaches, "open_slots": open_slots,
    }


def build_data(xlsx):
    """Build the dashboard dict from the output workbook (Open/Available recomputed)."""
    meta = _read_meta(xlsx)
    window, statuses = meta.get("Window", ""), meta.get("Occupied statuses", "")
    m = re.search(r"(\d{4})", window)
    year = int(m.group(1)) if m else tzutil.now_ist().year

    s = pd.read_excel(xlsx, sheet_name=SUMMARY_SHEET)
    s = s[s["Coach"].notna()]
    s = s[s["Coach"].astype(str).str.strip().str.upper() != "TOTAL"]
    coaches = []
    for _, r in s.iterrows():
        total, blocked, booked = _i(r.get("Total Slots")), _i(r.get("Blocked")), _i(r.get("Booked (appointments)"))
        coaches.append({"name": str(r["Coach"]).strip(), "total": total, "blocked": blocked,
                        "booked": booked, "avail": total - blocked, "open": total - blocked - booked,
                        "next_open": _fmt_dt(r.get("Next Open")), "last_open": _fmt_dt(r.get("Last Open"))})

    open_slots = []
    try:
        o = pd.read_excel(xlsx, sheet_name=OPEN_SHEET)
        for _, r in o.iterrows():
            coach = str(r["Coach"]).strip()
            if not coach or coach.lower() == "nan":
                continue
            for c in [c for c in o.columns if c != "Coach"]:
                if pd.notna(r[c]):
                    rec = _parse_slot(r[c], coach, year)
                    if rec:
                        open_slots.append(rec)
    except Exception:
        pass
    return _assemble(coaches, open_slots, window, statuses)


# ----------------------------------------------------------------------------- live path
def build_data_from_engine(g, open7, window="", statuses="", n0=None, n1=None):
    """Build the same dict directly from engine outputs (no Excel). Used by the live endpoint."""
    coaches = []
    for _, r in g.iterrows():
        total, blocked, booked = int(r["total"]), int(r["blocked"]), int(r["booked"])
        coaches.append({"name": str(r["name"]).strip(), "total": total, "blocked": blocked,
                        "booked": booked, "avail": total - blocked, "open": total - blocked - booked,
                        "next_open": _fmt_dt(r.get("next_open")), "last_open": _fmt_dt(r.get("last_open"))})
    open_slots = []
    op = open7.copy()
    if len(op):
        op["date"] = pd.to_datetime(op["date"])
        for _, r in op.iterrows():
            open_slots.append({"coach": str(r["name"]).strip(), "date": r["date"].strftime("%Y-%m-%d"),
                               "day": r["date"].strftime("%a"), "start": r["start"], "end": r["end"],
                               "reserved": bool(r.get("reserved", False))})
    return _assemble(coaches, open_slots, window, statuses, n0, n1)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Coach Availability</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#eef1f4; --panel:#ffffff; --ink:#152230; --muted:#5d6b7a; --line:#e2e7ec;
    --accent:#0d7a6f; --accent-weak:#e6f3f1;
    --open:#15a06e; --booked:#2f6fed; --blocked:#e0902a;
    --radius:14px; --shadow:0 1px 2px rgba(20,34,48,.05),0 6px 20px rgba(20,34,48,.06);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.45}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 22px 56px}
  header.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}
  h1{font-size:27px;font-weight:750;letter-spacing:-.02em;margin:0}
  .meta{color:var(--muted);font-size:13px;margin-top:4px}
  .meta b{color:var(--ink);font-weight:600}
  .stampbox{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
  .stamp{color:var(--muted);font-size:12px;text-align:right;white-space:nowrap}
  .refresh{font:inherit;font-size:13px;font-weight:600;color:#fff;background:var(--accent);
    border:0;border-radius:9px;padding:9px 15px;cursor:pointer;display:inline-flex;align-items:center;gap:7px}
  .refresh:hover{filter:brightness(1.05)}
  .refresh:disabled{opacity:.6;cursor:default}
  .refresh .sp{width:13px;height:13px;border:2px solid rgba(255,255,255,.5);border-top-color:#fff;
    border-radius:50%;display:none;animation:spin .8s linear infinite}
  .refresh.busy .sp{display:inline-block}
  @keyframes spin{to{transform:rotate(360deg)}}

  .kpis{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:24px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);min-width:240px}
  .kpi .v{font-size:30px;font-weight:740;letter-spacing:-.02em;line-height:1}
  .kpi .l{color:var(--muted);font-size:12.5px;margin-top:7px}
  .kpi.lead{background:linear-gradient(180deg,var(--accent-weak),#fff);border-color:#cfe7e3}
  .kpi.lead .v{color:var(--accent)}

  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:20px;margin-bottom:18px}
  .eyebrow{font-size:11px;letter-spacing:.10em;text-transform:uppercase;color:var(--muted);font-weight:700}
  .card h2{font-size:18px;font-weight:700;letter-spacing:-.01em;margin:5px 0 0}
  .card .h2sub{color:var(--muted);font-size:13px;margin:2px 0 16px}
  .hero{border:1px solid #cfe7e3;background:radial-gradient(120% 140% at 0% 0%, #f3faf9 0%, #ffffff 42%)}
  .filters{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 14px}
  select,input[type=text]{font:inherit;font-size:13.5px;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:9px;padding:9px 11px}
  input[type=text]{flex:1;min-width:180px}
  select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
  .tablebox{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  thead th{position:sticky;top:0;background:#f7f9fa;color:var(--muted);font-weight:600;text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);z-index:1}
  tbody td{padding:9px 12px;border-bottom:1px solid #eef1f4}
  tbody tr:nth-child(even){background:#fafbfc}
  tbody tr:hover{background:var(--accent-weak)}
  .coach{font-weight:600}.time{font-variant-numeric:tabular-nums}
  .badge{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:10.5px;font-weight:700;
    background:#fff4e5;color:#9a5b00;border:1px solid #f3d9b0;vertical-align:middle}
  .count{color:var(--muted);font-size:12.5px;margin-top:10px}
  .empty{padding:26px;text-align:center;color:var(--muted)}
  details.cap>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:9px;font-size:15px;font-weight:650}
  details.cap>summary::-webkit-details-marker{display:none}
  .chev{transition:transform .18s ease;color:var(--muted)}
  details.cap[open] .chev{transform:rotate(90deg)}
  .capgrid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:18px}
  @media(max-width:820px){.capgrid{grid-template-columns:1fr}}
  .legend{display:flex;gap:16px;margin:2px 0 4px;font-size:12px;color:var(--muted)}
  .dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:middle}
  canvas{max-width:100%}
  @media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <h1>Coach Availability</h1>
      <div class="meta" id="meta"></div>
    </div>
    <div class="stampbox">
      <button id="refreshBtn" class="refresh" hidden><span class="sp"></span><span class="lbl">↻ Refresh</span></button>
      <div class="stamp" id="stamp"></div>
    </div>
  </header>

  <div class="kpis" id="kpis"></div>

  <section class="card hero">
    <div class="eyebrow">Find an open slot</div>
    <h2>Open slots — next 7 days</h2>
    <div class="h2sub" id="rangelabel"></div>
    <div class="filters">
      <select id="fCoach"><option value="">All coaches</option></select>
      <select id="fDay"><option value="">All days</option></select>
      <input type="text" id="fSearch" placeholder="Search coach or time…" aria-label="Search open slots"/>
    </div>
    <div class="tablebox">
      <table><thead><tr><th>Coach</th><th>Date</th><th>Day</th><th>Time</th></tr></thead>
        <tbody id="rows"></tbody></table>
    </div>
    <div class="count" id="count"></div>
  </section>

  <section class="card">
    <div class="eyebrow">Demand at a glance</div>
    <h2>Open slots by day</h2>
    <div class="h2sub">Next 7 days</div>
    <canvas id="byDay" height="92"></canvas>
  </section>

  <section class="card">
    <details class="cap">
      <summary><span class="chev">▶</span> Capacity &amp; utilisation (this window)</summary>
      <div class="legend">
        <span><span class="dot" style="background:var(--open)"></span>Open</span>
        <span><span class="dot" style="background:var(--booked)"></span>Booked</span>
        <span><span class="dot" style="background:var(--blocked)"></span>Blocked</span>
      </div>
      <div class="capgrid"><div><canvas id="stack" height="230"></canvas></div><div><canvas id="util" height="230"></canvas></div></div>
    </details>
  </section>
</div>

<script>
const EMBEDDED = __DATA__;
const LIVE = __LIVE__;
let charts = {};
const fmtD   = d => new Date(d+'T00:00').toLocaleDateString(undefined,{day:'2-digit',month:'short'});
const fmtDow = d => new Date(d+'T00:00').toLocaleDateString(undefined,{weekday:'short',day:'2-digit',month:'short'});
const barLabels = {                       // draw the count above each bar
  id:'barLabels',
  afterDatasetsDraw(chart){
    const ctx=chart.ctx; ctx.save();
    ctx.font='600 12px ui-sans-serif,-apple-system,Segoe UI,sans-serif'; ctx.fillStyle='#152230'; ctx.textAlign='center';
    chart.getDatasetMeta(0).data.forEach((bar,i)=>{ const v=chart.data.datasets[0].data[i]; if(v!=null&&v!=='') ctx.fillText(v, bar.x, bar.y-6); });
    ctx.restore();
  }
};

function renderAll(DATA){
  const T = DATA.totals;
  document.getElementById('meta').innerHTML =
    `Window <b>${DATA.window||'—'}</b>${DATA.statuses?` &middot; occupied: <b>${DATA.statuses}</b>`:''}`;
  document.getElementById('stamp').textContent = (LIVE?'Updated · ':'Snapshot · ') + DATA.generated;
  document.getElementById('rangelabel').textContent =
    DATA.next7.from ? `${fmtDow(DATA.next7.from)} → ${fmtDow(DATA.next7.to)}` : 'No upcoming open slots in range';

  const kpis = [['Total Open slots', T.open7, true]];
  document.getElementById('kpis').innerHTML = kpis.map(k =>
    `<div class="kpi${k[2]?' lead':''}"><div class="v">${k[1]}</div><div class="l">${k[0]}</div></div>`).join('');

  buildFinder(DATA);
  drawCharts(DATA);
}

function buildFinder(DATA){
  const slots = DATA.open_slots;
  const fCoach=document.getElementById('fCoach'), fDay=document.getElementById('fDay'), fSearch=document.getElementById('fSearch');
  fCoach.length=1; fDay.length=1;                       // keep the "All …" option, drop the rest
  [...new Set(slots.map(s=>s.coach))].sort().forEach(c=>fCoach.add(new Option(c,c)));
  [...new Set(slots.map(s=>s.date))].sort().forEach(d=>fDay.add(new Option(fmtDow(d),d)));
  function apply(){
    const c=fCoach.value, d=fDay.value, q=fSearch.value.trim().toLowerCase();
    const rows = slots.filter(s => (!c||s.coach===c) && (!d||s.date===d) &&
      (!q||(s.coach+' '+s.start+' '+s.end).toLowerCase().includes(q)));
    document.getElementById('rows').innerHTML = rows.length
      ? rows.map(s=>`<tr><td class="coach">${s.coach}</td><td>${fmtD(s.date)}</td><td>${s.day}</td><td class="time">${s.start}–${s.end}${s.reserved?' <span class="badge">Reserved</span>':''}</td></tr>`).join('')
      : `<tr><td colspan="4" class="empty">No open slots match these filters.</td></tr>`;
    document.getElementById('count').textContent = `Showing ${rows.length} of ${slots.length} open slots`;
  }
  fCoach.onchange=apply; fDay.onchange=apply; fSearch.oninput=apply; apply();
}

function drawCharts(DATA){
  Object.values(charts).forEach(c=>{ if(c) c.destroy(); }); charts={};
  if(window.Chart){ Chart.defaults.font.family='ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif'; Chart.defaults.color='#5d6b7a'; }
  const slots=DATA.open_slots, byDay={}; slots.forEach(s=>byDay[s.date]=(byDay[s.date]||0)+1);
  const dks=Object.keys(byDay).sort();
  charts.byDay=new Chart(document.getElementById('byDay'),{type:'bar',
    data:{labels:dks.map(fmtDow),datasets:[{data:dks.map(d=>byDay[d]),backgroundColor:'#15a06e',borderRadius:5,maxBarThickness:46}]},
    plugins:[barLabels],
    options:{layout:{padding:{top:18}},plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grace:'10%',ticks:{precision:0},grid:{color:'#eef1f4'}},x:{grid:{display:false}}}}});
  const cs=[...DATA.coaches].sort((a,b)=>b.open-a.open);
  charts.stack=new Chart(document.getElementById('stack'),{type:'bar',
    data:{labels:cs.map(c=>c.name),datasets:[
      {label:'Open',data:cs.map(c=>c.open),backgroundColor:'#15a06e'},
      {label:'Booked',data:cs.map(c=>c.booked),backgroundColor:'#2f6fed'},
      {label:'Blocked',data:cs.map(c=>c.blocked),backgroundColor:'#e0902a'}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},title:{display:true,text:'Slots per coach',align:'start',font:{size:13}}},
      scales:{x:{stacked:true,beginAtZero:true,grid:{color:'#eef1f4'}},y:{stacked:true,grid:{display:false}}}}});
  const cu=DATA.coaches.map(c=>({n:c.name,u:c.total?Math.round((c.booked+c.blocked)/c.total*100):0})).sort((a,b)=>b.u-a.u);
  charts.util=new Chart(document.getElementById('util'),{type:'bar',
    data:{labels:cu.map(c=>c.n),datasets:[{data:cu.map(c=>c.u),backgroundColor:'#0d7a6f',borderRadius:4}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},title:{display:true,text:'Utilisation %  (Booked + Blocked / Total)',align:'start',font:{size:13}}},
      scales:{x:{beginAtZero:true,max:100,grid:{color:'#eef1f4'}},y:{grid:{display:false}}}}});
}

async function loadData(force){
  const btn=document.getElementById('refreshBtn'), stamp=document.getElementById('stamp');
  btn.classList.add('busy'); btn.disabled=true; stamp.textContent='Running pipeline…';
  try{
    const r=await fetch('/api/data?refresh='+(force?1:0));
    if(!r.ok) throw new Error('HTTP '+r.status);
    const j=await r.json();
    renderAll(j.data);
  }catch(e){
    stamp.textContent='Refresh failed: '+e.message;
  }finally{
    btn.classList.remove('busy'); btn.disabled=false;
  }
}

if(LIVE){
  const btn=document.getElementById('refreshBtn'); btn.hidden=false; btn.onclick=()=>loadData(true);
  document.getElementById('stamp').textContent='Loading…';
  loadData(false);
}else{
  renderAll(EMBEDDED);
}
</script>
</body>
</html>
"""


def render_html(data, live=False):
    return (TEMPLATE
            .replace("__DATA__", json.dumps(data))
            .replace("__LIVE__", "true" if live else "false"))


def generate(in_xlsx="coach_availability.xlsx", out_html="coach_availability_dashboard.html"):
    """Read the output workbook and write the static snapshot dashboard. Returns the data dict."""
    data = build_data(in_xlsx)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(data, live=False))
    return data


def main():
    in_path  = sys.argv[1] if len(sys.argv) > 1 else "coach_availability.xlsx"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "coach_availability_dashboard.html"
    data = generate(in_path, out_path)
    t = data["totals"]
    print(f"read {in_path}: {t['coaches']} coaches, {t['open7']} open slots (next 7d)")
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()