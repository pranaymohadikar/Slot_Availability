const EMBEDDED = {{ data_json|safe }};
const LIVE = {{ live_js|safe }};
let charts = {};
let lastData = null;
const ROLE_ORDER = ['Nutritionist','Physiotherapist','Psychologist','Other'];   // single source; was duplicated in buildFinder() + drawCharts()
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const roleColors = () => ({Nutritionist:cssVar('--role-nutritionist'),Physiotherapist:cssVar('--role-physio'),
                            Psychologist:cssVar('--role-psych'),Other:cssVar('--role-other')});
const fmtD   = d => new Date(d+'T00:00').toLocaleDateString(undefined,{day:'2-digit',month:'short'});
const fmtDow = d => new Date(d+'T00:00').toLocaleDateString(undefined,{weekday:'short',day:'2-digit',month:'short'});
const barLabels = {                       // draw the count above each individual bar
  id:'barLabels',
  afterDatasetsDraw(chart){
    const ctx=chart.ctx; ctx.save();
    ctx.font='600 11px ui-sans-serif,-apple-system,Segoe UI,sans-serif'; ctx.fillStyle=cssVar('--ink'); ctx.textAlign='center';
    chart.data.datasets.forEach((ds,di)=>{
      const meta=chart.getDatasetMeta(di); if(meta.hidden) return;
      meta.data.forEach((bar,i)=>{ const v=+ds.data[i]||0; if(v>0) ctx.fillText(v, bar.x, bar.y-5); });
    });
    ctx.restore();
  }
};

function currentTheme(){
  const forced = document.documentElement.getAttribute('data-theme');
  if(forced === 'dark' || forced === 'light') return forced;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyThemeButton(){
  const btn = document.getElementById('themeToggle'); if(!btn) return;
  const dark = currentTheme() === 'dark';
  btn.textContent = dark ? '☀' : '☾';
  btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
}

function initTheme(){
  applyThemeButton();
  const btn = document.getElementById('themeToggle'); if(!btn) return;
  btn.onclick = () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try{ localStorage.setItem('theme', next); }catch(e){}
    applyThemeButton();
    if(lastData) renderAll(lastData);       // canvases don't restyle on their own -- redraw with the new palette
  };
}

function renderAll(DATA){
  lastData = DATA;
  const T = DATA.totals;
  document.getElementById('meta').innerHTML =
    `Window <b>${DATA.window||'—'}</b>${DATA.statuses?` &middot; occupied: <b>${DATA.statuses}</b>`:''}`;
  document.getElementById('stamp').textContent = (LIVE?'Updated · ':'Snapshot · ') + DATA.generated;
  document.getElementById('rangelabel').textContent =
    DATA.next7.from ? `${fmtDow(DATA.next7.from)} → ${fmtDow(DATA.next7.to)}` : 'No upcoming open slots in range';

  const lead = `<div class="kpi lead"><div class="v">${T.open7}</div><div class="l">Total Open slots</div></div>`;
  const NEXT_UP_ROLES = ['Nutritionist','Physiotherapist','Psychologist'];   // coaching roles only; "Other" excluded on purpose
  const roleTiles = NEXT_UP_ROLES.map(role => {
    const upcoming = DATA.open_slots.filter(s => (s.role||'Other') === role).slice(0, 2);
    const lines = upcoming.length
      ? upcoming.map(s => `<div class="slotline"><b>${s.coach}</b><span class="stime">${fmtD(s.date)} ${s.start}${s.reserved?' <span class="badge">R</span>':''}</span></div>`).join('')
      : `<div class="slotline empty2">No upcoming slots</div>`;
    return `<div class="kpi roleNext"><div class="eyebrow">Next up · ${role}</div>${lines}</div>`;
  }).join('');
  document.getElementById('kpis').innerHTML = lead + roleTiles;

  buildFinder(DATA);
  drawCharts(DATA);
  renderBlockedGrid(DATA);
  renderReservedGaps(DATA);
}

