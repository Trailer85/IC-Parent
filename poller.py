#!/usr/bin/env python3
"""Unofficial Infinite Campus poller that publishes Home Assistant sensors."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import requests

LOG = logging.getLogger("ha-campus-parent")
RECENT_DAYS_DEFAULT = 14
MAX_ITEMS = 20


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def zone() -> ZoneInfo:
    return ZoneInfo(env("TZ", "America/New_York") or "America/New_York")


def now_local() -> datetime:
    return datetime.now(zone())


def recent_days() -> int:
    raw = env("CAMPUS_RECENT_DAYS", str(RECENT_DAYS_DEFAULT))
    try:
        value = int(raw)
    except ValueError:
        return RECENT_DAYS_DEFAULT
    return value if value > 0 else RECENT_DAYS_DEFAULT


def poll_hours() -> tuple[int, ...]:
    hours: list[int] = []
    for part in env("CAMPUS_POLL_HOURS", "6,18").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hour = int(part)
        except ValueError:
            continue
        if 0 <= hour <= 23:
            hours.append(hour)
    return tuple(hours) or (6, 18)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower())
    return slug.strip("_") or "student"


def parse_kids_config() -> list[dict] | None:
    """Optional CAMPUS_KIDS=campusFirst:Display Name,campusFirst:Display Name."""
    raw = env("CAMPUS_KIDS")
    if not raw:
        return None
    kids: list[dict] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            first, name = part.split(":", 1)
        else:
            first = name = part
        first = first.strip().lower()
        name = name.strip()
        if not first or not name:
            continue
        kids.append({"campus_first": first, "name": name, "slug": slugify(name)})
    return kids or None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s.replace("+0000", "+00:00"), fmt)
            if dt.tzinfo is None:
                if s.endswith("Z") or "+00:00" in s:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.replace(tzinfo=zone())
            return dt.astimezone(zone())
        except ValueError:
            continue
    return None


def as_date(value: Any):
    dt = parse_dt(value)
    return dt.date() if dt else None


class Campus:
    def __init__(self, base: str, district: str, username: str, password: str):
        self.base = base.rstrip("/")
        self.district = district
        self.username = username
        self.password = password
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        self.s.headers["User-Agent"] = "ha-campus-parent/0.1 (unofficial Infinite Campus poller)"

    def login(self) -> None:
        q = urlencode(
            {
                "nonBrowser": "true",
                "username": self.username,
                "password": self.password,
                "appName": self.district,
                "portalLoginPage": "parents",
            }
        )
        url = f"{self.base}/campus/verify.jsp?{q}"
        r = self.s.post(url, timeout=30)
        text = (r.text or "").lower()
        if r.status_code != 200 or "password-error" in text:
            raise RuntimeError("Infinite Campus login failed")
        if not self.s.cookies:
            raise RuntimeError("Infinite Campus login produced no session cookie")

    def get_json(self, path: str) -> Any:
        url = urljoin(self.base + "/", path.lstrip("/"))
        r = self.s.get(url, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"GET {path} -> {r.status_code}")
        if not r.content:
            return None
        try:
            return r.json()
        except json.JSONDecodeError:
            return None


def as_list(payload: Any) -> list:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("assignments", "students", "data", "items", "results", "grades"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
        if any(k in payload for k in ("personID", "assignmentName", "courseName", "firstName")):
            return [payload]
    return []


def kid_from_student(student: dict, configured: list[dict] | None) -> dict | None:
    first = (student.get("firstName") or student.get("alias") or "").strip()
    first_l = first.lower()
    if configured is None:
        if not first:
            return None
        return {
            "campus_first": first_l.split()[0],
            "name": first,
            "slug": slugify(first),
        }
    for kid in configured:
        cf = kid["campus_first"]
        if first_l == cf or first_l.startswith(cf + " "):
            return kid
    return None


TIME_RANGE_RE = re.compile(
    r"\(?\s*(\d{1,2}:\d{2})\s*(a\.?m\.?|p\.?m\.?)?\s*[-–]\s*(\d{1,2}:\d{2})\s*(a\.?m\.?|p\.?m\.?)?\s*\)?",
    re.I,
)


def _meridiem(hhmm: str, token: str | None) -> str:
    if token:
        return "PM" if token.lower().startswith("p") else "AM"
    h = int(hhmm.split(":")[0])
    if h == 12 or 1 <= h <= 6:
        return "PM"
    return "AM"


def _to_minutes(hhmm: str, mer: str) -> int:
    h, m = (int(x) for x in hhmm.split(":")[:2])
    if h == 12:
        h = 12 if mer == "PM" else 0
    elif mer == "PM":
        h += 12
    return h * 60 + m


def split_teacher_times(teacher: str) -> tuple[str, str, str]:
    """Pull 'Last, F. 8:00-3:00' / 'Last, F. (7:40AM-7:50AM)' into name + 24h start/end."""
    s = teacher or ""
    m = TIME_RANGE_RE.search(s)
    if not m:
        return s.strip(), "", ""
    start_m = _to_minutes(m.group(1), _meridiem(m.group(1), m.group(2)))
    end_m = _to_minutes(m.group(3), _meridiem(m.group(3), m.group(4)))
    name = TIME_RANGE_RE.sub("", s)
    name = re.sub(r"\s+", " ", name).strip(" \t,()")
    return name, f"{start_m // 60:02d}:{start_m % 60:02d}:00", f"{end_m // 60:02d}:{end_m % 60:02d}:00"


def today_schedule(roster: list, instructional: list, now: datetime) -> list[dict]:
    today = now.date()
    period_schedule_id = None
    is_school = False
    for day in instructional or []:
        d = as_date(day.get("date"))
        if d == today:
            is_school = bool(day.get("isSchoolDay", True))
            period_schedule_id = day.get("periodScheduleID")
            break
    if not is_school:
        return []
    periods = []
    seen = set()
    for course in roster or []:
        for p in course.get("sectionPlacements") or []:
            start_d = as_date(p.get("startDate"))
            end_d = as_date(p.get("endDate"))
            if start_d and start_d > today:
                continue
            if end_d and end_d < today:
                continue
            if period_schedule_id and p.get("periodScheduleID") not in (None, period_schedule_id):
                continue
            key = (p.get("periodSequence"), p.get("courseName") or course.get("courseName"))
            if key in seen:
                continue
            seen.add(key)
            teacher_raw = p.get("teacherDisplay") or course.get("teacherDisplay") or ""
            teacher, t_start, t_end = split_teacher_times(teacher_raw)
            periods.append(
                {
                    "period": p.get("periodName") or str(p.get("periodSequence") or ""),
                    "seq": p.get("periodSequence") or 0,
                    "start": t_start or p.get("startTime") or "",
                    "end": t_end or p.get("endTime") or "",
                    "course": p.get("courseName") or course.get("courseName") or "",
                    "teacher": teacher,
                    "room": p.get("roomName") or course.get("roomName") or "",
                }
            )
    periods.sort(key=lambda x: (x["start"] or "99:99:99", x["course"] or ""))
    return periods


def assignment_row(a: dict) -> dict:
    return {
        "name": a.get("assignmentName") or "",
        "course": a.get("courseName") or "",
        "due": a.get("dueDate") or "",
        "score": a.get("score") or a.get("scorePercentage") or "",
        "points": a.get("scorePoints") or "",
        "total": a.get("totalPoints"),
        "missing": bool(a.get("missing")),
        "late": bool(a.get("late")),
    }


def bucket_assignments(assignments: list, now: datetime) -> dict:
    today = now.date()
    tomorrow = today + timedelta(days=1)
    missing, due_today, due_tomorrow, recent = [], [], [], []
    cutoff = now - timedelta(days=recent_days())
    for a in assignments or []:
        if a.get("dropped"):
            continue
        due = as_date(a.get("dueDate"))
        modified = parse_dt(a.get("modifiedDate")) or parse_dt(a.get("assignedDate"))
        row = assignment_row(a)
        if a.get("missing"):
            missing.append(row)
        if due == today:
            due_today.append(row)
        elif due == tomorrow:
            due_tomorrow.append(row)
        if a.get("score") and modified and modified >= cutoff:
            recent.append({**row, "updated": modified.isoformat()})
    recent.sort(key=lambda x: x.get("updated") or "", reverse=True)
    return {
        "missing": missing[:MAX_ITEMS],
        "due_today": due_today[:MAX_ITEMS],
        "due_tomorrow": due_tomorrow[:MAX_ITEMS],
        "recent_scores": recent[:MAX_ITEMS],
    }


def course_grades(grades_json: Any, now: datetime) -> list[dict]:
    cutoff = now - timedelta(days=recent_days())
    out: list[dict] = []
    seen: set[tuple] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        if not isinstance(obj, dict):
            return
        name = obj.get("courseName") or obj.get("course") or ""
        task = obj.get("taskName") or obj.get("task") or ""
        score = (
            obj.get("progressPercent")
            or obj.get("percent")
            or obj.get("formattedScore")
            or obj.get("progressScore")
            or obj.get("score")
            or obj.get("grade")
            or obj.get("postedGrade")
        )
        posted = obj.get("postedScore") or obj.get("postedGrade")
        updated = parse_dt(
            obj.get("modifiedDate") or obj.get("scoreDate") or obj.get("progressDate") or obj.get("date")
        )
        if name and score is not None and (not updated or updated >= cutoff):
            key = (str(name), str(task), str(score))
            if key not in seen:
                seen.add(key)
                out.append(
                    {
                        "course": name,
                        "task": task,
                        "score": score,
                        "posted": posted,
                        "updated": updated.isoformat() if updated else "",
                    }
                )
        for v in obj.values():
            if isinstance(v, (list, dict)):
                walk(v)

    walk(grades_json)
    out.sort(key=lambda x: x.get("updated") or "", reverse=True)
    return out[:MAX_ITEMS]


def next_period_state(periods: list, now: datetime) -> str:
    if not periods:
        return "no school"
    for p in periods:
        end = parse_dt(p.get("end")) if p.get("end") and "T" in str(p.get("end")) else None
        start_s = str(p.get("start") or "")
        try:
            hh, mm, *_ = start_s.replace(".", ":").split(":")
            start = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if start >= now:
                return f"{p['course']} {start.strftime('%-I:%M')}"
        except (ValueError, TypeError):
            continue
        if end and end >= now:
            return p["course"]
    return "done"


class HA:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        self.token = token

    def post_state(self, entity_id: str, state: Any, attributes: dict) -> None:
        url = f"{self.base}/api/states/{entity_id}"
        body = json.dumps({"state": state, "attributes": attributes}).encode()
        req = requests.Request(
            "POST",
            url,
            data=body,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        r = requests.Session().send(req.prepare(), timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"HA {entity_id} -> {r.status_code} {r.text[:200]}")


def publish_kid(ha: HA, kid: dict, schedule: list, buckets: dict, grades: list) -> None:
    slug, name = kid["slug"], kid["name"]
    base_attr = {"attribution": "Infinite Campus", "kid": name}

    ha.post_state(
        f"sensor.{slug}_schedule_today",
        next_period_state(schedule, now_local()),
        {
            **base_attr,
            "friendly_name": f"{name} schedule today",
            "icon": "mdi:calendar-clock",
            "periods": schedule,
            "count": len(schedule),
        },
    )
    for key, icon, fname in (
        ("missing", "mdi:alert", "missing assignments"),
        ("due_today", "mdi:calendar-today", "due today"),
        ("due_tomorrow", "mdi:calendar-arrow-right", "due tomorrow"),
        ("recent_scores", "mdi:clipboard-check", "recent scores"),
    ):
        items = buckets.get(key) or []
        ha.post_state(
            f"sensor.{slug}_assignments_{key}" if key != "recent_scores" else f"sensor.{slug}_recent_scores",
            str(len(items)),
            {
                **base_attr,
                "friendly_name": f"{name} {fname}",
                "icon": icon,
                "assignments": items,
            },
        )
    ha.post_state(
        f"sensor.{slug}_recent_grades",
        str(len(grades)),
        {
            **base_attr,
            "friendly_name": f"{name} recent grades",
            "icon": "mdi:school",
            "grades": grades,
        },
    )
    missing_n = len(buckets.get("missing") or [])
    ha.post_state(
        f"binary_sensor.{slug}_has_missing",
        "on" if missing_n else "off",
        {
            **base_attr,
            "friendly_name": f"{name} has missing work",
            "icon": "mdi:alert-circle",
            "device_class": "problem",
        },
    )


def publish_status(ha: HA, state: str, extra: dict | None = None) -> None:
    attrs = {
        "friendly_name": "Campus sync",
        "icon": "mdi:sync",
        "attribution": "Infinite Campus",
    }
    if extra:
        attrs.update(extra)
    ha.post_state("sensor.campus_sync_status", state, attrs)


def run_once(ha: HA) -> None:
    user, password = env("IC_USERNAME"), env("IC_PASSWORD")
    base, district = env("IC_BASE_URL"), env("IC_DISTRICT")
    if not user or not password or not base or not district:
        publish_status(
            ha,
            "needs_credentials",
            {"detail": "set IC_BASE_URL, IC_DISTRICT, IC_USERNAME, and IC_PASSWORD"},
        )
        LOG.warning("missing Infinite Campus credentials")
        return
    campus = Campus(base, district, user, password)
    campus.login()
    students = as_list(campus.get_json("/campus/api/portal/students"))
    configured = parse_kids_config()
    now = now_local()
    matched = 0
    names = []
    for student in students:
        kid = kid_from_student(student, configured)
        if not kid:
            names.append(student.get("firstName") or "?")
            continue
        matched += 1
        pid = student["personID"]
        roster = as_list(campus.get_json(f"/campus/resources/portal/roster?personID={pid}"))
        assignments = as_list(campus.get_json(f"/campus/api/portal/assignment/listView?personID={pid}"))
        cal_id = None
        for en in student.get("enrollments") or []:
            if en.get("showOnPortal"):
                cal_id = en.get("calendarID")
                break
        if cal_id is None and student.get("enrollments"):
            cal_id = student["enrollments"][0].get("calendarID")
        instructional = []
        if cal_id:
            instructional = as_list(
                campus.get_json(f"/campus/resources/calendar/instructionalDay?calendarID={cal_id}")
            )
        grades_json = None
        for path in (
            f"/campus/resources/portal/grades?personID={pid}",
            f"/campus/api/portal/grades?personID={pid}",
        ):
            try:
                grades_json = campus.get_json(path)
                if grades_json:
                    break
            except RuntimeError:
                continue
        schedule = today_schedule(roster, instructional, now)
        buckets = bucket_assignments(assignments, now)
        grades = course_grades(grades_json, now)
        publish_kid(ha, kid, schedule, buckets, grades)
        LOG.info(
            "%s: periods=%s missing=%s due_today=%s due_tomorrow=%s scores=%s grades=%s",
            kid["slug"],
            len(schedule),
            len(buckets["missing"]),
            len(buckets["due_today"]),
            len(buckets["due_tomorrow"]),
            len(buckets["recent_scores"]),
            len(grades),
        )
    if matched == 0:
        publish_status(
            ha,
            "no_match",
            {
                "detail": "no students matched CAMPUS_KIDS (or the parent account has none)",
                "seen": names[:10],
            },
        )
        return
    publish_status(
        ha,
        "ok",
        {
            "last_success": now.isoformat(),
            "kids": matched,
            "unmatched": names,
        },
    )


def seconds_until_next(now: datetime) -> float:
    candidates = []
    for h in poll_hours():
        t = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        candidates.append(t)
    nxt = min(candidates)
    return max(30.0, (nxt - now).total_seconds())


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ha_base = env("HA_BASE_URL", "http://127.0.0.1:8123")
    token = env("HA_TOKEN")
    if not token:
        LOG.error("HA_TOKEN is required (Home Assistant long-lived access token)")
        return 1
    once = "--once" in sys.argv
    fire = "--now" in sys.argv or once or env("CAMPUS_RUN_ON_START", "1") == "1"

    def ha_client() -> HA:
        return HA(ha_base, token)

    def safe_run():
        try:
            run_once(ha_client())
        except Exception as e:
            LOG.exception("poll failed")
            try:
                publish_status(ha_client(), "error", {"detail": str(e)[:300]})
            except Exception:
                pass

    if fire:
        safe_run()
    if once:
        return 0
    hours = ",".join(f"{h:02d}:00" for h in poll_hours())
    while True:
        wait = seconds_until_next(now_local())
        LOG.info("sleeping %.0fs until next %s pull", wait, hours)
        time.sleep(wait)
        safe_run()


if __name__ == "__main__":
    raise SystemExit(main())
