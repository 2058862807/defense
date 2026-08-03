#!/usr/bin/env bash
#
# PROTEAN DEFENSE - one-click launcher (used by the Windows desktop shortcut)
#
# Starts the backend + frontend detached (survives terminal timeouts), waits
# for the dashboard to come up, then opens it in the default browser.
#
# Set PROTEAN_NO_BROWSER=1 to skip opening the browser (headless use).
set -u

ROOT=/mnt/c/Users/Dustin/defense_v2
cd "$ROOT" || exit 1

bash scripts/start_stack.sh --detach

if [ "${PROTEAN_NO_BROWSER:-}" = "1" ]; then
  echo "PROTEAN DEFENSE stack started (browser launch skipped)."
  exit 0
fi

echo "Waiting for dashboard at http://localhost:3000 ..."
ready=""
for _ in $(seq 1 60); do
  if curl -s -o /dev/null --max-time 2 http://localhost:3000/; then
    ready=1
    break
  fi
  sleep 2
done

if [ -n "$ready" ]; then
  echo "Dashboard ready: http://localhost:3000"
  powershell.exe -NoProfile -Command "Start-Process 'http://localhost:3000'" 2>/dev/null
else
  echo "Dashboard did not come up within 2 minutes - check /tmp/backend.log and /tmp/frontend.log"
fi
exit 0
