Changed: with `output`, Python `Botbox.run()` writes everything the proxy container prints
to `proxy.log` in that directory, and `RunResult.proxy` is empty, including in
`Timeout.result`. The file is truncated with the stream files before setup and remains
after teardown. tinyproxy now logs to stdout in the foreground instead of to a file in a
bind-mounted, world-writable directory; that mount is gone. A proxy that won't start
still raises with the last 64 KiB of its output. Calls without `output` keep the proxy
log in `RunResult.proxy` as before.
