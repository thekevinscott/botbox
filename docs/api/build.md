# `build()`

```python
await box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. [`run()`](./run) and [`session()`](./session) call this every time; Docker's layer cache keeps an unchanged build fast.

Concurrent builds of one tag, from any process, take turns without blocking the event loop. Cancelling the task, or an `asyncio.timeout` firing, stops the build in progress. A failed build raises `botbox.DockerException` with the build's error in `stderr`.

```python
tag = await Botbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
```
