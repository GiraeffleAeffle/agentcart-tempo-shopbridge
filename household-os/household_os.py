#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import html
import http.cookies
import json
import os
import pathlib
import queue
import re
import secrets
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo


TASK_ROUTE = re.compile(r"^/api/vikunja/tasks/([0-9]+)/(complete|due-date|comment|description)$")
SAFE_SCRIPT_ROUTE = re.compile(r"^/api/ha/scripts/([A-Za-z0-9_.-]+)$")
CHAT_JOB_EVENTS_ROUTE = re.compile(r"^/api/openclaw/chat/jobs/([A-Za-z0-9_-]+)/events$")
ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
SESSION_COOKIE = "household_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
LOGIN_USERS = {"demo"}
CHAT_JOB_RETENTION_SECONDS = 60 * 30
HTML_BLOCK_RE = re.compile(r"<(p|h[1-6]|ul|ol|li|blockquote|div|table|strong|em|br|span|a)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<]+")
CYCLE_CALENDAR_ROUTE = "/calendar/cycle-support.ics"
TASK_CALENDAR_ROUTE = "/calendar/vikunja-tasks.ics"
CYCLE_EVENT_LABELS = {
    "rest": "Cycle support - rest window",
    "planning": "Cycle support - planning window",
    "ovulation": "Cycle support - ovulation estimate",
    "steady": "Cycle support - steady window",
    "sensitive": "Cycle support - low-friction window",
    "next": "Cycle support - expected next cycle",
}


class HouseholdError(Exception):
    status = 500

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class BadRequest(HouseholdError):
    status = 400


class Unauthorized(HouseholdError):
    status = 401


class Forbidden(HouseholdError):
    status = 403


class NotFound(HouseholdError):
    status = 404


class UpstreamError(HouseholdError):
    status = 502


@dataclass(frozen=True)
class Config:
    bind: str
    port: int
    timezone: str
    household_token: str
    audit_log_path: pathlib.Path
    chat_history_path: pathlib.Path
    session_path: pathlib.Path
    vikunja_api_url: str
    vikunja_web_url: str
    vikunja_token: str
    homeassistant_url: str
    homeassistant_token: str
    openclaw_gateway_url: str
    openclaw_gateway_token: str
    notify_services: tuple[str, ...]
    shopping_todo_entity: str
    co2_entity_ids: tuple[str, ...]
    window_entity_ids: tuple[str, ...]
    co2_threshold_ppm: int
    allowed_script_ids: tuple[str, ...]
    cycle_calendar_enabled: bool
    cycle_calendar_token: str
    cycle_calendar_start_date: str
    cycle_calendar_length_days: int
    cycle_calendar_period_days: int
    cycle_calendar_months_ahead: int
    task_calendar_enabled: bool
    task_calendar_token: str
    task_calendar_days_past: int
    task_calendar_days_ahead: int
    task_calendar_event_minutes: int
    agentcart_url: str = ""
    agentcart_token: str = ""
    agentcart_approval_wait_seconds: int = 180

    @classmethod
    def from_env(cls) -> "Config":
        cycle_token = os.getenv("CYCLE_CALENDAR_TOKEN", "")
        return cls(
            bind=os.getenv("HOUSEHOLD_OS_BIND", "127.0.0.1"),
            port=int(os.getenv("HOUSEHOLD_OS_PORT", "8088")),
            timezone=os.getenv("HOUSEHOLD_OS_TIMEZONE", "Europe/Berlin"),
            household_token=os.getenv("HOUSEHOLD_OS_TOKEN", ""),
            audit_log_path=pathlib.Path(os.getenv("AUDIT_LOG_PATH", "./audit.jsonl")),
            chat_history_path=pathlib.Path(os.getenv("CHAT_HISTORY_PATH", "./chat.jsonl")),
            session_path=pathlib.Path(os.getenv("SESSION_PATH", "./sessions.json")),
            vikunja_api_url=os.getenv("VIKUNJA_API_URL", "http://vikunja:3456/api/v1").rstrip("/"),
            vikunja_web_url=(os.getenv("VIKUNJA_WEB_URL") or os.getenv("VIKUNJA_SERVICE_PUBLICURL", "")).rstrip("/"),
            vikunja_token=os.getenv("VIKUNJA_TOKEN", ""),
            homeassistant_url=os.getenv("HOMEASSISTANT_URL", "http://homeassistant.local:8123").rstrip("/"),
            homeassistant_token=os.getenv("HOMEASSISTANT_TOKEN", ""),
            openclaw_gateway_url=os.getenv("OPENCLAW_GATEWAY_URL", "").rstrip("/"),
            openclaw_gateway_token=os.getenv("OPENCLAW_GATEWAY_TOKEN", ""),
            notify_services=csv_env("HA_NOTIFY_SERVICES"),
            shopping_todo_entity=os.getenv("HA_SHOPPING_TODO_ENTITY", "todo.shopping_list"),
            co2_entity_ids=csv_env("HA_CO2_ENTITY_IDS"),
            window_entity_ids=csv_env("HA_WINDOW_ENTITY_IDS"),
            co2_threshold_ppm=int(os.getenv("HA_CO2_THRESHOLD_PPM", "1000")),
            allowed_script_ids=csv_env("HA_ALLOWED_SCRIPT_IDS"),
            cycle_calendar_enabled=env_bool("CYCLE_CALENDAR_ENABLED", False),
            cycle_calendar_token=cycle_token,
            cycle_calendar_start_date=os.getenv("CYCLE_CALENDAR_START_DATE", ""),
            cycle_calendar_length_days=int(os.getenv("CYCLE_CALENDAR_LENGTH_DAYS", "28")),
            cycle_calendar_period_days=int(os.getenv("CYCLE_CALENDAR_PERIOD_DAYS", "5")),
            cycle_calendar_months_ahead=int(os.getenv("CYCLE_CALENDAR_MONTHS_AHEAD", "6")),
            task_calendar_enabled=env_bool("TASK_CALENDAR_ENABLED", False),
            task_calendar_token=os.getenv("TASK_CALENDAR_TOKEN") or cycle_token,
            task_calendar_days_past=int(os.getenv("TASK_CALENDAR_DAYS_PAST", "14")),
            task_calendar_days_ahead=int(os.getenv("TASK_CALENDAR_DAYS_AHEAD", "180")),
            task_calendar_event_minutes=int(os.getenv("TASK_CALENDAR_EVENT_MINUTES", "30")),
            agentcart_url=os.getenv("AGENTCART_URL", "").rstrip("/"),
            agentcart_token=os.getenv("AGENTCART_TOKEN", ""),
            agentcart_approval_wait_seconds=int(os.getenv("AGENTCART_APPROVAL_WAIT_SECONDS", "180")),
        )


def csv_env(name: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in os.getenv(name, "").split(",") if part.strip())


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def json_default(value: Any) -> str:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def inline_html(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return URL_RE.sub(lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>', escaped)


def description_to_vikunja_html(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if HTML_BLOCK_RE.search(text):
        return text

    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{inline_html(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if not list_items:
            list_type = None
            return
        if list_type == "task":
            blocks.append('<ul data-type="taskList">' + "".join(list_items) + "</ul>")
        else:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
        list_items.clear()
        list_type = None

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(len(heading.group(1)) + 1, 6)
            blocks.append(f"<h{level}>{inline_html(heading.group(2))}</h{level}>")
            continue

        task_item = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", line)
        if task_item:
            flush_paragraph()
            if list_type not in (None, "task"):
                flush_list()
            list_type = "task"
            checked = task_item.group(1).lower() == "x"
            checked_attr = ' checked="checked"' if checked else ""
            list_items.append(
                f'<li data-type="taskItem" data-checked="{str(checked).lower()}">'
                f"<label><input type=\"checkbox\"{checked_attr}><span></span></label>"
                f"<div><p>{inline_html(task_item.group(2))}</p></div></li>"
            )
            continue

        bullet = re.match(r"^-\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            if list_type not in (None, "bullet"):
                flush_list()
            list_type = "bullet"
            list_items.append(f"<li><p>{inline_html(bullet.group(1))}</p></li>")
            continue

        if list_type:
            flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "".join(blocks)


def build_url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    if not path.startswith("/"):
        path = "/" + path
    url = base_url.rstrip("/") + path
    if query:
        clean_query = {
            key: value
            for key, value in query.items()
            if value is not None and value != "" and value != []
        }
        if clean_query:
            url += "?" + urllib.parse.urlencode(clean_query, doseq=True)
    return url


def request_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 20,
) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, default=json_default).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return None
            return parse_response_body(raw, response.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as error:
        raw = error.read()
        detail = parse_response_body(raw, error.headers.get("Content-Type", "")) if raw else None
        raise UpstreamError(
            f"Upstream returned HTTP {error.code}",
            detail={"url": redact_url(url), "status": error.code, "body": detail},
        ) from error
    except urllib.error.URLError as error:
        raise UpstreamError(f"Could not reach upstream service: {error.reason}") from error


def parse_response_body(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8")
    if "json" in content_type or text[:1] in ("{", "["):
        return json.loads(text)
    return text


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "done", "completed"}:
        return True
    if normalized in {"false", "0", "no", "n", "open", "needs_action"}:
        return False
    raise BadRequest(f"Invalid boolean value: {value}")


def parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    return dt.date.fromisoformat(str(value)[:10])


def parse_datetime(value: Any) -> dt.datetime | None:
    if value in (None, "", "0001-01-01T00:00:00Z"):
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.year <= 1:
        return None
    return parsed


def cycle_support_events(
    *,
    start_date: dt.date,
    cycle_length_days: int = 28,
    period_days: int = 5,
    months_ahead: int = 6,
    today: dt.date | None = None,
) -> list[dict[str, Any]]:
    if cycle_length_days < 21 or cycle_length_days > 45:
        raise BadRequest("CYCLE_CALENDAR_LENGTH_DAYS must be between 21 and 45")
    if period_days < 1 or period_days > 10:
        raise BadRequest("CYCLE_CALENDAR_PERIOD_DAYS must be between 1 and 10")
    if months_ahead < 1 or months_ahead > 18:
        raise BadRequest("CYCLE_CALENDAR_MONTHS_AHEAD must be between 1 and 18")

    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=months_ahead * 31)
    cycle_start = start_date
    while cycle_start + dt.timedelta(days=cycle_length_days) < today - dt.timedelta(days=14):
        cycle_start += dt.timedelta(days=cycle_length_days)

    events: list[dict[str, Any]] = []
    while cycle_start <= horizon:
        definitions = [
            (
                "rest",
                cycle_start,
                cycle_start + dt.timedelta(days=period_days),
                "Check in gently. Keep plans flexible and make practical support easy: food, warmth, errands, chores.",
            ),
            (
                "planning",
                cycle_start + dt.timedelta(days=period_days),
                cycle_start + dt.timedelta(days=13),
                "Good window for plans, errands, and household momentum when the household wants support.",
            ),
            (
                "ovulation",
                cycle_start + dt.timedelta(days=8),
                cycle_start + dt.timedelta(days=15),
                "Approximate only. Be attentive, do not assume mood/libido, and do not use this as contraception.",
            ),
            (
                "steady",
                cycle_start + dt.timedelta(days=14),
                cycle_start + dt.timedelta(days=21),
                "Finish open household tasks and reduce decision load before the low-friction window.",
            ),
            (
                "sensitive",
                cycle_start + dt.timedelta(days=21),
                cycle_start + dt.timedelta(days=cycle_length_days),
                "Reduce friction. Handle chores early, avoid unnecessary conflict, and ask what support would help.",
            ),
            (
                "next",
                cycle_start + dt.timedelta(days=cycle_length_days),
                cycle_start + dt.timedelta(days=cycle_length_days + 1),
                "Expected next cycle start. Check in gently and make comfort/supplies easy.",
            ),
        ]
        for kind, start, end, description in definitions:
            if end <= start:
                continue
            events.append(
                {
                    "uid": f"cycle-support-{cycle_start.isoformat()}-{kind}@household-os",
                    "summary": CYCLE_EVENT_LABELS[kind],
                    "description": description,
                    "start": start,
                    "end": end,
                }
            )
        cycle_start += dt.timedelta(days=cycle_length_days)
    return events


def ical_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ical_fold(line: str) -> list[str]:
    if len(line.encode("utf-8")) <= 75:
        return [line]
    folded: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if current and len(candidate.encode("utf-8")) > 75:
            folded.append(current)
            current = " " + char
        else:
            current = candidate
    if current:
        folded.append(current)
    return folded


def render_cycle_calendar(config: Config, *, now: dt.datetime | None = None) -> str:
    start_date = parse_date(config.cycle_calendar_start_date)
    if start_date is None:
        raise BadRequest("CYCLE_CALENDAR_START_DATE is not configured")
    now = now or dt.datetime.now(dt.timezone.utc)
    events = cycle_support_events(
        start_date=start_date,
        cycle_length_days=config.cycle_calendar_length_days,
        period_days=config.cycle_calendar_period_days,
        months_ahead=config.cycle_calendar_months_ahead,
        today=now.astimezone(ZoneInfo(config.timezone)).date(),
    )
    dtstamp = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Household OS//Cycle Support//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Cycle Support",
        f"X-WR-TIMEZONE:{ical_escape(config.timezone)}",
    ]
    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{ical_escape(str(event['uid']))}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{event['start'].strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{event['end'].strftime('%Y%m%d')}",
                f"SUMMARY:{ical_escape(str(event['summary']))}",
                f"DESCRIPTION:{ical_escape(str(event['description']))}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in ical_fold(line)) + "\r\n"


def strip_html_text(value: str, *, limit: int = 500) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|h[1-6]|div)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def task_link(config: Config, task: dict[str, Any]) -> str:
    if not config.vikunja_web_url or not task.get("id"):
        return ""
    return f"{config.vikunja_web_url}/tasks/{task['id']}"


def calendar_task_description(config: Config, task: dict[str, Any], project_name: str) -> str:
    parts = [f"Project: {project_name}"]
    assignees = ", ".join(user["username"] for user in task.get("assignees") or [] if user.get("username"))
    labels = ", ".join(label["title"] for label in task.get("labels") or [] if label.get("title"))
    if assignees:
        parts.append(f"Assigned: {assignees}")
    if labels:
        parts.append(f"Labels: {labels}")
    link = task_link(config, task)
    if link:
        parts.append(f"Vikunja: {link}")
    description = strip_html_text(str(task.get("description") or ""))
    if description:
        parts.append("")
        parts.append(description)
    return "\n".join(parts)


def task_calendar_events(
    config: Config,
    tasks: list[dict[str, Any]],
    projects: dict[Any, str],
    *,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    tz = ZoneInfo(config.timezone)
    now = now or dt.datetime.now(tz)
    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    start_window = local_now.date() - dt.timedelta(days=max(config.task_calendar_days_past, 0))
    end_window = local_now.date() + dt.timedelta(days=max(config.task_calendar_days_ahead, 1))
    duration = dt.timedelta(minutes=max(config.task_calendar_event_minutes, 5))
    events: list[dict[str, Any]] = []

    for task in tasks:
        if task.get("done"):
            continue
        due = parse_datetime(task.get("due_date"))
        if due is None:
            continue
        local_due = due.astimezone(tz) if due.tzinfo else due.replace(tzinfo=tz)
        if local_due.date() < start_window or local_due.date() > end_window:
            continue
        project_name = projects.get(task.get("project_id"), f"Project {task.get('project_id')}")
        title = str(task.get("title") or "Untitled task").strip() or "Untitled task"
        all_day = local_due.time() == dt.time(0, 0)
        event: dict[str, Any] = {
            "uid": f"vikunja-task-{task.get('id')}-due@household-os",
            "summary": f"Task due: {title}",
            "description": calendar_task_description(config, task, str(project_name)),
            "url": task_link(config, task),
            "all_day": all_day,
        }
        if all_day:
            event["start"] = local_due.date()
            event["end"] = local_due.date() + dt.timedelta(days=1)
        else:
            event["start"] = local_due
            event["end"] = local_due + duration
        events.append(event)

    return sorted(events, key=lambda event: event["start"])


def render_task_calendar(
    config: Config,
    tasks: list[dict[str, Any]],
    projects: dict[Any, str],
    *,
    now: dt.datetime | None = None,
) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    events = task_calendar_events(config, tasks, projects, now=now)
    dtstamp = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Household OS//Vikunja Tasks//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Household Tasks",
        f"X-WR-TIMEZONE:{ical_escape(config.timezone)}",
    ]
    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{ical_escape(str(event['uid']))}",
                f"DTSTAMP:{dtstamp}",
                f"SUMMARY:{ical_escape(str(event['summary']))}",
                f"DESCRIPTION:{ical_escape(str(event['description']))}",
                "TRANSP:TRANSPARENT",
            ]
        )
        if event.get("url"):
            lines.append(f"URL:{ical_escape(str(event['url']))}")
        if event["all_day"]:
            lines.extend(
                [
                    f"DTSTART;VALUE=DATE:{event['start'].strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{event['end'].strftime('%Y%m%d')}",
                ]
            )
        else:
            lines.extend(
                [
                    f"DTSTART;TZID={ical_escape(config.timezone)}:{event['start'].strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID={ical_escape(config.timezone)}:{event['end'].strftime('%Y%m%dT%H%M%S')}",
                ]
            )
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in ical_fold(line)) + "\r\n"


