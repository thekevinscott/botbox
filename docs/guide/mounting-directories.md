# Mounting directories

Give the agent directories to read or write by passing bind mounts to `run()`.

```python
result = await box.run(
    command=agent.command("Fix the tests"),
    mounts=[
        ("./reference", "/reference", "ro"),
        ("./out",       "/out",       "rw"),
    ],
    workdir="/out",
)
```

Each mount is host path, container path, mode (`"ro"` or `"rw"`). Missing host paths raise.

If given, `workdir` must be a mounted path or inside one; otherwise `run()` raises. Docker would create it root-owned and the agent could not write to it. Without `workdir`, the command starts in the agent's home.

Next: [Reading the result](./reading-the-result).
