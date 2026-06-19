#!/usr/bin/env bash
set -euo pipefail

AGENTCART_URL="${AGENTCART_URL:-http://127.0.0.1:8099}"
HOUSEHOLD_OS_URL="${HOUSEHOLD_OS_URL:-http://household-os.local:8088}"
OPENCLAW_GATEWAY_URL="${OPENCLAW_GATEWAY_URL:-http://openclaw.local:18789}"
DESKTOP_OLLAMA_URL="${DESKTOP_OLLAMA_URL:-http://desktop-ai.local:11435}"
AGENTCART_TOKEN="${AGENTCART_TOKEN:-}"
OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
AGENTCART_DELIVERY_CALENDAR_TOKEN="${AGENTCART_DELIVERY_CALENDAR_TOKEN:-}"

section() {
  printf '
== %s ==
' "$1"
}

agentcart_curl() {
  if test -n "$AGENTCART_TOKEN"; then
    curl -fsS -H "X-AgentCart-Token: $AGENTCART_TOKEN" "$@"
  else
    curl -fsS "$@"
  fi
}

section "AgentCart health"
agentcart_curl "$AGENTCART_URL/health" | jq .

section "Integration status"
agentcart_curl "$AGENTCART_URL/v1/integrations/status"   | jq '{home_assistant, vikunja, delivery_calendar, energy, tempo_mpp}'

section "Household OS health"
if curl -fsS --max-time 10 "$HOUSEHOLD_OS_URL/health" >/tmp/agentcart-household-health.json 2>/dev/null; then
  jq '{ok, vikunja_configured, homeassistant_configured, openclaw_configured, agentcart_configured}' /tmp/agentcart-household-health.json
else
  printf 'Household OS not reachable at %s. This is optional for the WooCommerce-only demo.
' "$HOUSEHOLD_OS_URL"
fi
rm -f /tmp/agentcart-household-health.json

section "OpenClaw gateway health"
if test -n "$OPENCLAW_GATEWAY_TOKEN"; then
  curl -fsS --max-time 10 -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" "$OPENCLAW_GATEWAY_URL/health" || true
else
  curl -fsS --max-time 10 "$OPENCLAW_GATEWAY_URL/health" || printf 'OpenClaw gateway not reachable at %s.
' "$OPENCLAW_GATEWAY_URL"
fi

section "Delivery calendar feed"
if test -n "$AGENTCART_DELIVERY_CALENDAR_TOKEN"; then
  curl -fsS "$AGENTCART_URL/calendar/agentcart-deliveries.ics?token=$AGENTCART_DELIVERY_CALENDAR_TOKEN"     | grep -E "SUMMARY|DTSTART|DTEND"     | tail -12 || true
else
  printf 'AGENTCART_DELIVERY_CALENDAR_TOKEN is not set; skipping calendar feed.
'
fi

section "Desktop Ollama endpoint"
if curl -fsS --max-time 5 "$DESKTOP_OLLAMA_URL/api/tags" >/tmp/agentcart-ollama-tags.json 2>/dev/null; then
  jq '{models: [.models[].name]}' /tmp/agentcart-ollama-tags.json
else
  printf 'Desktop Ollama not reachable at %s. Local model is optional for the recorded demo.
' "$DESKTOP_OLLAMA_URL"
fi
rm -f /tmp/agentcart-ollama-tags.json
