# """
# Coach Availability Pipeline — fetch (API) -> calculate -> Excel, in one command.

# Modules:
#   mytatva_api.py        data-source layer (fetch_availability / fetch_consumed)
#   coach_availability.py calculation engine (build_slots / classify / summarise / write_excel)
#   pipeline.py           this orchestrator

# Setup:
#   pip install python-dotenv pandas openpyxl requests
#   # .env in this folder:  MYTATVA_TOKEN=...  /  MYTATVA_HEALTH_SECRET=...

# Run:
#   python pipeline.py                              # current month, fetch + calc
#   python pipeline.py --start 2026-05-01 --end 2026-05-31
#   python pipeline.py --step fetch                 # only pull + save the two Excels
#   python pipeline.py --step calc                  # only calculate from existing Excels

# Created 12-Jun-2026 IST.
# """
# import argparse, calendar
# from datetime import date
# import pandas as pd

# import mytatva_api as api
# import coach_availability as ca
# import dashboard
# import tzutil



# def run_data(start, end, today=None, status="P,F,N", exclude_time_slot="", exclude_coach=""):
#     """Live fetch + calculate, returning the dashboard data dict (no files written).
#     Shared by the FastAPI endpoint; the CLI (main) uses the same engine calls."""
#     statuses = {s.strip() for s in status.split(",") if s.strip()}
#     excl_dur = {int(x) for x in exclude_time_slot.split(",") if x.strip()}
#     excl_co  = [c.strip() for c in exclude_coach.split(",") if c.strip()]
#     w0, w1 = pd.Timestamp(start), pd.Timestamp(end)
#     today_ts = pd.Timestamp(today) if today else pd.Timestamp(tzutil.today_ist())
#     slots_df = api.fetch_availability()
#     consumed_df = api.fetch_consumed(start, end)
#     g, inst, open7, (n0, n1) = ca.calculate(slots_df, consumed_df, w0, w1, today_ts, statuses, excl_dur, excl_co)
#     return dashboard.build_data_from_engine(g, open7, f"{w0.date()} to {w1.date()}",
#                                             ", ".join(sorted(statuses)), n0, n1)


# def main():
#     ap = argparse.ArgumentParser()
#     _t = tzutil.today_ist()
#     _from = _t.replace(day=1).isoformat()
#     _to = _t.replace(day=calendar.monthrange(_t.year, _t.month)[1]).isoformat()
#     ap.add_argument("--start", default=_from, help="window start YYYY-MM-DD (default: 1st of this month)")
#     ap.add_argument("--end", default=_to, help="window end YYYY-MM-DD (default: last day of this month)")
#     ap.add_argument("--today", help="open-upcoming cutoff YYYY-MM-DD (default: now)")
#     ap.add_argument("--status", default="P,F,N", help="occupied statuses (default P,F,N; M & C excluded)")
#     ap.add_argument("--exclude-time-slot", default="", help="durations to drop, e.g. 60")
#     ap.add_argument("--exclude-coach", default="", help="coach name substrings to drop, comma-separated")
#     ap.add_argument("--step", choices=["fetch", "calc", "all"], default="all",
#                     help="fetch = pull+save Excels only; calc = compute from saved Excels; all = both")
#     ap.add_argument("--slots-file", default="availability.xlsx", help="intermediate slots Excel")
#     ap.add_argument("--consumed-file", default="consumed.xlsx", help="intermediate consumed Excel")
#     ap.add_argument("--out", default="coach_availability.xlsx", help="final output workbook")
#     ap.add_argument("--out-html", default="coach_availability_dashboard.html", help="dashboard HTML output")
#     ap.add_argument("--no-dashboard", action="store_true", help="skip building the dashboard")
#     a = ap.parse_args()

