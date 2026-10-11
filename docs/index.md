---
layout: home

hero:
  name: botbox
  tagline: Run a coding agent inside a locked-down Docker container.
  actions:
    - theme: brand
      text: Getting Started
      link: /getting-started
    - theme: alt
      text: How-to Guides
      link: /guide/
    - theme: alt
      text: Explanation
      link: /explanation/

features:
  - title: No capabilities, no privilege escalation
    details: "--cap-drop ALL, no-new-privileges, no setuid binaries."
  - title: Network only to an allowlist
    details: No network access beyond the whitelist.
  - title: Logs available
    details: The agent's transcript and the proxy's log come back on the result.
---
