Fixed: `CodexAgent.allow` is typed `tuple[str, ...]`, so `Botbox(CodexAgent())` passes strict mypy against the `Agent` protocol.
