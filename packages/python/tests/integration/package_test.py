"""The installed package's public surface: one async `Botbox`, on botbox's own Docker SDK."""

import importlib.metadata
import importlib.util
import inspect

import botbox
from botbox.docker.DockerException import DockerException
from botbox.Timeout import Timeout


def describe_botbox() -> None:
    def it_has_no_async_botbox() -> None:
        assert not hasattr(botbox, "AsyncBotbox")
        assert not hasattr(botbox, "AsyncSession")

    def it_builds_and_runs_as_coroutines() -> None:
        assert inspect.iscoroutinefunction(botbox.Botbox.build)
        assert inspect.iscoroutinefunction(botbox.Botbox.run)

    def it_holds_sessions_as_async_context_managers() -> None:
        assert inspect.isasyncgenfunction(inspect.unwrap(botbox.Botbox.session))
        assert inspect.iscoroutinefunction(botbox.Session.message)

    def it_reaps_dead_runs_as_a_coroutine() -> None:
        assert inspect.iscoroutinefunction(botbox.reap)

    def it_raises_its_own_docker_exception() -> None:
        assert botbox.DockerException is DockerException

    def it_raises_its_own_timeout() -> None:
        assert botbox.Timeout is Timeout

    def it_does_not_depend_on_python_on_whales() -> None:
        requires = importlib.metadata.requires("botbox") or []
        assert not [r for r in requires if r.startswith("python-on-whales")]
        assert importlib.util.find_spec("python_on_whales") is None
