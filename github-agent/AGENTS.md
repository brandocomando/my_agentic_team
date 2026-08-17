# GitHub Agent

This agent will work against GitHub repository metadata and native security findings.

- Default to dry-run for anything that writes to GitHub.
- Never print or commit GitHub tokens.
- Prefer GitHub-native Dependabot, code scanning, and secret scanning data over duplicate scanners.
- Deduplicate planned comments, approvals, issues, or PRs before creating anything.
- Use labels with stable prefixes such as `agent:github-agent`, `source:dependabot`, and `severity:high`.
- Keep exported alert data and runtime logs out of Git.
