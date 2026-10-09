# Sourced from docker-entrypoint.sh — do not execute directly.
# Installs agent CLIs into /opt/codync-cli when auth env is set and the binary is missing.
set -eu

CODYNC_CLI_HOME="${CODYNC_CLI_HOME:-/opt/codync-cli}"
OPENCODE_VERSION="${OPENCODE_VERSION:-1.18.35}"

_lazy_home() {
  export HOME="${CODYNC_CLI_HOME}"
  export NPM_CONFIG_PREFIX="${CODYNC_CLI_HOME}/.npm"
  export PATH="${CODYNC_CLI_HOME}/.npm/bin:${CODYNC_CLI_HOME}/.local/bin:${CODYNC_CLI_HOME}/.opencode/bin:/usr/local/bin:/usr/share/dotnet:${PATH}"
}

# True when the CLI is on PATH or already installed under CODYNC_CLI_HOME.
# POSIX sh — this file is sourced from docker-entrypoint.sh (/bin/sh).
agent_cli_present() {
  name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    return 0
  fi
  base="${CODYNC_CLI_HOME}"
  for p in \
    "${base}/.local/bin/${name}" \
    "${base}/.npm/bin/${name}" \
    "${base}/.opencode/bin/${name}" \
    "${base}/bin/${name}"; do
    if [ -x "$p" ]; then
      return 0
    fi
  done
  if [ -d "$base" ]; then
    if [ -n "$(find "$base" -type f -path "*/bin/${name}" -perm -111 -print -quit 2>/dev/null)" ]; then
      return 0
    fi
  fi
  return 1
}

_npm_global() {
  _lazy_home
  npm install -g "$1"
}

_install_pi() {
  if agent_cli_present pi; then return 0; fi
  if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
    return 0
  fi
  _npm_global @earendil-works/pi-coding-agent
}

_install_gemini() {
  if agent_cli_present gemini; then return 0; fi
  if [ -z "${GEMINI_API_KEY:-}" ]; then return 0; fi
  _npm_global @google/gemini-cli
}

_install_copilot() {
  if agent_cli_present copilot; then return 0; fi
  if [ -z "${COPILOT_GITHUB_TOKEN:-}" ] && [ -z "${GH_TOKEN:-}" ]; then return 0; fi
  _npm_global @github/copilot
}

_install_droid() {
  if agent_cli_present droid; then return 0; fi
  if [ -z "${FACTORY_API_KEY:-}" ]; then return 0; fi
  _npm_global droid
}

_install_qoder() {
  if agent_cli_present qodercli || agent_cli_present qoder; then return 0; fi
  if [ -z "${QODER_PERSONAL_ACCESS_TOKEN:-}" ]; then return 0; fi
  _npm_global @qoder-ai/qodercli
}

_install_codebuddy() {
  if agent_cli_present codebuddy; then return 0; fi
  if [ -z "${CODEBUDDY_API_KEY:-}" ]; then return 0; fi
  _npm_global @tencent-ai/codebuddy-code
}

_install_auggie() {
  if agent_cli_present auggie; then return 0; fi
  if [ -z "${AUGMENT_SESSION_AUTH:-}" ]; then return 0; fi
  _npm_global @augmentcode/auggie
}

_install_cline() {
  if agent_cli_present cline; then return 0; fi
  if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then return 0; fi
  _npm_global cline
}

_install_kilo() {
  if agent_cli_present kilo; then return 0; fi
  if [ -z "${KILO_API_KEY:-}" ]; then return 0; fi
  _npm_global @kilocode/cli
}

