# `build()`

```python
await box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. [`run()`](./run) calls this every time; Docker's layer cache keeps an unchanged build fast.

Concurrent builds of one tag, from any process, all succeed; the tag ends on whichever finished last. Cancelling the task, or an `asyncio.timeout` firing, stops the build in progress. A failed build raises `botbox.DockerException` with the build's error in `stderr`.

```python
tag = await Botbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
```
