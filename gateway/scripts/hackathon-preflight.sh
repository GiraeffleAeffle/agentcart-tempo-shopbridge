#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HA_API="$SCRIPT_DIR/../../scripts/ha-api.sh"
PVE_HOST="${PVE_HOST:-pve}"
OPENCLAW_CT="${OPENCLAW_CT:-104}"

run_ct() {
  local command="$1"
  ssh "$PVE_HOST" "pct exec $OPENCLAW_CT -- bash -lc $(printf '%q' "$command")"
}

section() {
  printf '\n== %s ==\n' "$1"
}

section "Services"
run_ct "systemctl is-active openclaw-gateway.service agentcart.service agentcart-mpp-smoke.service"

section "AgentCart health"
run_ct 'set -a; . /etc/openclaw/agentcart.env; set +a; curl -fsS -H "X-AgentCart-Token: $AGENTCART_TOKEN" http://127.0.0.1:8099/health'

section "Integration status"
run_ct 'set -a; . /etc/openclaw/agentcart.env; set +a; curl -fsS -H "X-AgentCart-Token: $AGENTCART_TOKEN" http://127.0.0.1:8099/v1/integrations/status | jq "{home_assistant, vikunja, delivery_calendar, energy, tempo_mpp}"'

section "Home Assistant AgentCart callback"
if test ! -x "$HA_API"; then
  printf 'Home Assistant API helper not found: %s\n' "$HA_API" >&2
  exit 1
fi
HA_SERVICES_JSON="$("$HA_API" GET /api/services)"
printf '%s' "$HA_SERVICES_JSON" | jq '{
  rest_commands: (
    [.[] | select(.domain == "rest_command") | .services | keys[]]
    | map(select(startswith("agentcart_")))
  )
}'
printf '%s' "$HA_SERVICES_JSON" | jq -e '
  any(.[]; .domain == "rest_command"
    and (.services | has("agentcart_approval_decision"))
    and (.services | has("agentcart_trigger_low_tea")))
' >/dev/null
"$HA_API" GET /api/states/automation.agentcart_mobile_approval_action \
  | jq -e '{state, last_triggered: .attributes.last_triggered} | select(.state == "on")'
"$HA_API" GET /api/states/binary_sensor.agentcart_online \
  | jq -e '{state} | select(.state == "on")'

section "OpenClaw gateway health"
run_ct 'set -a; . /etc/openclaw/gateway.env; set +a; curl -fsS -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" http://127.0.0.1:18789/health'

section "Household OS chat bridge"
curl -fsS --max-time 10 http://192.168.178.150:8088/health | jq '{ok, vikunja_configured, homeassistant_configured, openclaw_configured, agentcart_configured}'
ssh "$PVE_HOST" 'pct exec 106 -- bash -lc '"'"'
cd /opt/household-os
docker-compose exec -T household-os python - << "PY" | sed -n "1,18p"
from household_os import Config, HouseholdServer
server = HouseholdServer(("127.0.0.1", 0), Config.from_env())
try:
    print(server.agentcart_context_summary())
finally:
    server.server_close()
PY
'"'"''

section "Open household tasks"
run_ct 'cd /home/openclaw/workspace/skills/agentcart && runuser -u openclaw -- python3 scripts/agentcart-command.py << "JSON" | jq "{state, tasks: [.tasks[] | {id, title, due_date, url}]}"
{"command":"list_open_tasks","args":{"limit":8}}
JSON'

section "Energy surplus"
run_ct 'cd /home/openclaw/workspace/skills/agentcart && runuser -u openclaw -- python3 scripts/agentcart-command.py << "JSON" | jq "{state, offerable, net_export_w, recommendation, reasons, thresholds}"
{"command":"energy_surplus","args":{}}
JSON'

section "Delivery calendar feed"
run_ct 'set -a; . /etc/openclaw/agentcart.env; set +a; curl -fsS "http://127.0.0.1:8099/calendar/agentcart-deliveries.ics?token=$AGENTCART_DELIVERY_CALENDAR_TOKEN" | grep -E "SUMMARY|DTSTART|DTEND" | tail -12'

section "Desktop Ollama endpoint"
if ! curl -fsS --max-time 5 http://192.168.178.72:11435/api/tags >/tmp/agentcart-ollama-tags.json 2>/dev/null; then
  printf 'Desktop Ollama is offline; asking Home Assistant to wake and prepare it.\n'
  run_ct 'set -a; . /etc/openclaw/agentcart.env; set +a; curl -fsS -X POST -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" -H "Content-Type: application/json" "$HOMEASSISTANT_URL/api/services/script/desktop_ai_prepare_ollama" --data "{}" >/dev/null'
  for _ in $(seq 1 18); do
    if curl -fsS --max-time 5 http://192.168.178.72:11435/api/tags >/tmp/agentcart-ollama-tags.json 2>/dev/null; then
      break
    fi
    sleep 10
  done
fi

if test -s /tmp/agentcart-ollama-tags.json; then
  jq "{models: [.models[].name]}" /tmp/agentcart-ollama-tags.json
  section "OpenClaw local model smoke"
  run_ct 'runuser -u openclaw -- env HOME=/home/openclaw OLLAMA_API_KEY=ollama-local openclaw --profile ollama-test infer model run --local --model ollama/gemma4:e2b --thinking off --prompt "Reply with exactly: pong" --json'
  if test "${AGENTCART_PREFLIGHT_LOCAL_AGENT:-0}" = "1"; then
    section "OpenClaw local embedded-agent smoke"
    run_ct 'runuser -u openclaw -- env HOME=/home/openclaw OLLAMA_API_KEY=ollama-local openclaw --profile ollama-test agent --agent main --local --session-id agentcart-preflight-local-agent --timeout 180 --json --thinking off --message "Reply with exactly: OK local agent"'
  fi
else
  printf 'Desktop Ollama is still offline after wake attempt.\n'
fi
rm -f /tmp/agentcart-ollama-tags.json