#     statuses = {s.strip() for s in a.status.split(",") if s.strip()}
#     excl_dur = {int(x) for x in a.exclude_time_slot.split(",") if x.strip()}
#     excl_co  = [c.strip() for c in a.exclude_coach.split(",") if c.strip()]
#     w0, w1 = pd.Timestamp(a.start), pd.Timestamp(a.end)
#     today = pd.Timestamp(a.today) if a.today else pd.Timestamp(tzutil.today_ist())
#     print(f"window: {a.start} -> {a.end} | occupied statuses: {','.join(sorted(statuses))} | step: {a.step}")

#     # ---------- FETCH ----------
#     if a.step in ("fetch", "all"):
#         print("fetching availability ...")
#         slots_df = api.fetch_availability(save=a.slots_file)
#         print("fetching consumed ...")
#         # consumed window auto-follows the analysis window so the months can't mismatch
#         consumed_df = api.fetch_consumed(a.start, a.end, save=a.consumed_file)
#         if a.step == "fetch":
#             print("fetch-only done. wrote", a.slots_file, "and", a.consumed_file)
#             return
#     else:  # calc only: read the previously saved Excels
#         slots_df = pd.read_excel(a.slots_file)
#         consumed_df = pd.read_excel(a.consumed_file)

#     # ---------- CALCULATE ----------
#     g, inst, open7, (n0, n1) = ca.calculate(slots_df, consumed_df, w0, w1, today, statuses, excl_dur, excl_co)
#     if "appointment_start_time" in consumed_df.columns:
#         cmax = pd.to_datetime(consumed_df["appointment_start_time"], errors="coerce").max()
#         if pd.notna(cmax) and cmax < n1:
#             print(f"  note: consumed data ends {cmax.date()}; open slots after that in the 7-day view may be overstated")

#     print(g[["name", "role", "total", "blocked", "booked", "avail_for_booking", "open", "open_7d"]].to_string(index=False))
#     tot = dict(total=int(g["total"].sum()), blocked=int(g["blocked"].sum()),
#                booked=int(g["booked"].sum()), avail=int(g["avail_for_booking"].sum()),
#                open=int(g["open"].sum()))
#     print("\nTOTALS:", tot)
#     print(f"open slots {n0.date()}..{n1.date()}: {len(open7)} across {open7['name'].nunique() if len(open7) else 0} coaches")

#     meta = {
#         "Source": "MyTatva API (get_availability + get_chief_healthcoach_appointment_task_details)",
#         "Window": f"{w0.date()} to {w1.date()}",
#         "Occupied statuses": ", ".join(sorted(statuses)),
#         "Excluded durations": ", ".join(map(str, sorted(excl_dur))) or "none",
#         "Excluded coaches": ", ".join(excl_co) or "none",
#         "Matching": "interval overlap (strict); touching edges excluded",
#         "Booked": "slot start = exact type-A appointment start",
#         "Blocked": "slot overlaps any consumed interval (block or off-grid/custom appt)",
#         "Available for booking": "Total - Blocked",
#         "Open": "Available for booking - Booked",
#         "Open (upcoming)": f"open slots dated {today.date()} onward",
#         "Open (next 7d)": f"open slots {n0.date()} to {n1.date()} (after today)",
#         "TOTALS": str(tot),
#     }
#     ca.write_excel(g, inst, a.out, meta, open7=open7)
#     print("saved", a.out)

#     # ---------- DASHBOARD ----------  (reads the workbook just written -> snapshot HTML)
#     if not a.no_dashboard:
#         dashboard.generate(a.out, a.out_html)
#         print("saved", a.out_html)


# if __name__ == "__main__":
#     main()



"""
Coach Availability Pipeline — fetch (API) -> calculate -> Excel, in one command.

Modules:
  mytatva_api.py        data-source layer (fetch_availability / fetch_consumed)
  coach_availability.py calculation engine (build_slots / classify / summarise / write_excel)
  pipeline.py           this orchestrator

Setup:
  pip install python-dotenv pandas openpyxl requests
  # .env in this folder:  MYTATVA_TOKEN=...  /  MYTATVA_HEALTH_SECRET=...

Run:
  python pipeline.py                              # current month, fetch + calc
  python pipeline.py --start 2026-05-01 --end 2026-05-31
  python pipeline.py --step fetch                 # only pull + save the two Excels
  python pipeline.py --step calc                  # only calculate from existing Excels

Created 12-Jun-2026 IST.
"""
import argparse, calendar, time
from datetime import date
import pandas as pd

