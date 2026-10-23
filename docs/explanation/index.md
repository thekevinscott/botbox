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

`run()` does this, in order, through the `docker` CLI as asyncio subprocesses:

1. Checks the mounts and `workdir`. A `workdir` outside every mount raises here, before anything is built. Then a missing host path is created as a dir owned by you. Docker would create either one root-owned.
2. Builds the harness image, then your `dockerfile` on top (see [Images](#images)).
3. Sweeps up after runs whose owner died (see [Lifetime](#lifetime)), then makes a temporary directory on the host. The agent's home lives in it, with the harness's credentials staged in (see [Home and Credentials](#home-and-credentials)).
4. Starts a proxy for this run (see [Network](#network)).
5. Runs the container with the command as `sh -c`, in one attached `docker run`. Its stdout and stderr stream to the host.
6. Reads the exit code from the stopped container with `docker container inspect`, then removes it.
7. Reads the transcript and the proxy log out of the temporary directory, stops and removes the proxy, and deletes the directory.

The client attaches before the container starts, so no output is missed. Neither container has `--rm`, so the exit code is read from the stopped container and can't race its removal. If the container isn't stopped when the client exits, the client died while the daemon was up, and the run raises `DockerException`. So does a container that never started: a missing image, say, raises with `return_code` 125.

If the inspect fails and `docker version` fails too, the daemon is gone and `exit_code` is -1. The output that already streamed out is kept, and the transcript and proxy log are read from the host directory as usual. That's why both live on the host and not in the container.

Every teardown step runs shielded, so a second cancel can't cut it short. A step that fails is a `RuntimeWarning`, and the result still comes back. The attached client forwards SIGTERM to the container and keeps waiting, so a cancel kills it outright. Both containers carry the label `botbox.run=<token>`. A cancel that lands between Docker creating a container and starting it can leave a created one behind; the label lets the sweep find it.

Inside `async with Botbox(...)`, SIGTERM cancels the task in the block through `loop.add_signal_handler`, and the block raises `SystemExit(143)` once teardown is done. Python's default SIGTERM exits without unwinding. A SIGTERM handler you set yourself is left alone.

## The Container

Every agent container runs with:

- `--cap-drop ALL` and `--security-opt no-new-privileges`.
- `--user` set to your uid and gid, with `HOME` at the harness's home, so the agent can write the temporary home and your mounts as you. botbox refuses to run as root. The harness images strip setuid bits, so nothing in the image can become root.
- `--network none` and the proxy's PID namespace, with the proxy variables (`HTTP_PROXY`, `HTTPS_PROXY` and their lowercase forms) pointing at the run's proxy.
- The temporary home mounted read-write at the harness's home, plus your mounts. The home is owner-only, so only your uid can write it. That keeps an agent from leaving files in it that you can't delete, credentials included.

Your command runs as `botbox-relay sh -c <command>`. The relay is a script in each harness image; it starts a forwarder from the proxy port on the container's loopback to the proxy's socket, then runs your command. If your uid has no passwd entry in the image, the relay first adds one named `user`, so `whoami` and `git` work. The harness images make `/etc/passwd` writable for this.

## Network

The container runs with `--network none`: a loopback interface and nothing else. No route out, no DNS. Its only way out is a unix socket, mounted read-only at `/run/botbox`. A tinyproxy container on Docker's default bridge serves that socket. The proxy variables point at `127.0.0.1:41893` inside the container, where the relay forwards to the socket. Nothing in the run creates a Docker network.

The proxy denies by default. It allows the harness's own hosts plus your `allow`, and it checks the whole request URL, port included. An allowed host is reachable by CONNECT on port 443 and by plain HTTP on port 80. Every other port is refused, whatever the method.

tinyproxy listens on the proxy container's loopback and accepts only loopback clients. Other containers on the default bridge can reach the proxy's address, but nothing listens there. The socket is the only way in, and only this run's container has it mounted.

The proxy runs with no capabilities, a cap on its process count, and a pinned uid (100) apart from the agent's. It writes its log into the host temporary directory as it goes, and that log becomes `result.proxy`.

### Lifetime

The owning Python process starts the proxy with one attached `docker run --interactive` and holds its stdin. The proxy runs under an init (`--init`). When stdin closes, the proxy exits and its init with it. The agent container joins the proxy's PID namespace (`--pid container:<proxy>`), and when a namespace's init exits the kernel kills every process in it. So the agent dies with the proxy, however the owner dies: a normal return, an exception, or SIGKILL. The agent can't prevent it by ignoring signals.

Sharing the namespace means the agent can see the proxy's processes, but not touch them. They run as another uid, so the agent can't signal them or read their `/proc` entries beyond what any user can. The relay refuses to start if the agent runs as the proxy's uid. The proxy's init also reaps whatever the agent orphans.

A normal end or a cancel removes both containers. After SIGKILL of the owner they stay, stopped and labelled `botbox.run=<token>`. The host temporary directory stays too, credentials included.

So each run takes a lock. Runs live in `botbox-<uid>/` under the system temp directory, owner-only. A run holds an exclusive `flock` on `<token>.lock` there for its whole life, beside its temporary directory `<token>/`. The kernel drops the lock however the owner dies. Each run starts by sweeping: a lock it can take belongs to a dead run, so it removes that run's containers by label, in any state, then its directory, then the lock file. `botbox.reap()` does the same on demand.

The lock is the only test of liveness. A pid or boot id check reads a live owner as dead when it runs in another container or reaches a remote daemon, and pid reuse reads a dead one as alive. The lock file is outside every mount, so the agent can't touch it. It is locked before it gets its name, so a sweep never finds a live run's lock free.

There is no network at run time beyond the allowlist, so installs belong in the image build.

## Home and Credentials

Each run's home is a fresh host directory, mounted at the harness's home (`/home/user`). The harness's login is copied in, or, with `api_key`, a fresh credentials file (mode 600) holds only that key and nothing is read from the host. Copying means a token refresh inside the run never touches the host's file. botbox reads no `.env`.

After the container exits, every file matching the harness's transcript pattern becomes an entry in `result.transcript`. The agent can write anything in its home, so botbox defends the read:

- A match that resolves outside the home is a link to a host file, and is skipped. The container has exited by then, so no link can change after the check.
- Bytes that aren't UTF-8 are replaced, and a file that won't open is skipped. The agent can't break the run's result.

## Sessions

`session()` sets up the same way as `run()`, then starts the agent's session command in a `docker run --interactive` that stays attached. The proxy's init reaps whatever the agent leaves running in the background when the CLI exits.

The CLI's stdin is a pipe the process holds, written through an asyncio write-pipe transport. Its stdout and stderr come back through read-pipe transports, so no thread reads them. `stream()` and `message()` write one line in the harness's input format, then read stdout line by line, parsing each as JSON, until the harness's end-of-turn event. When the client exits, the waiting turn wakes and ends, and later writes are dropped instead of filling the pipe.

The block's end closes stdin, waits for the client, reads the exit code, removes the container and reads the transcript as `run()` does. A cancel or an error in the block kills the client first, then the same teardown runs, shielded.

## Images

`build()` runs on every `run()` and `session()`. Docker's layer cache keeps an unchanged build fast. Your `dockerfile` is built on top of the harness image, tagged by a hash of the Dockerfile's path, for example `botbox-claude-<hash>:latest`.

Each build runs `docker buildx build --load --progress=quiet` as an asyncio subprocess, and keeps the last 64 KiB of its stderr for the error. buildx runs in its own session, so Ctrl-C reaches it only as a cancel. On cancel, botbox stops the buildx client and waits for it to exit, even through a second cancel. BuildKit drops a build when its client goes away.

Two `docker build`s of one tag at once fail: the loser looks up an image id that no longer exists. So each build takes a file lock keyed by the tag, in the system temp directory, and concurrent builds from any process take turns. It polls for the lock every 50ms without blocking, so the event loop keeps running while it waits. A blocking `flock` in a thread would keep waiting after the task was cancelled.

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
- **Hosts:** `openrouter.ai` for `openrouter`. For any other provider, the host of its `baseUrl` in `models.json`.
- **Transcript:** `.pi/agent/sessions/**/*.jsonl`.

In every harness the prompt, model and effort are shell-quoted before they go into the command.
