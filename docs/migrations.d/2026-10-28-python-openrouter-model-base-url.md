# botbox: an OpenRouter model with its own `baseUrl` is refused

## Summary

On `PiAgent("openrouter", ...)` with the host's login, a model under `models` or `modelOverrides` in the host's `~/.pi/agent/models.json` that sets its own `baseUrl` raises `ValueError` when the run starts. botbox used to drop that `baseUrl`, so the model went to OpenRouter through the credential proxy without a warning.

## Required changes

Remove the model's `baseUrl` to send it to OpenRouter. To reach the model's own server, define it under a provider other than `openrouter` and select that provider.

## Deprecations removed

None.

## Behavior changes without code changes

A run that used to start with such a model now fails before the image builds.

## Verification

Start a run on `openrouter` with the host's `models.json`. It starts, or raises a `ValueError` naming the model that sets a `baseUrl`.
