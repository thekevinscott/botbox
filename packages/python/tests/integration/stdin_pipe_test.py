import os

from adocker.Image.StdinPipe import StdinPipe


def describe_StdinPipe() -> None:
    async def it_closes_the_write_end_in_a_forked_child_and_not_in_the_parent() -> None:
        pipe = await StdinPipe.open()
        child = os.fork()
        if child == 0:
            os._exit(0 if pipe.pipe.closed else 1)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert not pipe.pipe.closed
        pipe.release()
        pipe.writer.close()
