# How It Works

Running experiments with LLM agents needs a container. An experiment runs an agent many times, unattended, with its permission prompts turned off. Each run should see only the files you give it, reach only the hosts you allow, and leave a record of what it did.

botbox is that container. It gives each run:

1. **A ready agent CLI.** Claude Code, Codex or pi. See [the harnesses](#claude-code).
2. **No capabilities, no privilege escalation.** See [The Container](#the-container).
3. **Network only to an allowlist.** See [Network](#network).
4. **Mounted directories,** read-only or read-write.
5. **Logs.** The agent's transcript and the proxy's log come back on the result. See [Home and Credentials](#home-and-credentials).

This page is what botbox does with Docker to get there. For how to call it, see [Getting Started](../getting-started).

## A Run

`run()` does this, in order:

1. Checks the mounts and `workdir`. A missing host path or a `workdir` outside every mount raises here, before anything is built: Docker would create either one root-owned.
2. Builds the harness image, then your `dockerfile` on top (see [Images](#images)).
3. Makes a temporary directory on the host. The agent's home lives in it, with the harness's credentials staged in (see [Home and Credentials](#home-and-credentials)).
4. Starts a proxy for this run (see [Network](#network)).
5. Runs the container with the command as `sh -c`, in one attached `docker run --rm`. Its stdout and stderr stream to the host, and the client waits for it to exit and be removed.
6. Reads the transcript and the proxy log out of the temporary directory, stops the proxy, and deletes the directory.

The client attaches before the container starts, so no output is missed. It also waits for the removal itself and reports the exit code it saw, so `--rm` can't race the result. There is no separate create step, so no container is left created but never started. Killing the client doesn't stop the container, so a run that raises removes it by name.

If the daemon refuses the container, say for a missing image or a mount it can't make, the client exits 125, 126 or 127 with the daemon's error on stderr, and that comes back as the result.

If the Docker daemon dies mid-run, the client exits 125 with its error on stderr. botbox then checks the daemon, and if it doesn't answer, `exit_code` is -1. The output that already streamed out is kept, and the transcript and proxy log are read from the host directory as usual. That's why both live on the host and not in the container.

Inside `with Botbox(...)`, SIGTERM raises `SystemExit`, so a run in progress unwinds and tears down. Python's default SIGTERM exits without unwinding. A SIGTERM handler you set yourself is left alone.

## The Container

Every agent container runs with:

- `--cap-drop ALL` and `--security-opt no-new-privileges`.
- `--user user`. The harness images strip setuid bits, so nothing in the image can become root.
- `--network none` and the proxy's PID namespace, with the proxy variables (`HTTP_PROXY`, `HTTPS_PROXY` and their lowercase forms) pointing at the run's proxy.
- The temporary home mounted read-write at the harness's home, plus your mounts.

Your command runs as `botbox-relay sh -c <command>`. The relay is a script in each harness image; it starts a forwarder from the proxy port on the container's loopback to the proxy's socket, then runs your command.

## Network

The container runs with `--network none`: a loopback interface and nothing else. No route out, no DNS. Its only way out is a unix socket, mounted read-only at `/run/botbox`. A tinyproxy container on Docker's default bridge serves that socket. The proxy variables point at `127.0.0.1:41893` inside the container, where the relay forwards to the socket. Nothing in the run creates a Docker network.

The proxy denies by default. It allows the harness's own hosts plus your `allow`, and it checks the whole request URL, port included. An allowed host is reachable by CONNECT on port 443 and by plain HTTP on port 80. Every other port is refused, whatever the method.

tinyproxy listens on the proxy container's loopback and accepts only loopback clients. Other containers on the default bridge can reach the proxy's address, but nothing listens there. The socket is the only way in, and only this run's container has it mounted.

The proxy runs with no capabilities, a cap on its process count, and a pinned uid (100) apart from the agent's. It writes its log into the host temporary directory as it goes, and that log becomes `result.proxy`.

### Lifetime

The owning Python process starts the proxy with one attached `docker run --interactive --rm` and holds its stdin. There is no separate create step, so an owner that dies mid-start leaves no container behind. The proxy runs under an init (`--init`). When stdin closes, the proxy exits and its init with it. The agent container joins the proxy's PID namespace (`--pid container:<proxy>`), and when a namespace's init exits the kernel kills every process in it. So the agent dies with the proxy, however the owner dies: a normal return, an exception, or SIGKILL. The agent can't prevent it by ignoring signals.

Sharing the namespace means the agent can see the proxy's processes, but not touch them. They run as another uid, so the agent can't signal them or read their `/proc` entries beyond what any user can. The relay refuses to start if the agent runs as the proxy's uid. The proxy's init also reaps whatever the agent orphans.

Both containers run with `--rm`, so after SIGKILL of the owner no container is left. The host temporary directory stays.

There is no network at run time beyond the allowlist, so installs belong in the image build.

## Home and Credentials

Each run's home is a fresh host directory, mounted at the harness's home (`/home/user`). The harness's login is copied in, or, with `api_key`, a fresh credentials file (mode 600) holds only that key and nothing is read from the host. Copying means a token refresh inside the run never touches the host's file. botbox reads no `.env`. The one environment variable it reads is `PI_AGENT_HOST`, for `PiAgent("tower")`.

After the container exits, every file matching the harness's transcript pattern becomes an entry in `result.transcript`. The agent can write anything in its home, so botbox defends the read:

- A match that resolves outside the home is a link to a host file, and is skipped. The container has exited by then, so no link can change after the check.
- Bytes that aren't UTF-8 are replaced, and a file that won't open is skipped. The agent can't break the run's result.

## Sessions

`session()` sets up the same way as `run()`, then runs the container attached with stdin open, in one `docker run --interactive --rm`. The proxy's init reaps whatever the agent leaves running in the background when the CLI exits.

`message()` writes one line to the CLI's stdin in the harness's input format, then reads stdout line by line, parsing each as JSON, until the harness's end-of-turn event. stderr is drained on a separate thread, so a chatty stderr can't fill its pipe and stall the CLI. `close()` ends stdin, waits for the CLI to exit, then reads the transcript and tears down as `run()` does.

## Images

`build()` runs on every `run()` and `session()`. Docker's layer cache keeps an unchanged build fast. Your `dockerfile` is built on top of the harness image, tagged by a hash of the Dockerfile's path, for example `botbox-claude-<hash>:latest`.

Two `docker build`s of one tag at once fail: the loser looks up an image id that no longer exists. So each build takes a file lock keyed by the tag, in the system temp directory, and concurrent builds from any process take turns.

`AsyncBotbox.build()` runs the same builds with `docker buildx build --load --progress=quiet`, as an asyncio subprocess, and keeps the last 64 KiB of its stderr for the error. It takes the same lock file. It polls for the lock every 50ms without blocking, so the event loop keeps running while it waits. A blocking `flock` in a thread would keep waiting after the task was cancelled. On cancel, it stops the buildx client and waits for it to exit. BuildKit drops a build when its client goes away.

Each harness image stands alone, with no shared base. A harness is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to call the CLI. Adding one means one Dockerfile, one class, and one row in the [harness table](../harnesses/).

## Claude Code

- **Image:** `agents/claude/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay and a pinned `@anthropic-ai/claude-code`, with the auto-updater and non-essential traffic turned off.
- **Command:** `claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config`, plus `--model` and `--effort` when set.
- **Session:** `claude -p --input-format stream-json --output-format stream-json --verbose`, with the same permission and MCP flags. Each message goes in as a `user` event. A turn ends at the `result` event.
- **Credentials:** `.credentials.json` is copied into `.claude/`. With `api_key`, the key goes in `.claude/api_key`, and a `settings.json` whose `apiKeyHelper` reads it.
- **Hosts:** `api.anthropic.com`.
- **Transcript:** `.claude/projects/**/*.jsonl`.

### Login Expiry

A copied login is a snapshot. Its access token expires, typically within hours. Renewing it needs a host outside the allowlist (`platform.claude.com`), so the agent can't renew it inside the box, and a run that outlasts the token fails with a 401. Renewals on the host don't reach a running container.

botbox doesn't cover this. Opening the renewal host isn't a fix: renewal likely rotates the login, which would sign out the host's own sessions.

## Codex

- **Image:** `agents/codex/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay and a pinned `@openai/codex`.
- **Command:** `codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --disable plugins --config analytics.enabled=false <prompt>`, plus `--model` and `--config model_reasoning_effort=` when set. Codex's own sandbox is off because the container is the sandbox.
- **Session:** none. Codex's only long-running mode, `codex app-server`, needs a per-session handshake.
- **Credentials:** `auth.json` is copied into `.codex/`. With `api_key`, a fresh `.codex/auth.json` holds the key in API-key mode.
- **Hosts:** `chatgpt.com` for a copied login, `api.openai.com` with `api_key`.
- **Transcript:** `.codex/sessions/**/*.jsonl`.

## pi

- **Image:** `agents/pi/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay, `python3`, `ripgrep`, `fd` and a pinned `@earendil-works/pi-coding-agent`.
- **Command:** `pi -p <prompt> --mode json --provider <provider>`, plus `--model` when set.
- **Session:** `pi --mode rpc --provider <provider>`. Each message goes in as a `prompt` command. A turn ends at the `agent_end` event.
- **Credentials:** `auth.json`, and `models.json` if present, are copied into `.pi/agent/`. With `api_key`, a fresh `.pi/agent/auth.json` holds the key for `provider` and nothing else.
- **Hosts:** `openrouter.ai` for `openrouter`, `$PI_AGENT_HOST` for `tower`.
- **Transcript:** `.pi/agent/sessions/**/*.jsonl`.

In every harness the prompt, model and effort are shell-quoted before they go into the command.
