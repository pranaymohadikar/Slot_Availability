# Handoff — Coach Slot Availability

Updated: 2026-10-01, after a session covering three one-off reporting requests and one real
engine change (`buffer_time` support). Still **not a git repo** — no `.git` anywhere in this
folder. Everything below is local/unpushed and only as safe as the OneDrive sync plus the
`.phase1-backup/` copies noted at the end.

For architecture/data-flow/module reference, see `Readme.md` — it's been updated to match
everything below. This file only tracks session-to-session status and open items.

---

## Status of the 2026-07-31 handoff's open items

1. **Init git + push** — still declined, still not done. Still the biggest structural risk.
2. **Live-verify the threaded fetch** — **incidentally confirmed today.** Several live fetches
   ran during today's session (schema check + three report date ranges): 1.5–2.9s each for a
   single `fetch_availability()` or `fetch_consumed()` call, well under the old ~10.5s
   *sequential* baseline. Not a formal `[timing]`-log benchmark, but real evidence the threading
   fix is working in production.
3. **Visually verify the UI changes** (dark mode, purple accent, KPI row) in an actual browser —
   **still not done.** Nothing touched the dashboard UI this session either way.
4. **Unmapped-coach handling decision** — still pending, unchanged.
5. **`Slots_availability/` duplicate folder** — still present, still not cleaned up. Now even
   more stale relative to the real files after today's changes.
6. **Stray `Coach Availability — Architecture & Code-Quality Review.html` + `_files/`** — still
   sitting in the project root, still not mine, still unaddressed.
7. **Morning/Evening/Night slot categorization** — never picked back up. Still just an idea.
8. **No auth on the live app** — unchanged, still open.
9. **`prompt.md`** — still present; still fine to delete if you don't want it as a record.

---

## What got done today (2026-10-01)

### Three one-off reserved-slot utilization reports (August 2026)
Requested as one-time reports, not permanent dashboard features — nothing added to
`dashboard.py`/`app.py` for these.

- **1–15 Aug** (uniformly weeks 1–3 → last-2-slots/day reserved): 509 reserved, 345 used, 164
  unused (~68%).
- **16–22 Aug** (user-designated as "week 4" for this report specifically → last-3/day,
  overriding the live day-of-month formula for this one-off): 354 reserved, 201 used, 153
  unused (~57%).
- **16–31 Aug** (real, unmodified hardcoded week rule — spans week3 days 16-21 at last-2/day and
  week4 days 22-31 at last-3/day): 716 reserved, 319 used, 397 unused (~45%).

All three: built from **live API data** (not the stale local `availability.xlsx`/`consumed.xlsx`,
which don't reach August at all), "used" defined as reserved+Booked (the existing P/F/N
type-A exact-start-time match — booked/fulfilled/no-show; cancelled correctly does **not**
count as used), and independently cross-checked by recomputing "used" straight from raw
`consumed` rows bypassing `classify()`'s `booked` column entirely — **0 mismatches** across all
three reports (354, 509, and 716 reserved slots checked respectively). All three Excel files
were sent to the user via `SendUserFile`; local copies (`_tmp_aug*.xlsx`) are still sitting in
the project root — see Open items.

A calendar-week (Sun–Sat, "week1 = the week containing the 1st") alternative to the hardcoded
day-of-month rule was discussed in depth — confirmed that interpretation reproduces the user's
16–22-Aug-is-week-4 framing, and that a per-date-independent resolution for weeks spanning two
months (option A in that discussion) would be consistent with how spillover is already handled
elsewhere. **This was never implemented or decided** — the user explicitly asked for the
*hardcoded* day-of-month rule for the final 16–31 report instead, so the live `build_slots()`
week-of-month formula is **unchanged** from 31-Jul. If this comes back, see the "calendar weeks"
discussion for the worked-out math before redoing it.

### API schema check — found `buffer_time`
Fetched live availability data and diffed its columns against the stale local
`availability.xlsx` to check for upstream API changes. Findings:
- **False alarm**: `reserved_slot_config.week1-4` showed a dtype difference (`str` vs. `object`)
  — this is purely an Excel-roundtrip artifact (nested JSON gets stringified when saved to
  `.xlsx`), not an API change. `_reserved_windows()` already handles both forms.
