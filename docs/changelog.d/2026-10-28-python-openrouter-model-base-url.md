Changed: on `openrouter`, a model in the host's `models.json` that sets its own `baseUrl` now raises `ValueError` when the run starts. It used to be dropped silently, sending the model to OpenRouter.
