"""The installed package's public surface: one async `Botbox`, on botbox's own Docker SDK."""

import importlib.metadata
import importlib.util
import inspect

import adocker
import botbox
from adocker import DockerException
from botbox.Timeout import Timeout


def describe_botbox() -> None:
    def it_has_no_async_botbox() -> None:
        assert not hasattr(botbox, "AsyncBotbox")

    def it_builds_and_runs_as_coroutines() -> None:
        assert inspect.iscoroutinefunction(botbox.Botbox.build)
        assert inspect.iscoroutinefunction(botbox.Botbox.run)

    def it_exports_one_agent_base_class() -> None:
        assert inspect.isabstract(botbox.Agent)
        agents = (botbox.ClaudeAgent, botbox.CodexAgent, botbox.PiAgent)
        assert all(issubclass(agent, botbox.Agent) for agent in agents)
        assert not hasattr(botbox, "SessionAgent")
        assert not hasattr(botbox, "InjectingAgent")

    def it_raises_its_own_docker_exception() -> None:
        assert botbox.DockerException is DockerException

    def it_raises_its_own_timeout() -> None:
        assert botbox.Timeout is Timeout

    def it_does_not_depend_on_python_on_whales() -> None:
        requires = importlib.metadata.requires("botbox") or []
        assert not [r for r in requires if r.startswith("python-on-whales")]
        assert importlib.util.find_spec("python_on_whales") is None


def describe_adocker() -> None:
    def it_exports_only_its_classes() -> None:
        assert adocker.__all__ == [
            "Container",
            "DockerException",
            "Dockerfile",
            "Image",
            "Mount",
            "Volume",
        ]
        assert all(inspect.isclass(getattr(adocker, name)) for name in adocker.__all__)

    def it_does_its_docker_work_as_coroutines() -> None:
        assert inspect.iscoroutinefunction(adocker.Dockerfile.build)
        assert inspect.iscoroutinefunction(adocker.Image.run)
        assert inspect.iscoroutinefunction(adocker.Container.wait)
        assert inspect.iscoroutinefunction(adocker.Container.exec)
        assert inspect.iscoroutinefunction(adocker.Volume.__aenter__)

    def it_shares_botboxs_docker_exception() -> None:
        assert adocker.DockerException is botbox.DockerException
