# Spike #65: credential-injecting proxy

Reference only. This directory is a go/no-go prototype for #65, not code to merge.

**Verdict: go.** Claude Code (subscription and API key) and Codex (ChatGPT login) both run in a
`--network none` container that holds only placeholder credentials. An Envoy sidecar outside the
container adds the real token. No TLS interception or CA changes are needed.

## How it works

```
agent container (--network none)            Envoy container (bridge)
  claude / codex                              listener on unix socket
    -> http://127.0.0.1:41894  --socat-->     credential_injector (token from file-watched SDS)
                                              path allowlist, else 403
                                              TLS origination -> api.anthropic.com / chatgpt.com
```

- The agent talks plain HTTP to a loopback port. socat forwards it to a unix socket that Envoy
  serves, the same shape as today's `botbox-relay` and tinyproxy socket.
- Claude Code gets `ANTHROPIC_BASE_URL=http://127.0.0.1:41894`. Codex gets a custom model provider
  with `base_url = http://127.0.0.1:41894/backend-api/codex` and `requires_openai_auth = true`.
- Envoy originates TLS to the real host, so the container never sees a certificate it has to
  trust. Nothing is intercepted.
- The container's login is a placeholder: a fake `.credentials.json` with a far-future expiry
  (so Claude Code stays in subscription mode and never tries to refresh), or a fake Codex
  `auth.json` with unsigned JWTs, the real account id and plan type, and no usable refresh token.
- `write_secret.py` reads the host's login and writes the Envoy SDS secret atomically (temp file
  plus rename). With `--watch` it rewrites the secret whenever the host login file changes. It
  never refreshes anything. Envoy picks up the new file through `watched_directory` without a
  restart.
- Envoy strips the placeholder header and sets the real one: `Authorization: Bearer <token>` for
  OAuth logins, `x-api-key` for an API key.

## Running it

Needs Docker, `uv`, the `botbox-claude:latest` / `botbox-codex:latest` images, and a login on the
host. Scripts take the scratch dir that `up.sh` prints.

```sh
s=$(spikes/65/up.sh oauth)        # or: apikey (reads $ANTHROPIC_API_KEY), codex
spikes/65/agent.sh "$s"           # one claude -p / codex exec call that replies "pong"
spikes/65/agent.sh "$s" <cmd...>  # any command in the box
uv run --no-project python spikes/65/session_test.py "$s" ~/.claude/.credentials.json
spikes/65/down.sh "$s"            # prints Envoy's access log, removes the container and dir
```

`session_test.py` runs three stream-json turns in one session and swaps a bogus token into the
proxy between turns 1 and 2, then the real one back before turn 3.

## Findings

All runs used Claude Code 2.1.296 and codex-cli 0.162.1 from the botbox images, Envoy v1.36.2.

**Subscription through a base URL works.** `claude -p` with a placeholder login and
`ANTHROPIC_BASE_URL` returned the right answer once Envoy swapped in the host's access token.
Claude Code still sends `anthropic-beta: oauth-2025-04-20` and its other betas on its own, because
it thinks it is logged in. The proxy adds no headers beyond `Authorization`.

**Usage lands on the subscription.** Evidence is the response headers, not the billing console:

| mode | `anthropic-ratelimit-unified-status` | `-unified-5h-utilization` | `-tokens-limit` |
|---|---|---|---|
| OAuth token injected | `allowed` | present | absent |
| API key injected | absent | absent | present |

The `total_cost_usd` in Claude Code's result is computed client-side at list price either way.
It is not evidence of API billing.

**Endpoints.** With `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` (already set in the image),
Claude Code in `-p` and stream-json session mode called only `POST /v1/messages?beta=true`,
including tool-use turns. The allowlist is `/v1/messages` and `/v1/messages/count_tokens`
(the latter verified by a direct call). `/v1/models`, `/v1/files`, `/v1/messages/batches` and
`/api/oauth/profile` get a 403 from the proxy. Codex needs `/backend-api/codex/responses` and
`/backend-api/codex/models`. With its `apps` feature on, Codex also calls
`https://chatgpt.com/backend-api/ps/mcp` directly, ignoring the provider base URL; that fails
under `--network none` and costs about 20 seconds of retries, so pass `--disable apps`.

