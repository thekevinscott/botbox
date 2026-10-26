from typing import Any
from unittest.mock import Mock

from adocker.Image.run_args import run_args

NONE: dict[str, Any] = {
    "name": "box",
    "interactive": False,
    "init": False,
    "rm": False,
    "labels": {},
    "user": None,
    "env": {},
    "mounts": (),
    "tmpfs": (),
    "workdir": None,
    "network": None,
    "pid": None,
    "pids_limit": None,
    "cap_drop": (),
    "security_opt": (),
    "log_driver": None,
    "entrypoint": None,
}


def describe_run_args() -> None:
    def it_names_the_container_and_runs_the_command_on_the_image() -> None:
        assert run_args("img", ["sh", "-c", "x"], **NONE) == [
            "run",
            "--name",
            "box",
            "img",
            "sh",
            "-c",
            "x",
        ]

    def it_passes_every_flag_it_is_given() -> None:
        options = {
            **NONE,
            "interactive": True,
            "init": True,
            "rm": True,
            "labels": {"a": "1", "b": "2"},
            "user": "1:2",
            "env": {"HOME": "/h", "X": "y=z"},
            "mounts": [
                Mock(volume_flag="/src:/dst:ro"),
                Mock(volume_flag="vol:/run:rw"),
            ],
            "tmpfs": ["/t:mode=0700"],
            "workdir": "/w",
            "network": "none",
            "pid": "container:p",
            "pids_limit": 64,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges", "x"],
            "log_driver": "none",
            "entrypoint": "sh",
        }
        assert run_args("img", [], **options) == [
            "run",
            "--interactive",
            "--init",
            "--rm",
            "--name",
            "box",
            "--label",
            "a=1",
            "--label",
            "b=2",
            "--user",
            "1:2",
            "--env",
            "HOME=/h",
            "--env",
            "X=y=z",
            "--volume",
            "/src:/dst:ro",
            "--volume",
            "vol:/run:rw",
            "--tmpfs",
            "/t:mode=0700",
            "--workdir",
            "/w",
            "--network",
            "none",
            "--pid",
            "container:p",
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--security-opt",
            "x",
            "--log-driver",
            "none",
            "--entrypoint",
            "sh",
            "img",
        ]

    def it_passes_a_zero_pids_limit() -> None:
        assert run_args("img", [], **{**NONE, "pids_limit": 0})[3:5] == ["--pids-limit", "0"]
