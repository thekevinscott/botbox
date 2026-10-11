# Python — testing

**pytest, with `pytest-describe` for BDD-flavour grouping and `pytest-asyncio` for async.**

```python
# mynewproduct/core_test.py
import pytest
from mynewproduct.core import process

def describe_process():
    def describe_when_items_is_empty():
        def it_returns_empty_dict():
            assert process([]) == {}

    def describe_when_items_has_duplicates():
        def it_counts_each_item():
            result = process(["a", "a", "b"])
            assert result == {"a": 2, "b": 1}

    @pytest.mark.parametrize("items,expected", [
        ([], {}),
        (["a"], {"a": 1}),
        (["a", "a"], {"a": 2}),
    ])
    def it_handles_various_inputs(items, expected):
        assert process(items) == expected
```

Naming convention: **`foo.py` ↔ `foo_test.py` colocated**. The legacy `test_foo.py` prefix also works (pytest discovers both with `python_files = ["*_test.py", "test_*.py"]`).

**Why colocated**: the test file sits next to its subject. Move the source file, the test moves with it. The directory hierarchy is the source hierarchy.

**`tests/` directory** holds integration tests, e2e tests, and shared fixtures. Unit tests live next to source.

**Async tests** — `asyncio_mode = "auto"` removes the `@pytest.mark.asyncio` decorator boilerplate:

```python
async def it_awaits_the_thing():
    result = await my_async_function()
    assert result == expected
```

With `asyncio_mode = "auto"`, async tests are picked up automatically. Reserve `@pytest.mark.asyncio` for the one-off case where you need a non-default loop scope or marker.

**Fixtures** in `conftest.py`. Prefer fixtures over inline `with patch(...)`:

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path

@pytest.fixture
def mock_external_api(mocker):
    api = mocker.patch("mynewproduct.external.fetch")
    api.return_value = {"status": "ok"}
    return api
```

For mocking a streaming external service (LLM client, network stream), build a fixture that exposes `set_response`, `set_error`, `set_responses` so each test configures the mock declaratively.

**Coverage** with `pytest-cov`, `branch=true`, `fail_under` set per project — 85 is a reasonable floor; aiming for 100 forces tests for trivia.
