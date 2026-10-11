# Engine owns the npm platform binaries

## Summary

The npm bundled-cli recipe built its per-target binaries from
`packages/node/scripts/build.mjs`, which meant nothing stamped the crate version
before `cargo build` — every published binary reported whatever version the
crate carried at the previous release. Declaring `[package.bundle_cli]` hands
cross-compilation to putitoutthere, whose `write-crate-version` step stamps
first. The binary's location inside the platform package moves as a consequence.

## Required changes

For a repo already generated from this template, mirror all five:

```toml
# putitoutthere.toml — new block. The `build = [{ mode = "bundled-cli" }]` line
# alone gates every bundled-cli step OFF.
[package.bundle_cli]
bin = "<binary-name>"
crate_path = "packages/rust"
```

```ts
// packages/node/src/bin.ts — the engine stages flat; bin-shim defaults to bin/
binaryDir: '',
```

- `packages/node/package.json`: `bin-shim` to `^0.2.2`, and delete the
  `optionalDependencies` block.
- `packages/node/scripts/build.mjs`: delete the cargo branch; the script builds
  only the JS launcher and exits early when `TARGET` names a triple.
- `.github/workflows/node.yml`: stage the smoke step's fake platform package at
  `$target/<binary>`, not `$target/bin/<binary>`.

## Deprecations removed

None.

## Behavior changes without code changes

- `<binary> --version` reports the version actually installed.
- Linux binaries build with `cargo zigbuild` against a pinned glibc 2.17 floor
  rather than the CI runner's glibc, so they run on older distributions.
- The binary sits at `@<scope>/<triple>/<binary>` instead of
  `@<scope>/<triple>/bin/<binary>`. Anything resolving that path directly needs
  updating; anything running the `bin` entry does not.
- The binary now ships executable. Under the nested layout the engine's
  `pickMainFile` chose the `bin` *directory* and the release-time chmod applied
  to it, leaving the binary at 0644 (thekevinscott/putitoutthere#626).

## Verification

```
$ npm install -g <package>
$ <binary> --version
<binary> <the version npm just installed>

$ npm pack @<scope>/x86_64-unknown-linux-gnu --dry-run
# one flat `package/<binary>`, mode -rwxr-xr-x, and "main": "<binary>"
```
