# Python — style

## Type hints

**Python 3.12+ syntax, no `__future__`.**

```python
def process(items: list[Item], *, max_retries: int = 3) -> dict[str, int]:
    ...

# PEP 695 generics (3.12+)
def first[T](items: list[T]) -> T | None:
    return items[0] if items else None

# Class generics
class Cache[K, V]:
    def __init__(self) -> None:
        self._store: dict[K, V] = {}

# Type alias
type UserId = int
type JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]
```

Use `T | None` not `Optional[T]`. Use `list[T]` not `List[T]`. Use `dict`, `tuple`, `set` lowercase. The capital-letter typing-module aliases are legacy.

**Mark the package typed**:

```
mynewproduct/
  py.typed         # empty file; tells type checkers the package has inline hints
```

Then `force-include` it in the wheel build (if hatchling needs hinting):

```toml
[tool.hatch.build.targets.wheel]
packages = ["mynewproduct"]
include = ["mynewproduct/py.typed"]
```

**dataclass for internal data, Pydantic at boundaries.**

```python
# Internal data shape — dataclass
from dataclasses import dataclass

@dataclass
class IterationResult:
    eval_idx: int
    iteration: int
    response: str
    passed: bool
    cached: bool = False

# LLM / network / user-input boundary — Pydantic
from pydantic import BaseModel, Field, ConfigDict

class Judgment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    passed: bool = Field(alias="pass", description="...")
    reasoning: str = Field(default="", description="...")
```

Pydantic's validation cost is paid only where validation is *useful* (parsing JSON from a model, validating user-supplied YAML). Internal data structures pay nothing.

**`Protocol` for structural typing**, **`TypeVar` is mostly obsolete** in 3.12+ (PEP 695 generics replace it).

```python
from typing import Protocol

class Loader(Protocol):
    def load(self, name: str) -> bytes: ...
```

**Import from `typing` only the names you use.** `Literal`, `Final`, `ClassVar`, `Annotated` each have real uses; pull them in deliberately.

**Type checker**: `ty` (Astral, alpha as of 2026), `mypy` (mature, stable), or `pyright` (Microsoft, fast). **Pick one and run it in CI.** For a library shipping to PyPI right now, mypy is the safest pick — `mypy --strict` finds the most footguns.

**Hints carry the public API contract.** Every public function and method has them; documentation explains *why*, not *what*.

---

## Async / sync discipline

**Default to async.**

- **`asyncio` only.**
- **Bounded concurrency via `asyncio.Semaphore`**:

  ```python
  sem = asyncio.Semaphore(parallel)
  async def run_one(t):
      async with sem:
          return await do_thing(t)
  results = await asyncio.gather(*(run_one(t) for t in tasks))
  ```

- **Fully consume async generators** — drain to completion rather than early-`break` or early-`return`. anyio's CancelScope errors under `asyncio.gather` come from leaving generators partially consumed. Drain the generator and defer exceptions:

  ```python
  result, deferred_error = None, None
  async for message in stream:
      if deferred_error is not None:
          continue   # drain the generator
      try:
          result = process(message)
      except Exception as e:
          deferred_error = e
  if deferred_error is not None:
      raise deferred_error
  ```

  Only relevant when aggregating multiple async iterators.

- **Sync-from-async** bridge — running a coroutine from sync code when there's already an event loop running. Use a fresh `ThreadPoolExecutor`:

  ```python
  def run_sync(coro):
      try:
          loop = asyncio.get_running_loop()
      except RuntimeError:
          return asyncio.run(coro)
      with ThreadPoolExecutor(max_workers=1) as pool:
          return pool.submit(asyncio.run, coro).result()
  ```

- **Sync core, async wrapper** is the right architecture for libraries that wrap I/O. Keep pure-computation code sync; add an async surface only when there's real I/O to overlap.

**Async hygiene**:

- An `async def` body actually `await`s something. If it doesn't, drop the `async`.
- Library code leaves the event loop to the caller. `asyncio.run` lives at the program entrypoint.
- Sleep is `await asyncio.sleep(n)` inside `async def`.
- Blocking I/O moves through `asyncio.to_thread` — or use the async client (`httpx.AsyncClient`, `aiofiles`).

---

## What good Python code looks like

- **Typed public surface**: every public function, method, and exported value has explicit hints. The signature is the contract.
- **Native 3.12+ syntax**: `list[T]`, `dict[K, V]`, `T | None`, PEP 695 generics (`def first[T](xs: list[T]) -> T | None`). Type aliases via `type Foo = ...`.
- **Specific exception handling**: each `except` names a concrete exception class and either re-raises with context, logs, or converts to a documented return value. A one-line comment explains the conversion.
- **`subprocess.run([...], shell=False)`** for process invocation. `json.loads` / `ast.literal_eval` for structured-data parsing. `pathlib.Path` for filesystem.
- **Default args are immutable**: `items: list[T] | None = None`, then `items = items if items is not None else []` inside the function.
- **Identity comparison for sentinels**: `is None`, `is True`, `is False` — or just truthiness (`if x:`, `if not x:`, `if not xs:`).
- **`for i, item in enumerate(items):`** and `for k, v in d.items():` over index-by-range.
- **f-strings** for interpolation. Always.
- **Explicit `__all__`** in every `__init__.py`. Heavy-dep subpackages loaded via PEP 562 `__getattr__`.
- **Slotted, frozen dataclasses where the data is immutable**: `@dataclass(frozen=True, slots=True)`. Catches typo-assignments and saves memory.
- **`Protocol` for structural typing** over inheritance. PEP 695 generics over `TypeVar` on 3.12+.
- **`cast(T, x)` carries a comment** explaining the unverified assumption.
- **Docstrings start with the verb** ("Parse a document and ..."), describe *why*, and let the signature carry the types.
- **Env vars read through a small config module** with documented defaults, not scattered `os.environ["FOO"]`.
- **`uv run pytest`, `ruff check`, `ruff format --check`, `ty check`** all green before review.
