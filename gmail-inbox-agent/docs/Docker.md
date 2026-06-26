# Docker

This project can run either directly with `uv` or as a one-shot Docker container.

Docker is useful for cron because the host only needs Docker, `.env`, credentials, tokens, rules, and data directories.

## Host Files

These stay on the host and are mounted into the container:

- `.env`
- `data/gmail_credentials.json`
- `data/gmail_token.json`
- `data/memory.sqlite` when using SQLite
- `config/rules.toml`

Ollama can continue running on the host. From Docker, use:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

The project uses `DOCKER_OLLAMA_BASE_URL` as the container override so your normal local `.env` can keep:

```text
OLLAMA_BASE_URL=http://localhost:11434
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

On Linux this is supported by the Docker run and Compose commands in `Taskfile.yml` via `host-gateway`.

## Task Commands

Install [Task](https://taskfile.dev/) if needed, then from `gmail-inbox-agent/`:

```bash
task test
task dry-run -- --max-messages 10
task apply -- --max-messages 1
task docker:dry-run -- --max-messages 10
```

`task docker:run` builds the image and runs the agent with host-mounted `data/` and `config/`:

```bash
task docker:run -- --dry-run --max-messages 10
```

## Direct Docker

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

## Docker Compose With SQLite

SQLite remains the default.

```bash
docker compose run --rm gmail-agent --dry-run --max-messages 10
```

## Docker Compose With Postgres

Postgres is optional and stores reviewed-message memory in a Docker named volume.

```bash
docker compose --profile postgres run --rm gmail-agent-postgres --dry-run --max-messages 10
docker compose --profile postgres down
```

Or with Task:

```bash
task compose:postgres:dry-run -- --max-messages 10
task compose:postgres:apply -- --max-messages 1
```

The Postgres service uses:

```text
postgresql://gmail_agent:gmail_agent@postgres:5432/gmail_agent
```

inside the Compose network. Do not use this simple credential pattern for a shared or hosted production database.

## Cron Example

SQLite Docker run:

```cron
0 7 * * * cd /path/to/gmail-inbox-agent && task docker:run -- --apply --max-messages 25
```

Compose with Postgres:

```cron
0 7 * * * cd /path/to/gmail-inbox-agent && task compose:postgres:apply -- --max-messages 25
```
