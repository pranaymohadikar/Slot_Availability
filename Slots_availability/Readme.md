# Coach Slot Availability

Computes and visualises per-coach slot availability for the MyTatva health-coach team:
**Total / Blocked / Booked / Available / Open** slots, plus an operational "find me an open
slot in the next 7 days" view.

Ships as two things off the same engine:

- an **Excel workbook** (`coach_availability.xlsx`) — 5 sheets, for audit and offline use
- an **HTML dashboard** (`coach_availability_dashboard.html`) — static snapshot, or a live
  FastAPI app with a Refresh button (deployed on Vercel)

All dates/times are **IST (Asia/Kolkata)**.

---

## Table of contents

1. [The model](#the-model)
2. [Architecture](#architecture)
3. [Data flow](#data-flow)
4. [Modules](#modules)
5. [Key concepts](#key-concepts)
6. [Outputs](#outputs)
7. [Running it](#running-it)
8. [Deployment (Vercel)](#deployment-vercel)
9. [Known issues](#known-issues)

---

## The model

Two inputs, one slot grid.

**Availability rules** (from the availability API) describe *when a coach works*: one row per
rule, e.g. `mon,wed,fri 09:00–13:00, 30-min slots, 2026-06-01..2026-06-30`. Rules are
**chopped** into individual slots, one per (coach, date, start-time).

**Consumed** (from the consumed API) describes *what is taken*: appointments and blocks, one
row each, as time intervals.

Each slot is then classified into exactly one bucket:

```
Booked   slot start exactly equals a type-A (P/F/N) appointment start
Blocked  any other overlap (type-B block, whole-day block, or off-grid/custom appointment)
Open     no overlap
```

Priority is **Booked > Blocked > Open** — a slot can't be two things.

```
Available for booking = Total  - Blocked
Open                  = Available - Booked
```

Overlap is **strict interval overlap**: slot `[s,e]` is consumed by `[bs,be]` iff
`s < be AND e > bs`. Touching edges do **not** overlap — a booking ending at 10:00 does not
consume the 10:00–10:30 slot.

---

## Architecture

```
                    ┌──────────────────┐
                    │   MyTatva API    │
                    │  availability    │
                    │  consumed        │
                    └────────┬─────────┘
                             │  (per chief_health_coach_id, paginated)
                    ┌────────▼─────────┐
                    │  mytatva_api.py  │  data-source layer
                    └────────┬─────────┘
                             │  raw DataFrames
                    ┌────────▼─────────┐
                    │    roles.py      │  coach_id → role
                    │  SOURCE OF TRUTH │  unmapped coaches are DROPPED
                    └────────┬─────────┘
                             │
                    ┌────────▼──────────────┐
                    │ coach_availability.py │  engine
                    │  build_slots          │  rules → slot grid
                    │  load_consumed        │  bookings + blocks → intervals
                    │  classify             │  Booked / Blocked / Open
                    │  summarise            │  per-coach monthly totals
                    │  window_slots         │  the next-7-day grid
                    │  blocked_grid         │  coach × day blocked counts
                    │  write_excel          │  5-sheet workbook
                    └────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │   pipeline.py    │  orchestrator (fetch → roles → calc → outputs)
                    └───┬──────────┬───┘
                        │          │
          ┌─────────────▼───┐  ┌───▼──────────────┐
          │ dashboard.py    │  │ coach_avail.xlsx │
          │  render_html    │  └──────────────────┘
          └───┬─────────┬───┘
              │         │
   ┌──────────▼──┐   ┌──▼──────────────┐
   │ static .html│   │ app.py (FastAPI)│  live, Refresh button
   └─────────────┘   └─────────────────┘
```

**Design principles**

- **One engine, two render paths.** `dashboard.py` builds an identical data dict either from
  the Excel workbook (`build_data`) or straight from the engine's in-memory frames
  (`build_data_from_engine`). The live app never round-trips through Excel — important because
  Vercel's filesystem is read-only. Both paths feed the same three record-shape helpers
  (`_coach_record`, `_open_slot_record`, `_blocked_record`) so a new field is defined once, not
  twice (31-Jul-2026: previously each path hand-built these dicts independently).
- **Single-file HTML, templated.** The page is still one self-contained file at request time —
  Chart.js from CDN, no build step, no separate assets served — but the *source* now lives in
  `templates/index.html.j2` + `dashboard.css` + `dashboard.js`, rendered via Jinja2 (31-Jul-2026;
  was a ~320-line Python string with manual `str.replace()` substitution).
- **Client-side aggregation.** The API serves raw open slots; the browser groups and filters
  them. Avoids over-engineering the backend.
- **Theme-aware.** Light/dark follows the OS (`prefers-color-scheme`), with a manual toggle
  button that overrides it via `localStorage` + a `data-theme` attribute. All colors are CSS
  custom properties — Chart.js canvases read the same tokens via `getComputedStyle` so charts
  stay in sync with the toggle instead of being hardcoded separately.

---

## Data flow

1. **Fetch** — `mytatva_api.py` loops over every `chief_health_coach_id` (from env, a JSON list)
   and paginates each endpoint, concatenating and de-duplicating the results.
2. **Roles** — `pipeline._apply_roles()` maps `health_coach_id → role` via `roles.py` and
   **drops every coach not in the map**. This scopes the whole dashboard consistently: KPI,
   finder, capacity, charts all cover the same coach set.
3. **Calculate** — the engine builds the month slot grid, classifies it, and summarises per
   coach. Separately it builds the **next-7-day window** (`today … today+6`) and derives both
   the open-slot list and the blocked grid from that one classified frame.
4. **Elapsed trim** — on a live refresh, slots on *today's* date whose start time has already
   passed are dropped from the **open-slot finder** (a 16:00 refresh hides today's 15:30 slot):
   you can't book a slot that has passed. The **blocked grid is not trimmed** — it counts the
   full day, so blocked figures don't shrink through the day and stay consistent with capacity.
   Future days are untouched. Backfills (`--today` in the past) are not trimmed.
5. **Render** — Excel workbook and/or HTML dashboard.

---

## Modules

| File | Role |
|---|---|
| `mytatva_api.py` | Data source. `fetch_availability()` / `fetch_consumed(start, end)`. Auth via `slot_availability_secret` header. Fetches all chief IDs **concurrently** (thread pool, shared `requests.Session`) and de-dupes (31-Jul-2026: was sequential, no session reuse). |
| `roles.py` | `coach_id → role` dict. **Source of truth** for which coaches appear anywhere. Keyed on UUID, never name. |
| `coach_availability.py` | The engine. Pure functions over DataFrames — no I/O except `write_excel`. |
| `pipeline.py` | Orchestrator. `run_data()` (live, in-memory) and `main()` (CLI, writes files). Owns role application and stage timing. |
| `dashboard.py` | Builds the data dict (two paths, shared record helpers) and renders `templates/index.html.j2` via Jinja2. |
| `templates/` | `index.html.j2` (page skeleton), `dashboard.css`, `dashboard.js` — the dashboard's actual markup/styles/logic (31-Jul-2026: extracted out of a Python string). |
| `constants.py` | Shared constants (currently `DEFAULT_STATUSES`) so business defaults like occupied-status codes live in one place, not copy-pasted into every argparse default. |
| `app.py` | FastAPI. `GET /` (shell), `GET /api/data?refresh=1` (re-runs the pipeline), `GET /healthz`. Short in-memory cache. |
| `tzutil.py` | IST helper. Fixed +5:30 offset (India has no DST), so a Windows laptop and a UTC Vercel box agree. Always use `now_ist()` / `today_ist()`. |

### Engine functions worth knowing

- `chop(start, end, step)` — cuts a rule window into slots. Only emits a slot that fits
  entirely inside the window (31-Jul-2026 fix — previously a trailing slot could run past
  `end_time` when the window length wasn't a multiple of `step`; see Known issues history).
- `build_slots(...)` — expands rules across dates/weekdays, clips to the window, de-dupes
  `(coach, date, slot_start)`, and flags `reserved` (see [Reserved slots](#key-concepts) —
  this is now a computed rule, not read from the API).
- `load_consumed(...)` — splits consumed into exact appointment starts, interval list, and
  whole-day blocks.
- `classify(...)` — applies the Booked > Blocked > Open priority. Vectorised (31-Jul-2026):
  one set-membership check for Booked, one `groupby(coach,date)` + numpy overlap pass for
  Blocked — was a Python function called once per slot via `.apply()`.
- `window_slots(...)` — builds + classifies the 7-day window **once**;
  `open_from_window()` and `blocked_grid()` both read from it.
- `calculate(...)` → `(g, inst, open7, (n0, n1), blk7)`.

---

## Key concepts

### `roles.py` is the source of truth

Coaches not listed there are **dropped entirely**, not bucketed as "Other". Every run prints
`roles.py: kept N mapped coaches, dropped M unmapped`.

Keyed on `health_coach_id` (UUID) because **the same person can have more than one coach_id**.
Vandna Lalchandani and Sridurga R both do. A name-keyed map would collide, and worse, could
silently point at a dead account (see [Known issues](#known-issues)).

### Reserved slots

**Changed 31-Jul-2026 — this is now a computed rule, not read from the API.** Reservation used
to come from each rule's `reserved_slot_config.week1..week4` field (API-supplied time windows
per week-of-month). That calculation is still in `build_slots()`, **commented out, not
deleted**, in case this needs reverting.

The current rule: for each `(coach, date)`, take that day's slots in chronological order and
reserve the **last 2** of them — except in **week 4 of the month** (days 22+), where it's the
**last 3**. Week-of-month uses the same bucketing as before (days 1–7 → w1, 8–14 → w2, 15–21 →
w3, 22+ → w4), computed from each slot's *own* date — so a 7-day finder window that spills into
the next month buckets correctly on its own (1-Aug is week1 of August, not an extension of
July's week4). A day with fewer than 2 (or 3) slots reserves whatever's there.

Reserved slots still count as **Open** — they get an amber badge, not a separate bucket. This
was true before and remains true: reservation never affects `classify()`, never affects any
total, and never blocks a booking — it's purely a display flag read by the dashboard badge, the
Reserved/Regular filter, the audit sheet's `Reserved` column, and `reserved_booking_gaps()`.

### Whole-day blocks

A whole-day block marks every slot that day as Blocked. In the blocked grid these are shown as
**"Full day"** rather than a raw number, so a coach who's simply off doesn't visually dwarf a
coach with 3 real blocks.

Note a `13/13` cell that is *not* "Full day" means every slot happened to be blocked
individually — a genuinely different situation.

### The two "Open" numbers

They are not the same and are easy to conflate:

- **Capacity → Open** = open slots across the **whole analysis month**. Untrimmed.
- **Finder → Open** = open slots in the **next 7 days**, elapsed slots trimmed.

Likewise the blocked grid counts the **full day**, so today's grid `total` will exceed the number
of slots the finder still shows for today. That is intended: the grid reports the day, the finder
reports what is still bookable.

---

## Outputs

### `coach_availability.xlsx`

| Sheet | Contents |
|---|---|
| Coach Availability | Per-coach summary. `Available` and `Open` are **live Excel formulas** (`=C-D`, `=G-F`), which pandas reads back as blank — the dashboard recomputes them from Total/Blocked/Booked. |
| Slot Detail (audit) | One row per slot: coach, role, date, times, status, Reserved. |
| Open Slots (next 7d) | Wide: one row per coach, one column per open slot, cell = `DD-Mon HH:MM-HH:MM`, `(R)` suffix if reserved. |
| Blocked (next 7d) | Coach × day, cell = `blocked/total`, or `Full day (n/n)`. |
| Method & Notes | Window, occupied statuses, matching rules, exclusions. |

### `coach_availability_dashboard.html`

Operational-first, in reading order. Light/dark theme follows the OS by default, with a
toggle button (☾/☀) next to Refresh; accent color is `#703b96` (purple) in light mode,
`#c084fc` in dark.

1. **KPI row** — Total Open slots (next 7 days), plus one "Next up" tile per coaching role
   (Nutritionist / Physiotherapist / Psychologist — "Other" excluded on purpose) showing that
   role's soonest 2 open slots, coach + date/time (31-Jul-2026: was a single tile).
2. **Find an open slot** — the hero. Filters: Role · Coach · Day · Reserved
   (All / Reserved only / Regular only) · free-text search. Picking a role narrows the coach
   list. Reserved slots carry an amber badge.
3. **Demand at a glance** — grouped bar chart: x-axis = the 7 days, one bar per role within each
   day, count above every bar.
4. **Capacity & utilisation** (collapsed) — per-coach stacked Open/Booked/Blocked, and
   utilisation ranking `(Booked + Blocked) / Total`.
5. **Blocked slots · next 7 days** (collapsed) — coach × day grid, `blocked/total`, red heatmap
   tint, "Full day" markers, row/column/grand totals. Counts the **full day**, including today's
   already-elapsed slots, so the numbers are stable across refreshes and reconcile with capacity.
   A `–` cell means no slots scheduled that day (≠ `0/9`, which means working with nothing blocked).

---

## Running it

### Setup

```bash
pip install -r requirements.txt
```

`.env` in the project folder:

```
SLOT_SECRET_KEY=...
CHIEF_HEALTH_COACH_ID='["id1","id2","id3"]'    # single-quote: avoids $ interpolation
MYTATVA_BASE_URL=https://<host>/api/v8/healthcoach
MYTATVA_HEALTH_SECRET=...
```

### CLI

```bash
python pipeline.py                                   # current IST month, fetch + calc
python pipeline.py --start 2026-06-01 --end 2026-06-30
python pipeline.py --step fetch                      # only pull + save the two Excels
python pipeline.py --step calc                       # only calculate from existing Excels
python pipeline.py --step calc --today 2026-06-12 --now "2026-06-12 16:00"   # simulate a refresh time
```

The analysis window defaults to the **current IST month** and follows the calendar
automatically. `--now` exists to test the elapsed-slot trim against historical data; live runs
use the real IST clock.

### Live app

```bash
uvicorn app:app --reload --port 8000
# http://localhost:8000
```

`GET /api/data?refresh=1` forces a fresh fetch + calculate (~4–11s depending on cold/warm).

---

## Deployment (Vercel)

Vercel auto-detects a FastAPI instance named `app` at a supported entrypoint (`app.py`). **No
`pyproject.toml` entrypoint block is needed** — and having both a Root Directory *and* an
entrypoint config will conflict and 404.

`vercel.json` in the repo root pins the function region to `bom1` (Mumbai) — `MYTATVA_BASE_URL`
is India-hosted, so this cuts per-call latency for the 6 fetch calls (3 chief IDs × 2 endpoints,
now concurrent — see Refresh performance below). It contains only `{"regions": ["bom1"]}`, no
`builds`/`functions` entrypoint config, so it does not conflict with the Root Directory
auto-detection above.

1. If `app.py` is not at the repo root, set **Settings → Build and Deployment → Root Directory**
   to the exact folder name. It's **case-sensitive** on Linux — copy it from GitHub, don't retype.
2. `requirements.txt` must sit next to `app.py`.
3. Set env vars in **Settings → Environment Variables**: `SLOT_SECRET_KEY`,
   `CHIEF_HEALTH_COACH_ID`, `MYTATVA_BASE_URL`, `MYTATVA_HEALTH_SECRET`. (`.env` is gitignored
   and does not ship.)
4. Deploy, then smoke-test `/healthz` → `/` → `/api/data?refresh=1`.

**Diagnosing a `NOT_FOUND` (e.g. `bom1::…`)**: that's Vercel's *platform* 404, not FastAPI's —
the request never reached your function. Check the deployment's **Functions** tab; if it's empty,
no function was created, which means the entrypoint wasn't found (usually a Root Directory
mismatch). FastAPI's own 404 returns JSON `{"detail":"Not Found"}`.

**Caveats**

- `MYTATVA_BASE_URL` must be a stable, publicly reachable host. An ngrok tunnel to a laptop dies
  the moment the machine sleeps.
- The in-memory cache doesn't survive across serverless invocations, so a cold load re-runs the
  pipeline.
- **There is no auth.** Anyone with the URL can view coach data and trigger refreshes. Gate it
  before sharing widely.

### Refresh performance

Baseline measured (cold, sequential fetch): fetch = **10.5s** of an **11.1s** total;
`calculate` = 0.62s. **The cost was entirely network, not compute.**

**31-Jul-2026: implemented.** `mytatva_api.py` now fetches all chief IDs concurrently via a
thread pool (safe — I/O-bound waits release the GIL) over a single shared `requests.Session`
(was sequential `requests.post()` per chief ID, fresh connection each time). Estimated
~11s → ~4s; combined with the `bom1` region pin above, should close most of the
local-vs-Vercel gap. **Not yet re-measured against the live API from this codebase** — the
next live refresh's `[timing]` log lines are the way to confirm the real number.

`classify()` was also vectorised the same day (see [Engine functions](#modules)) — at current
scale this was invisible next to the network cost, but matters once fetch is no longer the
bottleneck.

Stage timings print on every run (`[timing] …`, `flush=True`) — visible in Vercel's Logs tab.

---

## Known issues

**Chop overshoot — fixed 31-Jul-2026.** `chop()` used to emit a trailing slot that could run
past a rule's `end_time` when the window length wasn't a multiple of `time_slot` (Swetha
Kshirsagar's rule `16:30–17:15` @ 30 min used to yield a bogus `17:00–17:30` slot, offered as
bookable when she wasn't available then). Now only emits a slot when `start + step <= end`.
Real measured effect on the June 2026 dataset: −78 total slots / −52 open slots overall, all of
it on Swetha Kshirsagar specifically (402→324 total, 97→45 open) — no other coach's rules hit
this remainder in that month. Any coach could hit this in a future month if their rule's window
length isn't an exact multiple of their `time_slot`.

**`roles.py` coverage.** 20 entries (was 18 as of 28-Jul-2026; Dilpreet Kaushik and Sneha Pandey
added since). The previously-noted stale ID for Sridurga R — she was mapped to `3e952ad2-…`,
whose rules ended 2025-12-31, so she never appeared — was fixed 31-Jul-2026: she's now mapped
under her active ID `d1e01989-…` (rules Jun–Jul 2026). Vandna Lalchandani still has two IDs on
record; *a full scan for other multi-ID coaches is still pending.* Unmapped active coaches are
invisible everywhere (KPI, finder, capacity, demand chart, blocked grid) — never bucketed as
"Other" — and the current unmapped count hasn't been re-audited since the 28-Jul figure above.

**No auth.** See above.

**Reserved-slot logic changed 31-Jul-2026** (see [Reserved slots](#key-concepts)) — from an
API-config-driven mechanism to a computed last-2/last-3-per-day rule. The old
`reserved_slot_config`-based calculation is commented out in `build_slots()`, not deleted, so
it can be restored if the new rule doesn't hold up in practice. `_reserved_windows()` and
`_min()` are consequently unused right now but still defined for the same reason.

**`mytatva_api.py` version — resolved 31-Jul-2026.** The old token-auth dead code
(commented-out `_headers()`/`fetch_*` versions, stale `BASE` constants) has been removed. The
file now ships only the current env-driven (`MYTATVA_BASE_URL` + `slot_availability_secret`)
version, with session-reused, threaded fetches (see Refresh performance above).

---

Dated change history lives in the changelog comments at the top of each module
(`coach_availability.py`, `pipeline.py`, `dashboard.py`) — there is no separate `CHANGELOG.md`.