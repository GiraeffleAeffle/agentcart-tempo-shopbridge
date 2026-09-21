#!/bin/sh
# The durable plugin jobs remain bounded and can resume after interruption.
set -eu
child=''
stop() {
  if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null || true; fi
  exit 0
}
trap stop TERM INT
while :; do
  timeout --signal=TERM --kill-after=10 120 php -d memory_limit=256M \
    /var/www/html/wp-cli.phar cron event run --due-now --path=/var/www/html \
    >/dev/null 2>&1 &
  child=$!
  if wait "$child"; then
    touch /tmp/agentcart-scheduler-heartbeat
  else
    # Never forward plugin/provider output, which can contain customer data.
    printf '%s\n' 'ShopBridge scheduler: a due-job run failed; inspect manager diagnostics.' >&2
  fi
  sleep 60 &
  child=$!
  wait "$child" || true
  child=''
done
