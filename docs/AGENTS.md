# Docs — agent contract

The docs site is organized by [Diataxis](https://diataxis.fr): every page is
exactly one of four kinds, and that kind is **declared, not implied**. Skim the
[compass](https://diataxis.fr/compass/) before adding or moving a page.

## The four quadrants

| Quadrant | Lives in | Orientation | A page here is… | …and is **not** |
| --- | --- | --- | --- | --- |
| **Tutorial** | `getting-started.md` | learning | a lesson that walks a beginner through a guaranteed-to-succeed first run | a menu of options, an API dump, or the "why" |
| **How-to** | `guide/` | tasks | a recipe that solves one real problem for someone who knows the basics | a teaching exercise or a complete reference |
| **Reference** | `reference/`, `migrations.md` | information | a dry, complete description of the API / config / CLI surface | a tutorial, an opinion, or task framing |
| **Explanation** | `explanation/` | understanding | discursive background: why it works this way, trade-offs, alternatives | step-by-step instructions or exhaustive parameter tables |

Add a `tutorials/` directory once the tutorial outgrows a single page.

Not everything under `docs/` is a quadrant: `internals/` — like `changelog.d/`
and `migrations.d/` — is contributor/agent-facing material excluded from the
build via `srcExclude` in `.vitepress/config.ts`, deliberately outside the four
quadrants.

The cardinal rule: **one mode per page.** When a how-to sprouts an
"understanding" tangent, that paragraph belongs in `explanation/` behind a link
— not inline.

## Local rules

1. **Answer _why_ first.** Open every page by telling the reader why they're
   here — what they'll be able to do or understand when they finish. If a page
   can't justify itself in a sentence, merge or cut it.
2. **Build toward resolution.** No dead ends: every page ends by pointing to the
   next step (the next lesson, the how-to that applies a concept, the reference
   for the details). The set should carry a reader from first run to unblocked.
3. **Declare the quadrant in frontmatter** — every content page carries
   `diataxis: tutorial | how-to | reference | explanation`. The home page
   (`layout: home`) is exempt. Frontmatter is the machine-checkable source of
   truth; the directory layout and sidebar groups mirror it for humans.
4. **One mode per page** (see the cardinal rule above).
5. **Register the page** under its quadrant's group in `.vitepress/config.ts`.
   The top nav and homepage hero are the entry points into the quadrants
   (mirroring the [testing-conventions](https://thekevinscott.github.io/testing-conventions/)
   docs) — keep them pointing there.

## This is a template

These pages are deliberately thin stubs. A library cloning this repo **replaces
the content and keeps the structure** — the four quadrants, the frontmatter
rule, and this file are what's worth inheriting. Keep stubs short: they show the
shape, they aren't meant to be read.

## Enforcement (optional)

Structure over prose, like everything else here. The `diataxis:` key makes a
[`changelog.yml`](../.github/workflows/changelog.yml)-style gate a few lines of
bash — assert every `docs/**/*.md` except the home page declares a valid
quadrant — but it's intentionally **not wired in**; add it if you want a hard
gate. LLM-based docs auditors that grade pages against Diataxis exist too; they
need a key and add cost, so they stay opt-in and never a template default.
