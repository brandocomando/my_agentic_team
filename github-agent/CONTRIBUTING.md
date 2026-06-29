# Contributing To GitHub Agent

The GitHub Agent is planned as a repo maintenance and security automation agent. It will inspect scanner output, open labeled GitHub issues for findings, and eventually pick up those issues to propose fixes.

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

Do not commit `.env`, GitHub tokens, scanner reports, issue exports, logs, or local runtime state.

## Common Commands

```bash
task test
task plan -- --input findings/trivy.json
uv run github-agent plan-issues --input findings/trivy.json
```

## Safety Expectations

- Default to dry-run.
- Do not create or modify GitHub issues without an explicit apply mode.
- Never commit scanner reports that may include private paths or dependency metadata.
- Keep issue labels deterministic so scheduled runs can deduplicate work.
- Treat automated fixes as pull-request proposals, not direct pushes to `main`.

## Documentation

Update docs when behavior changes:

- Workflow or architecture changes: [Architecture.md](docs/Architecture.md)
- Planning and milestone changes: [Initial_Plan.md](docs/Initial_Plan.md)

## Commits

Use conventional commit titles with the `github-agent` scope:

```text
feat(github-agent): Add Trivy issue planner
fix(github-agent): Deduplicate scanner findings
docs(github-agent): Document scheduled scans
```

