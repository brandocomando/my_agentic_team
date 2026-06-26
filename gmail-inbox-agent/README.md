# Gmail Inbox Agent

A local Python agent that reviews Gmail inbox messages, classifies them with an LLM, applies labels, archives low-value mail, records local memory, and produces a summary.

It is designed to run safely from your machine, either directly with `uv`, with `docker run`, or through Docker Compose for scheduled one-shot runs.

## Documentation

- [Contributing guide](../CONTRIBUTING.md)
- [Initial implementation plan](docs/Initial_Plan.md)
- [Current architecture](docs/Architecture.md)
- [Gmail OAuth setup](docs/Gmail_OAuth_Setup.md)
- [Classification tuning](docs/Classification_Tuning.md)
- [LLM providers](docs/LLM_Providers.md)
- [Docker and Compose](docs/Docker.md)
- [Release and Docker publishing](docs/Release.md)

## What It Does

- Fetches only Gmail inbox messages.
- Skips messages already reviewed by the agent.
- Classifies each message with OpenAI, Ollama, or conservative fallback logic.
- Applies lowercase labels such as `ai-reviewed`, `ai-work`, and `ai-low-priority`.
- Archives low-value messages by removing the Gmail `INBOX` label.
- Stores reviewed message IDs in SQLite or optional Postgres.
- Sends a summary email only when new messages were processed.

The default mode is dry-run. The agent mutates Gmail only when `--apply` is passed.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A Google Cloud OAuth desktop client for Gmail
- One LLM provider:
  - OpenAI API key, or
  - Ollama running locally
- Optional:
  - Docker
  - Docker Compose
  - [Task](https://taskfile.dev/)

## Setup

1. Clone the repo and enter the agent directory:

```bash
git clone https://github.com/brandocomando/my_agentic_team.git
cd my_agentic_team/gmail-inbox-agent
```

2. Create local config:

```bash
cp .env.example .env
cp config/rules.example.toml config/rules.toml
```

3. Configure `.env`.

For OpenAI:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
USER_EMAIL=your_email@gmail.com
```

For Ollama:

```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.1:8b
USER_EMAIL=your_email@gmail.com
```

4. Follow [Gmail OAuth setup](docs/Gmail_OAuth_Setup.md), then save your OAuth client file at:

```text
data/gmail_credentials.json
```

5. Install dependencies and authenticate Gmail:

```bash
uv sync --extra dev
uv run gmail-inbox-agent --auth-check
```

## Running Locally

Dry-run first:

```bash
uv run gmail-inbox-agent --dry-run
```

Limit the run:

```bash
uv run gmail-inbox-agent --dry-run --max-messages 10
```

Apply changes only when ready:

```bash
uv run gmail-inbox-agent --apply --max-messages 10
```

Or with Task:

```bash
task dry-run -- --max-messages 10
task apply -- --max-messages 1
```

## Running With Docker

Docker uses host-mounted `.env`, `data/`, and `config/` so credentials and memory stay on your machine.

```bash
docker build -t gmail-inbox-agent:local .
docker run --rm \
  --env-file .env \
  -e OLLAMA_BASE_URL="${DOCKER_OLLAMA_BASE_URL:-http://host.docker.internal:11434}" \
  --add-host=host.docker.internal:host-gateway \
  -v "$PWD/data:/app/data" \
  -v "$PWD/config:/app/config" \
  gmail-inbox-agent:local \
  --dry-run --max-messages 10
```

Or with Task:

```bash
task docker:dry-run -- --max-messages 10
```

After releases are published, you can use:

```text
brandocomando8/gmail-inbox-agent:latest
```

## Running With Docker Compose

SQLite remains the default:

```bash
docker compose run --rm gmail-inbox-agent --dry-run --max-messages 10
```

Optional Postgres memory backend:

```bash
task compose:postgres:dry-run -- --max-messages 10
task compose:postgres:apply -- --max-messages 25
```

The Postgres service stores its data in a Docker named volume. App config, Gmail credentials, Gmail token, and rules still live on the host.

## Gmail Scopes

Required Gmail scopes:

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.send`

## Public Repo Safety

This repo is intended to be public. Do not commit local credentials, OAuth tokens, inbox memory, or run logs. The project `.gitignore` keeps `.env`, `data/gmail_credentials.json`, `data/gmail_token.json`, SQLite memory files, virtualenvs, caches, and logs out of Git.

## Cron Example

Local:

```cron
0 7 * * * cd /path/to/gmail-inbox-agent && uv run gmail-inbox-agent --apply
```

Docker Compose with Postgres:

```cron
0 7 * * * cd /path/to/gmail-inbox-agent && task compose:postgres:apply -- --max-messages 25
```
