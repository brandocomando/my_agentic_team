# Repository Agent Notes

This repo is public and contains local-first automation agents. Keep changes safe, documented, and easy to review.

## Repository Layout

This is a monorepo of independent agents, each a standalone `uv`/Python project:

- `gmail-inbox-agent/` — reviews Gmail inbox messages, labels/archives mail, and sends a summary report. Most mature: has a `Dockerfile`, `docker-compose.yml`, and CI release automation.
- `personal-finance-agent/` — imports bank CSVs, categorizes spending, and generates monthly reports. MVP stage, no Docker/release automation yet.
- `campsite-finder-agent/` — watches Recreation.gov/ReserveCalifornia for campsite availability and assists with booking. Newest agent, no Docker/release automation yet.

Each agent directory has its own `pyproject.toml`, `src/<package>/`, `tests/`, `Taskfile.yml`, `config/`, `data/`, and `docs/`. `gmail-inbox-agent` and `personal-finance-agent` also have their own `AGENTS.md` with agent-specific safety rules (for example, dry-run defaults and never deleting/replying/forwarding for Gmail, or never committing financial exports for the finance agent). **Check for an `AGENTS.md` inside the agent directory you're working in before making changes** — those rules take precedence for that agent.

See `README.md` for the full agent list/status and `CONTRIBUTING.md` for the contribution flow and repo layout expectations for new agents.

## Build & Test

All commands are run from inside the agent's directory (there is no root-level task runner across agents):

```bash
cd <agent-directory>
task sync   # or: uv sync --extra dev
task test   # or: uv run --extra dev pytest
```

- Tests live under `tests/` and import from `src/` via pytest's `pythonpath` setting in `pyproject.toml` — this is consistent across all three agents.
- `campsite-finder-agent` also needs the `browser` extra for Playwright-based commands: `uv sync --extra dev --extra browser`.
- There is no repo-wide linter, formatter, or type checker configured (no ruff/black/mypy). Don't assume tooling that isn't in an agent's `pyproject.toml` or `Taskfile.yml`.
- Docker builds and CI release automation currently exist only for `gmail-inbox-agent` (`Dockerfile`, `docker-compose.yml`, `.github/workflows/gmail-inbox-agent-release.yml` calling the shared `.github/workflows/reusable-agent-release.yml`). The other two agents don't build or release yet.

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

When behavior changes, update the relevant `docs/` file for that agent. For release workflow changes, update the agent release docs and any reusable workflow notes. See `CONTRIBUTING.md` for the full contribution flow and documentation expectations.
