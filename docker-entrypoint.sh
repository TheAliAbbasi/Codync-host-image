#!/bin/sh
# Runtime entrypoint for the unofficial Codync host image.
# Starts a session bus and an unlocked Secret Service, then writes CLI config
# only when the matching secret is set and that config is not already there.
# Nothing here opens a browser or a device-code login.
set -eu

export HOME="${HOME:-/var/lib/codync-host}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/codync-runtime}"
# goose must not take the connector keyring. The image sets this too.
export GOOSE_DISABLE_KEYRING=1

mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Curl-based CLIs land under /opt/codync-cli during the image build.
if [ -d /opt/codync-cli ]; then
  extra=$(find /opt/codync-cli -type d -name bin | paste -sd: -)
  if [ -n "$extra" ]; then
    PATH="${extra}:${PATH}"
    export PATH
  fi
fi

# Fixed password. It only protects connector secrets against someone who has
# the volume and not this image. It is not a second credential. See README.
KEYRING_PASSWORD=codync

start_secret_service() {
  if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    eval "$(dbus-launch --sh-syntax)"
    export DBUS_SESSION_BUS_ADDRESS
  fi
  mkdir -p "${HOME}/.local/share/keyrings"
  keyring_env=$(printf '%s\n' "$KEYRING_PASSWORD" | gnome-keyring-daemon --start --components=secrets --daemonize)
  eval "$keyring_env"
  export GNOME_KEYRING_CONTROL
  # The daemon may already hold the login keyring open. Unlock is the
  # headless path when it was created earlier and locked on restart.
  printf '%s\n' "$KEYRING_PASSWORD" | gnome-keyring-daemon --unlock || true
}

init_codex() {
  if [ -e "${HOME}/.codex/auth.json" ]; then
    return 0
  fi
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    printenv OPENAI_API_KEY | codex login --with-api-key
  elif [ -n "${CODEX_ACCESS_TOKEN:-}" ]; then
    printenv CODEX_ACCESS_TOKEN | codex login --with-access-token
  fi
}

init_kimi() {
  if [ -z "${KIMI_API_KEY:-}" ] || [ -e "${HOME}/.kimi-code/config.toml" ]; then
    return 0
  fi
  mkdir -p "${HOME}/.kimi-code"
  cat > "${HOME}/.kimi-code/config.toml" <<'EOF'
api_key_env = "KIMI_API_KEY"
EOF
}

init_qwen() {
  if [ -e "${HOME}/.qwen/settings.json" ]; then
    return 0
  fi
  qwen_type=""
  if [ -n "${DASHSCOPE_API_KEY:-}" ]; then
    qwen_type=dashscope
  elif [ -n "${OPENAI_API_KEY:-}" ]; then
    qwen_type=openai
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    qwen_type=anthropic
  elif [ -n "${GEMINI_API_KEY:-}" ]; then
    qwen_type=gemini
  fi
  if [ -z "$qwen_type" ]; then
    return 0
  fi
  mkdir -p "${HOME}/.qwen"
  cat > "${HOME}/.qwen/settings.json" <<EOF
{
  "security": {
    "auth": {
      "selectedType": "${qwen_type}"
    }
  }
}
EOF
}

init_minimax() {
  # Token Plan browser login is intentionally not invoked.
  if [ -z "${MCODE_PROVIDER_API_KEY:-}" ] || [ -e "${HOME}/.mcode" ]; then
    return 0
  fi
  mcode provider set-minimax-key
}

start_secret_service
init_codex
init_kimi
init_qwen
init_minimax

# Cortex needs SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD in
# the environment. Do not run `cortex auth login`.
# Google Antigravity is not installed: its ACP server has no headless init.

if [ "$#" -eq 0 ]; then
  set -- serve
fi

exec codync-host "$@"
