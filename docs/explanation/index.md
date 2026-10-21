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
4. Creates a private network and a proxy for this run (see [Network](#network)).
5. Starts the container with the command as `sh -c`, streams its stdout and stderr to the host, and waits for it to exit.
6. Reads the transcript and the proxy log out of the temporary directory, removes the proxy and the network, and deletes the directory.

The container is named before it starts, so an interrupted `docker run` can still be found and removed. A run that raises removes its container. A run that returns leaves it in place, exited, so `docker diff` can show what it wrote outside the mounts.

If the Docker daemon dies mid-run, the output that already streamed out is kept, `exit_code` is -1, and the transcript and proxy log are read from the host directory as usual. That's why both live on the host and not in the container.

`with Botbox(...)` tracks every container its runs created and removes them on exit. Inside the block, SIGTERM raises `SystemExit`, so the removal runs. Python's default SIGTERM exits without unwinding. A SIGTERM handler you set yourself is left alone.

## The Container

Every agent container runs with:

- `--cap-drop ALL` and `--security-opt no-new-privileges`.
- `--user user`. The harness images strip setuid bits, so nothing in the image can become root.
- The private network only, with the proxy variables (`HTTP_PROXY`, `HTTPS_PROXY` and their lowercase forms) pointing at the run's proxy.
- The temporary home mounted read-write at the harness's home, plus your mounts.

Your command runs as `sh -c <command>`.

## Network

The container joins a Docker network made with `--internal`: no gateway, no route out, no outside DNS. Its only way out is the proxy, a tinyproxy container that sits on both that network and Docker's default bridge.

The proxy denies by default. Its filter holds one exact-match pattern per allowed host: the harness's own hosts plus your `allow`. It tunnels CONNECT only to port 443.

Because the proxy is on the default bridge, any container there could reach it. So it accepts clients only from the run's own subnet. Using the default bridge for the way out means a run takes one network from the daemon's address pool, not two.

The proxy runs with no capabilities and as its own user. It writes its log into the host temporary directory as it goes, and that log becomes `result.proxy`. Network and proxy are made per run and removed afterwards, including on failure.

There is no network at run time beyond the allowlist, so installs belong in the image build.

## Home and Credentials

Each run's home is a fresh host directory, mounted at the harness's home (`/home/user`). The harness's login is copied in, or, with `api_key`, a fresh credentials file (mode 600) holds only that key and nothing is read from the host. Copying means a token refresh inside the run never touches the host's file. botbox reads no `.env`. The one environment variable it reads is `PI_AGENT_HOST`, for `PiAgent("tower")`.

After the container exits, every file matching the harness's transcript pattern becomes an entry in `result.transcript`. The agent can write anything in its home, so botbox defends the read:

- A match that resolves outside the home is a link to a host file, and is skipped. The container has exited by then, so no link can change after the check.
- Bytes that aren't UTF-8 are replaced, and a file that won't open is skipped. The agent can't break the run's result.

## Sessions

`session()` sets up the same way as `run()`, then creates the container with stdin open and an init process, and attaches to it with `docker start --attach --interactive`. The init process reaps whatever the agent leaves running in the background when the CLI exits.

`message()` writes one line to the CLI's stdin in the harness's input format, then reads stdout line by line, parsing each as JSON, until the harness's end-of-turn event. stderr is drained on a separate thread, so a chatty stderr can't fill its pipe and stall the CLI. `close()` ends stdin, waits for the CLI to exit, then reads the transcript and tears down as `run()` does.

## Images

`build()` runs on every `run()` and `session()`. Docker's layer cache keeps an unchanged build fast. Your `dockerfile` is built on top of the harness image, tagged by a hash of the Dockerfile's path, for example `botbox-claude-<hash>:latest`.

Two `docker build`s of one tag at once fail: the loser looks up an image id that no longer exists. So each build takes a file lock keyed by the tag, in the system temp directory, and concurrent builds from any process take turns.

Each harness image stands alone, with no shared base. A harness is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to call the CLI. Adding one means one Dockerfile, one class, and one row in the [harness table](../harnesses/).

## Claude Code

- **Image:** `agents/claude/Dockerfile`. Node, `git`, `ca-certificates` and a pinned `@anthropic-ai/claude-code`, with the auto-updater and non-essential traffic turned off.
- **Command:** `claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config`, plus `--model` and `--effort` when set.
- **Session:** `claude -p --input-format stream-json --output-format stream-json --verbose`, with the same permission and MCP flags. Each message goes in as a `user` event. A turn ends at the `result` event.
- **Credentials:** `.credentials.json` is copied into `.claude/`. With `api_key`, the key goes in `.claude/api_key`, and a `settings.json` whose `apiKeyHelper` reads it.
- **Hosts:** `api.anthropic.com`.
- **Transcript:** `.claude/projects/**/*.jsonl`.

### Login Expiry

A copied login is a snapshot. Its access token expires, typically within hours. Renewing it needs a host outside the allowlist (`platform.claude.com`), so the agent can't renew it inside the box, and a run that outlasts the token fails with a 401. Renewals on the host don't reach a running container.

botbox doesn't cover this. Opening the renewal host isn't a fix: renewal likely rotates the login, which would sign out the host's own sessions.

## Codex

- **Image:** `agents/codex/Dockerfile`. Node, `git`, `ca-certificates` and a pinned `@openai/codex`.
- **Command:** `codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --disable plugins --config analytics.enabled=false <prompt>`, plus `--model` and `--config model_reasoning_effort=` when set. Codex's own sandbox is off because the container is the sandbox.
- **Session:** none. Codex's only long-running mode, `codex app-server`, needs a per-session handshake.
- **Credentials:** `auth.json` is copied into `.codex/`. With `api_key`, a fresh `.codex/auth.json` holds the key in API-key mode.
- **Hosts:** `chatgpt.com` for a copied login, `api.openai.com` with `api_key`.
- **Transcript:** `.codex/sessions/**/*.jsonl`.

## pi

- **Image:** `agents/pi/Dockerfile`. Node, `git`, `ca-certificates`, `python3`, `ripgrep`, `fd` and a pinned `@earendil-works/pi-coding-agent`.
- **Command:** `pi -p <prompt> --mode json --provider <provider>`, plus `--model` when set.
- **Session:** `pi --mode rpc --provider <provider>`. Each message goes in as a `prompt` command. A turn ends at the `agent_end` event.
- **Credentials:** `auth.json`, and `models.json` if present, are copied into `.pi/agent/`. With `api_key`, a fresh `.pi/agent/auth.json` holds the key for `provider` and nothing else.
- **Hosts:** `openrouter.ai` for `openrouter`, `$PI_AGENT_HOST` for `tower`.
- **Transcript:** `.pi/agent/sessions/**/*.jsonl`.

In every harness the prompt is shell-quoted before it goes into the command.
