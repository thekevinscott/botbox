# Allowing hosts

The proxy denies every host by default except the agent's own (`api.anthropic.com` for Claude Code). Add more with `allow`.

```python
Botbox(ClaudeAgent(), allow=["registry.npmjs.org"])
```

For `PiAgent`, the `provider` argument selects the agent's own hosts.

Every connection, admitted or refused, is logged to `result.proxy`.

Next: [Reading the result](./reading-the-result). Background: [Network](../explanation/#network).
