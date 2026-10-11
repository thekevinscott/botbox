# Migration fragments

One file per breaking change, added in the PR that makes it — this folder
*is* the migration record. Filenames follow `YYYY-MM-DD-<pkg>-<slug>.md`
(UTC merge date; conventions in [`../changelog.d/README.md`](../changelog.d/README.md)),
and fragments are never deleted or rewritten.

Each fragment has five sections, in order:

1. **Summary** — one paragraph: what changed and why.
2. **Required changes** — before/after for public API. "None" if purely additive.
3. **Deprecations removed** — anything previously warned about that's now gone.
4. **Behavior changes without code changes** — same API, different runtime behavior.
5. **Verification** — commands that confirm the upgrade worked, with expected output.
