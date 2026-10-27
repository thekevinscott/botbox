from collections.abc import Mapping, Sequence

from adocker.Mount import Mount


def run_args(  # noqa: PLR0913
    image: str,
    command: Sequence[str],
    *,
    name: str,
    interactive: bool,
    init: bool,
    rm: bool,
    labels: Mapping[str, str],
    user: str | None,
    env: Mapping[str, str],
    mounts: Sequence[Mount],
    tmpfs: Sequence[str],
    workdir: str | None,
    network: str | None,
    pid: str | None,
    pids_limit: int | None,
    memory: str | None,
    cap_drop: Sequence[str],
    security_opt: Sequence[str],
    log_driver: str | None,
    entrypoint: str | None,
) -> list[str]:
    """The `docker run` arguments for `image` and `command` with these options."""
    flags = [
        *(["--interactive"] if interactive else []),
        *(["--init"] if init else []),
        *(["--rm"] if rm else []),
        "--name",
        name,
    ]
    pairs = [
        *(("--label", f"{key}={value}") for key, value in labels.items()),
        ("--user", user),
        *(("--env", f"{key}={value}") for key, value in env.items()),
        *(("--volume", mount.volume_flag) for mount in mounts),
        *(("--tmpfs", mount) for mount in tmpfs),
        ("--workdir", workdir),
        ("--network", network),
        ("--pid", pid),
        ("--pids-limit", None if pids_limit is None else str(pids_limit)),
        ("--memory", memory),
        ("--memory-swap", memory),
        *(("--cap-drop", cap) for cap in cap_drop),
        *(("--security-opt", option) for option in security_opt),
        ("--log-driver", log_driver),
        ("--entrypoint", entrypoint),
    ]
    flags += [arg for flag, value in pairs if value is not None for arg in (flag, value)]
    return ["run", *flags, image, *command]
