#!/usr/bin/env python3
"""
London Marathon 2027 - Garmin training dashboard
--------------------------------------------------
Standalone script. Run it any time with:

    python3 dashboard.py

It reads your saved Garmin login from ~/.garminconnect (created earlier by
garmin-mcp-auth) and NEVER prompts for your password. If the saved session
has expired, it prints instructions and stops rather than asking for
credentials.

It writes index.html next to this script. Open that file in any browser
to see the dashboard. Nothing is uploaded anywhere - everything runs and
stays on this machine.

Scope: only shows training data from R001 (2026-08-03) onwards, not your
full Garmin history, since that's when marathon training actually started.
"""

import json
import os
import sys
import traceback
from datetime import date, datetime, timedelta

TOKENSTORE = os.path.expanduser("~/.garminconnect")
R001_DATE = "2026-08-03"          # first marathon-training run - scope start
RACE_DATE = date(2027, 4, 25)      # London Marathon 2027
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

# ---------------------------------------------------------------------------
# Coach-maintained block. Claude updates this section (and only this section)
# after each run is logged - it's the qualitative layer on top of the raw
# Garmin/Strava numbers pulled automatically above.
# ---------------------------------------------------------------------------

COACH_NOTE = ("R004 done, 4.17 km - the farthest session yet - avg HR 135 (no heat factor "
              "today, so a genuinely stronger reading than R003's heat-elevated 137). RPE 5/10, "
              "comfortable throughout, minor discomfort for a couple of minutes then good "
              "recovery, finished strong. This is the first clean session of the block (RPE <=6, "
              "no worsening pain), but R003 still had some pain so it's only one - the run/walk "
              "ladder needs two consecutive clean sessions before advancing. R005 (tomorrow) is "
              "going off-plan by Joe's choice: a 40 min pyramid session (2-3-4-5-4-3-2 min running "
              "blocks with short walk breaks) instead of the usual identical repeat, to explore how "
              "far continuous running can go while staying slow and stopping at any shin discomfort. "
              "It's a good design - it peaks at 5 min continuous (more than double anything done so "
              "far) then tapers back down rather than ending on the hardest effort. It doesn't count "
              "as a ladder rung either way, so the two-consecutive-clean-sessions progression clock "
              "is still waiting on an actual repeat at R006 or beyond.")

NEXT_WORKOUT_TEXT = ("R004 - repeat 2 min run / 2 min walk x 8, same structure as "
                      "R001-R003, contingent on shins staying clear. 5 min warmup walk beforehand.")

# Full week plan, built from what Joe tells Claude about his week (driving,
# work, social commitments) plus the current training decision. Rebuilt by
# Claude each week - status is one of: training / rest / tbc / optional.
WEEK_PLAN = [
    {"date": "2026-08-10", "day": "Mon", "status": "rest", "summary": "No training logged."},
    {"date": "2026-08-11", "day": "Tue", "status": "rest", "summary": "No training logged."},
    {"date": "2026-08-12", "day": "Wed", "status": "training", "summary": "R004 done - 4.17 km, avg HR 135, little to no pain, felt strong. Farthest session yet."},
    {"date": "2026-08-13", "day": "Thu", "status": "training", "summary": "R005 - off-plan by choice: a 40 min pyramid session instead of the usual ladder repeat (2-3-4-5-4-3-2 min running blocks with short walk breaks, peaking at 5 min continuous then tapering back down). Slow pace, stop at any shin discomfort. Doesn't count as a ladder rung either way - treated as its own data point, not a repeat of R004."},
    {"date": "2026-08-14", "day": "Fri", "status": "rest", "summary": "250-mile drive, then football and beers. No training planned."},
    {"date": "2026-08-15", "day": "Sat", "status": "optional", "summary": "Free until 3pm, then a party. A short easy session possible in the morning if legs are fresh - optional, not required."},
    {"date": "2026-08-16", "day": "Sun", "status": "rest", "summary": "250-mile drive. No training planned."},
]

# Keyed by run date (YYYY-MM-DD) rather than activity id, since Strava and
# Garmin assign different ids to the same run - date is the one thing both
# platforms agree on.
RUN_NOTES = {
    "2026-08-03": {"run_id": "R001", "rpe": 5, "pain": "0", "decision": "Repeat the same run/walk session. Monitor heel stability and next-day soreness."},
    "2026-08-05": {"run_id": "R002", "rpe": 6, "pain": "-", "decision": "Do not progress automatically. Reassess shins over 24-48 hours; progress only if walking and daily activity are pain-free."},
    "2026-08-09": {"run_id": "R003", "rpe": 6, "pain": "Some, less than R002", "decision": "Hold. Repeat identical structure for R004, contingent on continued shin improvement."},
    "2026-08-12": {"run_id": "R004", "rpe": 5, "pain": "Minor discomfort a couple of minutes, resolved, good recovery, finished strong", "decision": "First clean session of the block (RPE 5, no worsening pain). Repeat identical structure for R005 - need a second consecutive clean session before advancing the run/walk ladder to 3:2 x6."},
}

