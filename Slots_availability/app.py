"""
Coach Availability — web app (FastAPI).

Serves the live dashboard and a data endpoint the Refresh button calls.
The endpoint re-runs the pipeline (fetch -> calculate) and returns the data dict.

Created 18-Jun-2026 IST.

Run locally:
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000
    # open http://localhost:8000
    # (needs .env with SLOT_SECRET_KEY and CHIEF_HEALTH_COACH_ID, and the API reachable)

Notes:
  - A short in-memory cache (CACHE_TTL) means a normal page load reuses a recent
    result; the Refresh button forces a fresh run (refresh=1).
  - No auth yet — add before exposing on the public internet (see deploy notes).
"""
import time, calendar
from datetime import date

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import pipeline
import dashboard
import tzutil

app = FastAPI(title="Coach Availability")

CACHE_TTL = 120  # seconds; Refresh bypasses this
_cache = {"data": None, "ts": 0.0}


def _current_window():
    t = tzutil.today_ist()
    start = t.replace(day=1).isoformat()
    end = t.replace(day=calendar.monthrange(t.year, t.month)[1]).isoformat()
    return start, end


def _get_data(force=False):
    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["ts"] < CACHE_TTL):
        return _cache["data"], True
    start, end = _current_window()
    data = pipeline.run_data(start, end)
    _cache["data"], _cache["ts"] = data, now
    return data, False


@app.get("/", response_class=HTMLResponse)
def index():
    # serve the shell immediately; the page fetches /api/data and shows a spinner
    return dashboard.render_html(None, live=True)


@app.get("/api/data")
def api_data(refresh: int = 0):
    try:
        data, cached = _get_data(force=bool(refresh))
        return JSONResponse({"data": data, "cached": cached})
    except SystemExit as e:           # the fetchers raise SystemExit on API/credential errors
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/healthz")
def healthz():
    return {"ok": True}