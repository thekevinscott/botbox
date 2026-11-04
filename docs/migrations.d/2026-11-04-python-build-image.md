# botbox: `Botbox.build()` returns an image

## Summary

`Botbox.build()` now returns `botbox.Image`, the image object returned by the final `Dockerfile.build()` step, instead of its tag string.

## Required changes

Before:

```python
tag = await box.build()
```

After:

```python
tag = (await box.build()).tag
```

Callers that run the image through botbox can retain the returned `Image` and call its methods directly.

## Deprecations removed

None.

## Behavior changes without code changes

The returned value is an `Image`, not a `str`. Code that passes it directly to a Docker command must use `.tag`.

## Verification

Run `image = await box.build()` and check that `isinstance(image, botbox.Image)` is true and `image.tag` is the expected Docker tag.
