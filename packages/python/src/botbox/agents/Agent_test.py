from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints
from unittest.mock import AsyncMock, Mock

import pytest

from botbox.agents.Agent import Agent

if TYPE_CHECKING:
    from botbox.agents.HomeFiles import HomeFiles


def describe_agent() -> None:
    def it_declares_what_an_agent_knows() -> None:
        assert set(get_type_hints(Agent)) == {
            "MESSAGE_TYPE",
            "allow",
            "channel",
            "credential_source",
            "dockerfile",
            "home",
            "image",
            "result",
            "sessions_dir",
        }

    def it_types_the_dockerfile_as_a_path() -> None:
        assert get_type_hints(Agent)["dockerfile"] is Path

    def it_types_the_egress_allowlist_as_a_tuple_of_hosts() -> None:
        assert get_type_hints(Agent)["allow"] == tuple[str, ...]

    def it_has_its_credentials_copied_in_by_default() -> None:
        assert OneShot().credential_source is None

    def describe_abstract_methods() -> None:
        def it_refuses_a_subclass_without_stage_auth() -> None:
            with pytest.raises(TypeError, match="stage_auth"):
                NoStageAuth()  # type: ignore[abstract]

        def it_refuses_a_subclass_without_command() -> None:
            with pytest.raises(TypeError, match="command"):
                NoCommand()  # type: ignore[abstract]

    def describe_without_a_session_mode() -> None:
        def it_has_no_session_command() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().session_command()

        def it_encodes_nothing() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().encode("hi")

        def it_reads_no_message() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().read_message(b"{}\n")


def describe_outside_a_session() -> None:
    async def it_refuses_to_send() -> None:
        with pytest.raises(RuntimeError, match="OneShot has no session open"):
            await OneShot().send("hi")

    def it_refuses_to_open_messages_or_replies() -> None:
        with pytest.raises(RuntimeError, match="no session open"):
            _ = OneShot().messages
        with pytest.raises(RuntimeError, match="no session open"):
            _ = OneShot().replies

    def it_refuses_a_callback() -> None:
        with pytest.raises(RuntimeError, match="no session open"):
            OneShot().on("reply", print)

    def it_has_no_result_yet() -> None:
        assert OneShot().result is None


def describe_in_a_session() -> None:
    @pytest.fixture
    def channel() -> Mock:
        return Mock(send=AsyncMock())

    @pytest.fixture
    def agent(channel: Mock) -> "Talker":
        agent = Talker()
        agent.channel = channel
        return agent

    async def it_sends_the_encoded_message_on_one_line(agent: "Talker", channel: Mock) -> None:
        await agent.send("hi")
        channel.send.assert_awaited_once_with(b"<hi>\n")

    def it_opens_messages_on_everything(agent: "Talker", channel: Mock) -> None:
        assert agent.messages is channel.subscribe.return_value
        [wanted] = channel.subscribe.call_args.args
        assert wanted(Mock(type="tool", text="")) is True

    def it_opens_replies_on_the_agents_own_messages_with_text(
        agent: "Talker", channel: Mock
    ) -> None:
        assert agent.replies is channel.subscribe.return_value
        [wanted] = channel.subscribe.call_args.args
        assert wanted(Mock(type="assistant", text="hi")) is True
        assert wanted(Mock(type="assistant", text="")) is False
        assert wanted(Mock(type="tool", text="hi")) is False

    def it_listens_for_replies_or_messages(agent: "Talker", channel: Mock) -> None:
        agent.on("reply", print)
        agent.on("message", print)
        reply, message = (call.args for call in channel.listen.call_args_list)
        assert reply[1] is message[1] is print
        assert reply[0](Mock(type="tool", text="hi")) is False
        assert message[0](Mock(type="tool", text="hi")) is True


class TalkerType(StrEnum):
    ASSISTANT = "assistant"
    TOOL = "tool"


class Talker(Agent):
    MESSAGE_TYPE = TalkerType
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: "HomeFiles") -> None:
        pass

    def command(self, prompt: str) -> str:
        return prompt

    def encode(self, message: str) -> str:
        return f"<{message}>"


class OneShot(Agent):
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: "HomeFiles") -> None: ...

    def command(self, prompt: str) -> str:
        return prompt


class NoStageAuth(Agent):
    def command(self, prompt: str) -> str:
        return prompt


class NoCommand(Agent):
    def stage_auth(self, home: "HomeFiles") -> None: ...
