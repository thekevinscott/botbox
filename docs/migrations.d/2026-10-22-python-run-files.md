# botbox: run files on disk

## Summary

`RunResult.transcript` and `RunResult.proxy` used to hold file contents in memory. The transcript came out of the agent's home by reading files the agent controls, which a running agent could race with a link. Now each result owns a temp directory, `RunResult.files`, holding the transcript and the proxy log. The transcript is moved in without being read, and links are never followed. The directory is deleted when the result is garbage collected, so a path into it is only good while the result lives.

## Required changes

`transcript` is a directory, each file at its path relative to the agent's home:

```python
# before
for path, text in result.transcript.items():
    ...

# after
for file in result.transcript.rglob("*"):
    if file.is_file():
        path, text = file.relative_to(result.transcript).as_posix(), file.read_text()
```

`proxy` is a path to the log:

```python
# before
print(result.proxy)

# after
print(result.proxy.read_text())
```

Keep the result alive while you use its files, or copy them out:

```python
# after
result.save("runs/fix-tests")
```

Code that constructs `RunResult` itself takes `RunResult(stdout, stderr, exit_code, image, files)`, and the result deletes `files` when collected.

## Deprecations removed

None.

## Behavior changes without code changes

- Transcript bytes are kept as written. Bytes that aren't UTF-8 used to be replaced.
- A transcript file the agent locked (`chmod 0`) is kept and made readable to its owner. It used to be skipped.
- Any link in the transcript folder is skipped, including one that stays inside the home. It used to be read.
- A proxy log that can't be copied warns `botbox could not copy its proxy log` and leaves `proxy.log` empty. The warning used to say `read`.
- A process killed outright leaves its result directory, `botbox-result-*` in the system temp directory.

## Verification

```python
import asyncio

from botbox import Botbox, ClaudeAgent

result = asyncio.run(Botbox(ClaudeAgent()).run("true"))
print(result.transcript.is_dir(), "Starting main loop" in result.proxy.read_text())
files = result.files
del result
print(files.exists())
```

Expected: `True True`, then `False`.