- **Real finding**: the API now sends `buffer_time` (minutes) on every rule row — not present in
  the old snapshot's schema at all, and not read anywhere in the engine until today. Also found
  `meta_data.buffer_time`, a rarely-populated (36/3441 rows) secondary field — explicitly **not**
  used, per the user's direction to use only the always-populated `buffer_time`.

### `buffer_time` support — implemented
A real engine change, not a refactor — confirmed the exact semantics with the user before
building: slots stay `time_slot` minutes long, but the *next* slot starts `time_slot +
buffer_time` minutes after the previous one starts (not just `time_slot` later), leaving a
`buffer_time`-minute gap between consecutive slots.

- `coach_availability.py`: `chop(start, end, step, buffer=0)` — new parameter, `buffer=0`
  (the default, and what missing/null `buffer_time` maps to) reproduces the old back-to-back
  output exactly.
- `build_slots()` reads each rule's `buffer_time` via `r.get("buffer_time", 0)` with a
  `pd.isna()` → 0 fallback, so old data without this column (e.g. the stale local snapshot)
  behaves exactly as before.
- **Verified**: the user's exact worked example (10:00–12:00 @ 30min, 10min buffer →
  `(10:00,10:30),(10:40,11:10),(11:20,11:50)`) matches exactly; `buffer=0` explicit and
  omitted both reproduce old back-to-back behavior; the `chop()` overshoot fix still works
  alongside this; tested against a real live rule (12:00–21:00 @ 30min, buffer=15) — all 11
  gaps between consecutive slots measured exactly 15 minutes. Full module compile/import check
  passes, and `build_slots()` runs end-to-end against real October 2026 live data (5,802 rows,
  no errors).
- **Real-world current usage is narrow**: of 3,441 live rule rows checked, 3,421 have
  `buffer_time=0` (unaffected), 19 have 15min, 1 has 10min. So this is a correct, verified
  change, but only visibly affects ~20 rules in the data as of this fetch.
- Backed up `coach_availability.py` to `.phase1-backup/coach_availability_pre_buffer_time.py`
  first.

---

## Open items / not done

1. **Init git + push** — unchanged, still the top structural risk.
2. **Visually verify the UI changes in a browser** — unchanged since 31-Jul, still not done.
3. **Unmapped-coach handling decision** — still pending.
4. **`Slots_availability/` duplicate** — still not cleaned up, now more stale than ever.
5. **Stray architecture-review HTML save** — still unaddressed.
6. **Three one-off report files still in the project root**: `_tmp_aug_reserved_report.xlsx`,
   `_tmp_aug1_15_reserved_report.xlsx`, `_tmp_aug16_31_reserved_report.xlsx`. Already delivered
   to the user via `SendUserFile`, so these local copies are redundant — fine to delete, or
   rename if you want to keep them without the "_tmp" prefix.
7. **Calendar-week definition** — discussed, math worked out, never decided or implemented. See
   "What got done today" above for where that conversation left off.
8. **No auth on the live app** — unchanged, still open.
9. **`buffer_time` not yet reflected in `coach_availability.xlsx`'s "Method & Notes" sheet or
   the dashboard's Method/meta text** — the engine honors it now, but nothing in the output
   explains to a viewer that gaps exist between some slots. Worth a small doc/UI note if
   `buffer_time` usage grows beyond today's ~20 rules.

---

## Suggested next steps (priority order)

1. **Init git + push** — same top priority as every handoff so far.
2. **Visually verify the UI** (dark mode, accent, KPI tiles) and **spot-check `buffer_time`
   gaps** in an actual rendered dashboard or Excel audit sheet — both are still purely
   code/data-level verified, never eyeballed.
3. **Decide on unmapped-coach handling** — pending across three handoffs now.
4. **Housekeeping**: delete the three `_tmp_aug*.xlsx` report files (or rename if keeping),
   clean up `Slots_availability/`, decide on the stray HTML save, delete `prompt.md` if unneeded.
5. **Decide on calendar weeks** if the reserved-slot reporting needs it again — the math is
   already worked out above, just needs a final yes/no and an implementation pass.
