#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${SITEDATA_SESSION_STATE_DIR:-$HOME/.local/share/adssearch/sitedata-session}"
PROFILE_DIR="${SITEDATA_CHROME_PROFILE_DIR:-$HOME/.cache/adssearch/sitedata-chrome-profile}"
DISPLAY_NUM="${SITEDATA_DISPLAY_NUM:-100}"
SCREEN_GEOMETRY="${SITEDATA_SCREEN_GEOMETRY:-1440x1100x24}"
CDP_PORT="${SITEDATA_CDP_PORT:-9333}"
VNC_PORT="${SITEDATA_VNC_PORT:-5999}"
NOVNC_PORT="${SITEDATA_NOVNC_PORT:-6080}"
START_URL="${SITEDATA_START_URL:-https://sitedata.dev/traffic/image2url.com}"
CHROME_BIN="${CHROME_BIN:-}"
CHROME_EXTRA_ARGS="${CHROME_EXTRA_ARGS:-}"

XVFB_PID_FILE="$STATE_DIR/xvfb.pid"
X11VNC_PID_FILE="$STATE_DIR/x11vnc.pid"
WEBSOCKIFY_PID_FILE="$STATE_DIR/websockify.pid"
CHROME_PID_FILE="$STATE_DIR/chrome.pid"
XAUTH_FILE="$STATE_DIR/Xauthority"
XVFB_LOG="$STATE_DIR/xvfb.log"
X11VNC_LOG="$STATE_DIR/x11vnc.log"
WEBSOCKIFY_LOG="$STATE_DIR/websockify.log"
CHROME_LOG="$STATE_DIR/chrome.log"

mkdir -p "$STATE_DIR" "$PROFILE_DIR"

find_chrome_bin() {
  if [[ -n "$CHROME_BIN" && -x "$CHROME_BIN" ]]; then
    echo "$CHROME_BIN"
    return 0
  fi

  local playwright_chrome="$HOME/.cache/ms-playwright/chromium-1140/chrome-linux/chrome"
  local candidates=(
    "google-chrome"
    "google-chrome-stable"
    "chromium"
    "chromium-browser"
    "$playwright_chrome"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done

  return 1
}

CHROME_PATH="$(find_chrome_bin || true)"
if [[ -z "$CHROME_PATH" ]]; then
  echo "No Chrome/Chromium executable found. Set CHROME_BIN explicitly." >&2
  exit 1
fi

is_pid_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_with_pidfile() {
  local pid_file="$1"
  shift
  if is_pid_running "$pid_file"; then
    return 0
  fi

  setsid -f "$@"
  sleep 1

  local pid
  pid="$(pgrep -n -f "$*")"
  echo "$pid" > "$pid_file"
}

if [[ ! -f "$XAUTH_FILE" ]]; then
  touch "$XAUTH_FILE"
  xauth -f "$XAUTH_FILE" add ":${DISPLAY_NUM}" . "$(mcookie)"
fi

if ! is_pid_running "$XVFB_PID_FILE"; then
  start_with_pidfile "$XVFB_PID_FILE" \
    Xvfb ":${DISPLAY_NUM}" -screen 0 "$SCREEN_GEOMETRY" -nolisten tcp -auth "$XAUTH_FILE" \
    >"$XVFB_LOG" 2>&1
fi

if ! is_pid_running "$X11VNC_PID_FILE"; then
  start_with_pidfile "$X11VNC_PID_FILE" \
    x11vnc -display ":${DISPLAY_NUM}" -auth "$XAUTH_FILE" -nopw -rfbport "$VNC_PORT" -forever -shared \
    >"$X11VNC_LOG" 2>&1
fi

if ! is_pid_running "$WEBSOCKIFY_PID_FILE"; then
  start_with_pidfile "$WEBSOCKIFY_PID_FILE" \
    /usr/bin/python3 /usr/bin/websockify --web /usr/share/novnc "$NOVNC_PORT" "localhost:${VNC_PORT}" \
    >"$WEBSOCKIFY_LOG" 2>&1
fi

if ! is_pid_running "$CHROME_PID_FILE"; then
  chrome_args=(
    "--remote-debugging-port=${CDP_PORT}"
    "--user-data-dir=${PROFILE_DIR}"
    "--no-first-run"
    "--no-default-browser-check"
    "--no-sandbox"
    "--new-window"
    "${START_URL}"
  )

  if [[ -n "$CHROME_EXTRA_ARGS" ]]; then
    # shellcheck disable=SC2206
    extra_args=( $CHROME_EXTRA_ARGS )
    chrome_args+=("${extra_args[@]}")
  fi

  DISPLAY=":${DISPLAY_NUM}" XAUTHORITY="$XAUTH_FILE" setsid -f "$CHROME_PATH" "${chrome_args[@]}" >"$CHROME_LOG" 2>&1
  sleep 2
  pgrep -n -f -- "--remote-debugging-port=${CDP_PORT}" > "$CHROME_PID_FILE"
fi

cat <<EOF
SiteData persistent session is ready.
  display: :${DISPLAY_NUM}
  cdp: http://127.0.0.1:${CDP_PORT}
  novnc: http://$(hostname -I | awk '{print $1}'):${NOVNC_PORT}/vnc.html
  profile_dir: ${PROFILE_DIR}
  state_dir: ${STATE_DIR}
EOF