**Streaming works.** Claude Code's SSE and Codex's responses stream both pass through. The route
has `timeout: 0s` and a 600s idle timeout.

**Token expiry mid-run.** The Claude access token lasts 8 hours from refresh. The Codex one lasts
about 10 days.

- Claude Code, on a bad token, retries once and fails in about 2s with
  `api_error_status: 401`, "OAuth access token is invalid". It makes no request to the proxy for
  a refresh. In a session it recovers: once the secret is good again the next turn succeeds,
  with the conversation intact.
- Codex, on a bad token, tries to refresh against `auth.openai.com` 5 times (no route, and the
  refresh token is a placeholder anyway), then emits `turn.failed` after about 44s. Recovery in a
  later turn was not tested (Codex has no botbox session mode).

**Hot reload works.** Rewriting the SDS file took effect on the next request, no restart.

**No leak.** After each run, a byte scan of the agent's home for the host's access, refresh and
id tokens found nothing. The real token exists only in the host scratch dir and in Envoy.

## What it would cost to productize

Roughly a medium change, mostly in `lockdown.py` and the agent classes:

1. **Sidecar.** Either add Envoy beside tinyproxy in the proxy container (two processes, two
   sockets) or replace tinyproxy with Envoy entirely. Replacing needs Envoy's CONNECT handling
   plus a host allowlist (dynamic forward proxy with a CONNECT matcher), which this spike did not
   build. Two processes in one sidecar is the smaller step. The Envoy image is far larger than the
   alpine tinyproxy one.
2. **Relay.** `botbox-relay` forwards a second loopback port to the credential socket. The
   existing `NO_PROXY=localhost,127.0.0.1` already keeps the base URL off tinyproxy.
3. **Token feed.** An asyncio task in the run that follows the host login's mtime and rewrites the
   SDS file in the run dir. About 30 lines; Envoy does the file watching. The secret file must be
   readable by Envoy's uid (101 here); mode 644 inside the owner-only run dir is enough.
4. **Agents.** `stage_auth` writes placeholders instead of copying the login, and the agent
   gets its base URL env or config. The model host leaves the tinyproxy allowlist.
   Codex adds `--disable apps`. API-key mode needs the same treatment so the key never enters
   the box.
5. **Expiry policy.** Decide between a pre-flight check and a keep-alive (see below). A pre-flight
   that refuses to start, or warns, when the token expires within the run's budget is cheap.
6. **Tests.** An e2e that runs each harness through the proxy and asserts no real token is in the
   home afterwards.

## Open questions

- **Idle host expiry.** The host's `claude` refreshes only when used. A run longer than the time
  left on the token will fail with a 401 unless something on the host refreshes it. Options: a
  pre-flight that fails fast when the remaining lifetime is short; or a host-side keep-alive that
  runs the host's own `claude` (its own refresh, with its own locking) when the token nears expiry.
  botbox refreshing the token itself brings back the rotation race. Not tested.
- **Terms of service.** The proxy relays Claude Code's own requests, but the agent can also call
  `/v1/messages` directly through the proxy with any client and get the injected token. A
  user-agent check is trivially spoofed. This is no worse than today, where the agent can read the
  token outright.
- **pi.** Not tested. pi's `models.json` takes a per-provider `baseUrl`, so the same pattern likely
  applies with an `Authorization: Bearer` (OpenRouter) rule.
- **Billing confirmation.** Headers say subscription. Checking the API console for zero usage
  during an OAuth run would close this.
- **Envoy for all egress.** Whether one Envoy can also do tinyproxy's job (CONNECT allowlist,
  per-request logging) well enough to drop tinyproxy.
