import os
import signal
import threading
from collections.abc import Iterator
from types import FrameType

import pytest

from botbox.sigterm import sigterm_unwinds


@pytest.fixture(autouse=True)
def default_handler() -> Iterator[None]:
    previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    yield
    signal.signal(signal.SIGTERM, previous)


def describe_sigterm_unwinds() -> None:
    def it_raises_system_exit_with_the_shell_exit_code() -> None:
        with pytest.raises(SystemExit) as raised, sigterm_unwinds():
            os.kill(os.getpid(), signal.SIGTERM)
        assert raised.value.code == 143

    def it_runs_finally_blocks_on_the_way_out() -> None:
        ran = []
        with pytest.raises(SystemExit), sigterm_unwinds():
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            finally:
                ran.append("finally")
        assert ran == ["finally"]

    def it_restores_the_default_handler_on_exit() -> None:
        with sigterm_unwinds():
            pass
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL

    def it_restores_the_default_handler_after_unwinding() -> None:
        with pytest.raises(SystemExit), sigterm_unwinds():
            os.kill(os.getpid(), signal.SIGTERM)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL

    def it_keeps_unwinding_until_the_outermost_hold_exits() -> None:
        with sigterm_unwinds():
            with sigterm_unwinds():
                pass
            with pytest.raises(SystemExit):
                os.kill(os.getpid(), signal.SIGTERM)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL

    def it_leaves_a_programs_own_handler_alone() -> None:
        def handler(_signum: int, _frame: FrameType | None) -> None:
            pass

        signal.signal(signal.SIGTERM, handler)
        with sigterm_unwinds():
            assert signal.getsignal(signal.SIGTERM) is handler
        assert signal.getsignal(signal.SIGTERM) is handler

    def it_leaves_a_handler_installed_while_held_alone() -> None:
        def handler(_signum: int, _frame: FrameType | None) -> None:
            pass

        with sigterm_unwinds():
            signal.signal(signal.SIGTERM, handler)
        assert signal.getsignal(signal.SIGTERM) is handler

    def it_does_nothing_off_the_main_thread() -> None:
        seen = []

        def hold() -> None:
            with sigterm_unwinds():
                seen.append(signal.getsignal(signal.SIGTERM))

        thread = threading.Thread(target=hold)
        thread.start()
        thread.join()
        assert seen == [signal.SIG_DFL]
