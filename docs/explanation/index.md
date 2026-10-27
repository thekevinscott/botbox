# How It Works

Running experiments with LLM agents needs a container. An experiment runs an agent many times, unattended, with its permission prompts turned off. Each run should see only the files you give it, reach only the hosts you allow, and leave a record of what it did.

botbox is that container. It gives each run:

1. **A ready agent CLI.** Claude Code, Codex or pi. See [the harnesses](#claude-code).
2. **No capabilities, no privilege escalation.** See [The Container](#the-container).
3. **Network only to an allowlist.** See [Network](#network).
4. **Mounted directories,** read-only or read-write.
5. **Logs.** The agent's output, transcripts and the proxy's log are written to a folder you choose. See [Output](#output).

This page is what botbox does with Docker to get there. For how to call it, see [Getting Started](../getting-started).

## A Run

`run()` does this, in order, through the `docker` CLI as asyncio subprocesses:

1. Checks the mounts and `workdir`. A `workdir` outside every mount raises here, before anything is built. Then a missing host path is created as a dir owned by you. Docker would create either one root-owned.
2. Builds the harness image, then your `dockerfile` on top (see [Images](#images)).
3. Makes a temporary directory on the host with Python's `tempfile`, for the run's streams and logs. The agent's home is not in it: it lives in the container (see [Home and Credentials](#home-and-credentials)).
4. Starts a proxy for this run (see [Network](#network)), and a credential proxy when the harness's login is injected (see [Credential Proxy](#credential-proxy)).
5. Runs the container with the command as `sh -c`, in one attached `docker run`. Its stdout and stderr stream to the host, into `stdout.txt` and `stderr.txt` in the temporary directory, and copies in `output` when one is given.
6. Reads the exit code from the stopped container with `docker container inspect`, then removes it.
7. Stops and removes the proxies, and deletes the temporary directory.

The client attaches before the container starts, so no output is missed. Neither container has `--rm`, so the exit code is read from the stopped container and can't race its removal. If the container isn't stopped when the client exits, or can't be inspected at all, the run raises `DockerException` with the client's code and stderr. So does a container that never started: a missing image, say, raises with `return_code` 125. A daemon that went away fails the inspect, and its error ("Cannot connect") is in the client's stderr. What already reached `output` stays there. That's why the streams, transcripts and proxy log are written on the host and not in the container.

## Output

A run's output has two homes. The first is the run's temporary directory. botbox always writes there, and removes it when the run ends. The second is `output`, a host directory you pass. It is optional, and it stays.

The agent's `docker run` client and the proxy's each pipe their stdout and stderr to botbox. botbox reads each pipe in chunks of up to 64 KiB, as they arrive, and writes each chunk to a file in the temporary directory, then to the same file in `output`, flushing both. The agent's go to `stdout.txt` and `stderr.txt`. Both of the proxy's go to `proxy.log`. No stream is held in memory whole.

A failed write to the temporary copy raises, and the run tears down. A failed write to `output`, a full disk say, is a `RuntimeWarning`: botbox stops writing that one file and the run carries on.

botbox reads only the temporary copies: the end of `stderr.txt` for a `DockerException`, the end of `proxy.log` when the proxy won't start, and `stdout.txt` for session events. So `output` failing never changes what a run does. The temporary directory sits under `TMPDIR`. On a tmpfs, the streams take memory, so keep it on disk.

Transcripts are different. With `output`, `output/transcripts/` is bind-mounted over the harness's sessions directory, and the CLI writes its transcripts there itself. There is no temporary copy. Without `output`, the CLI writes them into its home in the container, and they go with it.

`run()` and `session()` truncate `stdout.txt`, `stderr.txt` and `proxy.log` in `output` before building the image. Other files there, `transcripts/` included, are kept.

Every teardown step runs shielded, so a second cancel can't cut it short. A step that fails is a `RuntimeWarning`, and the result still comes back. The attached client forwards SIGTERM to the container and keeps waiting, so a cancel kills it outright. Every container in a run carries the label `botbox.run=<token>`. A cancel that lands between Docker creating a container and starting it can leave a created one behind; the label finds it.

Inside `async with Botbox(...)`, SIGTERM cancels the task in the block through `loop.add_signal_handler`, and the block raises `SystemExit(143)` once teardown is done. Python's default SIGTERM exits without unwinding. A SIGTERM handler you set yourself is left alone.

## The Container

Every agent container runs with:

- `--cap-drop ALL` and `--security-opt no-new-privileges`.
- `--user` set to your uid and gid, with `HOME` at the harness's home, so the agent can write its home and your mounts as you. botbox refuses to run as root. The harness images strip setuid bits, so nothing in the image can become root.
- `--network none` and the proxy's PID namespace, with the proxy variables (`HTTP_PROXY`, `HTTPS_PROXY` and their lowercase forms) pointing at the run's proxy.
- Your mounts. Nothing is mounted over the harness's home.

Your command runs as `botbox-relay sh -c <command>`. The relay is a script in each harness image; it writes the agent's staged files into its home, starts a forwarder from the proxy port on the container's loopback to the proxy's socket, then runs your command. If your uid has no passwd entry in the image, the relay first adds one named `user`, so `whoami` and `git` work. The harness images make `/etc/passwd` writable for this.

## Network

The container runs with `--network none`: a loopback interface and nothing else. No route out, no DNS. Its only way out is a unix socket, mounted read-only at `/run/botbox`. A tinyproxy container on Docker's default bridge serves that socket. The proxy variables point at `127.0.0.1:41893` inside the container, where the relay forwards to the socket. Nothing in the run creates a Docker network.

The proxy denies by default. It allows the harness's own hosts plus your `allow`, and it checks the whole request URL, port included. An allowed host is reachable by CONNECT on port 443 and by plain HTTP on port 80. Every other port is refused, whatever the method.

tinyproxy listens on the proxy container's loopback and accepts only loopback clients. Other containers on the default bridge can reach the proxy's address, but nothing listens there. The socket is the only way in, and only this run's container has it mounted.

The proxy runs with no capabilities, a cap on its process count, and a pinned uid (100) apart from the agent's. tinyproxy runs in the foreground and logs to its stdout. The attached `docker run` client pipes all of the container's output to botbox, which writes it to `proxy.log` (see [Output](#output)). The socket lives in a Docker volume made for the run, `botbox-run-<token>`, labelled `botbox.run=<token>`. The proxy mounts it read-write and the agent read-only. The allowlist reaches the proxy as an environment variable. The proxy container has no writable mount besides that volume.

### Lifetime

The owning Python process starts the proxy with one attached `docker run --interactive` and holds its stdin. The proxy runs under an init (`--init`). When stdin closes, the proxy exits and its init with it. The agent container joins the proxy's PID namespace (`--pid container:<proxy>`), and when a namespace's init exits the kernel kills every process in it. So the agent dies with the proxy, however the owner dies: a normal return, an exception, or SIGKILL. The agent can't prevent it by ignoring signals.

Sharing the namespace means the agent can see the proxy's processes, but not touch them. They run as another uid, so the agent can't signal them or read their `/proc` entries beyond what any user can. The relay refuses to start if the agent runs as the proxy's uid. The proxy's init also reaps whatever the agent orphans.

A normal end or a cancel removes the containers and the volume. After SIGKILL of the owner they stay, the containers stopped, all labelled `botbox.run=<token>`. The host temporary directory stays too, with whatever credentials were staged in it (a placeholder for an injected login).

botbox doesn't sweep up after a killed owner. Remove its containers with `docker rm --force $(docker ps --all --quiet --filter label=botbox.run=<token>)`, then its volume with `docker volume rm botbox-run-<token>`.

There is no network at run time beyond the allowlist, so installs belong in the image build.

### Credential Proxy

Some credentials never enter the box. Today those are Claude Code's and Codex's logins and `api_key`s (see [Claude Code](#claude-code) and [Codex](#codex)), and pi's OpenRouter key, from the host or `api_key` (see [pi](#pi)). pi's custom providers are staged in the home (see [Home and Credentials](#home-and-credentials)).

For an injected login, botbox starts a second sidecar beside tinyproxy: Envoy, from the upstream `envoyproxy/envoy:v1.36.2` image pinned by digest. It runs as uid 101, with no capabilities, `no-new-privileges` and a cap of 64 processes. It sits on Docker's default bridge and connects to its one upstream itself, not through tinyproxy. It joins tinyproxy's PID namespace, so it dies with tinyproxy's init, as the agent does. It serves `credentials.sock` in the run's volume, beside tinyproxy's socket. In the agent container, the relay forwards `127.0.0.1:41894` to that socket, and the harness's base URL points there. The relay refuses to start if the agent runs as uid 101, as it does for tinyproxy's uid.

**Where the credential lives.** In a tmpfs at `/run/credentials` inside the Envoy container, owned by uid 101 with mode 700. botbox writes no file for it on the host. It reaches Envoy on stdin: the container's shell writes it to the tmpfs, then execs Envoy, which won't start without it. A new token goes the same way, through `docker exec` with the token on stdin, written beside the old file and renamed over it. Envoy picks up a renamed file on its next request; it ignores one written in place. The agent container never mounts the tmpfs, and Envoy runs as a uid apart from the agent's. Envoy's config is on its command line, which the agent can see with `ps`. It names the secret's file but holds no secret.

**What it forwards.** Envoy sends a request upstream only if the whole path, without its query, matches the harness's pattern and the method is one it allows (`POST` by default). Anything else gets a 403 from Envoy: `botbox credential proxy: path not allowed`. Allowed requests go over TLS to port 443 of the one upstream host, whose certificate must name that host. Envoy sets the credential header, replacing any value the client sent, and drops the other auth headers the harness lists. For Claude Code on a login, that is `Authorization` on `POST /v1/messages` and `POST /v1/messages/count_tokens` to `api.anthropic.com`, with `x-api-key` dropped. With an `api_key`, it sets `x-api-key` on the same paths and drops `Authorization`. For pi on OpenRouter, it is `Authorization` on `POST /api/v1/chat/completions` to `openrouter.ai`.

**What it doesn't stop.** Anything in the box can send requests through the socket. A request on an allowed path goes out with the credential added. So the agent can spend the login's quota on whatever it sends there. It can't read the token, and it can't use it once the run ends.

Envoy's stdout and stderr, including one access-log line per request, go to `credentials.log` in `output`, or in the temporary directory without one. Leaving the run stops the Envoy container and removes it.

## Home and Credentials

The agent's home (`/home/user`) is part of its container. The harness image creates it, with every directory down to the sessions directory open to any uid, since the agent runs as yours. Nothing on the host backs it, and it goes when the container is removed.

Before the run, the agent's `stage_auth` writes its credentials and config into a `HomeFiles`. They travel into the container as a gzipped tar at the head of its stdin, and the relay unpacks them into the home before your command starts. Only the tar's size is in the env, as `BOTBOX_HOME_BYTES`, so `docker inspect` never shows the files. The relay reads exactly that many bytes, and the rest of stdin, a session's messages, goes to the command. For Claude's and Codex's login and `api_key`, and pi's OpenRouter key, the staged files hold a placeholder, and the [credential proxy](#credential-proxy) sends the real one. An agent opts in to that through `InjectingAgent`'s `credential_source`. One without it, such as pi on another provider, stages its host login as is, so that login is in the container's home for the run. A token refresh inside the run never touches the host's file. botbox reads no `.env`.

With `output`, `output/transcripts/` is mounted over the harness's sessions directory, so the CLI writes its transcripts there. botbox never reads them. Without `output`, they are deleted with the container.

## Sessions

`session()` sets up the same way as `run()`, then starts the agent's session command in a `docker run --interactive` that stays attached. The proxy's init reaps whatever the agent leaves running in the background when the CLI exits.

The CLI's stdin is a pipe the process holds, written through an asyncio write-pipe transport. Its stdout and stderr come back through read-pipe transports, so no thread reads them. They go to `stdout.txt` and `stderr.txt` as in a run (see [Output](#output)), and a `tail -F` follower of the temporary `stdout.txt` feeds the events. `stream()` and `message()` write one line in the harness's input format, then read stdout line by line, parsing each as JSON, until the harness's end-of-turn event. When the client exits, the waiting turn wakes and ends, and later writes are dropped instead of filling the pipe.

The block's end closes stdin, waits for the client, reads the exit code, and removes the container as `run()` does. A cancel or an error in the block kills the client first, then the same teardown runs, shielded.

## Images

`build()` runs on every `run()` and `session()`. Docker's layer cache keeps an unchanged build fast. Your `dockerfile` is built on top of the harness image, tagged by a hash of the Dockerfile's path, for example `botbox-claude-<hash>:latest`.

Each build runs `docker buildx build --load --progress=quiet` as an asyncio subprocess, and keeps the last 64 KiB of its stderr for the error. buildx runs in its own session, so Ctrl-C reaches it only as a cancel. On cancel, botbox stops the buildx client and waits for it to exit, even through a second cancel. BuildKit drops a build when its client goes away.

Concurrent builds of one tag, from any process, all succeed. Each loads its own image and moves the tag onto it, so the tag ends on whichever build finished last. botbox doesn't coordinate them.

Each harness image stands alone, with no shared base. A harness is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to call the CLI. Adding one means one Dockerfile, one class, and one row in the [harness table](../harnesses/).

## Claude Code

- **Image:** `agents/claude/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay and a pinned `@anthropic-ai/claude-code`, with the auto-updater and non-essential traffic turned off.
- **Command:** `claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config`, plus `--model` and `--effort` when set.
- **Session:** `claude -p --input-format stream-json --output-format stream-json --verbose`, with the same permission and MCP flags. Each message goes in as a `user` event. A turn ends at the `result` event.
- **Credentials:** the host login stays on the host. `.claude/.credentials.json` in the box holds placeholder tokens with a far-future expiry, and `ANTHROPIC_BASE_URL` points Claude Code at the credential proxy, which adds `Authorization: Bearer <host access token>` to `POST /v1/messages` and `/v1/messages/count_tokens` on their way to `api.anthropic.com` (see [Credential Proxy](#credential-proxy)). Its access log goes to `credentials.log`. Claude Code also calls `api.anthropic.com` directly for a few things, past `ANTHROPIC_BASE_URL`. botbox turns off its claude.ai MCP server fetch (`ENABLE_CLAUDEAI_MCP_SERVERS=false`). Its OAuth profile fetch is refused by the proxy, and the run goes on without it. With `api_key`, the key stays on the host as well. `.claude/api_key` holds a placeholder key, with a `settings.json` whose `apiKeyHelper` reads it. Claude Code sends that value as both `x-api-key` and `Authorization: Bearer`; the proxy drops the `Authorization` header and sets `x-api-key` to the real key, on the same two paths.
- **Hosts:** none, since the credential proxy carries the traffic.
- **Transcript:** `.claude/projects/**/*.jsonl`.

### Login Expiry

The access token expires, typically within hours, and botbox never renews it. Renewing likely rotates the login, which would sign out the host's own sessions.

Before it starts anything, a run reads the host login and raises `CredentialsExpired` if the token has already expired. While the agent runs, botbox rereads the host's file every 2 seconds and sends a changed token from the next request on. So a renewal that rewrites the host's file reaches a running box. If nothing on the host renews it, a run that outlasts the token fails its turns with a 401.

botbox keeps nothing alive for the login. Claude Code on the host must renew it, as the `CredentialsExpired` message says. A reread that finds the file unreadable or still expired, or a token that can't be sent, is tried again 2 seconds later. An unexpected error stops the following, and the run warns about it when it ends.

### Terms of Service

Anthropic's [legal and compliance page](https://code.claude.com/docs/en/legal-and-compliance) says developers "may not collect, store, or intermediate Claude.ai credentials or session tokens". The same page says this does not prevent "an end user from signing in to the unmodified Claude Code binary with their own Claude subscription".

On a login, botbox runs the unmodified Claude Code, on your machine, with your own subscription. But software other than Claude Code handles your session token: botbox reads it from your login file, and Envoy adds it to Claude Code's requests. If Anthropic reads any such handling as intermediating, this falls under it, as would copying the login into the box. botbox can't settle that. `api_key` avoids the question: the same page allows provisioning your own API key, as long as the usage is billed to you.

## Codex

- **Image:** `agents/codex/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay and a pinned `@openai/codex`.
- **Command:** `codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --disable plugins --disable apps --config analytics.enabled=false <prompt>`, plus `--model` and `--config model_reasoning_effort=` when set. Codex's own sandbox is off because the container is the sandbox.
- **Session:** none. Codex's only long-running mode, `codex app-server`, needs a per-session handshake.
- **Credentials:** the host login stays on the host. `.codex/auth.json` in the box holds unsigned placeholder tokens with the host's account id and plan, a far-future expiry and no usable refresh token. `.codex/config.toml` sets a model provider whose `base_url` is the credential proxy, which adds `Authorization: Bearer <host access token>` to `POST /backend-api/codex/responses` and `GET /backend-api/codex/models` on their way to `chatgpt.com`. `chatgpt_base_url` points at the proxy too, so Codex's account and settings calls get the proxy's 403 rather than leaving past it, and `--disable apps` stops its direct apps MCP call. With `api_key`, `auth.json` holds a placeholder key, and the proxy sends the real one on `POST /v1/responses` to `api.openai.com`. Its access log goes to `credentials.log`.
- **Hosts:** none, since the credential proxy carries the traffic.
- **Expiry:** as in [Login Expiry](#login-expiry): `CredentialsExpired` before the run if the host's access token has expired, and a renewed token sent from the next request on.
- **Transcript:** `.codex/sessions/**/*.jsonl`.

## pi

- **Image:** `agents/pi/Dockerfile`. Node, `git`, `ca-certificates`, `socat`, the relay, `python3`, `ripgrep`, `fd` and a pinned `@earendil-works/pi-coding-agent`.
- **Command:** `pi -p <prompt> --mode json`, plus `--provider <provider> --model <model>` when a model is set. pi rejects `--provider` without `--model`.
- **Session:** `pi --mode rpc`, with the same flags. Each message goes in as a `prompt` command. A turn ends at the `agent_settled` event, since retries and compaction can follow `agent_end`.
- **Credentials:** on `openrouter`, `.pi/agent/auth.json` holds a placeholder key and `.pi/agent/models.json` sets the provider's `baseUrl` to the credential proxy, which adds `Authorization: Bearer <key>` to `POST /api/v1/chat/completions` on its way to `openrouter.ai`. The key is `api_key`, or the literal `openrouter` key in the host's `auth.json`, reread every 2 seconds as for Claude. For any other provider, `auth.json`, and `models.json` if present, are copied into `.pi/agent/`.
- **Hosts:** none for `openrouter`, since the credential proxy carries the traffic. For any other provider, the host of its `baseUrl` in `models.json`.
- **Transcript:** `.pi/agent/sessions/**/*.jsonl`.

In every harness the prompt, model and effort are shell-quoted before they go into the command.
