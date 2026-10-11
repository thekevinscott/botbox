from pathlib import Path

from botbox.agents.ClaudeAgent import ClaudeAgent
from botbox.Botbox import Botbox


def describe_botbox() -> None:
    def it_keeps_the_agent() -> None:
        agent = ClaudeAgent()
        assert Botbox(agent).agent is agent

    def it_has_no_dockerfile_by_default() -> None:
        assert Botbox(ClaudeAgent()).dockerfile is None

    def it_holds_the_dockerfile_as_an_absolute_path(tmp_path: Path) -> None:
        assert Botbox(ClaudeAgent(), dockerfile=str(tmp_path / "Dockerfile")).dockerfile == (
            tmp_path / "Dockerfile"
        )

    def it_allows_nothing_extra_by_default() -> None:
        assert Botbox(ClaudeAgent()).allow == ()

    def it_holds_the_extra_hosts_as_a_tuple() -> None:
        assert Botbox(ClaudeAgent(), allow=["registry.npmjs.org"]).allow == ("registry.npmjs.org",)
