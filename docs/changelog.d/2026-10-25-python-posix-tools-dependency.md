Changed: the Python package depends on `posix-tools` from PyPI and no longer ships a
top-level `posix_tools` package of its own. botbox's process helpers moved to the private
`botbox.process`. Nothing in botbox's public API changes.