import mytatva_api as api
import coach_availability as ca
import dashboard
import tzutil
import roles


def _apply_roles(slots_df):
    """Attach role from roles.py and keep ONLY coaches listed there.
    roles.py is the source of truth: coaches not in the map are dropped entirely
    (so KPIs, finder, capacity and the demand chart all cover the same coach set)."""
    df = slots_df.copy()
    idcol = "health_coach_id" if "health_coach_id" in df.columns else "coach_id"
    df["role"] = df[idcol].map(roles.ROLE_BY_ID)
    keep = df["role"].notna()
    kept, dropped = df.loc[keep, idcol].nunique(), df.loc[~keep, idcol].nunique()
    print(f"  roles.py: kept {kept} mapped coaches, dropped {dropped} unmapped")
    return df[keep].copy()


def run_data(start, end, today=None, status="P,F,N", exclude_time_slot="", exclude_coach=""):
    """Live fetch + calculate, returning the dashboard data dict (no files written).
    Shared by the FastAPI endpoint; the CLI (main) uses the same engine calls."""
    statuses = {s.strip() for s in status.split(",") if s.strip()}
    excl_dur = {int(x) for x in exclude_time_slot.split(",") if x.strip()}
    excl_co  = [c.strip() for c in exclude_coach.split(",") if c.strip()]
    w0, w1 = pd.Timestamp(start), pd.Timestamp(end)
    today_ts = pd.Timestamp(today) if today else pd.Timestamp(tzutil.today_ist())

    # --- timing only: shows where the refresh spends its time (prints to server log) ---
    _t_total = time.perf_counter()
    def _lap(label, t0):
        print(f"  [timing] {label}: {time.perf_counter() - t0:.2f}s", flush=True)
        return time.perf_counter()

    _t = time.perf_counter()
    slots_df = api.fetch_availability()
    _t = _lap("fetch_availability", _t)
    slots_df = _apply_roles(slots_df)
    _t = _lap("apply_roles", _t)
    consumed_df = api.fetch_consumed(start, end)
    _t = _lap("fetch_consumed", _t)
    g, inst, open7, (n0, n1) = ca.calculate(slots_df, consumed_df, w0, w1, today_ts, statuses, excl_dur, excl_co)
    _t = _lap("calculate", _t)
    data = dashboard.build_data_from_engine(g, open7, f"{w0.date()} to {w1.date()}",
                                            ", ".join(sorted(statuses)), n0, n1)
    _lap("build_data", _t)
    print(f"  [timing] TOTAL run_data: {time.perf_counter() - _t_total:.2f}s", flush=True)
    return data


