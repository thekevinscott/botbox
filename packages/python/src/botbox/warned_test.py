import pytest

from botbox.warned import warned


class Interrupt(BaseException):
    """Stands in for a cancel."""


async def succeed() -> str:
    return "done"


async def fail() -> None:
    raise OSError("daemon gone")


def describe_warned() -> None:
    async def it_awaits_the_step_quietly(recwarn: pytest.WarningsRecorder) -> None:
        await warned(succeed(), "remove the box")
        assert len(recwarn) == 0

    async def it_warns_from_its_caller_instead_of_raising() -> None:
        with pytest.warns(
            RuntimeWarning, match="^botbox could not remove the box: daemon gone$"
        ) as w:
            await warned(fail(), "remove the box")
        assert w[0].filename == __file__

    async def it_lets_an_interrupt_through() -> None:
        async def interrupted() -> None:
            raise Interrupt

        with pytest.raises(Interrupt):
            await warned(interrupted(), "remove the box")
