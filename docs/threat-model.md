# Threat Model

botbox runs an agent with its permission prompts off. So it treats everything inside the box as hostile: the agent, the files it reads, the pages it fetches and every process it starts. A repo with instructions planted in a README, or a prompt-injected web page, can turn a well-meaning agent into an attacker. This page lists what that attacker can do, what botbox does about it, and what is left to you.

Trusted: the host, the Docker daemon, your code that calls botbox, your `dockerfile`, and your choice of mounts and allowed hosts. Anyone who can reach the Docker daemon is root on the host in practice, and is out of scope.

Each threat has four parts: who attacks, what botbox does about it now, what's left for you to handle, and why botbox doesn't close the gap itself.

## Forged session events

### Who Attacks

Any process in the box: a tool call, a test script from the repo, a build step. The agent CLI's stdout is a pipe to the `docker run` client, which writes it to `stdout.txt`. Processes the CLI starts may inherit it. Any process under the same uid can also open it through `/proc/<pid>/fd/1` of the shell above the CLI. Whatever it writes there lands in `stdout.txt`, and botbox reads it as the agent's output.

### What botbox Does

Nothing. A session parses each JSON line on stdout as an event (see [Sessions](./explanation/#sessions)). A forged end-of-turn event ends `stream()` early, and the real rest of that turn arrives at the start of the next one. A forged `result` can claim success, cost or usage that never happened. `run()` is the same: `stdout.txt` is whatever reached the container's stdout.

### What's Left

All of it. Treat events and `stdout` as agent output, not as facts. Don't gate a decision with security weight on them. The exit code comes from Docker and the proxy log is written by the proxy, out of the agent's reach, so both are firmer ground. Neither proves the work was done.

### Why botbox Doesn't Close It

It can't from outside the container. The CLI and every process it starts run as one uid and write the same pipe, so nothing outside can tell who wrote a line. A fix needs the agent's help: a CLI that writes events to a descriptor its tools can't reach, or runs its tools under another uid.

## Credential theft

### Who Attacks

The agent, or anything it runs. The login botbox stages in the home is readable by the agent's uid. A copied Claude Code or Codex login holds a refresh token as well as the access token, so a stolen copy can outlive the run. An `api_key` is in a file the agent can read too.

### What botbox Does

botbox copies only the harness's credential files into a fresh home, never the host's home or `.env` (see [Home and Credentials](./explanation/#home-and-credentials)). With `api_key`, the box gets a file that holds the key and nothing else. The copy means a refresh inside the box never touches the host's file. The home is deleted after the run.

### What's Left

The agent can read the token and send it out through any allowed host (see the next section), write it into a read-write mount, or print it into a result you publish. Using a stolen refresh token can also rotate the login and sign out the host's own sessions.

### Why botbox Doesn't Close It

It could; it isn't done yet. The box could hold a placeholder, with a sidecar outside it that adds the real token on the way out, so no real token reaches the home. Until then, prefer `api_key` with a scoped key and a spend limit, and revoke it if a run looks wrong.

## Exfiltration through allowed hosts

### Who Attacks

The agent, sending data out. It has nowhere to send it but the proxy.

### What botbox Does

The container has no network and no DNS. The proxy denies by default, checks the whole request URL, and admits only ports 443 and 80 on allowed hosts (see [Network](./explanation/#network)). Every request, admitted or refused, is in `proxy.log` in the run's `output`.

### What's Left

Anything an allowed host accepts. The model host is always allowed. The agent can call its API with a key of the attacker's own and store data in the attacker's account. An allowed code host takes a push or a gist. HTTPS goes through as a CONNECT tunnel, so the proxy sees the host and port, never the path or the body. Inside the tunnel the client can also ask for a different site served from the same address (domain fronting). Whether that works depends on the host's CDN. The proxy log shows which hosts were reached, not what was sent.

### Why botbox Doesn't Close It

Rules on paths and headers need the proxy to see inside TLS. For the model host, the sidecar design above gets there without interception: the agent talks plain HTTP to the sidecar, which allows only the API paths the CLI uses and overwrites the auth header, so a planted key never reaches the API. For other hosts it would take TLS interception with a CA inside the box. That is possible, not done, and breaks clients that pin certificates. A check that the TLS server name matches the CONNECT host would only catch a client that names another site in its TLS hello. Classic fronting names the allowed site there and the other site in the encrypted `Host` header, which only interception sees. Keep `allow` short.

## Host files through mounts

### Who Attacks

The agent, reading or writing what you mount.

### What botbox Does

Nothing from the host is visible except your mounts and the staged credentials. A missing mount source is created as an empty dir owned by you before anything runs. A `"ro"` mount is read-only (see [Mounting directories](./guide/mounting-directories)).

### What's Left

Everything in a mount is readable: `.env` files, tokens in `.git/config` remote URLs, anything else in the tree. A `"rw"` mount lets the agent write files that run later on the host, outside the box: git hooks, `core.hooksPath` or `core.fsmonitor` in `.git/config`, build scripts, package scripts, direnv or editor config. It can also leave a symlink that a host tool follows later.

Reviewing the result is a way in too. Git reads `.git/config` from the repo it runs in, and that file is in the mount. In a clone the agent wrote to, `git status` runs a planted `core.fsmonitor` command and the hooks in a planted `core.hooksPath`. `git diff` runs the fsmonitor command, plus any filter or diff driver that a planted `.gitattributes` names and the planted config defines. `git log` runs a planted `core.pager`. A shell prompt that shows whether the tree is dirty can run the hooks the moment you `cd` in.

### Why botbox Doesn't Close It

Writing to the mount is the feature. botbox can't tell a fix from a planted hook. It could offer a mode that copies a directory in and hands back a diff; that isn't done yet. Until then, keep the agent's tree apart from yours and review it from outside:

1. Mount a fresh clone, not your working tree. Leave out `.env` files, and keep tokens out of its remote URL.
2. Don't run git inside the clone, and don't open it in a tool that runs git for you.
3. Bring the work back from your own repo with `git fetch /path/to/clone <branch>`. The fetch copies the clone's commits and runs nothing from its config or hooks.
4. Review with `git log -p HEAD..FETCH_HEAD` in your repo, so your config applies, not the clone's. Read changes to build scripts, package scripts, `.gitattributes`, `.envrc` and editor config before you check the branch out or run anything from it.

## Resource exhaustion

### Who Attacks

The agent, using up host memory, processes, CPU or disk, by accident or on purpose.

### What botbox Does

The proxy has a process cap. The agent container has none: no memory, process or CPU limit. stdout and stderr go to files in `output`, so the agent can fill that disk; a session holds only the stdout line it is reading, and `output/transcripts/` is a writable mount of the host disk. Both containers run with no Docker log, so the daemon keeps no copy. The home is a Docker volume, so the agent can fill the disk under Docker's data directory. There is no default time limit. `Botbox(timeout=...)` sets one for every run and session, and a call can set its own.

### What's Left

All of the above. Set `timeout`, and keep an eye on the disk under Docker's data directory.

### Why botbox Doesn't Close It

Memory, processes and CPU it could; it isn't done yet. Disk is harder. Docker can't cap a bind mount's size, and the home has to live on the host so the transcripts survive a daemon that goes away. Capping it means a sized filesystem for each run. Time has an option but no default, since runs vary by orders of magnitude.

## The proxy as a way out

### Who Attacks

The agent, sending crafted requests to tinyproxy, the only service it can reach.

### What botbox Does

The proxy runs as its own uid with no capabilities, `no-new-privileges` and a process cap. It listens on its loopback only. Its image and packages are pinned. The agent shares its PID namespace but can't signal it or read its `/proc` (see [Lifetime](./explanation/#lifetime)).

### What's Left

A bug in tinyproxy's request parsing would give the agent code running in the proxy container. That container sits on Docker's default bridge with open egress: the internet, the host's bridge address and the local network.

### Why botbox Doesn't Close It

Limiting the proxy's own egress takes host firewall rules, which need root. botbox runs as you. It keeps the proxy small and pinned instead.

## Container escape

### Who Attacks

The agent, attacking the kernel or Docker.

### What botbox Does

Out of scope: botbox relies on Docker and the kernel. What it adds is in [The Container](./explanation/#the-container): a non-root user, `--cap-drop ALL`, `no-new-privileges`, no setuid binaries in the harness images, no network. Docker's default seccomp profile stays on, and its AppArmor profile where the host has AppArmor.

### What's Left

A kernel bug reachable through the allowed syscalls. Root in the container is root on the host, since the daemon doesn't remap uids by default.

### Why botbox Doesn't Close It

Stronger isolation is daemon config: user namespace remapping, or a sandboxed runtime such as gVisor. botbox can't install either. It could pass a runtime through to `docker run`; that isn't done yet.

## Other local users

### Who Attacks

Another account on the same host, without Docker access.

### What botbox Does

Each run's home and staged credentials live in a Docker volume, under Docker's data directory, which is closed to other users by default. On the way in they pass through a fresh directory from Python's `tempfile`: a random name, made exclusively, open only to its owner (mode 0700), deleted before the agent starts. The volume is removed when the run ends (see [Lifetime](./explanation/#lifetime)).

### What's Left

A `run()` command, prompt included, is in the `docker run` arguments, so any local user can read it in the process list.

### Why botbox Doesn't Close It

The prompt could go in through a file in the run directory; that isn't done yet.

## Image supply chain

### Who Attacks

Whoever controls an upstream image or package.

### What botbox Does

The proxy image is pinned by digest, its packages by version. The harness images pin each CLI by version.

### What's Left

The harness images start `FROM node:24.20.0-slim` by tag, not digest. The Debian packages aren't pinned, and npm resolves each CLI's dependencies at build time unless the package ships a lockfile. A rebuild can pick up whatever upstream serves that day.

### Why botbox Doesn't Close It

It could; it isn't done yet. Digest pins cost a bump for each base image update.

## Planted instructions

### Who Attacks

A repo or page whose content tells the agent what to do.

### What botbox Does

Claude Code runs with `--strict-mcp-config`, so a repo's own MCP config is ignored. Hooks or settings a repo carries run inside the box like any other tool call.

### What's Left

The agent may follow the instructions. Every section above is what follows from that.

### Why botbox Doesn't Close It

botbox can't tell instructions from data. It limits what an agent that follows them can reach.