def main():
    ap = argparse.ArgumentParser()
    _t = tzutil.today_ist()
    _from = _t.replace(day=1).isoformat()
    _to = _t.replace(day=calendar.monthrange(_t.year, _t.month)[1]).isoformat()
    ap.add_argument("--start", default=_from, help="window start YYYY-MM-DD (default: 1st of this month)")
    ap.add_argument("--end", default=_to, help="window end YYYY-MM-DD (default: last day of this month)")
    ap.add_argument("--today", help="open-upcoming cutoff YYYY-MM-DD (default: now)")
    ap.add_argument("--status", default="P,F,N", help="occupied statuses (default P,F,N; M & C excluded)")
    ap.add_argument("--exclude-time-slot", default="", help="durations to drop, e.g. 60")
    ap.add_argument("--exclude-coach", default="", help="coach name substrings to drop, comma-separated")
    ap.add_argument("--step", choices=["fetch", "calc", "all"], default="all",
                    help="fetch = pull+save Excels only; calc = compute from saved Excels; all = both")
    ap.add_argument("--slots-file", default="availability.xlsx", help="intermediate slots Excel")
    ap.add_argument("--consumed-file", default="consumed.xlsx", help="intermediate consumed Excel")
    ap.add_argument("--out", default="coach_availability.xlsx", help="final output workbook")
    ap.add_argument("--out-html", default="coach_availability_dashboard.html", help="dashboard HTML output")
    ap.add_argument("--no-dashboard", action="store_true", help="skip building the dashboard")
    a = ap.parse_args()

    statuses = {s.strip() for s in a.status.split(",") if s.strip()}
    excl_dur = {int(x) for x in a.exclude_time_slot.split(",") if x.strip()}
    excl_co  = [c.strip() for c in a.exclude_coach.split(",") if c.strip()]
    w0, w1 = pd.Timestamp(a.start), pd.Timestamp(a.end)
    today = pd.Timestamp(a.today) if a.today else pd.Timestamp(tzutil.today_ist())
    print(f"window: {a.start} -> {a.end} | occupied statuses: {','.join(sorted(statuses))} | step: {a.step}")

    # ---------- FETCH ----------
    if a.step in ("fetch", "all"):
        print("fetching availability ...")
        slots_df = api.fetch_availability(save=a.slots_file)
        print("fetching consumed ...")
        # consumed window auto-follows the analysis window so the months can't mismatch
        consumed_df = api.fetch_consumed(a.start, a.end, save=a.consumed_file)
        if a.step == "fetch":
            print("fetch-only done. wrote", a.slots_file, "and", a.consumed_file)
            return
    else:  # calc only: read the previously saved Excels
        slots_df = pd.read_excel(a.slots_file)
        consumed_df = pd.read_excel(a.consumed_file)

    # ---------- CALCULATE ----------
    slots_df = _apply_roles(slots_df)
    g, inst, open7, (n0, n1) = ca.calculate(slots_df, consumed_df, w0, w1, today, statuses, excl_dur, excl_co)
    if "appointment_start_time" in consumed_df.columns:
        cmax = pd.to_datetime(consumed_df["appointment_start_time"], errors="coerce").max()
        if pd.notna(cmax) and cmax < n1:
            print(f"  note: consumed data ends {cmax.date()}; open slots after that in the 7-day view may be overstated")

    print(g[["name", "role", "total", "blocked", "booked", "avail_for_booking", "open", "open_7d"]].to_string(index=False))
    tot = dict(total=int(g["total"].sum()), blocked=int(g["blocked"].sum()),
               booked=int(g["booked"].sum()), avail=int(g["avail_for_booking"].sum()),
               open=int(g["open"].sum()))
    print("\nTOTALS:", tot)
    print(f"open slots {n0.date()}..{n1.date()}: {len(open7)} across {open7['name'].nunique() if len(open7) else 0} coaches")

    meta = {
        "Source": "MyTatva API (get_availability + get_chief_healthcoach_appointment_task_details)",
        "Window": f"{w0.date()} to {w1.date()}",
        "Occupied statuses": ", ".join(sorted(statuses)),
        "Excluded durations": ", ".join(map(str, sorted(excl_dur))) or "none",
        "Excluded coaches": ", ".join(excl_co) or "none",
        "Matching": "interval overlap (strict); touching edges excluded",
        "Booked": "slot start = exact type-A appointment start",
        "Blocked": "slot overlaps any consumed interval (block or off-grid/custom appt)",
        "Available for booking": "Total - Blocked",
        "Open": "Available for booking - Booked",
        "Open (upcoming)": f"open slots dated {today.date()} onward",
        "Open (next 7d)": f"open slots {n0.date()} to {n1.date()} (after today)",
        "TOTALS": str(tot),
    }
    ca.write_excel(g, inst, a.out, meta, open7=open7)
    print("saved", a.out)

    # ---------- DASHBOARD ----------  (reads the workbook just written -> snapshot HTML)
    if not a.no_dashboard:
        dashboard.generate(a.out, a.out_html)
        print("saved", a.out_html)


if __name__ == "__main__":
    main()