#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-9222}"
USER_DATA_DIR="${USER_DATA_DIR:-$HOME/.cache/adssearch-chrome-debug}"
START_URL="${START_URL:-https://trends.google.com/trends/explore?geo=US}"
EXTENSION_PATH="${EXTENSION_PATH:-}"
CHROME_BIN="${CHROME_BIN:-}"
CHROME_EXTRA_ARGS="${CHROME_EXTRA_ARGS:-}"

find_chrome_bin() {
  if [[ -n "$CHROME_BIN" && -x "$CHROME_BIN" ]]; then
    echo "$CHROME_BIN"
    return 0
  fi

  local candidates=(
    "google-chrome"
    "google-chrome-stable"
    "chromium"
    "chromium-browser"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
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

mkdir -p "$USER_DATA_DIR"

ARGS=(
  "--remote-debugging-port=${PORT}"
  "--user-data-dir=${USER_DATA_DIR}"
  "--no-first-run"
  "--no-default-browser-check"
  "${START_URL}"
)

if [[ -n "$EXTENSION_PATH" ]]; then
  ARGS+=(
    "--disable-extensions-except=${EXTENSION_PATH}"
    "--load-extension=${EXTENSION_PATH}"
  )
fi

if [[ -n "$CHROME_EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS=( $CHROME_EXTRA_ARGS )
  ARGS+=("${EXTRA_ARGS[@]}")
fi

echo "Launching Chrome debug session"
echo "  chrome: ${CHROME_PATH}"
echo "  port: ${PORT}"
echo "  user_data_dir: ${USER_DATA_DIR}"
if [[ -n "$EXTENSION_PATH" ]]; then
  echo "  extension: ${EXTENSION_PATH}"
fi
if [[ -n "$CHROME_EXTRA_ARGS" ]]; then
  echo "  extra_args: ${CHROME_EXTRA_ARGS}"
fi

exec "$CHROME_PATH" "${ARGS[@]}"
