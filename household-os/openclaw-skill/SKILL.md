---
name: household-os-vikunja
description: Manage household Vikunja tasks and safe Home Assistant actions through the private Household OS bridge.
metadata:
  openclaw:
    requires:
      bins:
        - python3
---

# Household OS Vikunja Skill

Use this skill when a household user asks about household tasks, weekly planning,
shopping, reminders, Lüften checks, or safe home scripts.

Always call the Household OS bridge instead of calling Vikunja or Home Assistant
directly. The bridge enforces token separation, Home Assistant script allowlists,
and audit logging.

The command helper reads `HOUSEHOLD_OS_URL` and `HOUSEHOLD_OS_TOKEN` from the
environment. If they are not already set, it loads `/etc/openclaw/household-os.env`.

Command helper:

```sh
python3 {baseDir}/scripts/household-os-command.py <<'JSON'
{"command":"list_projects","args":{}}
JSON
```

Available commands:

- `list_projects` with `{}`.
- `list_tasks` with optional `project_id`, `done`, `due_before`, `due_after`,
  `stale_days`, and `include_comments`. Returned tasks include labels,
  assignees, due dates, reminders, and recurrence fields when Vikunja provides
  them.
- `create_task` with `project_id`, `title`, optional `description`, `due_date`,
  `priority`, `repeat_after`, `repeat_mode`, and `reminders`.
- `complete_task` with `task_id`.
- `update_due_date` with `task_id` and `due_date`; use `null` to clear it.
- `add_comment` with `task_id` and `comment`.
- `update_description` with `task_id` and `description`.
- `weekly_summary` with `{}`.
- `daily_summary` with optional `days`; returns overdue, today, tomorrow,
  upcoming, and next-24h reminder buckets for notification digests.
- `calendar_context` with `{}`; returns the private calendar-feed availability,
  today's approximate cycle-support window, upcoming cycle-support windows, and
  planning notes. It does not return calendar feed tokens.
- `notify` with `title` and `message`.
- `add_shopping_item` with `item`, optional `description`, and optional `due_date`.
- `ventilation_status` with `{}`.
- `trigger_safe_script` with `script_id`; only allowlisted Home Assistant scripts
  will run.

Suggestion workflow:

- When a household user asks "what should we do", "how do we solve this", "weekend
  plan", "what is next", or "what is due today", call `calendar_context` plus
  `daily_summary`, `weekly_summary`, or `list_tasks` first.
- Give concrete next actions, not just a restatement of the task title.
- Treat Vikunja due dates as deadlines or planning markers, not guaranteed fixed
  appointment blocks unless the task description says it is an appointment.
- Use cycle-support context only as a gentle planning aid. Do not make medical
  claims, do not assume another household member's mood or needs, and remind the user to confirm with the household.
- For buying tasks, suggest a short decision checklist and the smallest useful
  first purchase or research step.
- For life-admin tasks, identify the missing documents, the authority or portal
  to check, and a realistic next appointment/action.
- For home-automation tasks, start with one room or one sensor, then propose a
  testable Home Assistant automation path.
- Offer to update a task description, due date, or comment with the proposed
  plan, but wait for confirmation before writing changes.
- When writing `description` content, plain Markdown is accepted, but the bridge
  converts headings, bullet lists, and `- [ ]` / `- [x]` task lists into
  Vikunja's rich-text HTML so the task detail view stays readable.

Safety rules:

- Do not delete tasks, projects, comments, or Home Assistant entities.
- Ask a household user for confirmation before marking a task complete when the command
  could plausibly refer to more than one task.
- For Home Assistant, trigger only `trigger_safe_script`, `notify`,
  `add_shopping_item`, and `ventilation_status`.
- Never ask for or print Vikunja, Home Assistant, or Household OS tokens.
- Summaries should group stale, overdue, due-this-week, and no-due-date tasks.
- Treat Vikunja project names as the household board columns. The live board
  uses `Today / Recurring`, `This Week / Active`, `To Buy`, `Home Automation`,
  `Life Admin`, `Waiting / Scheduled`, and `Done / Archive`.
- Keep labels broad. The household label taxonomy is `routine`, `shopping`,
  `planning`, `life-admin`, `home`, `home-automation`, and `health`. Do not
  introduce narrow labels like `clothes`, `lights`, `air-quality`,
  `cleaning-robot`, `e-waste`, `personal-care`, `waiting`, or `done`.