_install_qwen() {
  if agent_cli_present qwen; then return 0; fi
  if [ -z "${DASHSCOPE_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ] && \
     [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
    return 0
  fi
  _npm_global @qwen-code/qwen-code
}

_install_kimi() {
  if agent_cli_present kimi; then return 0; fi
  if [ -z "${KIMI_API_KEY:-}" ]; then return 0; fi
  _npm_global @moonshot-ai/kimi-code
}

_install_minimax() {
  if agent_cli_present mcode; then return 0; fi
  if [ -z "${MCODE_PROVIDER_API_KEY:-}" ]; then return 0; fi
  _npm_global @minimax-ai/code
}

_install_opencode() {
  if agent_cli_present opencode; then return 0; fi
  if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ] && \
     [ -z "${GEMINI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ]; then
    return 0
  fi
  _lazy_home
  arch="$(dpkg --print-architecture)"
  case "$arch" in
    amd64) oc_arch=x64 ;;
    arm64) oc_arch=arm64 ;;
    *) echo "install-agent-on-demand: unsupported architecture for opencode: $arch" >&2; return 1 ;;
  esac
  mkdir -p "${CODYNC_CLI_HOME}/.opencode/bin"
  url="https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${oc_arch}.tar.gz"
  tmp="$(mktemp -d)"
  curl -fsSL "$url" -o "${tmp}/opencode.tar.gz"
  tar -xzf "${tmp}/opencode.tar.gz" -C "${tmp}"
  install -m 0755 "${tmp}/opencode" "${CODYNC_CLI_HOME}/.opencode/bin/opencode"
  rm -rf "${tmp}"
  "${CODYNC_CLI_HOME}/.opencode/bin/opencode" --version
}

_install_goose() {
  if agent_cli_present goose; then return 0; fi
  if [ -z "${GOOSE_PROVIDER:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && \
     [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
    return 0
  fi
  _lazy_home
  curl -fsSL https://github.com/aaif-goose/goose/releases/download/stable/download_cli.sh | CONFIGURE=false bash
}

_install_amp() {
  if agent_cli_present amp; then return 0; fi
  if [ -z "${AMP_API_KEY:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://ampcode.com/install.sh | bash
}

_install_junie() {
  if agent_cli_present junie; then return 0; fi
  if [ -z "${JUNIE_API_KEY:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://junie.jetbrains.com/install.sh | bash
}

_install_poolside() {
  if agent_cli_present pool || agent_cli_present poolside; then return 0; fi
  if [ -z "${POOLSIDE_API_KEY:-}" ] || [ -z "${POOLSIDE_STANDALONE_BASE_URL:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://downloads.poolside.ai/pool/install.sh | env POOL_INSTALL_ACCEPT_EULA=1 bash
}

_install_vibe() {
  if agent_cli_present vibe || agent_cli_present vibe-acp; then return 0; fi
  if [ -z "${MISTRAL_API_KEY:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://mistral.ai/vibe/install.sh | bash
}

_install_kiro() {
  if agent_cli_present kiro; then return 0; fi
  if [ -z "${KIRO_API_KEY:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://cli.kiro.dev/install | bash
}

_install_devin() {
  if agent_cli_present devin; then return 0; fi
  if [ -z "${WINDSURF_API_KEY:-}" ]; then return 0; fi
  _lazy_home
  curl -fsSL https://cli.devin.ai/install.sh | sed '$d' | bash
  devin --version
}

_install_cortex() {
  if agent_cli_present cortex; then return 0; fi
  if [ -z "${SNOWFLAKE_ACCOUNT:-}" ] || [ -z "${SNOWFLAKE_USER:-}" ] || \
     [ -z "${SNOWFLAKE_PASSWORD:-}" ]; then
    return 0
  fi
  _lazy_home
  curl -fsSL https://ai.snowflake.com/static/cc-scripts/install.sh | bash
}

# Run one installer; log and continue so a failed lazy install does not block serve.
_lazy_install_run() {
  if ! "$1"; then
    echo "install-agent-on-demand: $1 failed (continuing)" >&2
  fi
}

lazy_install_agents() {
  if [ ! -d "${CODYNC_CLI_HOME}" ]; then
    return 0
  fi
  saved_home="${HOME:-/var/lib/codync-host}"
  _lazy_install_run _install_pi
  _lazy_install_run _install_gemini
  _lazy_install_run _install_copilot
  _lazy_install_run _install_droid
  _lazy_install_run _install_qoder
  _lazy_install_run _install_codebuddy
  _lazy_install_run _install_auggie
  _lazy_install_run _install_cline
  _lazy_install_run _install_kilo
  _lazy_install_run _install_qwen
  _lazy_install_run _install_kimi
  _lazy_install_run _install_minimax
  _lazy_install_run _install_opencode
  _lazy_install_run _install_goose
  _lazy_install_run _install_amp
  _lazy_install_run _install_junie
  _lazy_install_run _install_poolside
  _lazy_install_run _install_vibe
  _lazy_install_run _install_kiro
  _lazy_install_run _install_devin
  _lazy_install_run _install_cortex
  export HOME="${saved_home}"
}
