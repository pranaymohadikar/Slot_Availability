"""
MyTatva data-source layer.
Fetches coach availability (slots) and consumed (appointments + blocks) from the
API and returns pandas DataFrames. No calculation logic lives here.

Credentials come from .env in the working directory:
    MYTATVA_TOKEN=...
    MYTATVA_HEALTH_SECRET=...

Created 12-Jun-2026 IST.
"""
import os, json, ast
import requests
import pandas as pd
from dotenv import load_dotenv      # pip install python-dotenv

load_dotenv()

#BASE = "https://api.mytatva.in/api/v8/healthcoach"
#BASE = "https://089b-202-83-17-158.ngrok-free.app/api/v8/healthcoach"
BASE = os.getenv("MYTATVA_BASE_URL")
AVAIL_URL = f"{BASE}/availability/get_availability"
DETAILS_URL = f"{BASE}/availability/get_chief_healthcoach_appointment_task_details"


# def _headers():
#     missing = [v for v in ("MYTATVA_TOKEN", "MYTATVA_HEALTH_SECRET") if not os.environ.get(v)]
#     if missing:
#         raise SystemExit(f"Missing in .env / environment: {', '.join(missing)}")
#     return {
#         "token": os.environ["MYTATVA_TOKEN"],
#         "health_secret": os.environ["MYTATVA_HEALTH_SECRET"],
#         "content-type": "text/plain",          # API expects text/plain; no origin/referer (they break auth)
#     }

def _headers(with_token=False):                       # 18-Jun-2026 IST: token now optional
    required = ["MYTATVA_HEALTH_SECRET"] + ["SLOT_SECRET_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing in .env / environment: {', '.join(missing)}")
    h = {"slot_availability_secret": os.environ["SLOT_SECRET_KEY"], "content-type": "application/json"}
    # if with_token:
    #     h["token"] = os.environ["MYTATVA_TOKEN"]
    return h

def _post(url, payload, with_token=False):            # 18-Jun-2026 IST
    r = requests.post(url, data=json.dumps(payload, separators=(",", ":")),
                      headers=_headers(with_token), timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code} at {url}: {r.text[:300]}")
    try:
        return r.json()
    except Exception:
        raise SystemExit("Response not JSON (encrypted?). First 300 chars:\n" + r.text[:300])

#New helper _chief_ids() — reads CHIEF_HEALTH_COACH_ID from .env
def _chief_ids():                                     # 18-Jun-2026 IST
    raw = os.environ.get("CHIEF_HEALTH_COACH_ID", "").strip()
    if not raw:
        raise SystemExit("CHIEF_HEALTH_COACH_ID missing in .env (e.g. ['123','456'])")
    try:
        ids = [str(x).strip() for x in ast.literal_eval(raw) if str(x).strip()]
    except Exception:
        raise SystemExit(f"CHIEF_HEALTH_COACH_ID not a valid list: {raw}")
    if not ids:
        raise SystemExit("CHIEF_HEALTH_COACH_ID is empty")
    return ids

def _find_records(payload):
    """Largest list-of-dicts anywhere in the response = the record array."""
    best = []
    def walk(o):
        nonlocal best
        if isinstance(o, list):
            if o and isinstance(o[0], dict) and len(o) > len(best):
                best = o
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(payload)
    return best


# def fetch_availability(per_page=200, hc_id="All", save=None): #need to change pagination -->
#     """Return all coach slot rules as a DataFrame (paginated)."""
#     rows, page = [], 1
#     while True:
#         data = _post(AVAIL_URL, {"page": str(page), "per_page": str(per_page), "health_coach_id": hc_id})
#         recs = _find_records(data)
#         print(f"  availability page {page}: {len(recs)} rows")
#         if not recs:
#             break
#         rows.extend(recs)
#         if len(recs) < per_page:
#             break
#         page += 1
#     df = pd.json_normalize(rows)
#     if save:
#         df.to_excel(save, index=False)
#         print("  saved ->", save)
#     return df


 #loop chief IDs, no token, dedupe, safety cap
def fetch_availability(per_page=200, chief_ids=None, save=None, max_pages=50):  # 18-Jun-2026 IST
    """Coach slot rules as a DataFrame. Auth = health_secret only (no token);
    loops over chief IDs from .env, each passed as health_coach_id; concat + dedupe."""
    if chief_ids is None:
        chief_ids = _chief_ids()
    rows = []
    for cid in chief_ids:
        page = 1
        while True:
            data = _post(AVAIL_URL,
                         {"page": str(page), "per_page": str(per_page), "health_coach_id": "All", "chief_health_coach_id": cid} ,
                         with_token=False)                   # <-- no token on availability
            recs = _find_records(data)
            print(f"  availability chief {cid} page {page}: {len(recs)} rows")
            if not recs:
                break
            rows.extend(recs)
            if len(recs) < per_page or page >= max_pages:     # <-- safety cap added
                break
            page += 1
    df = pd.json_normalize(rows)
    # 18-Jun-2026 IST: some columns return lists (unhashable) -> dedupe on a string view, keep original rows
    df = df.loc[df.astype(str).drop_duplicates().index].reset_index(drop=True)
    print(f"  availability total (deduped): {len(df)} rows from {len(chief_ids)} chief id(s)")
    if save:
        df.to_excel(save, index=False); print("  saved ->", save)
    return df


# def fetch_consumed(from_date, to_date, chief=None, details_type="A", save=None):
#     """Return consumed slots (appointments + blocks) as a DataFrame.
#     chief=None sends chief_health_coach_id: null (all coaches in one call).
#     details_type 'A' returns appointments AND blocks (distinguished by the
#     response's type / block_whole_day columns); 'B' is rejected by the API."""
#     data = _post(DETAILS_URL, {"details_type": details_type, "chief_health_coach_id": chief,
#                                "from_date": from_date, "to_date": to_date, "health_coach_id": cid},with_token=False)
#     if isinstance(data, dict) and str(data.get("code")) == "0":
#         raise SystemExit(f"Consumed fetch error: {data.get('message')}")
#     recs = _find_records(data)
#     print(f"  consumed {from_date}..{to_date}: {len(recs)} rows")
#     df = pd.json_normalize(recs)
#     if save:
#         df.to_excel(save, index=False)
#         print("  saved ->", save)
#     return df

def fetch_consumed(from_date, to_date, chief_ids=None, details_type="A", save=None):  # 18-Jun-2026 IST
    """Consumed slots (appointments + blocks) as a DataFrame.
    Loops over chief IDs from .env (same scoping pattern as availability),
    concatenating + de-duplicating across chiefs."""
    if chief_ids is None:
        chief_ids = _chief_ids()
    rows = []
    for cid in chief_ids:
        payload = {"details_type": details_type, 
                   "health_coach_id": cid, "from_date": from_date, "to_date": to_date}
        data = _post(DETAILS_URL, payload, with_token=False)
        if isinstance(data, dict) and str(data.get("code")) == "0":
            raise SystemExit(f"Consumed fetch error (chief {cid}): {data.get('message')}")
        recs = _find_records(data)
        print(f"  consumed chief {cid} {from_date}..{to_date}: {len(recs)} rows")
        rows.extend(recs)
    df = pd.json_normalize(rows)
    if len(df):
        df = df.loc[df.astype(str).drop_duplicates().index].reset_index(drop=True)  # list-safe dedupe
    print(f"  consumed total (deduped): {len(df)} rows from {len(chief_ids)} chief id(s)")
    if not len(df):
        raise SystemExit("Consumed returned 0 rows across all chiefs — check date range / response shape.")
    if save:
        df.to_excel(save, index=False); print("  saved ->", save)
    return df