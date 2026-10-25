# Contributing To GitHub Agent

The GitHub Agent is planned as a repo maintenance and security automation agent. It is currently paused while we evaluate GitHub-native Dependabot, code scanning, and secret scanning data.

## Local Setup

```bash
cd github-agent
uv sync --extra dev
uv run --extra dev pytest
```

Optional local config:

```bash
cp .env.example .env
cp config/github-agent.example.toml config/github-agent.toml
```

Do not commit `.env`, GitHub tokens, exported alert data, logs, or local runtime state.

## Common Commands

```bash
task test
task status
uv run github-agent status
```

## Safety Expectations

- Default to dry-run.
- Do not create or modify GitHub issues, PRs, or reviews without an explicit apply mode.
- Prefer GitHub-native security alerts and Dependabot PRs over duplicate local scanner output.
- Never commit exported alert data, tokens, logs, or local runtime state.
- Keep issue labels deterministic so scheduled runs can deduplicate work.
- Treat automated fixes as pull-request proposals, not direct pushes to `main`.

## Documentation

Update docs when behavior changes:

- Workflow or architecture changes: [Architecture.md](docs/Architecture.md)
- Planning and milestone changes: [Initial_Plan.md](docs/Initial_Plan.md)

## Commits

Use conventional commit titles with the `github-agent` scope:

```text
feat(github-agent): Add Dependabot alert evaluation
fix(github-agent): Skip noisy code scanning alert
docs(github-agent): Document native security signal review
```
