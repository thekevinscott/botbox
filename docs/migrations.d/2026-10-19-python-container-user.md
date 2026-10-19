# botbox: the container user is `user`

## Summary

The agent images rename the base image's `node` user to `user`, with home `/home/user`. The old name leaked the Node.js base image into an environment that is not Node-specific. UID and GID stay 1000, so bind-mount ownership is unchanged.

## Required changes

A `dockerfile` layer ends as the new user:

```dockerfile
# before
USER node
# after
USER user
```

Mount targets, `workdir` values and in-container paths under the agent's home move:

```python
# before
box.run(command, workdir="/home/node/project")
# after
box.run(command, workdir="/home/user/project")
```

## Deprecations removed

None.

## Behavior changes without code changes

Commands run as `user` with `$HOME=/home/user`. `CLAUDE_CONFIG_DIR` is `/home/user/.claude`; `PI_CODING_AGENT_DIR` is `/home/user/.pi/agent`. No `node` user exists, so a layer with a `RUN` after `USER node` fails to build (`unable to find user node`).

## Verification

```python
from botbox import Botbox, ClaudeAgent

print(Botbox(ClaudeAgent()).run("whoami; echo $HOME").stdout)
```

Expected:

```
user
/home/user
```
