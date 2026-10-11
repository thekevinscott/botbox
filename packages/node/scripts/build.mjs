#!/usr/bin/env node
// Builds the publishable JS launcher (`dist/bin.js`) and stages the repo-level
// fragment folders into the package.
//
// The per-target Rust binaries are NOT built here. putitoutthere's bundled-cli
// recipe cross-compiles them (see `[package.bundle_cli]` in putitoutthere.toml),
// which is what stamps the crate version before `cargo build` runs. Building
// them from this script bakes a stale `CARGO_PKG_VERSION` into every published
// binary — the release run never bumps the on-disk Cargo.toml. The engine
// stages each binary flat at the platform-package root, where its npm-platform
// handler picks it up.

import { spawnSync } from 'node:child_process';
import { cpSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const nodePkg = resolve(here, '..');

// The reusable workflow runs this script on every npm row, per-triple ones
// included (`if: matrix.kind == 'npm'`). Those rows exist only to produce a
// binary the engine builds and stages itself, so bail before spending a tsc
// run on a macOS or Windows runner.
const target = process.env.TARGET ?? '';
if (target !== '' && target !== 'main' && target !== 'noarch') {
  console.log(`nothing to build for TARGET=${target}; the engine stages the binary`);
  process.exit(0);
}

// Use the locally-installed tsc, regardless of which package manager
// (`npm` at release-time, `pnpm` at PR-time) populated node_modules.
run('npx', ['--no-install', 'tsc', '-b', '--clean', 'tsconfig.json'], { cwd: nodePkg });
run('npx', ['--no-install', 'tsc', '-p', 'tsconfig.json'], { cwd: nodePkg });

// npm's `files:` allowlist cannot reach outside the package root, so stage the
// repo-level changelog/migration fragment folders here (gitignored); the
// tarball then carries a version-exact record.
for (const dir of ['changelog.d', 'migrations.d']) {
  const staged = join(nodePkg, dir);
  rmSync(staged, { recursive: true, force: true });
  cpSync(join(nodePkg, '..', '..', 'docs', dir), staged, { recursive: true });
}

function run(cmd, args, opts) {
  // shell: true so Windows resolves `.cmd` shims (npx.cmd, tsc.cmd, etc.)
  // without each call hard-coding extensions. Args are static — no injection.
  const res = spawnSync(cmd, args, { stdio: 'inherit', shell: true, ...opts });
  if (res.status !== 0) {
    console.error(`failed: ${cmd} ${args.join(' ')} (exit ${res.status})`);
    process.exit(res.status ?? 1);
  }
}
