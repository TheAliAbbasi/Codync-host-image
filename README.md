# Unofficial Codync host images

These images are unofficial builds on [Codync](https://github.com/leepokai/Codync). They are not published by Po Kai Lee. Read [TRADEMARK.md](https://github.com/leepokai/Codync/blob/main/TRADEMARK.md) before offering Codync to anyone else.

Packaging files in this repository are [Apache-2.0](LICENSE). The image redistributes the Codync host. Codync is Copyright 2026 Po Kai Lee, Apache-2.0; releases 2.11.0 and earlier were MIT. The thin image copies that upstream `LICENSE` out of the host archive. See [NOTICE](NOTICE).

Images:

| Tag | What it is |
| --- | --- |
| `ghcr.io/thealiabbasi/codync-host:vX.Y.Z` | One upstream Linux host archive, both `linux/amd64` and `linux/arm64`. Historical tags stay on that version. |
| `ghcr.io/thealiabbasi/codync-host:latest` | The highest published `vX.Y.Z`. A backfill does not move this backward. |
| `ghcr.io/thealiabbasi/codync-host:runtime` | The image to run. Built `FROM` `:latest`, with agent CLIs, connector runtimes, and an entrypoint. Rebuilt when that host tag is current, not once per old release. |

`v1.0.0`–`v1.0.5` are not published. Those releases only contain macOS app archives. Desktop archives (`codync-linux-*.tar.gz`, AppImage, `.deb`) are never used.

## Run the runtime

Use one container. The host identity lives in the volume, so a second replica on the same volume will fight over it.

**Remote access (recommended):** pair the iPhone, macOS, or other desktop clients through Codync’s [Cloudflare Worker relay](https://github.com/leepokai/Codync/tree/main/cloud) — deploy that Worker to **your** Cloudflare account with Wrangler (it does not run inside this image), set `CODYNC_CLOUD_URL` on the container to the Worker’s HTTPS base URL, then pair from a client. Traffic uses the end-to-end encrypted device channel; the relay forwards ciphertext only. Clients reach the host over the cloud, not by publishing port **19222** on the internet.

**Do not** expose **19222** on a public load balancer, internet-facing Kubernetes Ingress, or any address reachable from the open internet. The host listens on `0.0.0.0:19222` inside the container; the local API (`/api/*`, bearer token) answers loopback callers only, but the encrypted device channel is still reachable on that port if you publish it. For cloud relay access you can omit `-p 19222:19222` entirely. See [Running the host on a Linux server](https://github.com/leepokai/Codync/blob/main/docs/guides/linux-servers.md) and the [remote relay spec](https://github.com/leepokai/Codync/blob/main/docs/reference/remote-relay.md).

Tailscale or an SSH tunnel to loopback (`ssh -N -L 19222:127.0.0.1:19222 user@host`) are optional LAN/VPN alternatives; they are not the primary way to reach a container on a cloud VM.

```bash
docker volume create codync-host
docker run -d --name codync-host \
  --restart unless-stopped \
  -v codync-host:/var/lib/codync-host \
  -e CODYNC_CLOUD_URL=https://your-worker.example.com \
  -e CURSOR_API_KEY \
  -e ANTHROPIC_API_KEY \
  ghcr.io/thealiabbasi/codync-host:runtime
```

Add `-p 19222:19222` only on a trusted private network (for example local debugging or pairing over VPC/Tailscale). Never map that port through a public-facing front end.

`HOME` is `/var/lib/codync-host`. That directory is the volume, and Codync stores `~/.codync` inside it. The keyring and CLI config files live there too, so they survive a new container.

An unset variable leaves that agent unconfigured. The entrypoint does not open a browser and does not start a device-code login. Google Antigravity is not installed.

### Inherited environment

Codync starts each CLI as a child, so the container environment is visible. No config file is written for these:

| Agent | Variables |
| --- | --- |
| Cursor | `CURSOR_API_KEY` |
| Claude Code | `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` |
| Pi | A provider key such as `ANTHROPIC_API_KEY` |
| OpenCode | A provider key such as `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |
| Grok | `XAI_API_KEY` |
| Gemini | `GEMINI_API_KEY`. `NO_BROWSER` is not authentication. |
| Copilot | `COPILOT_GITHUB_TOKEN` or `GH_TOKEN` |
| goose | A provider key, plus `GOOSE_PROVIDER` and `GOOSE_MODEL` when goose has no config. The image sets `GOOSE_DISABLE_KEYRING=1`. |
| Factory Droid | `FACTORY_API_KEY` |
| Amp | `AMP_API_KEY` |
| Junie | `JUNIE_API_KEY` |
| Poolside | `POOLSIDE_API_KEY` and `POOLSIDE_STANDALONE_BASE_URL` |
| Mistral Vibe | `MISTRAL_API_KEY` (`vibe-acp`) |
| Kiro | `KIRO_API_KEY` |
| Qoder | `QODER_PERSONAL_ACCESS_TOKEN` |
| CodeBuddy | `CODEBUDDY_API_KEY`, and `CODEBUDDY_INTERNET_ENVIRONMENT` when that edition requires it |
| Auggie | `AUGMENT_SESSION_AUTH` (session JSON) |
| Devin | `WINDSURF_API_KEY` for `devin acp`. The vendor does not document where that key is minted. |
| Cline | `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |
| Kilo | `KILO_API_KEY`. Codync’s badge checks Gateway login, so the badge can stay empty while `kilo acp` runs. |

### Config the entrypoint writes

Only when the secret is set and the config is missing:

| Agent | Variables | What happens |
| --- | --- | --- |
| Codex | `OPENAI_API_KEY`, or else `CODEX_ACCESS_TOKEN` | `codex login --with-api-key` or `codex login --with-access-token`. A bare key does not make `codex login status` succeed. |
| Kimi | `KIMI_API_KEY` | Writes `~/.kimi-code/config.toml` with `api_key_env` set to that variable. A bare `KIMI_API_KEY` is ignored by the CLI. |
| Qwen | `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY` | Writes `~/.qwen/settings.json` with the auth type that matches the first of those that is set. |
| MiniMax | `MCODE_PROVIDER_API_KEY` | Runs `mcode provider set-minimax-key`. The Token Plan browser login is not used. |
| Cortex | `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and `SNOWFLAKE_PASSWORD` (a PAT) | No file is written. `cortex auth login` is not run. |

## Keyring

Connector secrets are encrypted with a key in the freedesktop Secret Service. There is no plaintext fallback. Before `codync-host serve`, the entrypoint starts a session D-Bus and an unlocked `gnome-keyring-daemon`.

The keyring password is the fixed value `codync`. That is local-to-the-volume protection: it stops a stray copy of the volume from opening in a tool that asks for a password, and it is not a second secret. Anyone who has this image and the volume can unlock the keyring. Do not publish the volume.

## OCI connectors and the Docker socket

Connector packages install with `npx`, `uvx`, or `dnx`. Those three are in the image. OCI packages run `docker`. The image has the Docker CLI and does not run `dockerd`. Mount a daemon socket (or point at a sidecar) only if you install OCI connectors.

The runtime runs as the `codync` user, not root. The socket’s group on the host must match a supplementary group in the container (`--group-add`). Mounting `docker.sock` grants effective root on the host daemon — use only on machines you trust.

```bash
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)   # Linux; on macOS Docker Desktop use the GID from the VM docs
docker run -d --name codync-host \
  --restart unless-stopped \
  -v codync-host:/var/lib/codync-host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CODYNC_CLOUD_URL=https://your-worker.example.com \
  --group-add "$DOCKER_GID" \
  ghcr.io/thealiabbasi/codync-host:runtime
```

Kubernetes: mount the socket, set `securityContext.runAsUser` to the image’s `codync` UID, and add `supplementalGroups` with the node’s `docker` (or `root`) GID for that socket.

`git` and `ca-certificates` are installed because agents and `npx` need them. `codync-screen` is copied so the layout matches the host archive. Remote screen is not started.

## `CODYNC_CLOUD_URL`

Codync’s off-LAN path is a **Cloudflare Worker** plus Durable Objects in upstream [`cloud/`](https://github.com/leepokai/Codync/tree/main/cloud) ([`cloud/README.md`](https://github.com/leepokai/Codync/blob/main/cloud/README.md): Wrangler deploy, D1, secrets). That stack runs on **Cloudflare**, not in the `codync-host:runtime` image. After deploy, point the host at your Worker:

```bash
-e CODYNC_CLOUD_URL=https://your-worker.example.com
```

(no trailing slash; the host normalizes the URL.)

With the cloud URL set, the host registers with your Worker and maintains the encrypted relay channel. iPhone, macOS, and other Codync clients sign in to the same cloud, pair to this computer (QR or link), and talk to bots over that relay — same model as on a bare-metal Linux server ([linux-servers guide](https://github.com/leepokai/Codync/blob/main/docs/guides/linux-servers.md)). You do not need to publish port 19222 for that workflow.

| Audience | `CODYNC_CLOUD_URL` |
| --- | --- |
| Personal use on your own machines | Optional. Unset uses the cloud URL compiled into the host binary (when upstream provides one). |
| Hosted, resold, or multi-tenant services | **Required.** Deploy your own Worker from `cloud/` and set this variable. You may not use Codync Cloud. |

`CODYNC_CLOUD=off` disables cloud connectivity entirely (no relay; you would need a private path such as LAN, Tailscale, or SSH forwarding if you still want remote access).

For protocol and security details (signatures, relay behavior, what the Worker can and cannot see), see [remote-relay.md](https://github.com/leepokai/Codync/blob/main/docs/reference/remote-relay.md) and [environments and deployment](https://github.com/leepokai/Codync/blob/main/docs/guides/environments-and-deployment.md).

## Make the GHCR package public

The first push creates a **private** GitHub Container Registry package. Change it to public once:

1. Open [the package settings](https://github.com/users/TheAliAbbasi/packages/container/codync-host/settings).
2. If the package is not linked to this repository, connect `TheAliAbbasi/codync-host-image`.
3. Change the package visibility to public.

Later tags are published to the same package and stay on whatever visibility you set.

## Publish workflow

[`.github/workflows/publish.yml`](.github/workflows/publish.yml) runs at 06:15 UTC every day and can be started by hand.

- `missing` (default) builds host tags that are not on GHCR yet.
- `all` rebuilds every eligible host tag.
- `one` builds the tag you pass, for example `v2.11.2`.

Host builds use `fail-fast: false` and at most four at a time. A tag that `imagetools inspect` already finds is skipped. After that, `latest` is pointed at the highest semver already on GHCR, and `:runtime` is built from that tag.
