"""Integration tests: Docker mocked at the python_on_whales boundary."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def builds() -> list[dict[str, Any]]:
    """Every `docker build` in order: context, tag, Dockerfile, and the Dockerfile's text."""
    return []


@pytest.fixture(autouse=True)
def docker_build(builds: list[dict[str, Any]]) -> Iterator[MagicMock]:
    with patch("python_on_whales.docker.build", autospec=True) as build:

        def record(context: Path, **options: Any) -> None:
            builds.append(
                {
                    "context": Path(context),
                    "tags": options["tags"],
                    "file": Path(options["file"]),
                    "text": Path(options["file"]).read_text(),
                }
            )

        build.side_effect = record
        yield build
