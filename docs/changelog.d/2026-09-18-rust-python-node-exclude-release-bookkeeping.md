Fixed: Rust, Python, and Node release globs exclude package-root
`testing-conventions.toml` files and the `e2e-attestations/`, `changelog.d/`,
and `migrations.d/` bookkeeping directories. Rust bookkeeping changes no
longer trigger dependent Python and npm releases; Rust source changes
continue to trigger all three packages.
