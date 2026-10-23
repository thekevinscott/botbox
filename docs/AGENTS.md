# Docs — agent contract

The site is the home page (`index.md`), `getting-started.md`, `explanation/index.md`, `threat-model.md`, `harnesses/`, `guide/` and `api/` (one page per public name).
`explanation/index.md` (How It Works) is the only page about what botbox does with Docker and why. Every other page is about using the SDK; link to How It Works rather than explaining internals inline.
`threat-model.md` covers what an attacker in the box can do and what botbox does about it; it links to How It Works for the mechanics.
Don't add pages unless asked.

`internals/`, `changelog.d/`, `migrations.d/` and `AGENTS.md` are contributor
and agent material, kept out of the build by `srcExclude` in
`.vitepress/config.ts`.
