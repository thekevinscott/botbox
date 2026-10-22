# botbox: plain HTTP reaches an allowed host only on port 80

## Summary

The proxy checked an allowed host but not the port for plain HTTP, so an agent could reach any port on an allowed host. It now matches the whole request URL. An allowed host is reachable by CONNECT on 443 and by plain HTTP on 80.

## Required changes

None.

## Deprecations removed

None.

## Behavior changes without code changes

- Plain HTTP to an allowed host on any port but 80 gets a 403 from the proxy, whether the port is in the request URL or the `Host` header. The built-in harnesses send all their traffic through CONNECT, so they're unaffected. Tools an agent runs that send plain HTTP, such as `curl http://...`, are.
- Refusals in `RunResult.proxy` read `Proxying refused on filtered url "<url>"`, not `filtered domain "<host>"`. For CONNECT the URL is `host:port`.

## Verification

```python
from botbox import Botbox, ClaudeAgent

probe = (
    "node -e 'require(\"http\").get({ port: 41893, path: \"http://api.anthropic.com:8022/\" },"
    " (r) => console.log(r.statusCode))'"
)
print(Botbox(ClaudeAgent()).run(probe).stdout)
```

Expected:

```
403
```
