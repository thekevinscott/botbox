import shlex
from collections.abc import Mapping


def with_env(env: Mapping[str, str], command: str) -> str:
    """`command` with `env` set on it as `K=V` prefixes, quoted for the shell."""
    if not env:
        return command
    return " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " " + command
