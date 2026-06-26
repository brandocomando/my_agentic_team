# Gmail Inbox Agent Architecture

This document is the living architecture reference for the Gmail Inbox Agent. Keep it updated when workflow steps, safety rules, labels, storage, infrastructure, or deployment automation change.

The original implementation spec lives in [Initial_Plan.md](./Initial_Plan.md). This file reflects the current implementation.

## System Overview

```mermaid
flowchart TD
    Cron["cron / local scheduler"] --> CLI["uv run gmail-agent"]
    CLI --> Graph["LangGraph workflow"]
    Graph --> GmailFetch["Gmail API: fetch inbox"]
    Graph --> MemoryRead["SQLite memory: reviewed IDs"]
    Graph --> Classifier["OpenAI classifier"]
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
    participant CLI as gmail-agent CLI
    participant Graph as LangGraph
    participant Gmail as Gmail API
    participant Memory as SQLite Memory
    participant LLM as OpenAI API

    User->>CLI: uv run gmail-agent --dry-run or --apply
    CLI->>Graph: Start AgentState
    Graph->>Gmail: Authenticate with OAuth
    Graph->>Gmail: Fetch in:inbox -label:"AI Reviewed"
    Gmail-->>Graph: Inbox messages
    Graph->>Memory: Check reviewed message IDs
    Memory-->>Graph: Already reviewed status
    Graph->>LLM: Classify unreviewed messages
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
    participant CLI as gmail-agent CLI
    participant Browser as Browser OAuth
    participant Gmail as Gmail API

    User->>CLI: uv run gmail-agent --auth-check
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
        Code["Agent source code"]
    end

    subgraph External["External services"]
        Gmail["Gmail API"]
        OpenAI["OpenAI API"]
    end

    Code --> Env
    Code --> Token
    Code --> Credentials
    Code --> DB
    Code --> Gmail
    Code --> OpenAI

    Env -. ignored .-> Git["Public Git repo"]
    Token -. ignored .-> Git
    Credentials -. ignored .-> Git
    DB -. ignored .-> Git
    Code --> Git
```

## Current Safety Rules

- Default mode is dry-run. The agent mutates Gmail only when `--apply` is passed.
- The agent fetches only messages in the Gmail inbox.
- Already reviewed mail is skipped using both `AI Reviewed` and SQLite memory.
- The agent never deletes, permanently removes, replies to, forwards, or marks messages as spam.
- Archive means removing the Gmail `INBOX` label.
- Low-confidence messages are not archived.
- Local credentials, OAuth tokens, SQLite memory, logs, virtualenvs, and caches are ignored by Git.

## Public Repo Change Management

When changing the agent, update this doc if the change affects:

- Workflow nodes or their order.
- Gmail scopes, labels, or mutation behavior.
- Memory schema or storage location.
- LLM prompts, classifier output schema, or model integration.
- Dry-run/apply safety behavior.
- Scheduling, containers, GitHub Actions, or deployment.
- OAuth setup or authentication behavior.

Keep implementation plans, milestone notes, and decision history under `docs/` so the public repo shows both the product and the engineering process behind it.