function buildFinder(DATA){
  const slots = DATA.open_slots;
  const fRole=document.getElementById('fRole'), fCoach=document.getElementById('fCoach'),
        fDay=document.getElementById('fDay'), fReserved=document.getElementById('fReserved'), fSearch=document.getElementById('fSearch');
  fRole.length=1; fDay.length=1;                        // keep the "All …" option, drop the rest
  ROLE_ORDER.filter(r=>slots.some(s=>(s.role||'Other')===r)).forEach(r=>fRole.add(new Option(r,r)));
  [...new Set(slots.map(s=>s.date))].sort().forEach(d=>fDay.add(new Option(fmtDow(d),d)));
  function fillCoaches(role){                            // coach list follows the selected role
    fCoach.length=1;
    [...new Set(slots.filter(s=>!role||(s.role||'Other')===role).map(s=>s.coach))].sort()
      .forEach(c=>fCoach.add(new Option(c,c)));
  }
  fillCoaches('');
  function apply(){
    const r=fRole.value, c=fCoach.value, d=fDay.value, rv=fReserved.value, q=fSearch.value.trim().toLowerCase();
    const rows = slots.filter(s => (!r||(s.role||'Other')===r) && (!c||s.coach===c) && (!d||s.date===d) &&
      (!rv || (rv==='res' ? s.reserved : !s.reserved)) &&
      (!q||(s.coach+' '+s.start+' '+s.end).toLowerCase().includes(q)));
    document.getElementById('rows').innerHTML = rows.length
      ? rows.map(s=>`<tr><td class="coach">${s.coach}</td><td>${fmtD(s.date)}</td><td>${s.day}</td><td class="time">${s.start}–${s.end}${s.reserved?' <span class="badge">Reserved</span>':''}</td></tr>`).join('')
      : `<tr><td colspan="4" class="empty">No open slots match these filters.</td></tr>`;
    document.getElementById('count').textContent = `Showing ${rows.length} of ${slots.length} open slots`;
  }
  fRole.onchange=()=>{ fillCoaches(fRole.value); fCoach.value=''; apply(); };
  fCoach.onchange=apply; fDay.onchange=apply; fReserved.onchange=apply; fSearch.oninput=apply; apply();
}

function drawCharts(DATA){
  Object.values(charts).forEach(c=>{ if(c) c.destroy(); }); charts={};
  const gridColor=cssVar('--chart-grid'), textColor=cssVar('--chart-text');
  if(window.Chart){ Chart.defaults.font.family='ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif'; Chart.defaults.color=textColor; }
  const ROLE_COLORS=roleColors();
  const slots=DATA.open_slots;
  const dks=[...new Set(slots.map(s=>s.date))].sort();
  const present=ROLE_ORDER.filter(role=>slots.some(s=>(s.role||'Other')===role));
  const dsRole=present.map(role=>({
    label:role,
    data:dks.map(d=>slots.filter(s=>s.date===d && (s.role||'Other')===role).length),
    backgroundColor:ROLE_COLORS[role], borderRadius:4, maxBarThickness:26}));   // grouped (no stack) -> bars sit side by side per day
  charts.byDay=new Chart(document.getElementById('byDay'),{type:'bar',
    data:{labels:dks.map(fmtDow),datasets:dsRole},
    plugins:[barLabels],
    options:{layout:{padding:{top:18}},
      plugins:{legend:{display:true,position:'bottom',labels:{boxWidth:10,boxHeight:10,usePointStyle:true,pointStyle:'circle',padding:14}}},
      scales:{y:{beginAtZero:true,grace:'12%',ticks:{precision:0},grid:{color:gridColor}},x:{grid:{display:false}}}}});
  const cs=[...DATA.coaches].sort((a,b)=>b.open-a.open);
  charts.stack=new Chart(document.getElementById('stack'),{type:'bar',
    data:{labels:cs.map(c=>c.name),datasets:[
      {label:'Open',data:cs.map(c=>c.open),backgroundColor:cssVar('--open')},
      {label:'Booked',data:cs.map(c=>c.booked),backgroundColor:cssVar('--booked')},
      {label:'Blocked',data:cs.map(c=>c.blocked),backgroundColor:cssVar('--blocked')}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},title:{display:true,text:'Slots per coach',align:'start',font:{size:13}}},
      scales:{x:{stacked:true,beginAtZero:true,grid:{color:gridColor}},y:{stacked:true,grid:{display:false}}}}});
  const cu=DATA.coaches.map(c=>({n:c.name,u:c.total?Math.round((c.booked+c.blocked)/c.total*100):0})).sort((a,b)=>b.u-a.u);
  charts.util=new Chart(document.getElementById('util'),{type:'bar',
    data:{labels:cu.map(c=>c.n),datasets:[{data:cu.map(c=>c.u),backgroundColor:cssVar('--accent'),borderRadius:4}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},title:{display:true,text:'Utilisation %  (Booked + Blocked / Total)',align:'start',font:{size:13}}},
      scales:{x:{beginAtZero:true,max:100,grid:{color:gridColor}},y:{grid:{display:false}}}}});
}