def cycle_calendar_context(config: Config, *, now: dt.datetime | None = None) -> dict[str, Any]:
    start_date = parse_date(config.cycle_calendar_start_date)
    if not config.cycle_calendar_enabled or start_date is None:
        return {"enabled": False}
    tz = ZoneInfo(config.timezone)
    now = now or dt.datetime.now(tz)
    today = now.astimezone(tz).date() if now.tzinfo else now.date()
    events = cycle_support_events(
        start_date=start_date,
        cycle_length_days=config.cycle_calendar_length_days,
        period_days=config.cycle_calendar_period_days,
        months_ahead=1,
        today=today,
    )
    active = [event for event in events if event["start"] <= today < event["end"]]
    upcoming = [event for event in events if event["start"] > today][:5]
    return {
        "enabled": True,
        "today": today.isoformat(),
        "start_date": start_date.isoformat(),
        "cycle_length_days": config.cycle_calendar_length_days,
        "period_days": config.cycle_calendar_period_days,
        "approximate": True,
        "active": [
            {
                "summary": event["summary"],
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
                "description": event["description"],
            }
            for event in active
        ],
        "upcoming": [
            {
                "summary": event["summary"],
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
            }
            for event in upcoming
        ],
    }


def task_due_date(task: dict[str, Any]) -> dt.date | None:
    due = parse_datetime(task.get("due_date"))
    return due.date() if due else None


def task_reminder_datetimes(task: dict[str, Any]) -> list[dt.datetime]:
    reminders: list[dt.datetime] = []
    for reminder in task.get("reminders") or []:
        value = reminder.get("reminder") if isinstance(reminder, dict) else reminder
        parsed = parse_datetime(value)
        if parsed is not None:
            reminders.append(parsed)
    return reminders


def is_stale(task: dict[str, Any], stale_days: int | None, now: dt.datetime) -> bool:
    if not stale_days:
        return False
    updated = parse_datetime(task.get("updated")) or parse_datetime(task.get("created"))
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=dt.timezone.utc)
    return updated < now.astimezone(dt.timezone.utc) - dt.timedelta(days=stale_days)


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "identifier": task.get("identifier"),
        "title": task.get("title"),
        "project_id": task.get("project_id"),
        "done": task.get("done", False),
        "due_date": task.get("due_date") or None,
        "priority": task.get("priority"),
        "description": task.get("description") or "",
        "labels": [
            {"id": label.get("id"), "title": label.get("title"), "hex_color": label.get("hex_color")}
            for label in task.get("labels") or []
            if isinstance(label, dict)
        ],
        "assignees": [
            {"id": user.get("id"), "username": user.get("username"), "name": user.get("name")}
            for user in task.get("assignees") or []
            if isinstance(user, dict)
        ],
        "reminders": task.get("reminders") or [],
        "repeat_after": task.get("repeat_after") or 0,
        "repeat_mode": task.get("repeat_mode"),
        "created": task.get("created"),
        "updated": task.get("updated"),
        "comment_count": task.get("comment_count"),
    }


def filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    project_id: int | None = None,
    done: bool | None = None,
    due_before: dt.date | None = None,
    due_after: dt.date | None = None,
    stale_days: int | None = None,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or dt.datetime.now(dt.timezone.utc)
    filtered: list[dict[str, Any]] = []
    for task in tasks:
        if project_id is not None and int(task.get("project_id") or 0) != project_id:
            continue
        if done is not None and bool(task.get("done")) is not done:
            continue
        due = task_due_date(task)
        if due_before is not None and (due is None or due > due_before):
            continue
        if due_after is not None and (due is None or due < due_after):
            continue
        if stale_days is not None and not is_stale(task, stale_days, now):
            continue
        filtered.append(normalize_task(task))
    return filtered


class VikunjaClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, **query: Any) -> Any:
        self._require_token()
        return request_json(
            method,
            build_url(self.config.vikunja_api_url, path, query or None),
            self.config.vikunja_token,
            payload,
        )

    def verify_login(self, username: str, password: str) -> None:
        request_json(
            "POST",
            build_url(self.config.vikunja_api_url, "/login"),
            "",
            {"username": username, "password": password, "long_token": False},
        )

    def _require_token(self) -> None:
        if not self.config.vikunja_token:
            raise UpstreamError("VIKUNJA_TOKEN is not configured")

    def list_projects(self) -> list[dict[str, Any]]:
        projects = self._request("GET", "/projects", per_page=100, is_archived=False, expand="permissions")
        return [
            {
                "id": project.get("id"),
                "title": project.get("title"),
                "identifier": project.get("identifier"),
                "parent_project_id": project.get("parent_project_id"),
                "is_archived": project.get("is_archived", False),
                "max_permission": project.get("max_permission"),
            }
            for project in projects
        ]

    def list_tasks(
        self,
        *,
        project_id: int | None = None,
        done: bool | None = None,
        due_before: dt.date | None = None,
        due_after: dt.date | None = None,
        stale_days: int | None = None,
        include_comments: bool = False,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        expand = ["comment_count"]
        if include_comments:
            expand.append("comments")

        for page in range(1, 11):
            page_tasks = self._request(
                "GET",
                "/tasks",
                page=page,
                per_page=100,
                sort_by="due_date",
                order_by="asc",
                expand=expand,
            )
            if not page_tasks:
                break
            tasks.extend(page_tasks)
            if len(page_tasks) < 100:
                break

        return filter_tasks(
            tasks,
            project_id=project_id,
            done=done,
            due_before=due_before,
            due_after=due_after,
            stale_days=stale_days,
        )

    def get_task(self, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}", expand="comments")

    def create_task(
        self,
        *,
        project_id: int,
        title: str,
        description: str = "",
        due_date: str | None = None,
        priority: int | None = None,
        repeat_after: int | None = None,
        repeat_mode: int | None = None,
        reminders: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise BadRequest("Task title is required")
        payload: dict[str, Any] = {"title": title.strip()}
        if description:
            payload["description"] = description_to_vikunja_html(description)
        if due_date:
            payload["due_date"] = due_date
        if priority is not None:
            payload["priority"] = priority
        if repeat_after is not None:
            payload["repeat_after"] = repeat_after
        if repeat_mode is not None:
            payload["repeat_mode"] = repeat_mode
        if reminders is not None:
            payload["reminders"] = reminders
        return normalize_task(self._request("PUT", f"/projects/{project_id}/tasks", payload))

    def update_task(self, task_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_task(task_id)
        payload = {
            "id": task_id,
            "title": current.get("title"),
            "project_id": current.get("project_id"),
            "description": current.get("description") or "",
            "due_date": current.get("due_date"),
            "done": current.get("done", False),
            "priority": current.get("priority"),
            "repeat_after": current.get("repeat_after") or 0,
            "repeat_mode": current.get("repeat_mode"),
            "reminders": current.get("reminders") or [],
        }
        payload.update({key: value for key, value in updates.items() if value is not None})
        return normalize_task(self._request("POST", f"/tasks/{task_id}", payload))

    def complete_task(self, task_id: int) -> dict[str, Any]:
        return self.update_task(task_id, {"done": True})

    def update_due_date(self, task_id: int, due_date: str | None) -> dict[str, Any]:
        return self.update_task(task_id, {"due_date": due_date or None})

    def update_description(self, task_id: int, description: str) -> dict[str, Any]:
        return self.update_task(task_id, {"description": description_to_vikunja_html(description)})

    def add_comment(self, task_id: int, comment: str) -> dict[str, Any]:
        if not comment.strip():
            raise BadRequest("Comment is required")
        return self._request("PUT", f"/tasks/{task_id}/comments", {"comment": comment.strip()})

    def weekly_summary(self, timezone: str) -> dict[str, Any]:
        tz = ZoneInfo(timezone)
        now = dt.datetime.now(tz)
        today = now.date()
        projects = {project["id"]: project["title"] for project in self.list_projects()}
        open_tasks = self.list_tasks(done=False)

        overdue: list[dict[str, Any]] = []
        due_this_week: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        no_due: list[dict[str, Any]] = []
        for task in open_tasks:
            due = task_due_date(task)
            if due is None:
                no_due.append(task)
            elif due < today:
                overdue.append(task)
            elif due <= today + dt.timedelta(days=7):
                due_this_week.append(task)
            if is_stale(task, 30, now):
                stale.append(task)

        def project_name(task: dict[str, Any]) -> str:
            return projects.get(task.get("project_id"), f"project {task.get('project_id')}")

        lines = [
            f"Open household tasks: {len(open_tasks)}",
            f"Overdue: {len(overdue)}",
            f"Due in the next 7 days: {len(due_this_week)}",
            f"Stale for 30+ days: {len(stale)}",
            f"Without due date: {len(no_due)}",
        ]
        for label, bucket in (("Overdue", overdue[:5]), ("Stale", stale[:5]), ("Soon", due_this_week[:5])):
            if bucket:
                lines.append(label + ":")
                for task in bucket:
                    due_text = (task_due_date(task) or "no due date")
                    lines.append(f"- {task['title']} ({project_name(task)}, due {due_text})")

        return {
            "generated_at": now.isoformat(),
            "counts": {
                "open": len(open_tasks),
                "overdue": len(overdue),
                "due_this_week": len(due_this_week),
                "stale_30_days": len(stale),
                "no_due_date": len(no_due),
            },
            "overdue": overdue[:20],
            "due_this_week": due_this_week[:20],
            "stale": stale[:20],
            "text": "\n".join(lines),
        }

    def daily_summary(self, timezone: str, days: int = 3) -> dict[str, Any]:
        days = max(1, min(int(days), 14))
        tz = ZoneInfo(timezone)
        now = dt.datetime.now(tz)
        today = now.date()
        projects = {project["id"]: project["title"] for project in self.list_projects()}
        open_tasks = self.list_tasks(done=False)

        overdue: list[dict[str, Any]] = []
        due_today: list[dict[str, Any]] = []
        due_tomorrow: list[dict[str, Any]] = []
        upcoming: list[dict[str, Any]] = []
        reminder_window: list[dict[str, Any]] = []
        reminder_until = now + dt.timedelta(hours=24)

        for task in open_tasks:
            due = task_due_date(task)
            if due is not None:
                if due < today:
                    overdue.append(task)
                elif due == today:
                    due_today.append(task)
                elif due == today + dt.timedelta(days=1):
                    due_tomorrow.append(task)
                elif due <= today + dt.timedelta(days=days):
                    upcoming.append(task)

            for reminder in task_reminder_datetimes(task):
                localized = reminder.astimezone(tz) if reminder.tzinfo else reminder.replace(tzinfo=tz)
                if now <= localized <= reminder_until:
                    reminder_window.append(task)
                    break

        def sort_key(task: dict[str, Any]) -> tuple[dt.date, str]:
            return (task_due_date(task) or dt.date.max, str(task.get("title") or ""))

        for bucket in (overdue, due_today, due_tomorrow, upcoming, reminder_window):
            bucket.sort(key=sort_key)

        def project_name(task: dict[str, Any]) -> str:
            return projects.get(task.get("project_id"), f"project {task.get('project_id')}")

        def due_text(task: dict[str, Any]) -> str:
            due = task_due_date(task)
            if due is None:
                return "no due date"
            delta = (due - today).days
            if delta < 0:
                return f"{abs(delta)}d overdue"
            if delta == 0:
                return "today"
            if delta == 1:
                return "tomorrow"
            return f"in {delta}d"

        def task_line(task: dict[str, Any]) -> str:
            return f"- {task['title']} ({project_name(task)}, {due_text(task)})"

        lines = [
            "Household task digest",
            f"Overdue: {len(overdue)} | Today: {len(due_today)} | Tomorrow: {len(due_tomorrow)} | Next {days}d: {len(upcoming)}",
        ]
        for label, bucket in (
            ("Overdue", overdue[:6]),
            ("Today", due_today[:6]),
            ("Tomorrow", due_tomorrow[:5]),
            (f"Next {days}d", upcoming[:5]),
            ("Reminders in next 24h", reminder_window[:5]),
        ):
            if bucket:
                lines.append(label + ":")
                lines.extend(task_line(task) for task in bucket)

        if not any((overdue, due_today, due_tomorrow, upcoming, reminder_window)):
            lines.append("Nothing urgent is due. Use Vikunja for backlog planning.")
        if self.config.vikunja_web_url:
            lines.append(f"Vikunja: {self.config.vikunja_web_url}")

        return {
            "generated_at": now.isoformat(),
            "days": days,
            "counts": {
                "open": len(open_tasks),
                "overdue": len(overdue),
                "today": len(due_today),
                "tomorrow": len(due_tomorrow),
                "upcoming": len(upcoming),
                "reminders_next_24h": len(reminder_window),
            },
            "overdue": overdue[:20],
            "today": due_today[:20],
            "tomorrow": due_tomorrow[:20],
            "upcoming": upcoming[:20],
            "reminders_next_24h": reminder_window[:20],
            "text": "\n".join(lines),
        }


class HomeAssistantClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        self._require_token()
        return request_json(method, build_url(self.config.homeassistant_url, path), self.config.homeassistant_token, payload)

    def _require_token(self) -> None:
        if not self.config.homeassistant_token:
            raise UpstreamError("HOMEASSISTANT_TOKEN is not configured")

    def state(self, entity_id: str) -> dict[str, Any]:
        ensure_entity_id(entity_id)
        return self._request("GET", f"/api/states/{entity_id}")

    def notify(self, title: str, message: str) -> dict[str, Any]:
        if not self.config.notify_services:
            raise BadRequest("HA_NOTIFY_SERVICES is empty")
        results: dict[str, Any] = {}
        for service in self.config.notify_services:
            domain, service_name = parse_service(service, expected_domain="notify")
            results[service] = self._request(
                "POST",
                f"/api/services/{domain}/{service_name}",
                {"title": title, "message": message},
            )
        return {"sent": list(results.keys()), "results": results}

    def add_shopping_item(self, item: str, description: str = "", due_date: str | None = None) -> dict[str, Any]:
        if not item.strip():
            raise BadRequest("Shopping item is required")
        ensure_entity_id(self.config.shopping_todo_entity)
        payload: dict[str, Any] = {"entity_id": self.config.shopping_todo_entity, "item": item.strip()}
        if description:
            payload["description"] = description
        if due_date:
            payload["due_date"] = due_date
        return self._request("POST", "/api/services/todo/add_item", payload)

    def ventilation_status(self) -> dict[str, Any]:
        co2_states = [self.state(entity_id) for entity_id in self.config.co2_entity_ids]
        window_states = [self.state(entity_id) for entity_id in self.config.window_entity_ids]
        high_co2 = [
            state
            for state in co2_states
            if numeric_state(state) is not None and numeric_state(state) >= self.config.co2_threshold_ppm
        ]
        open_windows = [state for state in window_states if str(state.get("state")).lower() in {"on", "open"}]
        return {
            "threshold_ppm": self.config.co2_threshold_ppm,
            "needs_lueften": bool(high_co2 and not open_windows),
            "co2": compact_states(co2_states),
            "windows": compact_states(window_states),
        }

    def trigger_safe_script(self, script_id: str) -> dict[str, Any]:
        ensure_entity_id(script_id)
        if script_id not in self.config.allowed_script_ids:
            raise Forbidden(f"Script is not allowlisted: {script_id}")
        return self._request("POST", "/api/services/script/turn_on", {"entity_id": script_id})


class OpenClawClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.config.openclaw_gateway_url or not self.config.openclaw_gateway_token:
            raise UpstreamError("OpenClaw gateway URL or token is not configured")
        payload = {
            "model": "openclaw/main",
            "messages": messages,
            "stream": False,
        }
        response = request_json(
            "POST",
            build_url(self.config.openclaw_gateway_url, "/v1/chat/completions"),
            self.config.openclaw_gateway_token,
            payload,
            timeout=300,
        )
        choices = response.get("choices", []) if isinstance(response, dict) else []
        if not choices:
            raise UpstreamError("OpenClaw returned no choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not content.strip():
            raise UpstreamError("OpenClaw returned an empty response")
        return content.strip()


class AgentCartClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def configured(self) -> bool:
        return bool(self.config.agentcart_url and self.config.agentcart_token)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        query: dict[str, Any] | None = None,
        authorization: str = "",
        timeout: int = 30,
        allow_statuses: tuple[int, ...] = tuple(range(200, 300)),
    ) -> tuple[int, dict[str, str], Any]:
        if not self.config.agentcart_url or not self.config.agentcart_token:
            raise UpstreamError("AgentCart URL or token is not configured")
        body = None
        headers = {
            "Accept": "application/json",
            "X-AgentCart-Token": self.config.agentcart_token,
        }
        if authorization:
            headers["Authorization"] = authorization
        if payload is not None:
            body = json.dumps(payload, default=json_default, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            build_url(self.config.agentcart_url, path, query),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                parsed = parse_response_body(raw, response.headers.get("Content-Type", "")) if raw else None
                return response.status, dict(response.headers.items()), parsed
        except urllib.error.HTTPError as error:
            raw = error.read()
            parsed = parse_response_body(raw, error.headers.get("Content-Type", "")) if raw else None
            if error.code in allow_statuses:
                return error.code, dict(error.headers.items()), parsed
            raise UpstreamError(
                f"AgentCart returned HTTP {error.code}",
                detail={"path": path, "status": error.code, "body": parsed},
            ) from error
        except urllib.error.URLError as error:
            raise UpstreamError(f"Could not reach AgentCart: {error.reason}") from error

    def list_open_tasks(self, *, limit: int = 8) -> dict[str, Any]:
        return self.request("GET", "/v1/tasks/open", query={"limit": limit})[2]

    def energy_surplus(self) -> dict[str, Any]:
        return self.request("GET", "/v1/energy/surplus")[2]

    def dashboard_state(self) -> dict[str, Any]:
        return self.request("GET", "/v1/dashboard/state")[2]

    def search_catalog(self, query: str) -> dict[str, Any]:
        return self.request("GET", "/v1/catalog/search", query={"q": query}, timeout=30)[2]

    def quote_tournament(self, query: str, *, quantity: int = 1) -> dict[str, Any]:
        return self.request(
            "GET",
            "/v1/quote-tournament",
            query={"q": query, "country": "DE", "postal_code": "10115", "quantity": quantity},
            timeout=60,
        )[2]

    def get_quote(self, quote_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/quotes/{urllib.parse.quote(quote_id)}", timeout=30)[2]

    def create_energy_offer(self) -> dict[str, Any]:
        payload = {
            "buyer_scope": "neighbor-demo",
            "price_cents_per_kwh": 18,
            "market_reference_cents_per_kwh": 30,
            "feed_in_reference_cents_per_kwh": 8,
            "duration_minutes": 30,
            "valid_minutes": 15,
        }
        return self.request("POST", "/v1/energy/offers", payload, timeout=60)[2]

    def accept_energy_offer(self, offer_id: str) -> dict[str, Any]:
        payload = {
            "buyer_id": "neighbor-demo",
            "buyer_display_name": "Demo Neighbour",
        }
        return self.request("POST", f"/v1/energy/offers/{urllib.parse.quote(offer_id)}/accept", payload, timeout=120)[2]

    def create_quote(self, reason: str, *, product_id: str = "tea_hazels_chocolate_100g", quantity: int = 1) -> dict[str, Any]:
        payload = {
            "agent_id": "household-os-chat",
            "reason": reason,
            "items": [{"product_id": product_id, "quantity": quantity}],
            "ship_to": {"country": "DE", "postal_code": "10115"},
        }
        return self.request("POST", "/v1/quotes", payload, timeout=30)[2]

    def create_approval(self, quote_id: str) -> dict[str, Any]:
        payload = {
            "quote_id": quote_id,
            "channel": "household_os_chat",
            "delivery_channels": ["chat", "home_assistant", "web", "api"],
        }
        return self.request("POST", "/v1/approvals", payload, timeout=30)[2]

    def approval_status(self, approval_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v1/approvals/{urllib.parse.quote(approval_id)}", timeout=15)[2]

    def decide_approval(self, approval_id: str, token: str, decision: str, *, approver: str) -> dict[str, Any]:
        payload = {
            "decision": decision,
            "token": token,
            "approver": approver,
        }
        return self.request("POST", f"/v1/approvals/{urllib.parse.quote(approval_id)}/decision", payload, timeout=30)[2]

    def checkout(self, quote_id: str, approval_id: str) -> dict[str, Any]:
        payload = {
            "quote_id": quote_id,
            "approval_id": approval_id,
            "idempotency_key": f"household-os-chat-{approval_id}",
        }
        status, _headers, body = self.request(
            "POST",
            "/v1/checkout",
            payload,
            timeout=120,
            allow_statuses=tuple(list(range(200, 300)) + [402]),
        )
        if status == 402:
            authorization = str((body or {}).get("demo_authorization") or "")
            if not authorization:
                raise UpstreamError("AgentCart payment challenge did not include demo authorization")
            status, _headers, body = self.request(
                "POST",
                "/v1/checkout",
                payload,
                authorization=authorization,
                timeout=120,
                allow_statuses=tuple(range(200, 300)),
            )
        if status not in range(200, 300):
            raise UpstreamError(f"AgentCart checkout failed with HTTP {status}", detail=body)
        return body


@dataclass
class ChatJob:
    id: str
    actor: str
    user_message: str
    created_at: str
    events: queue.Queue[dict[str, Any]]
    status: str = "queued"
    error: str | None = None
    reply: str | None = None
    message: dict[str, Any] | None = None


def ensure_entity_id(entity_id: str) -> None:
    if not ENTITY_ID.match(entity_id):
        raise BadRequest(f"Invalid Home Assistant entity_id: {entity_id}")


def parse_service(service: str, *, expected_domain: str | None = None) -> tuple[str, str]:
    if "." not in service:
        raise BadRequest(f"Invalid Home Assistant service: {service}")
    domain, service_name = service.split(".", 1)
    if expected_domain and domain != expected_domain:
        raise BadRequest(f"Expected {expected_domain} service, got {service}")
    if not re.match(r"^[a-z0-9_]+$", domain) or not re.match(r"^[a-z0-9_]+$", service_name):
        raise BadRequest(f"Invalid Home Assistant service: {service}")
    return domain, service_name


def numeric_state(state: dict[str, Any]) -> float | None:
    try:
        return float(state.get("state"))
    except (TypeError, ValueError):
        return None


def compact_states(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "entity_id": state.get("entity_id"),
            "state": state.get("state"),
            "unit": state.get("attributes", {}).get("unit_of_measurement"),
            "friendly_name": state.get("attributes", {}).get("friendly_name"),
            "last_updated": state.get("last_updated"),
        }
        for state in states
    ]


HOUSEHOLD_TEA_PREFERENCE_WORDS = {"fav", "favorite", "favourite", "preferred", "usual", "regular", "normal", "standard"}
HOUSEHOLD_TEA_CONTEXT_WORDS = {"my", "our", "household"}


def close_to_any(value: str, expected: set[str], *, threshold: float = 0.82) -> bool:
    return value in expected or any(difflib.SequenceMatcher(None, value, candidate).ratio() >= threshold for candidate in expected)


def mentions_household_tea_preference(message: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", message.lower())
    token_set = set(tokens)
    if "hazel" in token_set and "chocolate" in token_set:
        return True
    if "tea" not in token_set:
        return False
    return bool(token_set & HOUSEHOLD_TEA_CONTEXT_WORDS) or any(
        close_to_any(token, HOUSEHOLD_TEA_PREFERENCE_WORDS) for token in tokens
    )


def is_agentcart_demo_message(message: str) -> bool:
    text = message.lower()
    if "agentcart" in text:
        return True
    if mentions_household_tea_preference(message):
        return True
    if any(term in text for term in ("shaver", "detergent", "coffee", "household product", "woocommerce")):
        return True
    if "excess energy" in text or "energy surplus" in text or "sell" in text and "energy" in text:
        return True
    return False


def money(cents: Any, currency: str = "EUR") -> str:
    try:
        amount = int(cents)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount / 100:.2f} {currency}"


def delivery_text(container: dict[str, Any]) -> str:
    window = container.get("delivery_window") or {}
    if window.get("earliest_date") and window.get("latest_date"):
        return f"{window['earliest_date']} to {window['latest_date']} ({window.get('label', 'estimated')})"
    estimate = container.get("delivery_estimate") or {}
    return str(estimate.get("label") or "not available")


def payment_proof_text(receipt: dict[str, Any]) -> str:
    proof = receipt.get("external_value_proof") or {}
    if not proof:
        return "No external value proof attached."
    bits = [
        str(proof.get("provider") or "unknown provider"),
        str(proof.get("state") or "unknown state"),
    ]
    if proof.get("network"):
        bits.append(str(proof["network"]))
    if proof.get("value_transfer") is not None:
        bits.append(f"value_transfer={str(proof.get('value_transfer')).lower()}")
    if proof.get("real_settlement") is not None:
        bits.append(f"real_settlement={str(proof.get('real_settlement')).lower()}")
    body = proof.get("body") if isinstance(proof.get("body"), dict) else {}
    stdout = proof.get("stdout") if isinstance(proof.get("stdout"), dict) else {}
    proof_body = body or stdout
    if proof_body.get("amount"):
        bits.append(f"amount={proof_body['amount']}")
    receipt_reference = proof.get("transaction_reference")
    proof_receipt = proof.get("payment_receipt") if isinstance(proof.get("payment_receipt"), dict) else {}
    if not receipt_reference and proof_receipt.get("reference"):
        receipt_reference = proof_receipt["reference"]
    if receipt_reference:
        bits.append(f"reference={str(receipt_reference)[:12]}...")
    if proof.get("explorer_url"):
        bits.append(f"explorer={proof['explorer_url']}")
    return ", ".join(bits)


def order_items_text(order: dict[str, Any]) -> str:
    items = order.get("items") if isinstance(order.get("items"), list) else []
    if not items:
        return "unknown item"
    return ", ".join(f"{item.get('quantity', 1)}x {item.get('title', 'item')}" for item in items)


def format_agentcart_policy_denial(quote: dict[str, Any]) -> str:
    policy = quote.get("policy_result") or {}
    reasons = policy.get("reasons") if isinstance(policy.get("reasons"), list) else []
    lines = [
        "AgentCart created a quote but household policy denied the purchase.",
        f"- Quote: {quote.get('id')}",
        f"- Product: {order_items_text(quote)}",
        f"- Total: {money(quote.get('total_cents'), quote.get('currency', 'EUR'))}",
    ]
    lines.extend(f"- Policy reason: {reason}" for reason in reasons)
    return "\n".join(lines)


def format_agentcart_pending_approval(quote: dict[str, Any], approval: dict[str, Any]) -> str:
    url = approval.get("decision_url") or approval.get("approval_url")
    return "\n".join(
        [
            "AgentCart is waiting for human approval.",
            f"- Product: {order_items_text(quote)}",
            f"- Total: {money(quote.get('total_cents'), quote.get('currency', 'EUR'))}",
            f"- Delivery estimate: {delivery_text(quote)}",
            f"- Approval id: {approval.get('id')}",
            f"- Approval URL: {url or 'available in the Home Assistant notification'}",
            "Approve in this chat, on the phone/watch notification, or through the approval URL.",
        ]
    )


def format_agentcart_approval_stopped(quote: dict[str, Any], approval: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"AgentCart did not complete checkout because approval is {approval.get('state')}.",
            f"- Product: {order_items_text(quote)}",
            f"- Total: {money(quote.get('total_cents'), quote.get('currency', 'EUR'))}",
            f"- Approval id: {approval.get('id')}",
        ]
    )


def format_agentcart_checkout_summary(checkout: dict[str, Any]) -> str:
    order = checkout.get("order") if isinstance(checkout.get("order"), dict) else {}
    receipt = checkout.get("payment_receipt") if isinstance(checkout.get("payment_receipt"), dict) else order.get("payment_receipt", {})
    lines = [
        "AgentCart completed the tea order after human approval.",
        f"- Product: {order_items_text(order)}",
        f"- Final price: {money(order.get('total_cents'), order.get('currency', 'EUR'))}",
        f"- Delivery window: {delivery_text(order)}",
        f"- Merchant of record: {(order.get('merchant_of_record') or {}).get('name', 'unknown')}",
        f"- Merchant order: {order.get('merchant_order_id') or (order.get('merchant_order') or {}).get('id')}",
        f"- Order id: {order.get('id')}",
        f"- Payment receipt: {receipt.get('id')}",
        f"- Tempo MPP proof: {payment_proof_text(receipt)}",
    ]
    vikunja = order.get("vikunja_task") or {}
    if vikunja:
        lines.append(f"- Vikunja task: {vikunja.get('url') or vikunja.get('state')}")
    calendar = order.get("calendar_event") or {}
    if calendar:
        lines.append(f"- Calendar sync: {calendar.get('state')}")
    agentcart_url = os.getenv("AGENTCART_URL", "").rstrip("/")
    if agentcart_url and order.get("id"):
        lines.append(f"- Proof page: {agentcart_url}/orders/{order.get('id')}")
    lines.append(f"- Audit: open AgentCart dashboard with purchase id {order.get('quote_id')}")
    return "\n".join(lines)


def format_agentcart_order(order: dict[str, Any]) -> str:
    receipt = order.get("payment_receipt") if isinstance(order.get("payment_receipt"), dict) else {}
    shipment = order.get("shipment") if isinstance(order.get("shipment"), dict) else {}
    return "\n".join(
        [
            "Latest AgentCart order:",
            f"- Product: {order_items_text(order)}",
            f"- State: {order.get('state')}",
            f"- Final price: {money(order.get('total_cents'), order.get('currency', 'EUR'))}",
            f"- Delivery window: {delivery_text(order)}",
            f"- Shipment status: {shipment.get('status', 'not_shipped')}",
            f"- Estimated delivery: {shipment.get('estimated_delivery') or 'not available'}",
            f"- Merchant order: {order.get('merchant_order_id')}",
            f"- Payment receipt: {receipt.get('id')}",
            f"- Payment proof: {payment_proof_text(receipt)}",
            f"- Proof page: {os.getenv('AGENTCART_URL', '').rstrip('/') + '/orders/' + str(order.get('id')) if os.getenv('AGENTCART_URL') and order.get('id') else 'open the AgentCart dashboard'}",
        ]
    )


def format_agentcart_energy_trade(result: dict[str, Any]) -> str:
    offer = result.get("offer") if isinstance(result.get("offer"), dict) else {}
    settlement = result.get("settlement") if isinstance(result.get("settlement"), dict) else {}
    receipt = settlement.get("payment_receipt") if isinstance(settlement.get("payment_receipt"), dict) else {}
    telemetry = offer.get("telemetry_snapshot") if isinstance(offer.get("telemetry_snapshot"), dict) else {}
    lines = [
        "AgentCart created and accepted a demo neighbour energy offer.",
        f"- Offer id: {offer.get('id')}",
        f"- Quantity: {offer.get('quantity_kwh')} kWh for {offer.get('price_cents_per_kwh')} ct/kWh",
        f"- Demo amount: {money(settlement.get('amount_cents'), settlement.get('currency', 'EUR'))}",
        f"- Current net export at offer time: {telemetry.get('net_export_w', 'unknown')} W",
        f"- Settlement state: {settlement.get('state')}",
        f"- Payment proof: {payment_proof_text(receipt)}",
        "- Legal/physical scope: demo only; no grid delivery or compliant energy-sharing settlement was performed.",
    ]
    agentcart_url = os.getenv("AGENTCART_URL", "").rstrip("/")
    if agentcart_url:
        lines.append(f"- Judge/energy view: {agentcart_url}/energy")
    return "\n".join(lines)


class HouseholdServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], config: Config) -> None:
        super().__init__(address, HouseholdHandler)
        self.config = config
        self.vikunja = VikunjaClient(config)
        self.homeassistant = HomeAssistantClient(config)
        self.openclaw = OpenClawClient(config)
        self.agentcart = AgentCartClient(config)
        self.chat_jobs: dict[str, ChatJob] = {}
        self.chat_jobs_lock = threading.Lock()
        self.agentcart_pending_approval: dict[str, Any] | None = None
        self.agentcart_pending_lock = threading.Lock()

    def create_chat_job(self, actor: str, user_message: str) -> ChatJob:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        job = ChatJob(
            id=secrets.token_urlsafe(12),
            actor=actor,
            user_message=user_message,
            created_at=now,
            events=queue.Queue(),
        )
        job.events.put({"type": "status", "status": "queued", "message": "Queued for OpenClaw", "time": now})
        with self.chat_jobs_lock:
            self.prune_chat_jobs_locked()
            self.chat_jobs[job.id] = job
        threading.Thread(target=self.run_chat_job, args=(job.id,), daemon=True).start()
        return job

    def get_chat_job(self, job_id: str) -> ChatJob | None:
        with self.chat_jobs_lock:
            return self.chat_jobs.get(job_id)

    def prune_chat_jobs_locked(self) -> None:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=CHAT_JOB_RETENTION_SECONDS)
        for job_id, job in list(self.chat_jobs.items()):
            created_at = parse_datetime(job.created_at)
            if job.status in {"done", "failed"} and (created_at is None or created_at < cutoff):
                self.chat_jobs.pop(job_id, None)

    def update_chat_job(self, job_id: str, **updates: Any) -> ChatJob | None:
        with self.chat_jobs_lock:
            job = self.chat_jobs.get(job_id)
            if job is None:
                return None
            for key, value in updates.items():
                setattr(job, key, value)
            return job

    def emit_chat_job_event(self, job: ChatJob, event: dict[str, Any]) -> None:
        job.events.put(event)

    def run_chat_job(self, job_id: str) -> None:
        job = self.get_chat_job(job_id)
        if job is None:
            return
        try:
            self.update_chat_job(job.id, status="running")
            self.emit_chat_job_event(
                job,
                {
                    "type": "status",
                    "status": "running",
                    "message": "OpenClaw is reading the household context",
                    "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )
            user_event = {
                "role": "user",
                "actor": job.actor,
                "content": job.user_message,
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            self.append_chat(user_event)
            self.emit_chat_job_event(
                job,
                {
                    "type": "status",
                    "status": "running",
                    "message": "OpenClaw is writing a reply",
                    "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )
            assistant_reply = self.agentcart_chat_reply(job)
            if assistant_reply is None:
                assistant_reply = self.openclaw.chat(self.openclaw_messages())
            assistant_event = {
                "role": "assistant",
                "actor": "agentcart" if is_agentcart_demo_message(job.user_message) else "openclaw",
                "content": assistant_reply,
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            self.append_chat(assistant_event)
            self.update_chat_job(job.id, status="done", reply=assistant_reply, message=assistant_event)
            self.emit_chat_job_event(
                job,
                {
                    "type": "done",
                    "status": "done",
                    "reply": assistant_reply,
                    "message": assistant_event,
                    "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )
        except Exception as error:
            self.update_chat_job(job.id, status="failed", error=str(error))
            self.emit_chat_job_event(
                job,
                {
                    "type": "failed",
                    "status": "failed",
                    "error": str(error),
                    "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )

    def remember_agentcart_approval(self, quote: dict[str, Any], approval: dict[str, Any]) -> None:
        token = str(approval.get("decision_token") or "")
        if not token:
            return
        with self.agentcart_pending_lock:
            self.agentcart_pending_approval = {
                "quote": quote,
                "approval": approval,
                "token": token,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    def current_agentcart_approval(self) -> dict[str, Any] | None:
        with self.agentcart_pending_lock:
            return dict(self.agentcart_pending_approval) if self.agentcart_pending_approval else None

    def clear_agentcart_approval(self, approval_id: str | None = None) -> None:
        with self.agentcart_pending_lock:
            if approval_id is None or (
                self.agentcart_pending_approval
                and (self.agentcart_pending_approval.get("approval") or {}).get("id") == approval_id
            ):
                self.agentcart_pending_approval = None

    def agentcart_chat_reply(self, job: ChatJob) -> str | None:
        message = job.user_message
        if not is_agentcart_demo_message(message) and not self.is_agentcart_approval_reply(message):
            return None
        if not self.agentcart.configured():
            return "AgentCart is not configured in Household OS yet, so I cannot run the demo from this chat surface."

        lowered = message.lower()
        if self.is_agentcart_approval_reply(message):
            return self.agentcart_decide_pending_purchase(job)
        wants_buy = ("buy" in lowered or "order" in lowered or "checkout" in lowered) and (
            "tea" in lowered
            or "hazel" in lowered
            or mentions_household_tea_preference(message)
            or "shaver" in lowered
            or "detergent" in lowered
            or "coffee" in lowered
        )
        wants_latest_order = any(word in lowered for word in ("arrive", "arrival", "delivery", "audit", "receipt", "order status"))
        wants_energy_offer = (
            any(word in lowered for word in ("energy", "electricity", "solar", "strom"))
            and any(word in lowered for word in ("sell", "offer", "surplus", "excess", "neighbor", "neighbour", "nachbar"))
        )
        if wants_energy_offer:
            return self.agentcart_offer_energy_demo(job)
        if wants_buy:
            return self.agentcart_buy_requested_product(job)
        if wants_latest_order:
            return self.agentcart_latest_order_summary()
        return self.agentcart_context_summary()

    def is_agentcart_approval_reply(self, message: str) -> bool:
        if not self.current_agentcart_approval():
            return False
        lowered = message.lower().strip()
        approve_words = ("approve", "approved", "yes", "ok", "continue", "buy it", "order it", "mach", "ja")
        reject_words = ("reject", "rejected", "no", "cancel", "stop", "nein")
        return any(word in lowered for word in approve_words + reject_words)

    def agentcart_decide_pending_purchase(self, job: ChatJob) -> str:
        pending = self.current_agentcart_approval()
        if not pending:
            return "I do not have a pending AgentCart approval to decide."
        approval = pending.get("approval") if isinstance(pending.get("approval"), dict) else {}
        quote = pending.get("quote") if isinstance(pending.get("quote"), dict) else {}
        token = str(pending.get("token") or "")
        approval_id = str(approval.get("id") or "")
        lowered = job.user_message.lower()
        decision = "rejected" if any(word in lowered for word in ("reject", "rejected", "no", "cancel", "stop", "nein")) else "approved"
        decided = self.agentcart.decide_approval(approval_id, token, decision, approver="household_os_chat")
        if decision == "rejected":
            self.clear_agentcart_approval(approval_id)
            return format_agentcart_approval_stopped(quote, decided)
        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": "Chat approval received; AgentCart is completing HTTP 402 payment checkout",
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        checkout = self.agentcart.checkout(str(decided.get("quote_id") or quote.get("id")), approval_id)
        self.clear_agentcart_approval(approval_id)
        return format_agentcart_checkout_summary(checkout)

    def agentcart_context_summary(self) -> str:
        tasks = self.agentcart.list_open_tasks(limit=8)
        energy = self.agentcart.energy_surplus()
        lines = ["AgentCart household context is available from this chat."]
        if tasks.get("state") == "ok":
            lines.append("")
            lines.append("Open shopping tasks:")
            for task in tasks.get("tasks", [])[:6]:
                due = f" due {task['due_date']}" if task.get("due_date") else ""
                lines.append(f"- #{task.get('id')}: {task.get('title')}{due}")
        else:
            lines.append(f"Open tasks could not be read: {tasks.get('reason') or tasks.get('error')}")
        lines.append("")
        lines.append(f"Energy surplus: {energy.get('state', 'unknown')}")
        if "net_export_w" in energy:
            lines.append(f"- Net export: {energy.get('net_export_w')} W")
        if energy.get("reasons"):
            lines.extend(f"- {reason}" for reason in energy["reasons"])
        if energy.get("recommendation"):
            lines.append(f"- Recommendation: {energy['recommendation']}")
        lines.append("")
        lines.append("I will not buy or sell anything unless you explicitly ask and approve the action.")
        return "\n".join(lines)

    def agentcart_buy_requested_product(self, job: ChatJob) -> str:
        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": "AgentCart is discovering shops and running a private quote tournament",
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        query = self.agentcart_query_for_message(job.user_message)
        tournament = self.agentcart.quote_tournament(query)
        winner = tournament.get("winner") if isinstance(tournament, dict) else None
        if not isinstance(winner, dict) or not winner.get("quote_id"):
            return "\n".join(
                [
                    "AgentCart could not find an eligible final quote for this request.",
                    f"- Query: {query}",
                    "- No order or approval was created.",
                ]
            )
        quote = self.agentcart.get_quote(str(winner["quote_id"]))
        policy = quote.get("policy_result", {})
        if policy.get("decision") == "deny":
            return format_agentcart_policy_denial(quote)

        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": (
                    f"Best quote: {winner.get('merchant_name')} at "
                    f"{money(winner.get('total_cents'), winner.get('currency', 'EUR'))}; requesting approval"
                ),
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        approval = self.agentcart.create_approval(quote["id"])
        self.remember_agentcart_approval(quote, approval)
        if not self.agentcart_should_wait_for_approval(job.user_message):
            return format_agentcart_pending_approval(quote, approval)
        deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=self.config.agentcart_approval_wait_seconds)
        while dt.datetime.now(dt.timezone.utc) < deadline:
            current = self.agentcart.approval_status(approval["id"])
            state = current.get("state")
            if state == "approved":
                self.emit_chat_job_event(
                    job,
                    {
                        "type": "status",
                        "status": "running",
                        "message": "Approval received; AgentCart is completing HTTP 402 payment checkout",
                        "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                    },
                )
                checkout = self.agentcart.checkout(quote["id"], approval["id"])
                self.clear_agentcart_approval(approval["id"])
                return format_agentcart_checkout_summary(checkout)
            if state in {"rejected", "expired"}:
                self.clear_agentcart_approval(approval["id"])
                return format_agentcart_approval_stopped(quote, current)
            time_left = max(0, int((deadline - dt.datetime.now(dt.timezone.utc)).total_seconds()))
            self.emit_chat_job_event(
                job,
                {
                    "type": "status",
                    "status": "running",
                    "message": f"Waiting for chat or phone/watch approval ({time_left}s left)",
                    "time": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )
            threading.Event().wait(3)
        latest = self.agentcart.approval_status(approval["id"])
        return format_agentcart_pending_approval(quote, latest)

    def agentcart_should_wait_for_approval(self, message: str) -> bool:
        lowered = message.lower()
        return any(
            phrase in lowered
            for phrase in (
                "wait",
                "after i approve",
                "after approval",
                "phone",
                "watch",
                "apple watch",
            )
        )

    def agentcart_query_for_message(self, message: str) -> str:
        lowered = message.lower()
        if "shaver" in lowered:
            return "shaver"
        if "detergent" in lowered or "laundry" in lowered:
            return "detergent"
        if "coffee" in lowered:
            return "coffee"
        if mentions_household_tea_preference(message):
            return "buy my favorite tea"
        if "woo" in lowered or "woocommerce" in lowered:
            return "Hazel's Chocolate Tea"
        return "tea"

    def agentcart_product_for_message(self, message: str) -> str:
        lowered = message.lower()
        if "shaver" in lowered:
            return self.first_catalog_product_id("shaver") or "favorite_tea"
        if "detergent" in lowered or "laundry" in lowered:
            return self.first_catalog_product_id("detergent") or "favorite_tea"
        if "coffee" in lowered:
            return self.first_catalog_product_id("coffee") or "favorite_tea"
        if mentions_household_tea_preference(message):
            return self.first_catalog_product_id("buy my favorite tea") or "favorite_tea"
        if "woo" in lowered or "woocommerce" in lowered:
            return self.first_catalog_product_id("woo tea") or "favorite_tea"
        return "favorite_tea"

    def first_catalog_product_id(self, query: str) -> str | None:
        result = self.agentcart.search_catalog(query)
        products = result.get("products") if isinstance(result, dict) else []
        if isinstance(products, list) and products:
            product_id = products[0].get("id") if isinstance(products[0], dict) else None
            return str(product_id) if product_id else None
        return None

    def agentcart_offer_energy_demo(self, job: ChatJob) -> str:
        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": "AgentCart is checking Home Assistant energy surplus",
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        energy = self.agentcart.energy_surplus()
        if not energy.get("offerable"):
            lines = [
                "AgentCart did not create an energy offer because the current household telemetry is not offerable.",
                f"- State: {energy.get('state', 'unknown')}",
                f"- Net export: {energy.get('net_export_w', 'unknown')} W",
            ]
            lines.extend(f"- Reason: {reason}" for reason in energy.get("reasons", []))
            return "\n".join(lines)
        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": "AgentCart is publishing a short-lived neighbour energy offer",
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        offer = self.agentcart.create_energy_offer()
        self.emit_chat_job_event(
            job,
            {
                "type": "status",
                "status": "running",
                "message": "Demo neighbour is accepting the offer; AgentCart is attaching MPP proof",
                "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        result = self.agentcart.accept_energy_offer(offer["id"])
        return format_agentcart_energy_trade(result)

    def agentcart_latest_order_summary(self) -> str:
        state = self.agentcart.dashboard_state()
        orders = state.get("orders") if isinstance(state, dict) else []
        if not isinstance(orders, list) or not orders:
            return "I do not see an AgentCart order yet."
        order = sorted(orders, key=lambda item: str(item.get("created_at", "")), reverse=True)[0]
        return format_agentcart_order(order)

    def openclaw_messages(self) -> list[dict[str, str]]:
        system = {
            "role": "system",
            "content": (
                "You are the private Household OS assistant for the demo household. "
                "Use the household-os-vikunja skill for household tasks, weekly planning, shopping, "
                "reminders, ventilation checks, and safe Home Assistant actions. "
                "For planning, inspect calendar_context and live Vikunja tasks before suggesting a schedule. "
                "When asked how to solve tasks, inspect the live tasks first, then suggest practical next actions. "
                "Treat due dates as planning markers unless the task says it is a fixed appointment. "
                "Use cycle-support context only as a gentle aid and do not assume another household member's mood or needs. "
                "Ask for confirmation before completing tasks or triggering safe Home Assistant scripts."
            ),
        }
        history = [
            {"role": event["role"], "content": event["content"]}
            for event in self.chat_history(limit=20)
            if event.get("role") in {"user", "assistant"} and event.get("content")
        ]
        return [system] + history

    def chat_history(self, limit: int = 100) -> list[dict[str, Any]]:
        path = self.config.chat_history_path
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        messages = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                messages.append(event)
        return messages

    def append_chat(self, event: dict[str, Any]) -> None:
        path = self.config.chat_history_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=json_default, sort_keys=True) + "\n")


class HouseholdHandler(BaseHTTPRequestHandler):
    server: HouseholdServer

    def do_GET(self) -> None:
        try:
            path, query = self.path_parts()
            if path == "/":
                self.send_html(index_html())
            elif path == "/chat":
                self.send_html(chat_html())
            elif path == "/health":
                self.send_json(
                    {
                        "ok": True,
                        "vikunja_configured": bool(self.server.config.vikunja_token),
                        "homeassistant_configured": bool(self.server.config.homeassistant_token),
                        "openclaw_configured": bool(
                            self.server.config.openclaw_gateway_url and self.server.config.openclaw_gateway_token
                        ),
                        "agentcart_configured": bool(
                            self.server.config.agentcart_url and self.server.config.agentcart_token
                        ),
                        "auth_enabled": bool(self.server.config.household_token),
                    }
                )
            elif path == CYCLE_CALENDAR_ROUTE:
                self.handle_cycle_calendar(query)
            elif path == TASK_CALENDAR_ROUTE:
                self.handle_task_calendar(query)
            elif path == "/api/auth/me":
                username = self.session_username()
                self.send_json({"authenticated": bool(username), "username": username})
            elif path == "/api/openclaw/history":
                self.require_auth()
                self.send_json({"messages": self.chat_history()})
            elif match := CHAT_JOB_EVENTS_ROUTE.match(path):
                self.require_auth()
                job = self.server.get_chat_job(match.group(1))
                if job is None:
                    raise NotFound("Chat job not found")
                self.stream_chat_job_events(job)
            elif path == "/api/vikunja/projects":
                self.require_auth()
                self.send_json({"projects": self.server.vikunja.list_projects()})
            elif path == "/api/vikunja/tasks":
                self.require_auth()
                self.send_json({"tasks": self.query_tasks(query)})
            elif path == "/api/vikunja/weekly-summary":
                self.require_auth()
                self.send_json(self.server.vikunja.weekly_summary(self.server.config.timezone))
            elif path == "/api/vikunja/daily-summary":
                self.require_auth()
                self.send_json(self.server.vikunja.daily_summary(self.server.config.timezone, int(query.get("days") or 3)))
            elif path == "/api/ha/ventilation":
                self.require_auth()
                self.send_json(self.server.homeassistant.ventilation_status())
            else:
                raise NotFound("Route not found")
        except Exception as error:
            self.send_error_json(error)

    def do_POST(self) -> None:
        try:
            path, _query = self.path_parts()
            payload = self.read_json()

            if path == "/api/auth/login":
                self.handle_login(payload)
                return
            if path == "/api/auth/logout":
                session_id = self.session_id_from_cookie()
                if session_id:
                    sessions = self.load_sessions()
                    sessions.pop(session_id, None)
                    self.save_sessions(sessions)
                self.send_json({"ok": True}, headers=[self.expire_session_cookie()])
                return

            self.require_auth()
            actor = self.current_actor()

            if path == "/api/command":
                result = self.handle_command(payload)
                self.audit(actor, payload.get("command", "unknown"), payload.get("args", {}))
                self.send_json(result)
            elif path == "/api/vikunja/tasks":
                result = self.server.vikunja.create_task(**task_create_args(payload))
                self.audit(actor, "create_task", {"task": result})
                self.send_json({"task": result}, status=201)
            elif match := TASK_ROUTE.match(path):
                task_id = int(match.group(1))
                action = match.group(2)
                result = self.handle_task_action(task_id, action, payload)
                self.audit(actor, action, {"task_id": task_id})
                self.send_json({"task": result})
            elif path == "/api/ha/notify":
                result = self.server.homeassistant.notify(
                    title=str(payload.get("title", "Household OS")),
                    message=str(payload.get("message", "")),
                )
                self.audit(actor, "notify", {"title": payload.get("title")})
                self.send_json(result)
            elif path == "/api/ha/shopping":
                result = self.server.homeassistant.add_shopping_item(
                    item=str(payload.get("item", "")),
                    description=str(payload.get("description", "")),
                    due_date=payload.get("due_date"),
                )
                self.audit(actor, "add_shopping_item", {"item": payload.get("item")})
                self.send_json({"result": result}, status=201)
            elif path == "/api/openclaw/chat":
                result = self.handle_openclaw_chat(payload, actor)
                self.audit(actor, "openclaw_chat", {"message_chars": len(str(payload.get("message", "")))})
                self.send_json(result)
            elif path == "/api/openclaw/chat/jobs":
                result = self.handle_openclaw_chat_job(payload, actor)
                self.audit(actor, "openclaw_chat_job", {"message_chars": len(str(payload.get("message", "")))})
                self.send_json(result, status=202)
            elif match := SAFE_SCRIPT_ROUTE.match(path):
                script_id = match.group(1)
                result = self.server.homeassistant.trigger_safe_script(script_id)
                self.audit(actor, "trigger_safe_script", {"script_id": script_id})
                self.send_json({"result": result})
            else:
                raise NotFound("Route not found")
        except Exception as error:
            self.send_error_json(error)

    def handle_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command", "")).strip()
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            raise BadRequest("args must be an object")

        if command == "list_projects":
            return {"projects": self.server.vikunja.list_projects()}
        if command == "list_tasks":
            return {"tasks": self.query_tasks(args)}
        if command == "create_task":
            return {"task": self.server.vikunja.create_task(**task_create_args(args))}
        if command == "complete_task":
            return {"task": self.server.vikunja.complete_task(int(args["task_id"]))}
        if command == "update_due_date":
            return {"task": self.server.vikunja.update_due_date(int(args["task_id"]), args.get("due_date"))}
        if command == "add_comment":
            return {"comment": self.server.vikunja.add_comment(int(args["task_id"]), str(args.get("comment", "")))}
        if command == "update_description":
            return {"task": self.server.vikunja.update_description(int(args["task_id"]), str(args.get("description", "")))}
        if command == "weekly_summary":
            return self.server.vikunja.weekly_summary(self.server.config.timezone)
        if command == "daily_summary":
            return self.server.vikunja.daily_summary(self.server.config.timezone, int(args.get("days") or 3))
        if command == "calendar_context":
            return self.calendar_context()
        if command == "notify":
            return self.server.homeassistant.notify(str(args.get("title", "Household OS")), str(args.get("message", "")))
        if command == "add_shopping_item":
            return {
                "result": self.server.homeassistant.add_shopping_item(
                    str(args.get("item", "")),
                    str(args.get("description", "")),
                    args.get("due_date"),
                )
            }
        if command == "ventilation_status":
            return self.server.homeassistant.ventilation_status()
        if command == "trigger_safe_script":
            return {"result": self.server.homeassistant.trigger_safe_script(str(args.get("script_id", "")))}
        if command.startswith(("delete_", "remove_")):
            raise Forbidden("Destructive commands are not enabled in this proof of concept")
        raise BadRequest(f"Unknown command: {command}")

    def handle_openclaw_chat(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        user_message = str(payload.get("message", "")).strip()
        if not user_message:
            raise BadRequest("message is required")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.append_chat({"role": "user", "actor": actor, "content": user_message, "time": now})
        messages = self.openclaw_messages()
        assistant_reply = self.server.openclaw.chat(messages)
        assistant_event = {
            "role": "assistant",
            "actor": "openclaw",
            "content": assistant_reply,
            "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self.append_chat(assistant_event)
        return {"reply": assistant_reply, "message": assistant_event}

    def handle_openclaw_chat_job(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        user_message = str(payload.get("message", "")).strip()
        if not user_message:
            raise BadRequest("message is required")
        job = self.server.create_chat_job(actor, user_message)
        return {
            "job_id": job.id,
            "status": job.status,
            "events_url": f"/api/openclaw/chat/jobs/{urllib.parse.quote(job.id)}/events",
        }

    def handle_cycle_calendar(self, query: dict[str, Any]) -> None:
        config = self.server.config
        if not config.cycle_calendar_enabled:
            raise NotFound("Calendar feed is not enabled")
        if not config.cycle_calendar_token:
            raise Forbidden("Calendar feed token is not configured")
        supplied = str(query.get("token", ""))
        if not secrets.compare_digest(supplied, config.cycle_calendar_token):
            raise Unauthorized("Missing or invalid calendar token")
        self.send_ical(render_cycle_calendar(config))

    def handle_task_calendar(self, query: dict[str, Any]) -> None:
        config = self.server.config
        if not config.task_calendar_enabled:
            raise NotFound("Task calendar feed is not enabled")
        if not config.task_calendar_token:
            raise Forbidden("Task calendar feed token is not configured")
        supplied = str(query.get("token", ""))
        if not secrets.compare_digest(supplied, config.task_calendar_token):
            raise Unauthorized("Missing or invalid calendar token")
        projects = {project["id"]: project["title"] for project in self.server.vikunja.list_projects()}
        tasks = self.server.vikunja.list_tasks(done=False)
        self.send_ical(render_task_calendar(config, tasks, projects))

    def calendar_context(self) -> dict[str, Any]:
        config = self.server.config
        return {
            "timezone": config.timezone,
            "today": dt.datetime.now(ZoneInfo(config.timezone)).date().isoformat(),
            "task_calendar": {
                "enabled": config.task_calendar_enabled,
                "route": TASK_CALENDAR_ROUTE,
                "mode": "Open Vikunja tasks with due dates are shown as transparent due markers.",
                "days_past": config.task_calendar_days_past,
                "days_ahead": config.task_calendar_days_ahead,
            },
            "cycle_support": cycle_calendar_context(config),
            "planning_note": (
                "Use calendar context as a gentle planning aid. Confirm with the household member before making assumptions "
                "from cycle-support windows, and use Vikunja due dates as task deadlines rather than fixed time blocks."
            ),
        }

    def stream_chat_job_events(self, job: ChatJob) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        while True:
            try:
                event = job.events.get(timeout=2)
            except queue.Empty:
                event = self.chat_job_snapshot(job)
            try:
                self.write_sse_event(event.get("type", "status"), event)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            if event.get("type") in {"done", "failed"}:
                return

    def chat_job_snapshot(self, job: ChatJob) -> dict[str, Any]:
        created_at = parse_datetime(job.created_at) or dt.datetime.now(dt.timezone.utc)
        elapsed = int((dt.datetime.now(dt.timezone.utc) - created_at).total_seconds())
        status = job.status
        if status == "done":
            return {
                "type": "done",
                "status": status,
                "reply": job.reply,
                "message": job.message,
                "elapsed_seconds": elapsed,
            }
        if status == "failed":
            return {"type": "failed", "status": status, "error": job.error or "OpenClaw failed", "elapsed_seconds": elapsed}
        return {
            "type": "status",
            "status": status,
            "message": "OpenClaw is still working",
            "elapsed_seconds": elapsed,
            "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def write_sse_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
        data = json.dumps(payload, default=json_default, sort_keys=True)
        for line in data.splitlines() or ["{}"]:
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def openclaw_messages(self) -> list[dict[str, str]]:
        return self.server.openclaw_messages()

    def chat_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.server.chat_history(limit)

    def append_chat(self, event: dict[str, Any]) -> None:
        self.server.append_chat(event)

    def handle_task_action(self, task_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "complete":
            return self.server.vikunja.complete_task(task_id)
        if action == "due-date":
            return self.server.vikunja.update_due_date(task_id, payload.get("due_date"))
        if action == "comment":
            return self.server.vikunja.add_comment(task_id, str(payload.get("comment", "")))
        if action == "description":
            return self.server.vikunja.update_description(task_id, str(payload.get("description", "")))
        raise BadRequest(f"Unknown task action: {action}")

    def query_tasks(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        project_id = params.get("project_id")
        return self.server.vikunja.list_tasks(
            project_id=int(project_id) if project_id not in (None, "") else None,
            done=parse_bool(params.get("done")),
            due_before=parse_date(params.get("due_before")),
            due_after=parse_date(params.get("due_after")),
            stale_days=int(params["stale_days"]) if params.get("stale_days") else None,
            include_comments=parse_bool(params.get("include_comments")) is True,
        )

    def handle_login(self, payload: dict[str, Any]) -> None:
        username = str(payload.get("username", "")).strip().lower()
        password = str(payload.get("password", ""))
        if username not in LOGIN_USERS:
            raise Forbidden("Only configured household users can log in to Household OS")
        if not password:
            raise BadRequest("password is required")
        try:
            self.server.vikunja.verify_login(username, password)
        except UpstreamError as error:
            raise Unauthorized("Invalid username or password") from error
        session_id, expires_at = self.create_session(username)
        self.audit(username, "login", {"expires_at": expires_at})
        self.send_json(
            {"ok": True, "username": username, "expires_at": expires_at},
            headers=[self.session_cookie(session_id)],
        )

    def require_auth(self) -> None:
        if self.session_username():
            return
        expected = self.server.config.household_token
        if not expected:
            return
        supplied = self.headers.get("X-Household-Token", "")
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            supplied = auth_header.removeprefix("Bearer ").strip()
        if supplied != expected:
            raise Unauthorized("Missing or invalid Household OS token")

    def current_actor(self) -> str:
        return self.session_username() or self.headers.get("X-Household-Actor", "token")

    def session_username(self) -> str | None:
        session_id = self.session_id_from_cookie()
        if not session_id:
            return None
        sessions = self.load_sessions()
        session = sessions.get(session_id)
        if not isinstance(session, dict):
            return None
        expires_at = parse_datetime(session.get("expires_at"))
        if expires_at is None or expires_at < dt.datetime.now(dt.timezone.utc):
            sessions.pop(session_id, None)
            self.save_sessions(sessions)
            return None
        username = session.get("username")
        return str(username) if username in LOGIN_USERS else None

    def session_id_from_cookie(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return None
        cookie = http.cookies.SimpleCookie()
        cookie.load(raw)
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def create_session(self, username: str) -> tuple[str, str]:
        sessions = self.load_sessions()
        now = dt.datetime.now(dt.timezone.utc)
        for session_id, session in list(sessions.items()):
            expires_at = parse_datetime(session.get("expires_at")) if isinstance(session, dict) else None
            if expires_at is None or expires_at < now:
                sessions.pop(session_id, None)
        session_id = secrets.token_urlsafe(32)
        expires_at = (now + dt.timedelta(seconds=SESSION_MAX_AGE_SECONDS)).isoformat()
        sessions[session_id] = {"username": username, "expires_at": expires_at}
        self.save_sessions(sessions)
        return session_id, expires_at

    def load_sessions(self) -> dict[str, Any]:
        path = self.server.config.session_path
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def save_sessions(self, sessions: dict[str, Any]) -> None:
        path = self.server.config.session_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sessions, sort_keys=True, indent=2), encoding="utf-8")
        path.chmod(0o600)

    def session_cookie(self, session_id: str) -> tuple[str, str]:
        return (
            "Set-Cookie",
            f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_MAX_AGE_SECONDS}",
        )

    def expire_session_cookie(self) -> tuple[str, str]:
        return ("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise BadRequest("Invalid JSON body") from error
        if not isinstance(value, dict):
            raise BadRequest("JSON body must be an object")
        return value

    def path_parts(self) -> tuple[str, dict[str, Any]]:
        parsed = urllib.parse.urlsplit(self.path)
        query = {
            key: values[-1] if len(values) == 1 else values
            for key, values in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()
        }
        return parsed.path.rstrip("/") or "/", query

    def audit(self, actor: str, action: str, detail: dict[str, Any]) -> None:
        config = self.server.config
        event = {
            "id": str(uuid.uuid4()),
            "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "detail": detail,
            "remote": self.client_address[0],
        }
        config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with config.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=json_default, sort_keys=True) + "\n")

    def send_json(self, payload: dict[str, Any], status: int = 200, headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, default=json_default, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, body: str, status: int = 200) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_ical(self, body: str, status: int = 200) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Disposition", 'inline; filename="cycle-support.ics"')
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_error_json(self, error: Exception) -> None:
        status = getattr(error, "status", 500)
        payload = {"error": str(error)}
        detail = getattr(error, "detail", None)
        if detail is not None:
            payload["detail"] = detail
        if status == 500:
            payload["trace"] = traceback.format_exc().splitlines()[-5:]
        self.send_json(payload, status=status)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))


def require_keys(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    missing = [key for key in keys if payload.get(key) in (None, "")]
    if missing:
        raise BadRequest(f"Missing required field(s): {', '.join(missing)}")
    return payload


def task_create_args(payload: dict[str, Any]) -> dict[str, Any]:
    require_keys(payload, "project_id", "title")
    args: dict[str, Any] = {
        "project_id": int(payload["project_id"]),
        "title": str(payload["title"]),
        "description": str(payload.get("description", "")),
        "due_date": payload.get("due_date") or None,
    }
    if payload.get("priority") not in (None, ""):
        args["priority"] = int(payload["priority"])
    if payload.get("repeat_after") not in (None, ""):
        args["repeat_after"] = int(payload["repeat_after"])
    if payload.get("repeat_mode") not in (None, ""):
        args["repeat_mode"] = int(payload["repeat_mode"])
    if isinstance(payload.get("reminders"), list):
        args["reminders"] = payload["reminders"]
    return args


def index_html() -> str:
    commands = [
        "list_projects",
        "list_tasks",
        "create_task",
        "complete_task",
        "update_due_date",
        "add_comment",
        "weekly_summary",
        "daily_summary",
        "calendar_context",
        "notify",
        "add_shopping_item",
        "ventilation_status",
        "trigger_safe_script",
    ]
    options = "\n".join(f'<option value="{html.escape(command)}">{html.escape(command)}</option>' for command in commands)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Household OS</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f2;
      --panel: #ffffff;
      --text: #20231f;
      --muted: #5e675c;
      --line: #d8dccc;
      --accent: #2e6f57;
      --accent-2: #b4532a;
      --code: #111713;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #161915;
        --panel: #20251f;
        --text: #f0f2ea;
        --muted: #b7bda9;
        --line: #394033;
        --accent: #79c49f;
        --accent-2: #e39a70;
        --code: #080a08;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 16px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(960px, calc(100vw - 24px));
      margin: 0 auto;
      padding: 24px 0;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .status, .topbar {{ color: var(--muted); font-size: 14px; }}
    .topbar {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    a {{ color: var(--accent); }}
    .surface {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    form {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    label {{ display: grid; gap: 6px; color: var(--muted); font-size: 13px; }}
    input, select, textarea, button {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: transparent;
      color: var(--text);
    }}
    textarea {{
      grid-column: 1 / -1;
      min-height: 132px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 14px;
    }}
    button {{
      grid-column: 1 / -1;
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 650;
    }}
    button.secondary {{
      grid-column: auto;
      width: auto;
      background: transparent;
      color: var(--text);
      border-color: var(--line);
    }}
    pre {{
      min-height: 220px;
      margin: 16px 0 0;
      padding: 14px;
      overflow: auto;
      background: var(--code);
      color: #e8f3e8;
      border-radius: 8px;
      white-space: pre-wrap;
    }}
    .danger {{ color: var(--accent-2); }}
    #app[hidden], #login[hidden], #logout[hidden] {{ display: none; }}
    @media (max-width: 680px) {{
      form {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Household OS</h1>
      <div class="topbar">
        <span class="status" id="status">checking</span>
        <button id="logout" class="secondary" type="button" hidden>Log out</button>
        <a href="/chat">Chat</a>
      </div>
    </header>
    <section class="surface" id="login">
      <form id="login-form">
        <label>Username
          <input id="username" placeholder="demo" autocomplete="username">
        </label>
        <label>Vikunja password
          <input id="password" type="password" autocomplete="current-password">
        </label>
        <button type="submit">Log in</button>
      </form>
    </section>
    <section class="surface" id="app" hidden>
      <form id="command-form">
        <label>Command
          <select id="command">{options}</select>
        </label>
        <textarea id="args">{{}}</textarea>
        <button type="submit">Send</button>
      </form>
      <pre id="output"></pre>
    </section>
  </main>
  <script>
    const login = document.getElementById("login");
    const app = document.getElementById("app");
    const username = document.getElementById("username");
    const password = document.getElementById("password");
    const loginForm = document.getElementById("login-form");
    const logout = document.getElementById("logout");
    const command = document.getElementById("command");
    const args = document.getElementById("args");
    const output = document.getElementById("output");
    const status = document.getElementById("status");
    function headers() {{
      return {{"Content-Type": "application/json"}};
    }}
    async function me() {{
      const res = await fetch("/api/auth/me", {{credentials:"same-origin"}});
      return res.ok ? await res.json() : {{authenticated:false}};
    }}
    function showAuthed(user) {{
      login.hidden = true;
      app.hidden = false;
      logout.hidden = false;
      status.textContent = user ? `logged in as ${{user}}` : "private";
      status.classList.remove("danger");
    }}
    function showLogin(text = "login required") {{
      login.hidden = false;
      app.hidden = true;
      logout.hidden = true;
      status.textContent = text;
    }}
    const examples = {{
      list_tasks: {{"done": false, "due_before": new Date(Date.now() + 7*864e5).toISOString().slice(0, 10)}},
      create_task: {{"project_id": 1, "title": "Buy oat milk", "description": "", "due_date": ""}},
      complete_task: {{"task_id": 1}},
      update_due_date: {{"task_id": 1, "due_date": new Date().toISOString().slice(0, 10)}},
      add_comment: {{"task_id": 1, "comment": "Handled through Household OS."}},
      daily_summary: {{"days": 3}},
      notify: {{"title": "Household OS", "message": "Test notification"}},
      add_shopping_item: {{"item": "Coffee", "description": ""}},
      trigger_safe_script: {{"script_id": "script.household_lueften_reminder"}}
    }};
    command.addEventListener("change", () => {{
      args.value = JSON.stringify(examples[command.value] || {{}}, null, 2);
    }});
    command.dispatchEvent(new Event("change"));
    async function load() {{
      const auth = await me();
      if (auth.authenticated) showAuthed(auth.username);
      else showLogin();
    }}
    loginForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const res = await fetch("/api/auth/login", {{
        method:"POST",
        headers:headers(),
        credentials:"same-origin",
        body:JSON.stringify({{username:username.value, password:password.value}})
      }});
      if (!res.ok) {{
        showLogin("login failed");
        status.classList.add("danger");
        return;
      }}
      password.value = "";
      await load();
    }});
    logout.addEventListener("click", async () => {{
      await fetch("/api/auth/logout", {{method:"POST", headers:headers(), credentials:"same-origin", body:"{{}}"}});
      output.textContent = "";
      showLogin();
    }});
    document.getElementById("command-form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      output.textContent = "running";
      let parsedArgs;
      try {{
        parsedArgs = JSON.parse(args.value || "{{}}");
      }} catch (error) {{
        output.textContent = "Invalid JSON";
        return;
      }}
      const response = await fetch("/api/command", {{
        method: "POST",
        headers: headers(),
        credentials: "same-origin",
        body: JSON.stringify({{command: command.value, args: parsedArgs}})
      }});
      const text = await response.text();
      try {{
        output.textContent = JSON.stringify(JSON.parse(text), null, 2);
      }} catch {{
        output.textContent = text;
      }}
    }});
    load().catch(() => showLogin("offline"));
  </script>
</body>
</html>"""


def chat_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Household OS Chat</title>
  <style>
    :root { color-scheme: light dark; --bg:#f7f7f2; --panel:#fff; --text:#20231f; --muted:#5e675c; --line:#d8dccc; --accent:#2e6f57; }
    @media (prefers-color-scheme: dark) { :root { --bg:#161915; --panel:#20251f; --text:#f0f2ea; --muted:#b7bda9; --line:#394033; --accent:#79c49f; } }
    * { box-sizing: border-box; }
    body { margin:0; font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }
    main { width:min(960px, calc(100vw - 24px)); margin:0 auto; min-height:100vh; display:grid; grid-template-rows:auto 1fr auto; gap:12px; padding:16px 0; }
    header { display:flex; justify-content:space-between; gap:12px; align-items:baseline; flex-wrap:wrap; }
    h1 { margin:0; font-size:24px; letter-spacing:0; }
    a { color:var(--accent); }
    #messages { display:flex; flex-direction:column; gap:10px; overflow:auto; padding:8px 0; }
    .msg { border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:12px; white-space:pre-wrap; }
    .meta { color:var(--muted); font-size:12px; margin-bottom:6px; }
    form { display:grid; gap:8px; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; }
    .row { display:grid; grid-template-columns:1fr auto; gap:8px; }
    input, textarea, button { border:1px solid var(--line); border-radius:6px; padding:10px 12px; font:inherit; background:transparent; color:var(--text); }
    textarea { min-height:76px; resize:vertical; }
    button { background:var(--accent); border-color:var(--accent); color:white; font-weight:650; cursor:pointer; }
    button.secondary { background:transparent; color:var(--text); border-color:var(--line); }
    button:disabled, textarea:disabled { opacity:.65; cursor:progress; }
    #login { align-self:start; }
    #app[hidden], #login[hidden] { display:none; }
    .topbar { display:flex; gap:8px; align-items:center; color:var(--muted); font-size:14px; }
    .composer-status { min-height:20px; color:var(--muted); font-size:14px; }
    .msg.pending { border-style:dashed; }
    .msg.failed { border-color:#b4532a; }
    @media (max-width:680px) { .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Household OS Chat</h1>
      <div class="topbar">
        <span id="who"></span>
        <button id="logout" class="secondary" type="button" hidden>Log out</button>
        <a href="/">Commands</a>
      </div>
    </header>
    <section id="login">
      <form id="login-form">
        <div class="row">
          <input id="username" placeholder="demo" autocomplete="username">
          <input id="password" type="password" placeholder="Vikunja password" autocomplete="current-password">
        </div>
        <button type="submit">Log in</button>
      </form>
    </section>
    <section id="app" hidden>
      <section id="messages"></section>
      <form id="form">
        <div class="row">
          <textarea id="message" placeholder="Ask OpenClaw about household tasks..."></textarea>
          <button id="send" type="submit">Send</button>
        </div>
        <div id="composer-status" class="composer-status"></div>
      </form>
    </section>
  </main>
  <script>
    const login = document.getElementById("login");
    const app = document.getElementById("app");
    const username = document.getElementById("username");
    const password = document.getElementById("password");
    const message = document.getElementById("message");
    const send = document.getElementById("send");
    const composerStatus = document.getElementById("composer-status");
    const messages = document.getElementById("messages");
    const form = document.getElementById("form");
    const loginForm = document.getElementById("login-form");
    const who = document.getElementById("who");
    const logout = document.getElementById("logout");
    let pending = false;
    let busyStarted = 0;
    let busyBase = "";
    let busyTimer = null;

    function headers() {
      return {"Content-Type": "application/json"};
    }
    async function me() {
      const res = await fetch("/api/auth/me", {credentials:"same-origin"});
      return res.ok ? await res.json() : {authenticated:false};
    }
    function showAuthed(user) {
      login.hidden = true;
      app.hidden = false;
      logout.hidden = false;
      who.textContent = user ? `Logged in as ${user}` : "";
    }
    function showLogin() {
      login.hidden = false;
      app.hidden = true;
      logout.hidden = true;
      who.textContent = "";
      stopBusy();
    }
    function render(items) {
      messages.innerHTML = "";
      for (const item of items) {
        const el = document.createElement("article");
        el.className = "msg";
        if (item.pending) el.classList.add("pending");
        if (item.failed) el.classList.add("failed");
        if (item.pending) el.dataset.pendingReply = "true";
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${item.role || "message"} · ${item.actor || ""} · ${item.time || ""}`;
        const body = document.createElement("div");
        body.className = "body";
        body.textContent = item.content || "";
        el.append(meta, body);
        messages.appendChild(el);
      }
      messages.scrollTop = messages.scrollHeight;
    }
    function setBusy(base) {
      pending = true;
      busyBase = base;
      if (!busyStarted) busyStarted = Date.now();
      message.disabled = true;
      send.disabled = true;
      refreshBusy();
      if (!busyTimer) busyTimer = setInterval(refreshBusy, 1000);
    }
    function refreshBusy() {
      if (!pending || !busyBase) return;
      const elapsed = Math.max(0, Math.floor((Date.now() - busyStarted) / 1000));
      const text = elapsed ? `${busyBase} (${elapsed}s)` : busyBase;
      composerStatus.textContent = text;
      const pendingBody = document.querySelector("[data-pending-reply] .body");
      if (pendingBody) pendingBody.textContent = text;
    }
    function stopBusy() {
      pending = false;
      busyStarted = 0;
      busyBase = "";
      message.disabled = false;
      send.disabled = false;
      composerStatus.textContent = "";
      if (busyTimer) clearInterval(busyTimer);
      busyTimer = null;
    }
    function statusText(data) {
      if (data.message) return data.message;
      if (data.status === "queued") return "Queued for OpenClaw";
      if (data.status === "running") return "OpenClaw is writing a reply";
      return "OpenClaw is working";
    }
    function waitForJob(eventsUrl) {
      return new Promise((resolve, reject) => {
        const source = new EventSource(eventsUrl);
        let closed = false;
        source.addEventListener("status", (event) => {
          const data = JSON.parse(event.data || "{}");
          setBusy(statusText(data));
        });
        source.addEventListener("done", (event) => {
          closed = true;
          source.close();
          resolve(JSON.parse(event.data || "{}"));
        });
        source.addEventListener("failed", (event) => {
          closed = true;
          source.close();
          const data = JSON.parse(event.data || "{}");
          reject(new Error(data.error || "OpenClaw failed"));
        });
        source.onerror = () => {
          if (!closed) setBusy("Waiting for the OpenClaw event stream to reconnect");
        };
      });
    }
    async function load() {
      const auth = await me();
      if (!auth.authenticated) {
        showLogin();
        return;
      }
      showAuthed(auth.username);
      const res = await fetch("/api/openclaw/history", {headers: headers(), credentials:"same-origin"});
      if (res.ok && !pending) render((await res.json()).messages || []);
    }
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const res = await fetch("/api/auth/login", {
        method:"POST",
        headers:headers(),
        credentials:"same-origin",
        body:JSON.stringify({username:username.value, password:password.value})
      });
      if (!res.ok) {
        who.textContent = "Login failed";
        return;
      }
      password.value = "";
      await load();
    });
    logout.addEventListener("click", async () => {
      await fetch("/api/auth/logout", {method:"POST", headers:headers(), credentials:"same-origin", body:"{}"});
      showLogin();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (pending) return;
      const text = message.value.trim();
      if (!text) return;
      message.value = "";
      setBusy("Sending to OpenClaw");
      const auth = await me();
      const historyResponse = await fetch("/api/openclaw/history", {headers: headers(), credentials:"same-origin"});
      const current = historyResponse.ok ? ((await historyResponse.json()).messages || []) : [];
      render([
        ...current,
        {role:"user", actor:auth.username || "you", content:text, time:"sending"},
        {role:"assistant", actor:"openclaw", content:"Queued for OpenClaw", time:"working", pending:true}
      ]);
      try {
        const res = await fetch("/api/openclaw/chat/jobs", {method:"POST", headers:headers(), credentials:"same-origin", body:JSON.stringify({message:text})});
        if (!res.ok) throw new Error(await res.text());
        const job = await res.json();
        setBusy("Queued for OpenClaw");
        await waitForJob(job.events_url);
        stopBusy();
        await load();
      } catch (error) {
        stopBusy();
        render([
          ...current,
          {role:"user", actor:auth.username || "you", content:text, time:"failed"},
          {role:"error", actor:"household-os", content:String(error.message || error), time:new Date().toISOString(), failed:true}
        ]);
      }
    });
    load();
    setInterval(() => { if (!pending) load(); }, 5000);
  </script>
</body>
</html>"""


def serve() -> None:
    config = Config.from_env()
    server = HouseholdServer((config.bind, config.port), config)
    print(f"Household OS listening on http://{config.bind}:{config.port}", flush=True)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private Household OS bridge")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve")
    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        serve()
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
