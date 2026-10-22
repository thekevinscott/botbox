#!/usr/bin/env bash
# Start the credential proxy. Prints the scratch dir the other scripts take.
#   up.sh oauth [credentials.json]   subscription: Bearer token from the host login
#   up.sh apikey                     API key from $ANTHROPIC_API_KEY
#   up.sh codex [auth.json]          ChatGPT login: Bearer token from the host's Codex login
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mode=${1:?oauth, apikey or codex}
envoy_image=envoyproxy/envoy:v1.36.2

mkdir -p "${TMPDIR:-/tmp}/claude"
scratch=$(mktemp -d "${TMPDIR:-/tmp}/claude/spike65-XXXXXX")
chmod 755 "$scratch"
mkdir -m 777 "$scratch/sockets"
mkdir -m 755 "$scratch/creds"
echo "$mode" >"$scratch/mode"

case $mode in
oauth)
    credentials=${2:-$HOME/.claude/.credentials.json}
    header=Authorization
    strip=x-api-key
    upstream=api.anthropic.com
    paths='/v1/messages(/count_tokens)?'
    uv run --no-project python "$here/write_secret.py" oauth "$credentials" "$scratch/creds" --watch \
        >"$scratch/writer.log" 2>&1 &
    echo $! >"$scratch/writer.pid"
    ;;
apikey)
    header=x-api-key
    strip=authorization
    upstream=api.anthropic.com
    paths='/v1/messages(/count_tokens)?'
    uv run --no-project python "$here/write_secret.py" apikey "$scratch/creds"
    ;;
codex)
    login=${2:-$HOME/.codex/auth.json}
    header=Authorization
    strip=x-api-key
    upstream=chatgpt.com
    paths=${CODEX_PATHS:-/backend-api/codex/(responses|models)}
    uv run --no-project python "$here/write_secret.py" codex "$login" "$scratch/creds" --watch \
        >"$scratch/writer.log" 2>&1 &
    echo $! >"$scratch/writer.pid"
    ;;
*) echo "unknown mode $mode" >&2; exit 2 ;;
esac

sed -e "s/__HEADER__/$header/" -e "s/__STRIP__/$strip/" -e "s/__UPSTREAM__/$upstream/g" \
    -e "s#__PATHS__#$paths#" "$here/envoy.yaml.tmpl" >"$scratch/envoy.yaml"
chmod 644 "$scratch/envoy.yaml"

until [ -f "$scratch/creds/secret.yaml" ]; do sleep 0.1; done

name=spike65-envoy-$(basename "$scratch" | cut -d- -f2)
echo "$name" >"$scratch/envoy.name"
docker run -d --name "$name" --label spike65=1 \
    --user 101:101 --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
    --network bridge \
    -v "$scratch/envoy.yaml:/etc/envoy/envoy.yaml:ro" \
    -v "$scratch/creds:/etc/botbox-creds:ro" \
    -v "$scratch/sockets:/run/botbox:rw" \
    "$envoy_image" envoy -c /etc/envoy/envoy.yaml --log-level warn >/dev/null

for _ in $(seq 100); do
    [ -S "$scratch/sockets/creds.sock" ] && break
    sleep 0.1
done
[ -S "$scratch/sockets/creds.sock" ] || { docker logs "$name" >&2; exit 1; }
echo "$scratch"
