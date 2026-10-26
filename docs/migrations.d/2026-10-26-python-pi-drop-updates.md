# botbox: pi's streaming update events are dropped

## Summary

`PiAgent` commands no longer emit `message_update` or `tool_execution_update`, in session events or in `RunResult.stdout`.

## Required changes

Code that read the partial message from `message_update` reads the final one from `message_end`. Code that read tool progress from `tool_execution_update` reads the result from `tool_execution_end`. There is no replacement for the partials themselves.
