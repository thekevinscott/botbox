# botbox: agents reach the proxy over a unix socket

## Summary

Agent containers run with `--network none`. The proxy variables point at `127.0.0.1:41893` inside the container, where `/usr/local/bin/botbox-relay` forwards to the proxy's unix socket. The relay needs `socat`. The built-in harness images ship both.

## Required changes

A custom `Agent` with its own `dockerfile` installs `socat` and copies the relay in. botbox builds it with a `botbox` build context that holds the relay:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends socat
COPY --from=botbox --chmod=755 botbox-relay /usr/local/bin/botbox-relay
```

A `dockerfile` layer on a harness image needs no change, unless it sets the agent's uid to 100. That uid is the proxy's; use another.

## Deprecations removed

None.

## Behavior changes without code changes

- Commands run as `botbox-relay sh -c <command>`. A layer's `ENTRYPOINT` still wraps them.
- Port 41893 on the container's loopback is taken by the relay.
- The agent shares the proxy's PID namespace. `ps` shows the proxy's processes, owned by uid 100.
- No `botbox-jail-*` or `botbox-egress-*` networks are created.

## Verification

```python
from botbox import Botbox, ClaudeAgent

print(Botbox(ClaudeAgent()).run("tail -n +3 /proc/net/dev | cut -d: -f1").stdout)
```

Expected:

```
    lo
```
