#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = os.getenv("VIKUNJA_API_URL", "http://127.0.0.1:3456/api/v1").rstrip("/")
CREDS_PATH = pathlib.Path(os.getenv("HOUSEHOLD_BOOTSTRAP_CREDENTIALS", "/root/household-os/bootstrap-credentials.txt"))

PROJECT_RENAMES = {
    "Daily habits": "Today / Recurring",
    "Shopping": "To Buy",
    "Life admin": "Life Admin",
    "Home automation": "Home Automation",
    "Recurring reminders": "Waiting / Scheduled",
    "Weekend plan": "This Week / Active",
}
PROJECTS = [
    "Today / Recurring",
    "This Week / Active",
    "To Buy",
    "Home Automation",
    "Life Admin",
    "Waiting / Scheduled",
    "Done / Archive",
]

LABEL_COLORS = {
    "routine": "2e6f57",
    "shopping": "2c8f7b",
    "planning": "68707a",
    "life-admin": "b4532a",
    "home": "5f7f4f",
    "home-automation": "276b8f",
    "health": "b84a62",
}

LABEL_MERGES = {
    "daily": "routine",
    "recurring": "routine",
    "food": "shopping",
    "clothes": "shopping",
    "quick-win": "shopping",
    "personal-care": "health",
    "glasses": "health",
    "pension": "life-admin",
    "Germany": "life-admin",
    "home-assistant": "home-automation",
    "automation": "home-automation",
    "lights": "home-automation",
    "air-quality": "home-automation",
    "cleaning-robot": "home-automation",
    "e-waste": "home",
    "scheduled": None,
    "waiting": None,
    "done": None,
}


HTML_BLOCK_RE = re.compile(r"<(p|h[1-6]|ul|ol|li|blockquote|div|table|strong|em|br|span|a)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<]+")


