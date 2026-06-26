# Repository Agent Notes

This repo is public and contains local-first automation agents. Keep changes safe, documented, and easy to review.

## Pull Requests

PR titles must be valid conventional commit titles because this repo uses squash merge and the PR title becomes the commit message on `main`.

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

Allowed types used in this repo include:

- `feat`
- `fix`
- `docs`
- `chore`
- `test`
- `build`
- `refactor`
- `perf`
- `style`

Avoid PR titles like `Update docs` or `arm docker fix`; they will become weak squash commit messages and may not drive semantic-release correctly.

## Public Repo Safety

Never commit local secrets, OAuth tokens, Gmail credentials, runtime memory, private rules, logs, virtualenvs, or cache files.

Check ignored files before pushing when working near config/data paths:

```bash
git status --short --ignored
```

## Agent Docs

When behavior changes, update the relevant `docs/` file for that agent. For release workflow changes, update the agent release docs and any reusable workflow notes.
