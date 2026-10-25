import os

from botbox.posix_tools.process import owner_only


def describe_owner_only() -> None:
    def it_closes_the_pipe_in_a_forked_child_and_not_in_the_parent() -> None:
        read, write = os.pipe()
        with os.fdopen(write, "wb") as pipe, owner_only(pipe):
            child = os.fork()
            if child == 0:
                os._exit(0 if pipe.closed else 1)
            _, status = os.waitpid(child, 0)
            assert os.waitstatus_to_exitcode(status) == 0
            assert not pipe.closed
        os.close(read)