function renderBlockedGrid(DATA){
  const tbl=document.getElementById('bgrid'); if(!tbl) return;
  const rows=DATA.blocked||[];
  const card=document.getElementById('blkcard');
  if(!rows.length){ tbl.innerHTML='<tr><td class="empty">No blocked slots in the next 7 days.</td></tr>'; return; }
  const dates=[...new Set(rows.map(r=>r.date))].sort();
  const coaches=[...new Set(rows.map(r=>r.coach))].sort();
  const key=(c,d)=>c+'|'+d;
  const map={}; rows.forEach(r=>map[key(r.coach,r.date)]=r);
  const roleOf={}; rows.forEach(r=>roleOf[r.coach]=r.role);
  const maxb=Math.max(1,...rows.map(r=>r.blocked));
  const heat=cssVar('--heat');
  const tint=v=>v<=0?'':`background:rgba(${heat},${(0.08+0.55*(v/maxb)).toFixed(3)})`;  // heatmap
  let h='<thead><tr><th style="text-align:left">Coach</th><th style="text-align:left">Role</th>'
      + dates.map(d=>{const x=new Date(d+'T00:00');return `<th>${x.toLocaleDateString(undefined,{weekday:'short'})}<br>${x.getDate()} ${x.toLocaleDateString(undefined,{month:'short'})}</th>`;}).join('')
      + '<th>Total</th></tr></thead><tbody>';
  coaches.forEach(c=>{
    let rowTot=0;
    let tds='';
    dates.forEach(d=>{
      const r=map[key(c,d)];
      if(!r){ tds+='<td class="zero">–</td>'; return; }          // no slots scheduled that day
      rowTot+=r.blocked;
      if(r.whole_day){ tds+=`<td class="wd" title="Whole-day block">Full day<br>${r.blocked}/${r.total}</td>`; return; }
      if(r.blocked===0){ tds+=`<td class="zero">0/${r.total}</td>`; return; }
      tds+=`<td style="${tint(r.blocked)}">${r.blocked}/${r.total}</td>`;
    });
    h+=`<tr><td class="cname">${c}</td><td class="crole">${roleOf[c]||''}</td>${tds}<td class="tot">${rowTot}</td></tr>`;
  });
  // column totals
  let ftds=''; let grand=0;
  dates.forEach(d=>{ const s=rows.filter(r=>r.date===d).reduce((t,r)=>t+r.blocked,0); grand+=s; ftds+=`<td>${s}</td>`; });
  h+=`<tr class="totrow"><td class="cname">Total</td><td></td>${ftds}<td>${grand}</td></tr></tbody>`;
  tbl.innerHTML=h;
}

// 21-Jul-2026 IST: reserved-slot booking-gap table (live dashboard only)
function renderReservedGaps(DATA){
  const tbl=document.getElementById('rbgtable'); if(!tbl) return;
  const rows=DATA.reserved_gaps||[];
  if(!rows.length){ tbl.innerHTML='<tr><td class="empty">No reserved-slot booking data.</td></tr>'; return; }
  let h='<thead><tr><th style="text-align:left">Date</th><th style="text-align:left">Role</th><th>Bookings</th><th>Avg gap</th></tr></thead><tbody>';
  rows.forEach(r=>{
    const gap = r.avg_gap_min==null ? '–' : (r.avg_gap_min>=60 ? (r.avg_gap_min/60).toFixed(1)+'h' : Math.round(r.avg_gap_min)+'m');
    h += `<tr><td class="cname">${fmtD(r.date)}</td><td class="crole">${r.role}</td><td>${r.bookings}</td><td>${gap}</td></tr>`;
  });
  h+='</tbody>';
  tbl.innerHTML=h;
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

initTheme();
if(LIVE){
  const btn=document.getElementById('refreshBtn'); btn.hidden=false; btn.onclick=()=>loadData(true);
  document.getElementById('stamp').textContent='Loading…';
  loadData(false);
}else{
  renderAll(EMBEDDED);
}
