from unittest.mock import Mock

from botbox.session_result import session_result


def describe_session_result() -> None:
    async def it_retains_partial_output() -> None:
        live = Mock(stdout=Mock(into=bytearray(b"partial\xff")), stderr=bytearray(b"error\xff"))
        await session_result(live, "proxy log", "image", -1)
        assert live.result.stdout == "partial�"
        assert live.result.stderr == "error�"
        assert live.result.proxy == "proxy log"
        assert live.result.exit_code == -1

    async def it_leaves_stdout_empty_with_no_capture() -> None:
        live = Mock(stdout=None, stderr=bytearray())
        await session_result(live, "", "image", 0)
        assert live.result.stdout == ""
