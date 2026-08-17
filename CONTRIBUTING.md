# Contributing

Thanks for checking out this repo. It is both a working automation project and a public record of how local-first agents are designed, tested, documented, and shipped.

## Repository Layout

- `gmail-inbox-agent/` is the first active agent.
- Future agents should live in their own top-level directories.
- `.github/workflows/` contains reusable CI/release automation.
- Root-level docs describe repo-wide conventions. Agent-specific docs belong inside each agent directory.

## Public Contribution Flow

This is a public repository, but outside contributors should not expect direct push access. The normal flow is:

1. Fork the repository to your own GitHub account.
2. Create a feature branch in your fork.
3. Push your branch to your fork.
4. Open a pull request from your fork back to this repository.

For maintainers with direct access, still use a branch and pull request instead of pushing directly to `main`. This keeps CI, release automation, and review history visible.

## Agent Guides

- [Gmail Inbox Agent contributing guide](gmail-inbox-agent/CONTRIBUTING.md)
- [Gmail Inbox Agent README](gmail-inbox-agent/README.md)
- [GitHub Agent contributing guide](github-agent/CONTRIBUTING.md)
- [GitHub Agent README](github-agent/README.md)

When adding a new agent, include:

- `README.md`
- `CONTRIBUTING.md` if the agent has unique setup or safety rules
- `docs/Architecture.md`
- `.env.example` when configuration is needed
- Tests for meaningful behavior
- Public-repo-safe `.gitignore` entries for local secrets and runtime state

## Public Repo Safety

Never commit:

- `.env` files
- API keys or PATs
- OAuth credentials or tokens
- local rules containing private domains/names
- runtime databases or memory files
- logs
- virtualenvs or caches

Before pushing work near config/data paths, check:

```bash
git status --short --ignored
```

## PR Titles And Squash Merge

PR titles must use conventional commit format because this repo uses squash merge and the PR title becomes the commit message on `main`.

Use:

```text
<type>(<agent-or-area>): <Capitalized summary>
```

Examples:

```text
fix(gmail-inbox-agent): Update to support ARM Docker hosts
feat(gmail-inbox-agent): Add deterministic rules engine
docs(readme): Improve new user setup guide
chore(ci): Add reusable agent release workflow
```

Weak titles such as `Update docs` or `arm docker fix` should be rewritten before merge.

## Documentation Expectations

Update docs when behavior changes. At minimum:

- Architecture changes should update that agent's architecture doc.
- Runtime/deployment changes should update Docker or setup docs.
- Release workflow changes should update release docs.
- New safety rules should be documented in the relevant agent guide.

## Reusable Release Workflow

Agents should prefer `.github/workflows/reusable-agent-release.yml` for release automation. Agent-specific workflows should be thin callers with only agent-specific inputs such as directory, image name, release tag format, and display name.
