---
layout: home

hero:
  name: botbox
  tagline: Run a coding agent inside a locked-down Docker container.
  actions:
    - theme: brand
      text: How It Works
      link: /explanation/
    - theme: alt
      text: Get Started
      link: /getting-started

features:
  - title: No capabilities, no privilege escalation
    details: "--cap-drop ALL, no-new-privileges, no setuid binaries."
  - title: Network only to an allowlist
    details: No network access beyond the whitelist.
  - title: Logs available
    details: The agent's output, transcripts and the proxy's log are written to a folder you choose.
---
