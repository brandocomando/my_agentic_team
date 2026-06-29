# GitHub Agent

GitHub Agent is a planned repository maintenance agent for this public agent collection. It will run on schedules, collect security and maintenance findings from open-source scanners, open labeled GitHub issues, and eventually attempt safe fixes through pull requests.

## Status

Early scaffold. The first implemented behavior turns scanner JSON into deterministic GitHub issue proposals in dry-run mode.

## Documentation

- [Contributing guide](CONTRIBUTING.md)
- [Initial plan](docs/Initial_Plan.md)
- [Architecture](docs/Architecture.md)

## What It Will Do

- Run scheduled scans through GitHub Actions.
- Ingest scanner output from tools such as Trivy and pip-audit.
- Normalize findings into stable issue proposals.
- Label issues by agent, scanner, severity, and target area.
- Avoid duplicate issues for the same underlying finding.
- Later, pick up labeled issues and attempt fixes through pull requests.

## Setup

```bash
cd github-agent
uv sync --extra dev
cp .env.example .env
cp config/github-agent.example.toml config/github-agent.toml
```

## Plan Issues From Scanner Output

Save scanner output under `findings/` locally. That directory is ignored by Git.

```bash
uv run github-agent plan-issues --input findings/trivy.json
```

For pip-audit JSON:

```bash
uv run github-agent plan-issues --scanner pip-audit --target gmail-inbox-agent --input findings/pip-audit.json
```

The command prints issue proposals as JSON. It does not create GitHub issues yet.

## Python Dependency Audits

`pip-audit` is included as a dev dependency for Python vulnerability checks:

```bash
uv run pip-audit --format json
task scan:pip-audit
```

Use `--target` when planning issues from pip-audit output because pip-audit reports vulnerable packages, not the repo path that produced the report.

## Public Repo Safety

Never commit GitHub tokens, scanner reports, issue exports, logs, or local runtime state. This agent is designed for a public repository, so examples and docs should avoid private package names, private paths, and real vulnerability data unless already public.
