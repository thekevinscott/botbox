# `RunResult`

A frozen dataclass containing only `exit_code`, the command's exit code. A non-zero exit is a normal result. The code is -1 if no exit code was available, including a timeout or interrupted session.

Output is written live into the required `output` folder:

```text
output/
  stdout.txt
  stderr.txt
  transcripts/
  proxy/tinyproxy.log
```

The folder is created if needed. Use a separate folder for each run or session: stdout and stderr are opened afresh, while existing transcript files and unrelated caller files remain. botbox leaves this folder in place after success, failure, cancellation or timeout. After a process is killed, whatever reached disk remains; unflushed output and power loss are outside this guarantee.

See [Reading the result](../guide/reading-the-result) for examples.
