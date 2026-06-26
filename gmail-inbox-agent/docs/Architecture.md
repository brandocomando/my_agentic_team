# Gmail Inbox Agent Architecture

This document is the living architecture reference for the Gmail Inbox Agent. Keep it updated when workflow steps, safety rules, labels, storage, infrastructure, or deployment automation change.

The original implementation spec lives in [Initial_Plan.md](./Initial_Plan.md). This file reflects the current implementation.

## System Overview

```mermaid
flowchart TD
    Cron["cron / local scheduler"] --> CLI["uv run gmail-inbox-agent"]
    CLI --> Graph["LangGraph workflow"]
    Graph --> GmailFetch["Gmail API: fetch inbox"]
    Graph --> MemoryRead["SQLite memory: reviewed IDs"]
    Graph --> Classifier["LLM classifier"]
    Graph --> Rules["config/rules.toml"]
    Graph --> GmailActions["Gmail API: labels and archive"]
    Graph --> MemoryWrite["SQLite memory: record review"]
    Graph --> Summary["Summary report"]
    Summary --> Console["Rich CLI output"]
    Summary --> GmailSend["Gmail API: send email"]

    GmailFetch --> Inbox[("User Gmail Inbox")]
    GmailActions --> Inbox
    GmailSend --> Inbox
    MemoryRead --> DB[("data/memory.sqlite")]
    MemoryWrite --> DB
```

## LangGraph Workflow

The agent runs a linear workflow today. Each node receives and returns `AgentState`.

```mermaid
flowchart LR
    A["load_config"] --> B["authenticate_gmail"]
    B --> C["fetch_inbox_messages"]
    C --> D["filter_unreviewed_messages"]
    D --> E["classify_messages"]
    E --> F["apply_gmail_actions"]
    F --> G["record_memory"]
    G --> H["send_summary"]
```

## Message Processing Sequence

```mermaid
sequenceDiagram
    participant User as Local User
    participant CLI as gmail-inbox-agent CLI
    participant Graph as LangGraph
    participant Gmail as Gmail API
    participant Memory as SQLite Memory
    participant LLM as LLM Provider

    User->>CLI: uv run gmail-inbox-agent --dry-run or --apply
    CLI->>Graph: Start AgentState
    Graph->>Gmail: Authenticate with OAuth
    Graph->>Gmail: Fetch in:inbox -label:"ai-reviewed"
    Gmail-->>Graph: Inbox messages
    Graph->>Memory: Check reviewed message IDs
    Memory-->>Graph: Already reviewed status
    Graph->>LLM: Classify unreviewed messages with OpenAI or Ollama
    LLM-->>Graph: EmailClassification JSON
    alt dry run
        Graph-->>CLI: Print intended actions
    else apply
        Graph->>Gmail: Apply labels
        Graph->>Gmail: Remove INBOX label when safe to archive
        Graph->>Memory: Store reviewed message IDs
        Graph->>Gmail: Send summary email
    end
    CLI-->>User: Summary and final status
```

## Gmail OAuth Check

```mermaid
sequenceDiagram
    participant User as Local User
    participant CLI as gmail-inbox-agent CLI
    participant Browser as Browser OAuth
    participant Gmail as Gmail API

    User->>CLI: uv run gmail-inbox-agent --auth-check
    CLI->>Browser: Open OAuth approval when token is missing
    Browser-->>CLI: OAuth grant
    CLI->>Gmail: Request Gmail profile
    Gmail-->>CLI: Email address and mailbox counts
    CLI-->>User: Authentication status
```

## Data And Trust Boundaries

```mermaid
flowchart TB
    subgraph Local["Local machine"]
        Env[".env"]
        Token["data/gmail_token.json"]
        Credentials["data/gmail_credentials.json"]
        DB["data/memory.sqlite"]
        Rules["config/rules.toml"]
        Code["Agent source code"]
    end

    subgraph External["External services"]
        Gmail["Gmail API"]
        OpenAI["OpenAI API"]
        Ollama["Ollama API"]
    end

    Code --> Env
    Code --> Token
    Code --> Credentials
    Code --> DB
    Code --> Rules
    Code --> Gmail
    Code --> OpenAI
    Code --> Ollama

    Env -. ignored .-> Git["Public Git repo"]
    Token -. ignored .-> Git
    Credentials -. ignored .-> Git
    DB -. ignored .-> Git
    Rules -. ignored .-> Git
    Code --> Git
```

## Current Safety Rules

- Default mode is dry-run. The agent mutates Gmail only when `--apply` is passed.
- The agent fetches only messages in the Gmail inbox.
- Already reviewed mail is skipped using both `ai-reviewed` and SQLite memory.
- The agent never deletes, permanently removes, replies to, forwards, or marks messages as spam.
- Archive means removing the Gmail `INBOX` label.
- Low-confidence messages are not archived.
- Agent-generated summary emails are skipped when scanning the inbox.
- Apply runs do not send a summary email when no new emails were processed.
- Local credentials, OAuth tokens, SQLite memory, logs, virtualenvs, and caches are ignored by Git.

## Summary Reports

Summary report subjects include date and time so multiple runs per day are easy to distinguish:

```text
Gmail Inbox Agent Summary - YYYY-MM-DD HH:MM:SS TZ
```

Dry runs print the summary to the console. Apply runs send the summary email only when at least one new email was processed.

## Gmail Labels

Labels are lowercase and hyphenated to make automation, search, and future integrations easier:

- `ai-reviewed`
- `ai-important`
- `ai-needs-attention`
- `ai-money`
- `ai-work`
- `ai-family`
- `ai-appointments`
- `ai-newsletters`
- `ai-receipts`
- `ai-low-priority`

The code normalizes legacy `AI ...` label names before applying Gmail actions, but new labels should always use the lowercase `ai-*` convention.

## Public Repo Change Management

When changing the agent, update this doc if the change affects:

- Workflow nodes or their order.
- Gmail scopes, labels, or mutation behavior.
- Memory schema or storage location.
- LLM prompts, classifier output schema, or model integration.
- Supported LLM providers or provider configuration.
- Classification rules or prompt tuning behavior.
- Dry-run/apply safety behavior.
- Scheduling, containers, GitHub Actions, or deployment.
- OAuth setup or authentication behavior.

## Runtime Options

The agent can run directly with `uv`, as a Docker one-shot container, or through Docker Compose.

```mermaid
flowchart TD
    Local["uv run gmail-inbox-agent"] --> Agent["Gmail Inbox Agent"]
    Docker["docker run gmail-inbox-agent"] --> Agent
    Compose["docker compose run gmail-inbox-agent"] --> Agent
    Agent --> SQLite[("SQLite data/memory.sqlite")]
    Agent --> Postgres[("Optional Postgres")]
    Agent --> Gmail["Gmail API"]
    Agent --> LLM["OpenAI or host Ollama"]
```

## Release Pipeline

```mermaid
flowchart TD
    PR["Pull request"] --> Tests["uv pytest"]
    Push["Push to main"] --> Release["semantic-release"]
    Release --> Docker{"new version?"}
    Docker -->|yes| Hub["Docker Hub: latest, semver, sha"]
```

Keep implementation plans, milestone notes, and decision history under `docs/` so the public repo shows both the product and the engineering process behind it.
