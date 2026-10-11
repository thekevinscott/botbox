---
diataxis: reference
---

# Migrations

Migration records live in
[`docs/migrations.d/`](https://github.com/thekevinscott/template-lib/tree/main/docs/migrations.d)
in the repository — one timestamped file per breaking change, named
`YYYY-MM-DD-<pkg>-<slug>.md` (UTC merge date). Newest = highest sort order.
The folder is the record: no rendered file is assembled from it.

Changelog entries live alongside in
[`docs/changelog.d/`](https://github.com/thekevinscott/template-lib/tree/main/docs/changelog.d).
Published packages ship both folders where the packaging toolchain allows, so
the installed copy carries a version-exact record.
