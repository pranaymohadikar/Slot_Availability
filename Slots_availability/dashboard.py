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

Changes:
  19-Jun-2026 IST  Amber "Reserved" badge in the finder (static path detects the "(R)" marker in
                   the open-slots sheet; live path reads open7.reserved).
  10-Jul-2026 IST  Role support. `role` attached to each coach and each open slot in BOTH paths
                   (static: coach->role lookup from the summary sheet's Role column; live: from
                   the engine frames). "Demand at a glance" rebuilt as a GROUPED (clustered) bar
                   chart: x-axis = the 7 days, one bar per role within each day, count above every
                   bar, legend below. barLabels now labels each individual bar (was the stack
                   total). Colours: Nutritionist green / Physiotherapist blue / Psychologist
                   purple / Other grey. Only roles with slots are drawn.
  10-Jul-2026 IST  Finder filters: Role dropdown (selecting a role also narrows the Coach
                   dropdown to that role's coaches) and a 3-way Reserved dropdown
                   (All slots / Reserved only / Regular only). All filters AND together.
  10-Jul-2026 IST  New collapsed "Blocked slots · next 7 days" section: coach x day table of
                   blocked/total, red heatmap tint scaled to the block count, whole-day blocks
                   marked "Full day", row/column/grand totals. A "-" cell means no slots scheduled
                   that day (distinct from "0/9" = working, nothing blocked). Static path reads the
                   "Blocked (next 7d)" sheet; live path reads blk7. _assemble() carries `blocked`.

Run (static):
    python dashboard.py                       # coach_availability.xlsx -> coach_availability_dashboard.html
    python dashboard.py in.xlsx out.html
"""
import sys, json, re, os
from datetime import datetime
import jinja2
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


# ----------------------------------------------------------------------------- shared record shapes
# 31-Jul-2026 IST: build_data() (Excel) and build_data_from_engine() (live) used to each hand-write
# these three dict shapes independently. Factored out so a new field is added once, not twice --
# reserved_gaps already drifted this way once (engine-only; static path silently lacked it).
def _coach_record(name, role, total, blocked, booked, next_open, last_open):
    return {"name": name, "role": role or "Other", "total": total, "blocked": blocked,
            "booked": booked, "avail": total - blocked, "open": total - blocked - booked,
            "next_open": _fmt_dt(next_open), "last_open": _fmt_dt(last_open)}


def _open_slot_record(coach, date_str, day, start, end, reserved, role):
    return {"coach": coach, "date": date_str, "day": day, "start": start, "end": end,
            "reserved": bool(reserved), "role": role or "Other"}


def _blocked_record(coach, role, date_str, blocked, total, whole_day):
    return {"coach": coach, "role": role or "Other", "date": date_str,
            "blocked": blocked, "total": total, "whole_day": bool(whole_day)}


def _assemble(coaches, open_slots, window, statuses, n0=None, n1=None, blocked=None, reserved_gaps=None):
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
        "blocked": blocked or [],
        "reserved_gaps": reserved_gaps or [],   # 21-Jul-2026 IST: reserved-slot booking-gap table (live dashboard only)
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
        coaches.append(_coach_record(str(r["Coach"]).strip(), str(r.get("Role","")).strip(),
                                      total, blocked, booked, r.get("Next Open"), r.get("Last Open")))
    role_by_coach = {c["name"]: c["role"] for c in coaches}

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
                        open_slots.append(_open_slot_record(rec["coach"], rec["date"], rec["day"],
                                                             rec["start"], rec["end"], rec["reserved"],
                                                             role_by_coach.get(coach, "Other")))
    except Exception:
        pass

    blocked = []
    try:
        b = pd.read_excel(xlsx, sheet_name="Blocked (next 7d)")
        datecols = [c for c in b.columns if c not in ("Coach", "Role")]
        for _, r in b.iterrows():
            coach = str(r["Coach"]).strip()
            for c in datecols:
                cell = str(r[c]).strip()
                if not cell or cell.lower() == "nan":
                    continue
                wd = cell.startswith("Full day")
                m = re.search(r"(\d+)\s*/\s*(\d+)", cell)
                if not m:
                    continue
                dm = re.match(r"(\d{1,2})-([A-Za-z]{3})", str(c))
                if not dm:
                    continue
                dt = datetime.strptime(f"{dm.group(1)}-{dm.group(2)}-{year}", "%d-%b-%Y")
                blocked.append(_blocked_record(coach, str(r.get("Role","")).strip(), dt.strftime("%Y-%m-%d"),
                                                int(m.group(1)), int(m.group(2)), wd))
    except Exception:
        pass
    return _assemble(coaches, open_slots, window, statuses, blocked=blocked)


# ----------------------------------------------------------------------------- live path
def build_data_from_engine(g, open7, window="", statuses="", n0=None, n1=None, blk7=None, rbg=None):
    """Build the same dict directly from engine outputs (no Excel). Used by the live endpoint."""
    coaches = []
    for _, r in g.iterrows():
        coaches.append(_coach_record(str(r["name"]).strip(), str(r.get("role","")).strip(),
                                      int(r["total"]), int(r["blocked"]), int(r["booked"]),
                                      r.get("next_open"), r.get("last_open")))
    open_slots = []
    op = open7.copy()
    if len(op):
        op["date"] = pd.to_datetime(op["date"])
        for _, r in op.iterrows():
            open_slots.append(_open_slot_record(str(r["name"]).strip(), r["date"].strftime("%Y-%m-%d"),
                                                 r["date"].strftime("%a"), r["start"], r["end"],
                                                 r.get("reserved", False), str(r.get("role","")).strip()))
    blocked = []
    if blk7 is not None and len(blk7):
        b = blk7.copy()
        b["date"] = pd.to_datetime(b["date"])
        for _, r in b.iterrows():
            blocked.append(_blocked_record(str(r["name"]).strip(), str(r.get("role","")).strip(),
                                            r["date"].strftime("%Y-%m-%d"), int(r["blocked"]),
                                            int(r["total"]), r["whole_day"]))
    # 21-Jul-2026 IST: reserved-slot booking-gap table (live dashboard only; static/CLI path not wired yet)
    reserved_gaps = []
    if rbg is not None and len(rbg):
        for _, r in rbg.iterrows():
            reserved_gaps.append({"date": str(r["date"]), "role": str(r.get("role","")).strip() or "Other",
                                  "bookings": int(r["bookings"]),
                                  "avg_gap_min": None if pd.isna(r["avg_gap_min"]) else round(float(r["avg_gap_min"]), 1)})
    return _assemble(coaches, open_slots, window, statuses, n0, n1, blocked, reserved_gaps=reserved_gaps)


_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_JINJA_ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(_TEMPLATES_DIR), autoescape=False,
                                 keep_trailing_newline=True)   # match the old string-template's exact whitespace
# 31-Jul-2026 IST: TEMPLATE used to be a ~320-line Python string with __DATA__/__LIVE__
# placeholders swapped via str.replace(). Now templates/index.html.j2 + dashboard.css +
# dashboard.js, rendered through Jinja2 -- same output, real syntax highlighting/tooling on
# the CSS and JS. dashboard.js keeps the same two injection points, now as {{ data_json }}/
# {{ live_js }} instead of __DATA__/__LIVE__.


def render_html(data, live=False):
    css = open(os.path.join(_TEMPLATES_DIR, "dashboard.css"), encoding="utf-8").read()
    js = _JINJA_ENV.get_template("dashboard.js").render(
        data_json=json.dumps(data), live_js="true" if live else "false")
    return _JINJA_ENV.get_template("index.html.j2").render(css=css, js=js)


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