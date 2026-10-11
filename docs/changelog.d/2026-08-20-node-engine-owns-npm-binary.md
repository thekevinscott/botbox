**Fixed** — the template's npm recipe shipped a binary reporting the *previous*
release's version. `putitoutthere.toml` declared `build = [{ mode =
"bundled-cli" }]` without a `[package.bundle_cli]` block, and that block is what
the reusable workflow gates the bundled-cli steps on — `write-crate-version`
included. So `packages/node/scripts/build.mjs` cross-compiled the per-target
binaries itself, baking `CARGO_PKG_VERSION` in from an unbumped
`packages/rust/Cargo.toml`. Two repos generated from this template hit it in
production (thekevinscott/agent-transcripts#3, thekevinscott/steervec#12).

**Changed** — the engine now stages the binary flat at the platform-package
root, so the launcher passes `binaryDir: ''` and `bin-shim` moves to `^0.2.2`
(`binaryDir` landed in 0.2.1). The CI smoke step stages its fake platform
package the same way.

**Removed** — the pre-committed `optionalDependencies`. The engine rewrites them
at publish, so the pinned `0.0.1` entries only ever produced lockfile drift.
