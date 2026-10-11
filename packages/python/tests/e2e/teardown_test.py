"""What a real run leaves behind on the host: nothing, whether the command passes or fails."""

import pytest
from conftest import leftovers

from botbox import Botbox


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    def it_leaves_no_container_network_or_temp_home(box: Botbox, command: str) -> None:
        before = leftovers()
        box.run(command)
        assert leftovers() == before
