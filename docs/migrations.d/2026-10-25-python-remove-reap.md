# botbox: no crash sweep

## Summary

`botbox.reap()` is removed, and runs and sessions no longer sweep at start. The sweep deleted what earlier runs left behind, which goes against botbox's rule that run output is never deleted. botbox still tears down its own containers and temp home on a normal end, an error, a cancel or a timeout.

## Required changes

Drop calls to `botbox.reap()`. To clear up after a run whose owner was killed, remove its containers by its token:

```sh
# before
python -c "import asyncio, botbox; asyncio.run(botbox.reap())"

# after
docker rm --force $(docker ps --all --quiet --filter label=botbox.run=<token>)
```

Its temp home is `<token>/` in `botbox-<uid>/` under the system temp directory.

## Deprecations removed

None.

## Behavior changes without code changes

`run()` and `session()` no longer remove containers or temp homes left by runs whose owner died. Those stay until the caller removes them.

## Verification

```sh
python -c "import botbox; print(hasattr(botbox, 'reap'))"
```

Prints `False`.
