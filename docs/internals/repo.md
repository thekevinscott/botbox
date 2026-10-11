# Repo-wide conventions

Cross-cutting rules that apply across all language packages. Language-specific guidance lives in `python-supervision.md`, `typescript-supervision.md`, `rust-supervision.md`.

## Changelog + migration fragments

The changelog and migration record are **append-only fragment folders** at the repo root: `docs/changelog.d/` and `docs/migrations.d/`. The folders *are* the record — no rendered CHANGELOG is assembled at release time, nothing commits back to `main` per release, and fragments are never deleted, rewritten, or "flushed". One fragment per PR, added in that PR, keeps concurrent PRs structurally conflict-free (a shared changelog file makes every pair of in-flight PRs merge-conflict by construction). Both folders sit under `docs/` but are excluded from the docs site via VitePress `srcExclude`. The philosophy is global — every language package follows it.

Every PR that changes public API adds at least one fragment naming each touched package. Enforced in CI by [`changelog.yml`](../../.github/workflows/changelog.yml); a `skip-changelog:` trailer bypasses the check for genuinely internal refactors.

**Filenames** — `YYYY-MM-DD-<pkg>-<slug>.md`, where the date is the UTC *merge* date, not the author date (authored timestamps interleave wrongly across long-lived branches). Plain `ls` sorts chronologically; newest = highest sort order. For version attribution ("which release shipped X"), map fragment dates against tags via `git log --tags --simplify-by-decoration --format='%cI %d'`.

**Changelog fragments** (`docs/changelog.d/`) — a few sentences per fragment. Lead with the Keep a Changelog category (`Added` / `Changed` / `Deprecated` / `Removed` / `Fixed`); breaking changes carry a `**BREAKING**` marker and link to their `migrations.d/` fragment.

**Migration fragments** (`docs/migrations.d/`) — one per breaking change. Each has five sections, in order:

1. **Summary** — one paragraph: what changed and why.
2. **Required changes** — before/after for config, CLI flags, function/method arguments, action inputs. "None" if purely additive.
3. **Deprecations removed** — anything previously warned about that's now gone. "None" if nothing was removed.
4. **Behavior changes without code changes** — same API, different runtime behavior (tag format, exit codes, defaults).
5. **Verification** — commands the consumer runs to confirm the upgrade worked, with the expected output.

**Stubs at the conventional paths** — `packages/<pkg>/CHANGELOG.md`, `packages/<pkg>/MIGRATIONS.md`, and `docs/migrations.md` are short pointers into the folders, so anyone fetching the conventional filename gets one hop instead of a 404. Never append entries to the stubs.

**Ship the folders in artifacts where the toolchain allows** — the npm package stages both folders into the tarball at build time (`files:` allowlist + a copy step in `scripts/build.mjs`), so the installed copy under `node_modules/` is version-exact: it contains precisely the fragments up to that release. `cargo package` and maturin cannot include files outside the package root, so crate and wheel consumers take the stub → folder hop on GitHub instead.

Public-API surface for the purpose of these fragments: every exported value/type, every CLI flag, every config key, every observable artifact (tag format, GitHub Release body shape). Internal refactors, test-only changes, and docs-only edits stay out.

## CI logic in scripts, not workflow YAML

CI behavior that's more than glue lives in an **executable, tested script**, not inline in workflow or composite-action YAML. An inline `run:` / `actions/github-script` block can't be run locally, linted, or unit-tested — it only executes inside a CI run, where a typo surfaces as a failed job three minutes later. The fix is the move the rest of this repo already makes: turn it into source and give it a colocated test.

**The line.** A `run:` step is fine when it's a few straight-line commands, or a lone guard (`if … then exit; fi` around an early exit). Extract it the moment it grows iteration (`for` / `while` / `until` / `select`), multi-branch dispatch (`case`), text-munging (`awk` / `sed`, chained `grep` pipelines), or simply gets long. The trigger is *logic*, not line count — five sequential `mkdir` / `install` commands stay inline; a three-line `for` loop goes.

**Where it goes.** Extracted logic lives in an executable, tested script — a subcommand of a small package with colocated tests (`foo.py` ↔ `foo_test.py`, the same testing-conventions standard the packages follow), invoked from the workflow as a one-line `run:`. Python is the default; the language is open, but it must be executable and testable. A check that more than one repo needs belongs upstream in the tool that owns it (testing-conventions, putitoutthere, pr-monitor), not in a per-repo package. This repo's one remaining local gate is the changelog check in [`ci/`](../../ci/) (`uv run --project ci ci check-changelog`), tested in [`gha-scripts.yml`](../../.github/workflows/gha-scripts.yml) and locally via `just gha-test`. Convention source: [thekevinscott/putitoutthere#452](https://github.com/thekevinscott/putitoutthere/issues/452).

**Enforcement.** testing-conventions' [`workflow-lint`](https://github.com/thekevinscott/testing-conventions) check (`just gha-lint`, and [`workflow-lint.yml`](../../.github/workflows/workflow-lint.yml)) scans every workflow and composite action and fails CI on an inline block that crosses the line. It's a pragmatic scanner, not a shell parser — it keys on the unambiguous markers above and favors precision, so a borderline body may slip through. Extract those by judgment anyway; an extracted script is always testable, and the check stops complaining.
