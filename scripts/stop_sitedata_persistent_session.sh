#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${SITEDATA_SESSION_STATE_DIR:-$HOME/.local/share/adssearch/sitedata-session}"

stop_pidfile() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_pidfile "$STATE_DIR/chrome.pid"
stop_pidfile "$STATE_DIR/websockify.pid"
stop_pidfile "$STATE_DIR/x11vnc.pid"
stop_pidfile "$STATE_DIR/xvfb.pid"

echo "Stopped SiteData persistent session processes tracked in $STATE_DIR"
