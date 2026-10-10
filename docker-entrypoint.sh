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

umask 077

mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Curl-based CLIs land under /opt/codync-cli (build or lazy install).
if [ -d /opt/codync-cli ]; then
  extra=$(find /opt/codync-cli -type d -name bin | paste -sd: -)
  if [ -n "$extra" ]; then
    PATH="${extra}:${PATH}"
    export PATH
  fi
fi

if [ -f /usr/local/lib/codync/install-agent-on-demand.sh ]; then
  # shellcheck disable=SC1091
  . /usr/local/lib/codync/install-agent-on-demand.sh
  lazy_install_agents
  extra=$(find /opt/codync-cli -type d -name bin 2>/dev/null | paste -sd: -)
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
  i=0
  while [ "$i" -lt 50 ]; do
    if dbus-send --session --print-reply --dest=org.freedesktop.DBus \
      /org/freedesktop/DBus org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
      break
    fi
    i=$((i + 1))
    sleep 0.1
  done
  if ! dbus-send --session --print-reply --dest=org.freedesktop.DBus \
    /org/freedesktop/DBus org.freedesktop.DBus.ListNames >/dev/null 2>&1; then
    echo "docker-entrypoint: session D-Bus did not become ready" >&2
    exit 1
  fi

  mkdir -p "${HOME}/.local/share/keyrings"
  # --start does not read the password on stdin. With XDG_RUNTIME_DIR set,
  # a successful daemon also prints no environment: the control socket is
  # the default $XDG_RUNTIME_DIR/keyring path, so GNOME_KEYRING_CONTROL is
  # omitted. Treating that empty stdout as failure exited before serve.
  # --unlock on this same process reads the password, creates login.keyring
  # when the volume has none, or unlocks the file already stored there, and
  # then serves Secret Service. A wrong password still starts the daemon
  # but leaves the login collection locked; that exits 1 below.
  if ! printf '%s\n' "$KEYRING_PASSWORD" | gnome-keyring-daemon --unlock --components=secrets --daemonize >/dev/null; then
    echo "docker-entrypoint: gnome-keyring-daemon failed to start" >&2
    exit 1
  fi
  GNOME_KEYRING_CONTROL="${XDG_RUNTIME_DIR}/keyring"
  export GNOME_KEYRING_CONTROL

  i=0
  login_unlocked=0
  while [ "$i" -lt 50 ]; do
    reply=$(dbus-send --session --print-reply --dest=org.freedesktop.secrets \
      /org/freedesktop/secrets/collection/login \
      org.freedesktop.DBus.Properties.Get \
      string:org.freedesktop.Secret.Collection string:Locked 2>/dev/null || true)
    case "$reply" in
      *'boolean false'*)
        login_unlocked=1
        break
        ;;
    esac
    i=$((i + 1))
    sleep 0.1
  done
  if [ "$login_unlocked" -ne 1 ]; then
    echo "docker-entrypoint: could not unlock gnome-keyring" >&2
    exit 1
  fi
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

if [ -n "${OPENAI_API_KEY:-}" ] || [ -n "${CODEX_ACCESS_TOKEN:-}" ]; then
  init_codex
fi
if [ -n "${KIMI_API_KEY:-}" ]; then
  init_kimi
fi
if [ -n "${DASHSCOPE_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ] || \
   [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
  init_qwen
fi
if [ -n "${MCODE_PROVIDER_API_KEY:-}" ]; then
  init_minimax
fi

# Cortex needs SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD in
# the environment. Do not run `cortex auth login`.
# Google Antigravity is not installed: its ACP server has no headless init.

if [ "$#" -eq 0 ]; then
  set -- serve
fi

exec codync-host "$@"
