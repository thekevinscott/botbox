#!/usr/bin/env bash
# Stop the proxy and secret writer from up.sh, print the proxy's access log, delete the scratch dir.
set -uo pipefail
scratch=${1:?scratch dir from up.sh}
name=$(cat "$scratch/envoy.name")
docker logs "$name" 2>&1 | grep ACCESS
docker rm -f "$name" >/dev/null
[ -f "$scratch/writer.pid" ] && pkill -P "$(cat "$scratch/writer.pid")" 2>/dev/null
[ -f "$scratch/writer.pid" ] && kill "$(cat "$scratch/writer.pid")" 2>/dev/null
rm -rf "$scratch"
