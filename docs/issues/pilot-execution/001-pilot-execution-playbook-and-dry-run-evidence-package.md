# Pilot execution playbook and dry-run evidence package

GitHub issue: https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/issues/17

## What to build

Add a pilot execution playbook that turns the existing evidence runner into a
repeatable operator workflow before a real merchant pilot starts. The slice
should give an operator a dry-run path that generates the evidence folder
template, validates it with a production-shaped local env fixture, and explains
which artifacts must be replaced with real staging merchant evidence.

## Acceptance criteria

- [ ] A pilot execution readiness doc names the exact dry-run and real-pilot
  commands.
- [ ] The doc maps every generated evidence folder section to the pilot operator
  action that produces it.
- [ ] The dry-run command path produces an attachable JSON report without
  needing external merchant credentials.
- [ ] The real-pilot path clearly marks which evidence cannot be faked or reused
  from the sample folder.
- [ ] Release and pilot docs link to the playbook.

## Blocked by

None - can start immediately

## Slice metadata

Type: AFK
Source: Pilot Execution Readiness recommendation
