# How It Works

Why botbox is shaped the way it is.

## The error model

A non-zero exit is a normal `RunResult`. API errors inside the container are the CLI's to handle; they show up in `exit_code` and `stderr`. If the Docker daemon dies mid-run, `run()` still returns a `RunResult` with whatever transcript and proxy log exist.

`run()` raises only when setup fails or the run is interrupted.

## Home and credentials

Each run gets a fresh temporary home, mounted at the agent's home path. After the command exits, transcript files are read into `result.transcript` and the temporary home is deleted.

The harness's login is copied into that home, or a fresh credentials file holds the `api_key` you pass. botbox reads no `.env`. Which files, and where, is on each [harness page](../harnesses/).

## Network

The container joins a Docker `--internal` network. The only way out is a CONNECT proxy that denies by default. The agent contributes its own hosts (`api.anthropic.com` for Claude Code); `allow` adds more.

Every connection, admitted or refused, is logged to `result.proxy`. Network and proxy are per run and removed afterwards, including on failure. The proxy's own way out is Docker's default bridge, so a run takes one network from the daemon's address pool. The proxy accepts clients only from its own jail subnet, so sharing the bridge does not let other containers use it.

There is no network at run time beyond the allowlist, so installs happen in the image build.

Apply this: [Allowing hosts](../guide/allowing-hosts), [Reading the result](../guide/reading-the-result).
