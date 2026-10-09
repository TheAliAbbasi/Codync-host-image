# Custom runtime examples

The published [`ghcr.io/thealiabbasi/codync-host:runtime`](https://github.com/TheAliAbbasi/codync-host-image) image installs **Claude**, **Cursor**, **Codex**, and **Grok** at build time. Other agent CLIs are fetched on first container start when you set the matching auth environment variables (see the main [README](../README.md#slim-runtime-and-lazy-agent-installs)).

If you want specific agents available immediately (no first-start download) or on hosts without outbound npm/curl during runtime, extend `:runtime` and preinstall into `/opt/codync-cli`. The entrypoint’s `agent_cli_present` check skips lazy install when the binary is already on `PATH` or under that tree.

## `Dockerfile.preinstall-agents`

[`Dockerfile.preinstall-agents`](Dockerfile.preinstall-agents) shows a minimal pattern:

1. `FROM ghcr.io/thealiabbasi/codync-host:runtime`
2. Set `HOME`, `NPM_CONFIG_PREFIX`, and `PATH` like [`Dockerfile.runtime`](../Dockerfile.runtime) does during build.
3. Run one or two `RUN` steps that mirror [`scripts/install-agent-on-demand.sh`](../scripts/install-agent-on-demand.sh) (the example installs **Gemini** via npm and **OpenCode** from the release tarball).
4. Restore runtime `HOME`/`PATH` and `USER codync` before shipping.

Build from the repository root (so `COPY` paths resolve if you add them later):

```bash
docker build -f examples/Dockerfile.preinstall-agents -t my-codync-host:runtime .
```

Run as usual with `-v codync-host:/var/lib/codync-host` and your API keys. Preinstalled tools do not need a lazy install on first start; you still need the auth variables Codync expects for each agent.

Add more `RUN` layers by copying the matching `_install_*` block from `install-agent-on-demand.sh`, or call `npm install -g …` / curl installers with the same `HOME` layout. Pin versions with build `ARG`s (for example `OPENCODE_VERSION`).