def inline_html(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return URL_RE.sub(lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>', escaped)


def markdownish_to_vikunja_html(text: str) -> str:
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


def task_description_html(owners: list[str], description: str) -> str:
    return (
        f"<p><strong>Owners:</strong> {html.escape(', '.join(owners))}</p>"
        "<h3>Notes</h3>"
        + markdownish_to_vikunja_html(description)
    )


def normalize_label(title: str) -> str | None:
    return LABEL_MERGES.get(title, title if title in LABEL_COLORS else None)


def normalize_task_labels(labels: list[str]) -> list[str]:
    normalized: list[str] = []
    for label in labels:
        target = normalize_label(label)
        if target and target not in normalized:
            normalized.append(target)
    return normalized


def checklist(items: list[tuple[str, bool]]) -> str:
    if not items:
        return ""
    lines = ["", "", "## Checklist", ""]
    for text, done in items:
        lines.append(f"- [{'x' if done else ' '}] {text}")
    return "\n".join(lines)


def berlin_time(date_text: str, hour: int = 9, minute: int = 0) -> str:
    return f"{date_text}T{hour:02d}:{minute:02d}:00+02:00"


TASKS: list[dict[str, Any]] = [
    {
        "project": "Today / Recurring",
        "title": "Lüften!!",
        "owners": ["max"],
        "labels": ["daily", "home-assistant", "recurring"],
        "due_date": berlin_time("2026-05-31", 18, 30),
        "repeat_after": 86400,
        "repeat_mode": 0,
        "reminders": [{"reminder": berlin_time("2026-05-31", 18, 30)}],
        "description": "Ventilate the flat every day. Later this should be automated with Home Assistant, ideally based on CO2, humidity, temperature, and/or window sensors."
        + checklist([
            ("Decide which rooms need Lüften reminders", False),
            ("Check available CO2 / humidity sensors", False),
            ("Define threshold for notification", False),
            ("Create Home Assistant automation", False),
            ("Disable manual daily reminder once automation works", False),
        ]),
    },
    {
        "project": "Today / Recurring",
        "title": "Check HelloFresh code",
        "owners": ["max", "ana"],
        "labels": ["recurring", "food", "shopping"],
        "due_date": berlin_time("2026-06-07", 10, 0),
        "repeat_after": 1209600,
        "repeat_mode": 0,
        "reminders": [{"reminder": berlin_time("2026-06-07", 10, 0)}],
        "description": "Check whether there is a usable HelloFresh code. If yes, decide meals. If no, skip.",
    },
    {
        "project": "This Week / Active",
        "title": "Plan holidays year",
        "owners": ["max", "ana"],
        "labels": ["planning", "life-admin"],
        "due_date": berlin_time("2026-06-07", 18, 0),
        "reminders": [{"reminder": berlin_time("2026-06-07", 10, 0)}],
        "description": "Plan possible holiday periods for the year."
        + checklist([
            ("Check work calendars / possible vacation windows", False),
            ("Decide rough budget", False),
            ("Collect destination ideas", False),
            ("Decide first concrete holiday block", False),
            ("Add dates to calendar", False),
        ]),
    },
    {
        "project": "This Week / Active",
        "title": "Check if study time can count toward pension",
        "owners": ["max", "ana"],
        "labels": ["pension", "life-admin", "Germany"],
        "due_date": berlin_time("2026-06-05", 18, 0),
        "reminders": [{"reminder": berlin_time("2026-06-05", 9, 0)}],
        "description": "Check whether study time can count toward pension records. We read that up to 8 years may be counted. Relevant for both Max and Ana."
        + checklist([
            ("Max: collect study periods with dates", False),
            ("Ana: collect study periods with dates", False),
            ("Collect proof documents if available", False),
            ("Check DRV / Kontenklärung / V0100 process", False),
            ("Decide whether to book a Deutsche Rentenversicherung appointment", False),
        ]),
    },
    {
        "project": "This Week / Active",
        "title": "Decide what to do with old broken Putzi",
        "owners": ["max"],
        "labels": ["cleaning-robot", "e-waste", "home"],
        "due_date": berlin_time("2026-06-03", 18, 0),
        "reminders": [{"reminder": berlin_time("2026-06-03", 9, 0)}],
        "description": "Find out how to properly dispose of the old broken cleaning robot before replacing it."
        + checklist([
            ("Check whether battery needs to be removed", False),
            ("Check Wertstoffhof / recycling option", False),
            ("Check whether shop accepts old electronics", False),
            ("Remove old robot from app / Home Assistant", False),
            ("Dispose of old Putzi", False),
        ]),
    },
    {
        "project": "This Week / Active",
        "title": "Decide first room for light automation",
        "owners": ["max"],
        "labels": ["home-automation", "lights"],
        "due_date": berlin_time("2026-06-02", 18, 0),
        "reminders": [{"reminder": berlin_time("2026-06-02", 9, 0)}],
        "description": "Choose one room for the first light automation test. Do not start with the whole flat."
        + checklist([
            ("Choose first room: bedroom, kitchen, hallway, or living room", False),
            ("List existing lights in that room", False),
            ("Decide whether motion sensor or presence sensor is needed", False),
            ("Define desired behavior", False),
            ("Create first test automation", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Clothes for us",
        "owners": ["max", "ana"],
        "labels": ["shopping", "clothes"],
        "description": "General clothes shopping for both of us."
        + checklist([
            ("Trousers", False),
            ("Jogginghose", False),
            ("Wedding Lukas & Oanh", True),
            ("Jeans Ana", True),
        ]),
    },
    {"project": "To Buy", "title": "Trousers", "owners": ["max", "ana"], "labels": ["shopping", "clothes"], "description": "Buy trousers."},
    {
        "project": "To Buy",
        "title": "Diffuser for nice scent",
        "owners": ["max", "ana"],
        "labels": ["shopping", "home"],
        "description": "Get something that makes the flat smell nice."
        + checklist([
            ("Decide: diffuser, reed diffuser, room spray, candle, or smart diffuser", False),
            ("Choose scent style", False),
            ("Buy one small option first", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Proper shaver",
        "owners": ["max"],
        "labels": ["shopping", "personal-care"],
        "description": "Get a proper shaver."
        + checklist([
            ("Decide if it should be for face only or body + face", False),
            ("Decide wet/dry or electric only", False),
            ("Define budget", False),
            ("Compare options", False),
            ("Buy one", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "New Putzi 2.0",
        "owners": ["max"],
        "labels": ["shopping", "cleaning-robot", "home-automation"],
        "description": "Get a new cleaning robot to replace the old broken one. Roborock is one option."
        + checklist([
            ("Define requirements", False),
            ("Decide vacuum only or vacuum + mop", False),
            ("Decide Home Assistant integration importance", False),
            ("Compare Roborock options", False),
            ("Buy new robot", False),
        ]),
    },
    {"project": "To Buy", "title": "Tea cup", "owners": ["max", "ana"], "labels": ["shopping", "quick-win"], "description": "Buy a tea cup."},
    {"project": "To Buy", "title": "Jogginghose", "owners": ["max", "ana"], "labels": ["shopping", "clothes"], "description": "Buy jogging pants."},
    {
        "project": "To Buy",
        "title": "Fenster Lichtabdeckung Schlafzimmer",
        "owners": ["max", "ana"],
        "labels": ["shopping", "home"],
        "description": "Get light cover / curtain / blind solution for the bedroom window."
        + checklist([
            ("Measure bedroom window", False),
            ("Decide type: curtain, blind, blackout, privacy film", False),
            ("Buy solution", False),
            ("Install", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Fenster Lichtabdeckung Küche",
        "owners": ["max", "ana"],
        "labels": ["shopping", "home"],
        "description": "Get light cover / curtain / blind solution for the kitchen window."
        + checklist([
            ("Measure kitchen window", False),
            ("Decide type: curtain, blind, privacy film", False),
            ("Buy solution", False),
            ("Install", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Bewegungssensoren",
        "owners": ["max"],
        "labels": ["shopping", "home-automation", "lights"],
        "description": "Buy motion sensors for the first light automation test."
        + checklist([
            ("Decide room first", False),
            ("Check Home Assistant compatibility", False),
            ("Buy only 1-2 sensors for testing", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Aufenthaltssensoren",
        "owners": ["max"],
        "labels": ["shopping", "home-automation", "lights"],
        "description": "Buy presence sensors for rooms where motion sensors are not enough."
        + checklist([
            ("Decide where presence detection is actually needed", False),
            ("Compare mmWave / presence sensor options", False),
            ("Buy one for testing first", False),
        ]),
    },
    {
        "project": "To Buy",
        "title": "Verschiedene Lichter",
        "owners": ["max", "ana"],
        "labels": ["shopping", "home-automation", "lights"],
        "description": "Buy lights needed for automation or better room lighting."
        + checklist([
            ("Decide first room", False),
            ("Check existing lights", False),
            ("Decide what is missing", False),
            ("Buy lights only for the first test room", False),
        ]),
    },
    {
        "project": "Home Automation",
        "title": "Automate Lüften with Home Assistant",
        "owners": ["max"],
        "labels": ["home-assistant", "automation", "air-quality"],
        "description": "Replace manual Lüften reminder with a Home Assistant automation."
        + checklist([
            ("Check CO2 sensor availability", False),
            ("Check humidity sensors", False),
            ("Check temperature sensors", False),
            ("Decide notification logic", False),
            ("Add notification to Max and Ana", False),
            ("Test for one week", False),
            ("Tune threshold", False),
        ]),
    },
    {
        "project": "Home Automation",
        "title": "Lichtautomatisierung",
        "owners": ["max"],
        "labels": ["home-assistant", "automation", "lights"],
        "description": "Create useful light automation in the flat."
        + checklist([
            ("Decide first room", False),
            ("Buy/test Bewegungssensoren", False),
            ("Buy/test Aufenthaltssensoren if needed", False),
            ("Decide which lights should be automated", False),
            ("Create first Home Assistant automation", False),
            ("Test for one week", False),
            ("Tune behavior", False),
            ("Expand to second room only after first room works", False),
        ]),
    },
    {"project": "Home Automation", "title": "Bewegungssensoren setup", "owners": ["max"], "labels": ["home-assistant", "automation", "lights"], "description": "Set up motion sensors after buying the first test devices. Linked to the To Buy item."},
    {"project": "Home Automation", "title": "Aufenthaltssensoren setup", "owners": ["max"], "labels": ["home-assistant", "automation", "lights"], "description": "Set up presence sensors after buying the first test device. Linked to the To Buy item."},
    {"project": "Home Automation", "title": "Verschiedene Lichter setup", "owners": ["max"], "labels": ["home-assistant", "automation", "lights"], "description": "Set up the selected lights after the first test room is defined. Linked to the To Buy item."},
    {
        "project": "Waiting / Scheduled",
        "title": "Ana femtoLASIK",
        "owners": ["ana"],
        "labels": ["health", "scheduled"],
        "due_date": berlin_time("2026-06-08", 9, 0),
        "reminders": [{"reminder": berlin_time("2026-06-07", 18, 0)}],
        "description": "Ana has femtoLASIK planned on 08.06.2026.",
    },
    {
        "project": "Waiting / Scheduled",
        "title": "Glasses Ana",
        "owners": ["ana"],
        "labels": ["glasses", "health", "waiting", "shopping"],
        "reminders": [{"reminder": berlin_time("2026-06-22", 10, 0)}],
        "description": "Wait with new glasses decision because Ana will have femtoLASIK on 08.06.2026."
        + checklist([
            ("Wait for LASIK", False),
            ("Wait for follow-up / stable vision", False),
            ("Decide whether glasses are still needed", False),
        ]),
    },
    {"project": "Done / Archive", "title": "Wedding Lukas & Oanh clothes", "owners": ["max", "ana"], "labels": ["shopping", "clothes", "done"], "done": True, "description": "Done."},
    {"project": "Done / Archive", "title": "Jeans Ana", "owners": ["ana"], "labels": ["shopping", "clothes", "done"], "done": True, "description": "Done."},
]


class Vikunja:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> Any:
        url = BASE_URL + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode()) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode()
            raise RuntimeError(f"{method} {path} failed with HTTP {error.code}: {detail}") from error


def password_for(username: str) -> str:
    for line in CREDS_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(username + " / "):
            return line.split(" / ", 1)[1].strip()
    raise RuntimeError(f"Missing password for {username}")


def login(username: str = "household-assistant") -> str:
    payload = {"username": username, "password": password_for(username), "long_token": True}
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        BASE_URL + "/login",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())["token"]


def paged(api: Vikunja, path: str, **query: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(1, 20):
        batch = api.request("GET", path, query={**query, "page": page, "per_page": 50})
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 50:
            break
    return items


def ensure_projects(api: Vikunja) -> dict[str, int]:
    projects = paged(api, "/projects", is_archived="true")
    by_title = {project["title"]: project for project in projects}

    for old, new in PROJECT_RENAMES.items():
        if old in by_title and new not in by_title:
            project = by_title[old]
            project["title"] = new
            updated = api.request("POST", f"/projects/{project['id']}", project)
            by_title.pop(old)
            by_title[new] = updated

    for title in PROJECTS:
        if title not in by_title:
            by_title[title] = api.request("PUT", "/projects", {"title": title})

    return {title: int(by_title[title]["id"]) for title in PROJECTS}


def ensure_labels(api: Vikunja) -> dict[str, int]:
    existing = {label["title"]: label for label in paged(api, "/labels")}
    for title, color in LABEL_COLORS.items():
        if title not in existing:
            existing[title] = api.request("PUT", "/labels", {"title": title, "hex_color": color})
        elif existing[title].get("hex_color") != color:
            updated = dict(existing[title])
            updated["hex_color"] = color
            existing[title] = api.request("POST", f"/labels/{existing[title]['id']}", updated)
    return {title: int(label["id"]) for title, label in existing.items() if title in LABEL_COLORS}


def ensure_household_team(api: Vikunja) -> int:
    for team in paged(api, "/teams"):
        if team.get("name") == "Household":
            team_id = int(team["id"])
            break
    else:
        team = api.request("PUT", "/teams", {"name": "Household", "description": "Shared Max/Ana household planning team."})
        team_id = int(team["id"])

    for username, admin in (("max", True), ("ana", True), ("household-assistant", True)):
        try:
            api.request("PUT", f"/teams/{team_id}/members", {"username": username, "admin": admin})
        except RuntimeError as error:
            if "already" not in str(error).lower() and "duplicate" not in str(error).lower():
                raise
    return team_id


def ensure_project_shares(api: Vikunja, projects: dict[str, int], team_id: int) -> None:
    for project_id in projects.values():
        teams = paged(api, f"/projects/{project_id}/teams")
        relation = next((team for team in teams if int(team.get("id", 0)) == team_id or int(team.get("team_id", 0)) == team_id), None)
        if relation is None:
            api.request("PUT", f"/projects/{project_id}/teams", {"team_id": team_id, "permission": 2})
        elif int(relation.get("permission", 0)) < 2:
            api.request("POST", f"/projects/{project_id}/teams/{team_id}", {"team_id": team_id, "permission": 2})


def user_ids(api: Vikunja) -> dict[str, int]:
    ids: dict[str, int] = {}
    for username in ("max", "ana"):
        matches = api.request("GET", "/users", query={"s": username})
        for user in matches:
            if user.get("username") == username:
                ids[username] = int(user["id"])
    missing = {"max", "ana"} - set(ids)
    if missing:
        raise RuntimeError(f"Missing Vikunja users: {', '.join(sorted(missing))}")
    return ids


def task_payload(task: dict[str, Any], project_id: int) -> dict[str, Any]:
    payload = {
        "title": task["title"],
        "project_id": project_id,
        "description": task_description_html(task["owners"], task.get("description", "")),
        "done": bool(task.get("done", False)),
    }
    for field in ("due_date", "repeat_after", "repeat_mode", "reminders"):
        if field in task:
            payload[field] = task[field]
    return payload


def existing_tasks(api: Vikunja) -> dict[tuple[int, str], dict[str, Any]]:
    tasks = paged(api, "/tasks")
    return {(int(task["project_id"]), task["title"]): task for task in tasks}


def attach_labels(api: Vikunja, task_id: int, label_ids: list[int]) -> None:
    current = {int(label["id"]) for label in paged(api, f"/tasks/{task_id}/labels")}
    for label_id in label_ids:
        if label_id in current:
            continue
        api.request("PUT", f"/tasks/{task_id}/labels", {"label_id": label_id})


def set_assignees(api: Vikunja, task_id: int, assignee_ids: list[int]) -> None:
    api.request("POST", f"/tasks/{task_id}/assignees/bulk", {"assignees": [{"id": user_id} for user_id in assignee_ids]})


def import_tasks(api: Vikunja, projects: dict[str, int], labels: dict[str, int], users: dict[str, int]) -> dict[str, int]:
    existing = existing_tasks(api)
    created = 0
    updated = 0

    for task in TASKS:
        project_id = projects[task["project"]]
        key = (project_id, task["title"])
        payload = task_payload(task, project_id)
        if key in existing:
            payload["id"] = existing[key]["id"]
            saved = api.request("POST", f"/tasks/{payload['id']}", payload)
            updated += 1
        else:
            saved = api.request("PUT", f"/projects/{project_id}/tasks", payload)
            created += 1

        task_id = int(saved["id"])
        attach_labels(api, task_id, [labels[label] for label in normalize_task_labels(task["labels"])])
        set_assignees(api, task_id, [users[owner] for owner in task["owners"]])

    return {"created": created, "updated": updated, "total": len(TASKS)}


def restart_bridge() -> None:
    if pathlib.Path("/opt/household-os/docker-compose.yml").exists():
        subprocess.run(["docker-compose", "up", "-d", "household-os"], cwd="/opt/household-os", check=True)


def main() -> None:
    api = Vikunja(login())
    projects = ensure_projects(api)
    team_id = ensure_household_team(api)
    ensure_project_shares(api, projects, team_id)
    labels = ensure_labels(api)
    users = user_ids(api)
    result = import_tasks(api, projects, labels, users)
    restart_bridge()
    print(json.dumps({"team_id": team_id, "projects": projects, "tasks": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
