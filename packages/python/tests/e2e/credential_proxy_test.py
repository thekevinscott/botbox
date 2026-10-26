"""The credential proxy's Envoy config against the pinned Envoy image."""

import subprocess

from botbox.credential_proxy import Injection, envoy_config, sds_secret
from botbox.credential_proxy.envoy_config import IMAGE, SECRET_DIR, SECRET_FILE

ENVOY_USER = "101:101"
VALIDATE = 'cat >"$1"; exec envoy --mode validate --log-level warn --config-yaml "$2"'


def validate(config: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--user",
            ENVOY_USER,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--tmpfs",
            f"{SECRET_DIR}:uid=101,gid=101,mode=0700",
            "--entrypoint",
            "sh",
            IMAGE,
            "-c",
            VALIDATE,
            "sh",
            SECRET_FILE,
            config,
        ],
        input=sds_secret("Bearer placeholder"),
        capture_output=True,
        timeout=120,
    )


def describe_envoy_config() -> None:
    def it_passes_envoys_validation() -> None:
        injection = Injection(
            "api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)
        )
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode == 0, result.stdout + result.stderr
        assert b"OK" in result.stdout

    def it_passes_with_nothing_to_strip() -> None:
        injection = Injection("chatgpt.com", "/backend-api/codex/responses", "Authorization")
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode == 0, result.stdout + result.stderr

    def it_fails_a_regex_re2_rejects() -> None:
        injection = Injection("api.anthropic.com", "(?<=a)b", "Authorization")
        result = validate(envoy_config(injection, "/run/botbox/credentials.sock"))
        assert result.returncode != 0
