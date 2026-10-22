#!/usr/bin/env bash
# Run a command in a harness image with no network and no real credential.
#   agent.sh <scratch> [command...]     default: a one-word claude -p or codex exec call
# Stdin is passed through, so stream-json sessions work.
set -euo pipefail
scratch=${1:?scratch dir from up.sh}
shift
here=$(cd "$(dirname "$0")" && pwd)
mode=$(cat "$scratch/mode")
image=${AGENT_IMAGE:-botbox-claude:latest}
[ "$mode" = codex ] && image=${AGENT_IMAGE:-botbox-codex:latest}
port=41894

home=$scratch/home
if [ ! -d "$home" ]; then
    mkdir -m 700 "$home" "$home/.claude" "$home/.codex"
    if [ "$mode" = oauth ]; then
        # A placeholder login: Claude Code runs in subscription mode but holds nothing real.
        # The far expiry stops it trying to refresh.
        cat >"$home/.claude/.credentials.json" <<'JSON'
{"claudeAiOauth":{"accessToken":"sk-ant-oat01-placeholder","refreshToken":"sk-ant-ort01-placeholder","expiresAt":4102444800000,"scopes":["user:inference","user:profile","user:sessions:claude_code"],"subscriptionType":"max"}}
JSON
    fi
    if [ "$mode" = codex ]; then
        uv run --no-project python "$here/fake_codex_login.py" "${CODEX_LOGIN:-$HOME/.codex/auth.json}" \
            >"$home/.codex/auth.json"
        cat >"$home/.codex/config.toml" <<TOML
model_provider = "boxed"
[model_providers.boxed]
name = "boxed"
base_url = "http://127.0.0.1:$port/backend-api/codex"
wire_api = "responses"
requires_openai_auth = true
TOML
    fi
fi

envs=(-e "ANTHROPIC_BASE_URL=http://127.0.0.1:$port")
[ "$mode" = apikey ] && envs+=(-e "ANTHROPIC_API_KEY=sk-ant-api03-placeholder")

if [ $# -eq 0 ] && [ "$mode" = codex ]; then
    set -- codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
        --disable plugins --disable apps --config analytics.enabled=false "Reply with exactly the word pong."
elif [ $# -eq 0 ]; then
    set -- claude -p "Reply with exactly the word pong." --output-format json \
        --dangerously-skip-permissions --strict-mcp-config --model haiku
fi

exec docker run --rm -i --label spike65=1 \
    --network none --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" \
    -v "$scratch/sockets:/run/botbox:ro" \
    -v "$home:/home/user" \
    "${envs[@]}" \
    "$image" sh -c "(socat TCP-LISTEN:$port,bind=127.0.0.1,fork,reuseaddr UNIX-CONNECT:/run/botbox/creds.sock &)
until grep -q ':A3A6 00000000:0000 0A' /proc/net/tcp; do sleep 0.02; done
exec \"\$@\"" sh "$@"
