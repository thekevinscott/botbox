# Docs — agent contract

The site is the home page (`index.md`), `getting-started.md`, `explanation/index.md`, `harnesses/`, `guide/` and `reference/index.md`.
`explanation/index.md` (How It Works) is the only page about what botbox does with Docker and why. Every other page is about using the SDK; link to How It Works rather than explaining internals inline.
Don't add pages unless asked.

`internals/`, `changelog.d/`, `migrations.d/` and `AGENTS.md` are contributor
and agent material, kept out of the build by `srcExclude` in
`.vitepress/config.ts`.
