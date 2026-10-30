import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'botbox',
  description: 'Run a coding agent inside a locked-down Docker container.',
  base: '/botbox/',
  cleanUrls: true,
  // AGENTS.md is an agent-facing contract, not site content — keep it out of
  // the build. The changelog/migration fragment folders are the raw record
  // (one file per PR, see docs/internals/repo.md); they never publish either.
  // internals/ is contributor/agent-facing material, also excluded.
  // migrations.md is a pointer stub at the conventional path.
  srcExclude: ['**/AGENTS.md', 'changelog.d/**', 'migrations.d/**', 'internals/**', 'migrations.md'],
  themeConfig: {
    sidebar: [
      {
        items: [
          { text: 'Getting Started', link: '/getting-started' },
          { text: 'How It Works', link: '/explanation/' },
        ],
      },
      {
        text: 'Harnesses',
        items: [
          { text: 'Overview', link: '/harnesses/' },
          { text: 'Claude Code', link: '/harnesses/claude' },
          { text: 'Codex', link: '/harnesses/codex' },
          { text: 'pi', link: '/harnesses/pi' },
        ],
      },
      {
        text: 'Guides',
        items: [
          { text: 'Overview', link: '/guide/' },
          { text: 'Extending the image', link: '/guide/extending-the-image' },
          { text: 'Allowing hosts', link: '/guide/allowing-hosts' },
          { text: 'Mounting directories', link: '/guide/mounting-directories' },
          { text: 'Reading the result', link: '/guide/reading-the-result' },
        ],
      },
      {
        text: 'API',
        items: [
          { text: 'Botbox', link: '/api/botbox' },
          { text: 'build()', link: '/api/build' },
          { text: 'run()', link: '/api/run' },
          { text: 'RunResult', link: '/api/run-result' },
        ],
      },
      {
        text: 'Security',
        items: [{ text: 'Threat Model', link: '/threat-model' }],
      },
    ],
    socialLinks: [{ icon: 'github', link: 'https://github.com/thekevinscott/botbox' }],
    search: { provider: 'local' },
    outline: [2, 3],
  },
})