MILESTONES = [
    {"name": "Official Run #1", "status": "achieved", "detail": "R001 - 3.92 km run/walk - 3 Aug 2026"},
    {"name": "First efficiency improvement", "status": "achieved", "detail": "R002 - farther + lower HR than R001 - 5 Aug 2026"},
    {"name": "First continuous 20 min", "status": "not yet"},
    {"name": "First continuous 5K", "status": "not yet"},
    {"name": "First parkrun", "status": "not yet"},
    {"name": "First 10K", "status": "not yet"},
    {"name": "100 km total", "status": "not yet"},
    {"name": "First half marathon", "status": "not yet"},
    {"name": "1 stone lost", "status": "not yet"},
    {"name": "London Marathon 2027", "status": "not yet", "detail": "25 Apr 2027"},
]

WEIGHT_LOG = [
    {"date": "2026-08-03", "st": 18.7857, "note": "Starting baseline"},
    {"date": "2026-08-05", "st": 18.5, "note": "First Wednesday weigh-in"},
    {"date": "2026-08-12", "st": 18.7571, "note": "Weigh-in Wednesday - up from last week, roughly back to baseline"},
]

WARMUP_ROUTINE = [
    "2 min brisk walk - get blood flowing first",
    "Heel walks - ~20m walking on your heels, toes up (activates the tibialis anterior - directly targets the shin issue)",
    "Toe walks - ~20m up on your toes (calf activation, balance)",
    "Ankle circles - 10 each direction, each foot",
    "Leg swings - 10 each leg, front-to-back and side-to-side (hip mobility)",
    "A few walking lunges or high knees - 10-15 steps to prime the legs",
]

SHOE_NAME = "Hoka Clifton 9"
SHOE_PRIOR_KM = 300     # estimated mileage on these shoes before R001
SHOE_REPLACE_KM = 700   # typical replacement point

# Race plan: the overall phase structure from where training actually is
# today through to race day. This is not a fixed week-by-week schedule -
# individual sessions still get decided week to week from real data. It's
# the destination the week-to-week decisions are steering toward. Phase 1's
# length is injury-gated (shin issue), so everything after it is
# approximate and will shift if Phase 1 runs long or short.
RACE_PLAN_INTRO = (
    "You're 4 sessions in, still on run/walk intervals, still working through a shin "
    "issue that started at R002. At 6'4\" and roughly 18.5 stone, you're carrying more "
    "load per stride than most first-time marathoners, which is exactly why progression "
    "here is paced by pain and RPE rather than the calendar - going out too hard on volume "
    "before the shins are genuinely clear is the single biggest risk to this whole plan. "
    "4:30 for a first marathon is a realistic, achievable target on this timeline (about 38 "
    "weeks from R001 to race day) provided training stays consistent - it doesn't require "
    "the volume or intensity a faster marathon goal would."
)

RACE_PLAN_PHASES = [
    {
        "name": "Phase 1 - Injury resolution & run/walk base",
        "window": "Now - shin pain fully resolved (open-ended)",
        "mileage": "12-20 km/week",
        "focus": ("Run/walk ladder: 2min run/2min walk x8 (R001-R004) -&gt; 3:2 x6 -&gt; 4:2 x5 -&gt; 5:1 x6 -&gt; 8:1 x4 -&gt; "
                  "continuous running. Each rung keeps total time roughly the same, shifting more of it into running. "
                  "Advance a rung only once the last 2 sessions were RPE &le;6, no new/worsening shin pain, and "
                  "next-day soreness cleared within 24h - otherwise hold or drop back a rung. This phase ends when "
                  "it ends, not on a calendar date."),
        "current": True,
    },
    {
        "name": "Phase 2 - Base building",
        "window": "~8-10 weeks once Phase 1 clears (approx. Sept-Nov 2026)",
        "mileage": "20-35 km/week",
        "focus": "Run/walk intervals give way to continuous running. First continuous 20 min, first 5K, first 10K land in this phase. 3 runs/week typical, built around your driving and social weeks.",
        "current": False,
    },
    {
        "name": "Phase 3 - Build",
        "window": "~10-12 weeks (approx. Dec 2026-Feb 2027)",
        "mileage": "35-55 km/week",
        "focus": "Long run grows progressively most weeks (roughly +1-2 km at a time, with easier weeks every 3rd-4th week). First half marathon lands here. Still almost entirely easy effort - this plan is about durability, not speed.",
        "current": False,
    },
    {
        "name": "Phase 4 - Peak",
        "window": "~3-4 weeks (approx. March 2027)",
        "mileage": "50-60 km/week",
        "focus": "Longest runs of the block, 29-32 km, with some marathon-pace segments practiced late in the long run. Highest-volume weeks of the whole plan.",
        "current": False,
    },
    {
        "name": "Phase 5 - Taper",
        "window": "~2-3 weeks (April 2027, into race day 25 Apr)",
        "mileage": "Dropping to ~25-30% of peak",
        "focus": "Volume falls sharply, a little intensity stays. Goal is arriving fresh, not fit - the fitness is already banked by this point.",
        "current": False,
    },
]
# ---- end coach-maintained block ----


