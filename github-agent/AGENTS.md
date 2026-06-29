# GitHub Agent

This agent works against GitHub repository metadata and security findings.

- Default to dry-run for anything that writes to GitHub.
- Never print or commit GitHub tokens.
- Prefer issue creation over direct code changes for scanner findings.
- Deduplicate planned issues before creating anything.
- Use labels with stable prefixes such as `agent:github-agent`, `scanner:trivy`, and `severity:high`.
- Keep scanner reports and runtime logs out of Git.