# ---------------------------------------------------------------------------
# Login (token-only, never prompts for a password)
# ---------------------------------------------------------------------------

def get_client():
    try:
        from garminconnect import Garmin
    except ImportError:
        print("The 'garminconnect' package isn't installed.")
        print("Install it with:  pip3 install --upgrade garminconnect curl_cffi")
        sys.exit(1)

    try:
        client = Garmin()
        client.login(TOKENSTORE)
        return client
    except Exception as e:
        print(f"Could not log in to Garmin using the saved session at {TOKENSTORE}")
        print(f"Details: {e}")
        print()
        print("This script will not ask for your password.")
        print("If your saved session has expired, re-run your Garmin MCP")
        print("authentication step (garmin-mcp-auth) to refresh it, then run")
        print("this script again.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def daterange(start_str, end_str):
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_str, "%Y-%m-%d").date()
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


def safe(fn, *args, **kwargs):
    """Call fn, return None on any failure instead of crashing the script."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def fmt_seconds(total_seconds):
    if total_seconds is None:
        return None
    total_seconds = int(round(total_seconds))
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_pace_per_km(distance_m, duration_s):
    if not distance_m or not duration_s:
        return None
    km = distance_m / 1000.0
    if km <= 0:
        return None
    sec_per_km = duration_s / km
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d} /km"


def fmt_hm(hours_decimal):
    """6.9 -> '6h 54m'"""
    if hours_decimal is None:
        return None
    total_minutes = int(round(hours_decimal * 60))
    h, m = divmod(total_minutes, 60)
    return f"{h}h {m:02d}m"


# ---------------------------------------------------------------------------
# Data fetching - each section is isolated so one failure doesn't kill
# the rest of the dashboard.
# ---------------------------------------------------------------------------

def fetch_activities(client, today_str):
    raw = safe(client.get_activities_by_date, R001_DATE, today_str) or []
    runs = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
        if "run" not in type_key and "walk" not in type_key:
            continue
        distance_m = a.get("distance")
        duration_s = a.get("duration") or a.get("movingDuration")
        run_date = (a.get("startTimeLocal") or "")[:10]
        note = RUN_NOTES.get(run_date, {})
        runs.append({
            "id": a.get("activityId"),
            "name": a.get("activityName"),
            "date": (a.get("startTimeLocal") or "")[:10],
            "start_time": a.get("startTimeLocal"),
            "distance_km": round(distance_m / 1000.0, 2) if distance_m else None,
            "duration_s": duration_s,
            "duration_fmt": fmt_seconds(duration_s),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "pace": fmt_pace_per_km(distance_m, duration_s),
            "run_id": note.get("run_id", "-"),
            "rpe": note.get("rpe", "-"),
            "pain": note.get("pain", "-"),
            "decision": note.get("decision", ""),
        })
    runs.sort(key=lambda r: r["date"])
    return runs


def fetch_rhr(client, today_str):
    rows = safe(client.get_rhr_daily, R001_DATE, today_str) or []
    out = {}
    for row in rows:
        d = row.get("calendarDate")
        v = row.get("value")
        if d and v is not None:
            out[d] = v
    return out


def fetch_sleep(client, today_str):
    """Garmin's sleep, RHR and HRV endpoints all key their 'date' by the
    WAKE date (the morning the stats are reported), not the night the sleep
    started - and they're bundled together in the Garmin app under that same
    date (e.g. "Today" shows last night's sleep + this morning's resting HR
    together). Keep sleep keyed the same way here so it lines up with RHR
    and HRV in the same row instead of landing a day apart."""
    out = {}
    start = datetime.strptime(R001_DATE, "%Y-%m-%d").date()
    end = datetime.strptime(today_str, "%Y-%m-%d").date()
    d = start
    while d <= end:
        wake_date = d.isoformat()
        raw = safe(client.get_sleep_data, wake_date)
        if raw:
            dto = raw.get("dailySleepDTO") or {}
            scores = (raw.get("sleepScores") or {}).get("overall") or {}
            sleep_seconds = dto.get("sleepTimeSeconds")
            score = scores.get("value")
            qualifier = scores.get("qualifierKey")
            if sleep_seconds or score:
                out[wake_date] = {
                    "sleep_hours": round(sleep_seconds / 3600.0, 2) if sleep_seconds else None,
                    "score": score,
                    "qualifier": qualifier,
                }
        d += timedelta(days=1)
    return out


def fetch_hrv(client, today_str):
    raw = safe(client.get_hrv_data_range, R001_DATE, today_str)
    out = {}
    if not raw:
        return out
    rows = raw.get("hrvSummaries") or raw.get("hrvDailyValues") or []
    if isinstance(raw, list):
        rows = raw
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = row.get("calendarDate")
        if not d:
            continue
        out[d] = {
            "last_night_avg": row.get("lastNightAvg") or row.get("lastNight5MinHigh"),
            "weekly_avg": row.get("weeklyAvg"),
            "status": row.get("status"),
        }
    return out


def fetch_vo2max(client, today_str):
    raw = safe(client.get_max_metrics_range, R001_DATE, today_str)
    points = []
    if not raw:
        return points
    rows = raw if isinstance(raw, list) else raw.get("metrics") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = row.get("calendarDate")
        generic = row.get("generic") or {}
        vo2 = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue") or row.get("vo2MaxValue")
        if d and vo2:
            points.append({"date": d, "vo2max": vo2})
    points.sort(key=lambda r: r["date"])
    return points


def fetch_training_status_snapshot(client, today_str):
    raw = safe(client.get_training_status, today_str)
    if not raw:
        return None
    # Shape varies by account/device; pull out whatever's present rather
    # than assuming a fixed structure.
    try:
        latest = raw.get("mostRecentTrainingStatus") or raw
        dev_map = latest.get("latestTrainingStatusData") if isinstance(latest, dict) else None
        if isinstance(dev_map, dict) and dev_map:
            first = next(iter(dev_map.values()))
            return {
                "training_status": first.get("trainingStatusFeedbackPhrase") or first.get("trainingStatus"),
                "vo2max": first.get("vo2MaxPreciseValue") or first.get("vo2MaxValue"),
                "acute_load": first.get("weeklyTrainingLoad") or first.get("acuteTrainingLoad"),
            }
    except Exception:
        pass
    return None


def fetch_race_predictions(client):
    raw = safe(client.get_race_predictions)
    if not raw:
        return None
    return {
        "5K": fmt_seconds(raw.get("time5K")),
        "10K": fmt_seconds(raw.get("time10K")),
        "half_marathon": fmt_seconds(raw.get("timeHalfMarathon")),
        "marathon": fmt_seconds(raw.get("timeMarathon")),
    }


def fetch_data():
    client = get_client()
    today_str = date.today().isoformat()

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "r001_date": R001_DATE,
        "today": today_str,
        "activities": fetch_activities(client, today_str),
        "rhr": fetch_rhr(client, today_str),
        "sleep": fetch_sleep(client, today_str),
        "hrv": fetch_hrv(client, today_str),
        "vo2max": fetch_vo2max(client, today_str),
        "training_status": fetch_training_status_snapshot(client, today_str),
        "race_predictions": fetch_race_predictions(client),
    }
    return data


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def weeks_and_days_until(target_date):
    today = date.today()
    delta = (target_date - today).days
    weeks = delta // 7
    days = delta % 7
    return weeks, days, delta


def build_weekly_mileage(activities):
    """Bucket runs into ISO weeks. With <2 weeks of training this may be a
    single bar, which is expected and will grow as more weeks accrue."""
    buckets = {}
    for r in activities:
        if not r["date"] or not r["distance_km"]:
            continue
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        iso_year, iso_week, _ = d.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        buckets[key] = buckets.get(key, 0) + r["distance_km"]
    ordered = sorted(buckets.items())
    return [k for k, _ in ordered], [round(v, 1) for _, v in ordered]


def render_html(data):
    activities = data["activities"]
    rhr = data["rhr"]
    sleep = data["sleep"]
    hrv = data["hrv"]
    vo2max = data["vo2max"]
    race_pred = data["race_predictions"]

    race_weeks, race_days, race_total_days = weeks_and_days_until(RACE_DATE)

    total_km = round(sum(r["distance_km"] or 0 for r in activities), 1)
    run_count = len(activities)
    longest = max((r["distance_km"] or 0 for r in activities), default=0)
    avg_hr_vals = [r["avg_hr"] for r in activities if r.get("avg_hr")]
    avg_hr = round(sum(avg_hr_vals) / len(avg_hr_vals)) if avg_hr_vals else None

    week_labels, week_km = build_weekly_mileage(activities)

    # This week's runs (ISO week, based on the day the script is run)
    today = date.today()
    this_iso = today.isocalendar()[:2]
    week_runs = [r for r in activities
                 if r["date"] and datetime.strptime(r["date"], "%Y-%m-%d").date().isocalendar()[:2] == this_iso]
    if week_runs:
        week_rows_html = "".join(f"""
          <div class="week-row">
            <span><strong>{r.get('run_id','-')}</strong> &middot; {r['date']}</span>
            <span>{r['distance_km'] or '-'} km &middot; {r['pace'] or '-'} &middot; {r['avg_hr'] or '-'} bpm &middot; RPE {r.get('rpe','-')}</span>
          </div>""" for r in week_runs)
    else:
        week_rows_html = '<span class="muted">No runs yet this week.</span>'

    activities_by_date = {r["date"]: r for r in activities}
    status_labels = {"training": "Training", "rest": "Rest", "tbc": "TBC", "optional": "Optional"}
    today_str = date.today().isoformat()
    week_plan_rows = []
    for day in WEEK_PLAN:
        done = activities_by_date.get(day["date"])
        is_today = day["date"] == today_str
        if done:
            body = f"<strong>{done.get('run_id','-')}</strong> completed - {done['distance_km']} km, {done['pace'] or '-'}, {done['avg_hr'] or '-'} bpm, RPE {done.get('rpe','-')}"
            status = "done"
        else:
            body = day["summary"]
            status = day["status"]
        week_plan_rows.append(f"""
        <div class="week-row{' today' if is_today else ''}">
          <span><strong>{day['day']}</strong> {day['date'][5:]}{' (today)' if is_today else ''} <span class="pill {status}">{'Done' if status=='done' else status_labels.get(status, status)}</span></span>
          <span class="footer-note" style="margin-top:0;">{body}</span>
        </div>""")
    week_plan_html = "".join(week_plan_rows)

    weight_kpi_html = ""
    weight_detail_html = ""
    if WEIGHT_LOG:
        baseline, latest = WEIGHT_LOG[0], WEIGHT_LOG[-1]
        def st_lb(st):
            whole = int(st)
            lb = round((st - whole) * 14)
            return f"{whole} st {lb} lb"
        lost_lb = round(baseline["st"] * 14) - round(latest["st"] * 14)
        weight_kpi_html = f"""
    <div class="card">
      <div class="label">Weight</div>
      <div class="value">{st_lb(latest['st'])}</div>
      <div class="footer-note">as of {latest['date']}</div>
    </div>
    <div class="card">
      <div class="label">Weight lost</div>
      <div class="value">{lost_lb} lb</div>
      <div class="footer-note">since {baseline['date']}</div>
    </div>"""
        weight_rows = "".join(f"<tr><td>{w['date']}</td><td>{st_lb(w['st'])}</td><td class='footer-note'>{w.get('note','')}</td></tr>" for w in WEIGHT_LOG)
        weight_detail_html = f"""
        <table>
          <tr><th>Date</th><th>Weight</th><th>Note</th></tr>
          {weight_rows}
        </table>"""

    warmup_html = "".join(f"<li style='margin-bottom:6px;'>{w}</li>" for w in WARMUP_ROUTINE)

    phase_rows_html = "".join(f"""
        <div class="phase-card{' current' if p['current'] else ''}">
          <div class="phase-head">
            <span class="phase-name">{p['name']}</span>
            {'<span class="pill training">Current phase</span>' if p['current'] else ''}
          </div>
          <div class="footer-note" style="margin-top:2px;">{p['window']} &middot; {p['mileage']}</div>
          <p style="font-size:13px; margin:8px 0 0 0; line-height:1.5;">{p['focus']}</p>
        </div>""" for p in RACE_PLAN_PHASES)

    shoe_total = SHOE_PRIOR_KM + total_km
    shoe_pct = round((shoe_total / SHOE_REPLACE_KM) * 100)

    milestones_html = "".join(f"""
        <tr>
          <td style="font-weight:600;">{m['name']}</td>
          <td><span class="pill {'achieved' if m['status']=='achieved' else 'notyet'}">{'Achieved' if m['status']=='achieved' else 'Not yet'}</span></td>
          <td class="footer-note">{m.get('detail','')}</td>
        </tr>""" for m in MILESTONES)

    # Recovery panel: union of dates present in rhr/sleep/hrv, since R001
    recovery_dates = sorted(set(rhr.keys()) | set(sleep.keys()) | set(hrv.keys()))
    recovery_rows = []
    for d in recovery_dates:
        s = sleep.get(d, {})
        h = hrv.get(d, {})
        recovery_rows.append({
            "date": d,
            "rhr": rhr.get(d),
            "sleep_score": s.get("score"),
            "sleep_hours": s.get("sleep_hours"),
            "hrv_last_night": h.get("last_night_avg"),
            "hrv_status": h.get("status"),
        })

    vo2_note = ""
    if len(vo2max) <= 2:
        vo2_note = ('<p class="caveat">Only a couple of data points so far - too sparse to '
                    'call this a real trend yet. Worth revisiting in a few weeks.</p>')

    race_pred_html = ""
    if race_pred:
        race_pred_html = f"""
        <div class="section">
          <h2>Garmin race predictions</h2>
          <p class="caveat">Based on Garmin's current fitness model, which is still working off
          limited data this early in the block. Not meaningful yet - included for interest,
          not as a real forecast. Your actual goal is 4:30:00.</p>
          <p class="caveat">Planned: a dedicated marathon / half / 10K / 5K prediction panel, likely
          around Dec 2026-Jan 2027 once real race-pace efforts exist (Phase 3, Build). It'll show
          Garmin's estimate alongside a second one Claude calculates directly from your actual recent
          race-distance times (e.g. Riegel's formula) - two independent numbers instead of one
          black-box guess. Known reference point: 5K PB of 33:54, set 24 May 2024 - over 2 years before
          this block started, so useful as a rough sanity check only, not something to build a current
          prediction on.</p>
          <div class="pred-grid">
            <div><span class="pred-label">5K</span><span class="pred-value">{race_pred['5K'] or '-'}</span></div>
            <div><span class="pred-label">10K</span><span class="pred-value">{race_pred['10K'] or '-'}</span></div>
            <div><span class="pred-label">Half marathon</span><span class="pred-value">{race_pred['half_marathon'] or '-'}</span></div>
            <div><span class="pred-label">Marathon</span><span class="pred-value">{race_pred['marathon'] or '-'}</span></div>
          </div>
        </div>"""

    runs_rows_html = "".join(f"""
        <tr>
          <td>{r.get('run_id','-')}</td>
          <td>{r['date']}</td>
          <td>{r['name'] or ''}</td>
          <td>{r['distance_km'] or '-'} km</td>
          <td>{r['duration_fmt'] or '-'}</td>
          <td>{r['pace'] or '-'}</td>
          <td>{r['avg_hr'] or '-'}</td>
          <td>{r.get('rpe','-')}</td>
          <td>{r.get('pain','-')}</td>
          <td class="footer-note">{r.get('decision','')}</td>
        </tr>""" for r in reversed(activities))

    recovery_rows_html = "".join(f"""
        <tr>
          <td>{row['date']}</td>
          <td>{row['rhr'] if row['rhr'] is not None else '-'}</td>
          <td>{row['sleep_score'] if row['sleep_score'] is not None else '-'}</td>
          <td>{fmt_hm(row['sleep_hours']) or '-'}</td>
          <td>{row['hrv_last_night'] if row['hrv_last_night'] is not None else '-'}</td>
          <td>{row['hrv_status'] or '-'}</td>
        </tr>""" for row in reversed(recovery_rows))

    vo2_labels = json.dumps([p["date"] for p in vo2max])
    vo2_values = json.dumps([p["vo2max"] for p in vo2max])

    recovery_dates_js = json.dumps([row["date"] for row in recovery_rows])
    rhr_js = json.dumps([row["rhr"] for row in recovery_rows])
    sleep_score_js = json.dumps([row["sleep_score"] for row in recovery_rows])
    hrv_js = json.dumps([row["hrv_last_night"] for row in recovery_rows])

    # Pace & HR trend (chronological, one point per run)
    chrono = sorted(activities, key=lambda r: r["date"])
    trend_labels = json.dumps([f"{r.get('run_id','-')} ({r['date'][5:]})" for r in chrono])
    trend_pace = json.dumps([round((r["duration_s"] / (r["distance_km"] * 60)), 2) if r["duration_s"] and r["distance_km"] else None for r in chrono])
    trend_hr = json.dumps([round(r["avg_hr"]) if r["avg_hr"] else None for r in chrono])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>London Marathon 2027 - Training Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js"></script>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px; background: #f3f4f6; color: #1f2937;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 2px 0; letter-spacing: -0.01em; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 24px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }}
  .card .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; margin-bottom: 4px; }}
  .card .value {{ font-size: 22px; font-weight: 700; color: #111827; }}
  .card.accent {{ background: linear-gradient(135deg, #111827, #1f2937); border: none; }}
  .card.accent .label {{ color: #9ca3af; }}
  .card.accent .value {{ color: #fff; font-size: 26px; }}
  .card.accent .footer-note {{ color: #9ca3af; }}
  .section {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }}
  .section h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; margin: 0 0 12px 0; }}
  .chart-box {{ position: relative; height: 220px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid #f0f0f0; }}
  th {{ color: #6b7280; font-weight: 600; font-size: 11px; text-transform: uppercase; }}
  .caveat {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px;
             font-size: 12.5px; line-height: 1.5; color: #92400e; margin: 0 0 12px 0; }}
  .pred-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }}
  .pred-grid > div {{ background: #f9fafb; border-radius: 8px; padding: 10px; text-align: center; }}
  .pred-label {{ display: block; font-size: 11px; color: #6b7280; text-transform: uppercase; }}
  .pred-value {{ display: block; font-size: 18px; font-weight: 700; margin-top: 2px; }}
  .footer-note {{ font-size: 11px; color: #9ca3af; margin-top: 8px; }}
  .note {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 12px 14px; font-size: 13px; line-height: 1.5; color: #1e3a8a; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-left: 6px; }}
  .pill.achieved {{ background: #d1fae5; color: #065f46; }}
  .pill.notyet {{ background: #f3f4f6; color: #6b7280; }}
  .pill.training {{ background: #dbeafe; color: #1e40af; }}
  .pill.done {{ background: #d1fae5; color: #065f46; }}
  .pill.rest {{ background: #f3f4f6; color: #6b7280; }}
  .pill.tbc {{ background: #fef3c7; color: #92400e; }}
  .pill.optional {{ background: #ede9fe; color: #5b21b6; }}
  .muted {{ color: #9ca3af; }}
  .week-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: #f9fafb; border-radius: 8px; font-size: 13px; margin-bottom: 6px; gap: 10px; flex-wrap: wrap; }}
  .week-row.today {{ background: #111827; }}
  .week-row.today > span:first-child {{ color: #fff; }}
  .week-row.today .footer-note {{ color: #d1d5db; }}
  .tabs {{ display: flex; gap: 4px; margin-bottom: 18px; border-bottom: 1px solid #e5e7eb; }}
  .tab-btn {{ padding: 10px 18px; border: none; background: none; font-size: 13px; font-weight: 600;
              color: #6b7280; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }}
  .tab-btn:hover {{ color: #111827; }}
  .tab-btn.active {{ color: #111827; border-bottom-color: #111827; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .phase-card {{ background: #fff; border: 1px solid #e5e7eb; border-left: 4px solid #d1d5db; border-radius: 10px;
                 padding: 14px 16px; margin-bottom: 10px; }}
  .phase-card.current {{ border-left-color: #111827; background: #f9fafb; }}
  .phase-head {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }}
  .phase-name {{ font-weight: 700; font-size: 14px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>London Marathon 2027</h1>
  <div class="sub">Race day 25 April 2027 &middot; Training since R001 (3 Aug 2026) &middot; Generated {data['generated_at']}</div>

  <div class="grid">
    <div class="card accent">
      <div class="label">Countdown</div>
      <div class="value">{race_weeks}w {race_days}d</div>
      <div class="footer-note">{race_total_days} days total</div>
    </div>
    <div class="card"><div class="label">Runs logged</div><div class="value">{run_count}</div></div>
    <div class="card"><div class="label">Total distance</div><div class="value">{total_km} km</div></div>
    <div class="card"><div class="label">Longest run</div><div class="value">{longest} km</div></div>
    <div class="card"><div class="label">Avg HR</div><div class="value">{avg_hr if avg_hr else '-'}</div></div>
    {weight_kpi_html}
  </div>

  <div class="tabs">
    <button class="tab-btn active" data-tab="overview" onclick="showTab('overview')">Overview</button>
    <button class="tab-btn" data-tab="training" onclick="showTab('training')">Training</button>
    <button class="tab-btn" data-tab="recovery" onclick="showTab('recovery')">Recovery</button>
    <button class="tab-btn" data-tab="progress" onclick="showTab('progress')">Progress</button>
    <button class="tab-btn" data-tab="plan" onclick="showTab('plan')">Race Plan</button>
  </div>

  <div class="tab-panel active" id="tab-overview">
    <div class="section">
      <h2>Coach status</h2>
      <div class="note">{COACH_NOTE}</div>
    </div>

    <div class="section">
      <h2>This week's plan</h2>
      {week_plan_html}
      <p class="footer-note">Built from what you tell Claude about your week (driving, work, social plans) plus the current training decision. To push a session to your Garmin calendar/watch, just ask Claude in chat.</p>
    </div>

    <div class="section">
      <h2>Warm-up routine</h2>
      <ol style="font-size:14px; line-height:1.5; margin:0; padding-left:20px;">{warmup_html}</ol>
    </div>
  </div>

  <div class="tab-panel" id="tab-training">
    <div class="section">
      <h2>Weekly mileage (since R001)</h2>
      <div class="chart-box"><canvas id="mileageChart"></canvas></div>
      <div class="footer-note">Only shows the weeks since marathon training started - expect a single bar until week 2+.</div>
    </div>

    <div class="section">
      <h2>Pace &amp; heart rate trend</h2>
      <div class="chart-box"><canvas id="trendChart"></canvas></div>
    </div>

    <div class="section">
      <h2>All runs (since R001)</h2>
      <table>
        <tr><th>ID</th><th>Date</th><th>Name</th><th>Distance</th><th>Duration</th><th>Pace</th><th>Avg HR</th><th>RPE</th><th>Pain</th><th>Coach decision</th></tr>
        {runs_rows_html}
      </table>
    </div>
  </div>

  <div class="tab-panel" id="tab-recovery">
    <div class="section">
      <h2>Recovery: resting HR, sleep score, HRV</h2>
      <div class="chart-box"><canvas id="recoveryChart"></canvas></div>
      <table style="margin-top:14px;">
        <tr><th>Date</th><th>RHR</th><th>Sleep score</th><th>Sleep time</th><th>HRV (ms)</th><th>HRV status</th></tr>
        {recovery_rows_html}
      </table>
    </div>

    <div class="section">
      <h2>VO2max trend</h2>
      {vo2_note}
      <div class="chart-box"><canvas id="vo2Chart"></canvas></div>
    </div>

    {race_pred_html}
  </div>

  <div class="tab-panel" id="tab-progress">
    <div class="section">
      <h2>Milestones</h2>
      <table>{milestones_html}</table>
    </div>

    <div class="section">
      <h2>Weight</h2>
      {weight_detail_html or '<span class="muted">No weigh-ins logged yet.</span>'}
    </div>

    <div class="section">
      <h2>Shoe mileage — {SHOE_NAME}</h2>
      <div class="grid" style="margin-bottom:0;">
        <div class="card"><div class="label">Total mileage</div><div class="value">{shoe_total:.1f} km</div>
          <div class="footer-note">{SHOE_PRIOR_KM:.0f} prior + {total_km:.1f} since R001 (~{shoe_pct}% of {SHOE_REPLACE_KM}km)</div>
        </div>
      </div>
    </div>
  </div>

  <div class="tab-panel" id="tab-plan">
    <div class="section">
      <h2>Race plan: today &rarr; 25 April 2027</h2>
      <p style="font-size:13px; line-height:1.6; margin:0 0 4px 0;">{RACE_PLAN_INTRO}</p>
    </div>
    {phase_rows_html}
    <div class="footer-note" style="margin-top:4px;">This is the destination, not a locked schedule - individual sessions are still decided week to week from RPE, pain and recovery data. Phase 1's length is injury-gated, so later windows will shift if it runs long or short.</div>
  </div>

  <div class="footer-note">Re-run <code>python3 dashboard.py</code> any time to refresh this page with the latest Garmin data. Coach notes, next workout and milestones are updated by Claude after each run is logged.</div>
</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector('.tab-btn[data-tab="' + name + '"]').classList.add('active');
  Object.values(window.__charts || {{}}).forEach(c => c && c.resize());
}}

window.__charts = {{}};

window.__charts.mileage = new Chart(document.getElementById('mileageChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(week_labels)},
    datasets: [{{ label: 'km', data: {json.dumps(week_km)}, backgroundColor: '#111827', borderRadius: 4 }}]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
}});

window.__charts.trend = new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: {trend_labels},
    datasets: [
      {{ label: 'Pace (min/km, lower=faster)', data: {trend_pace}, borderColor: '#2563eb', backgroundColor: '#2563eb', yAxisID: 'y', tension: 0.25 }},
      {{ label: 'Avg HR (bpm)', data: {trend_hr}, borderColor: '#dc2626', backgroundColor: '#dc2626', yAxisID: 'y1', tension: 0.25 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ position: 'left', title: {{ display: true, text: 'min/km' }} }},
      y1: {{ position: 'right', title: {{ display: true, text: 'bpm' }}, grid: {{ drawOnChartArea: false }} }}
    }}
  }}
}});

window.__charts.recovery = new Chart(document.getElementById('recoveryChart'), {{
  type: 'line',
  data: {{
    labels: {recovery_dates_js},
    datasets: [
      {{ label: 'RHR', data: {rhr_js}, borderColor: '#dc2626', backgroundColor: 'transparent', tension: 0.3, yAxisID: 'y' }},
      {{ label: 'Sleep score', data: {sleep_score_js}, borderColor: '#2563eb', backgroundColor: 'transparent', tension: 0.3, yAxisID: 'y1' }},
      {{ label: 'HRV (ms)', data: {hrv_js}, borderColor: '#16a34a', backgroundColor: 'transparent', tension: 0.3, yAxisID: 'y' }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      y: {{ position: 'left' }},
      y1: {{ position: 'right', min: 0, max: 100, grid: {{ drawOnChartArea: false }} }}
    }}
  }}
}});

window.__charts.vo2 = new Chart(document.getElementById('vo2Chart'), {{
  type: 'line',
  data: {{
    labels: {vo2_labels},
    datasets: [{{ label: 'VO2max', data: {vo2_values}, borderColor: '#7c3aed', backgroundColor: 'transparent', tension: 0.3 }}]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});
</script>
</body>
</html>"""
    return html


def main():
    print("Logging in to Garmin (using saved session, no password prompt)...")
    data = fetch_data()
    print(f"Fetched {len(data['activities'])} activities since {R001_DATE}.")
    html = render_html(data)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print(f"Wrote {OUTPUT_FILE}")
    print("Open it in your browser to view the dashboard.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print("Something went wrong building the dashboard:")
        traceback.print_exc()
        sys.exit(1)
