# Gmail Inbox Agent — Python + LangGraph Implementation Spec

## Goal

Build a local Python agent that reviews only the user’s Gmail Inbox, classifies unreviewed emails, applies labels, archives low-value emails, and sends a summary report.

This is a local scheduled agent, not a web app.

The agent should run from the user’s machine via cron.

---

## Core Workflow

Scheduled run:

```text
cron
  ↓
python gmail_agent
  ↓
fetch Gmail inbox messages
  ↓
skip messages already reviewed by this agent
  ↓
classify each message with LLM
  ↓
apply labels
  ↓
archive low-value messages
  ↓
record reviewed message IDs
  ↓
email user a summary report
```

---

## Stack

Use:

* Python 3.11+
* `uv` for project/dependency management
* LangGraph for orchestration
* OpenAI API for LLM classification
* Gmail API for email access
* SQLite for local memory
* Pydantic for structured outputs
* Rich for CLI output
* pytest for tests

---

## Project Structure

```text
gmail-inbox-agent/
  README.md
  AGENTS.md
  pyproject.toml
  .env.example

  src/
    gmail_inbox_agent/
      __init__.py
      main.py
      config.py
      models.py
      graph.py

      gmail/
        __init__.py
        auth.py
        client.py
        actions.py

      memory/
        __init__.py
        db.py
        reviewed_messages.py

      llm/
        __init__.py
        classifier.py
        prompts.py

      reports/
        __init__.py
        summary.py

  data/
    gmail_token.json
    memory.sqlite

  tests/
    test_classifier.py
    test_memory.py
```

---

## Environment Variables

Create `.env.example`:

```text
OPENAI_API_KEY=

GMAIL_CREDENTIALS_PATH=./data/gmail_credentials.json
GMAIL_TOKEN_PATH=./data/gmail_token.json

MEMORY_DB_PATH=./data/memory.sqlite

USER_EMAIL=your_email@gmail.com

DRY_RUN=true
MAX_MESSAGES_PER_RUN=25
```

---

## Gmail API Setup

Use OAuth, not password auth.

Required Gmail scopes:

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
```

The app needs `gmail.modify` to:

* read inbox messages
* apply labels
* archive messages

The app needs `gmail.send` to email the summary report.

Do not request broader Gmail scopes unless necessary.

---

## Agent Labels

Create or use these Gmail labels:

```text
ai-reviewed
ai-important
ai-needs-attention
ai-money
ai-work
ai-family
ai-appointments
ai-newsletters
ai-receipts
ai-low-priority
```

Every processed message should receive:

```text
ai-reviewed
```

This is the main memory marker inside Gmail.

Also store reviewed Gmail message IDs in SQLite.

---

## Memory Strategy

Use two layers of memory:

### Gmail Label Memory

If message has label:

```text
ai-reviewed
```

skip it.

### SQLite Memory

Store reviewed message IDs locally.

Table:

```sql
create table if not exists reviewed_messages (
  gmail_message_id text primary key,
  thread_id text,
  subject text,
  from_email text,
  reviewed_at text,
  decision text,
  applied_labels text,
  archived boolean
);
```

This prevents duplicate work even if labels are changed later.

---

## Data Models

Use Pydantic.

```python
from typing import Literal
from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    gmail_message_id: str
    thread_id: str
    subject: str
    from_email: str
    to_email: str | None = None
    date: str | None = None
    snippet: str
    body_text: str | None = None
    existing_labels: list[str] = Field(default_factory=list)


class EmailClassification(BaseModel):
    importance: Literal["important", "normal", "low"]
    category: Literal[
        "work",
        "family",
        "money",
        "appointment",
        "receipt",
        "newsletter",
        "account",
        "spam_or_promo",
        "other",
    ]
    should_archive: bool
    should_highlight: bool
    labels_to_apply: list[str]
    summary: str
    reason: str
    confidence: float = Field(ge=0, le=1)


class ProcessedEmail(BaseModel):
    message: EmailMessage
    classification: EmailClassification
    actions_taken: list[str]
```

---

## LLM Classification Rules

The classifier should decide:

1. What category is this?
2. Is it important?
3. Should it be archived?
4. Should it be highlighted in the summary?
5. What labels should be applied?

Important examples:

* Bills
* Banking
* Taxes
* Job opportunities
* Interview requests
* School/family logistics
* Appointments
* Time-sensitive requests
* Anything requiring action

Archive examples:

* Promotions
* Newsletters
* Receipts with no action needed
* Marketing emails
* Low-value automated notifications

Never archive if unsure.

---

## Prompt Requirements

The LLM must return strict JSON matching `EmailClassification`.

System prompt:

```text
You are an email triage assistant for a busy parent and senior software engineer.

Your job is to classify Gmail inbox messages and recommend safe actions.

Rules:
- Be conservative.
- Never archive an email if it may require action.
- Highlight anything involving money, family, appointments, job opportunities, account security, or deadlines.
- Newsletters and promotions can usually be archived.
- Receipts can be archived unless they indicate a problem, refund, failed payment, or action needed.
- Apply useful labels.
- Return JSON only.
```

---

## LangGraph Design

Build a graph with these nodes:

```text
load_config
  ↓
authenticate_gmail
  ↓
fetch_inbox_messages
  ↓
filter_unreviewed_messages
  ↓
classify_messages
  ↓
apply_gmail_actions
  ↓
record_memory
  ↓
send_summary
```

State object:

```python
class AgentState(BaseModel):
    dry_run: bool
    messages: list[EmailMessage] = []
    unreviewed_messages: list[EmailMessage] = []
    processed: list[ProcessedEmail] = []
    errors: list[str] = []
```

---

## Gmail Fetching Requirements

Fetch only messages with:

```text
label:INBOX
```

Do not process archived messages.

Recommended Gmail query:

```text
in:inbox -label:"ai-reviewed"
```

Limit by:

```text
MAX_MESSAGES_PER_RUN
```

Default: 25.

---

## Gmail Actions

For each processed message:

Always apply:

```text
ai-reviewed
```

Apply category labels based on classification.

If `should_archive=true`, remove the `INBOX` label.

Important:

* In dry-run mode, do not modify Gmail.
* In dry-run mode, only report intended actions.

---

## Summary Email

Send an email to `USER_EMAIL`.

Subject:

```text
Gmail Agent Summary — YYYY-MM-DD
```

Body format:

```md
# Gmail Agent Summary

Processed: 18
Archived: 9
Highlighted: 4
Dry Run: true

## Needs Attention

### Interview request from ExampleCo
From: recruiter@example.com
Category: work
Reason: Time-sensitive job opportunity
Suggested action: Review and respond

## Archived / Low Priority

- Promo from Store
- Newsletter from Example
- Receipt from Amazon

## Labels Applied

- ai-work: 2
- ai-money: 1
- ai-newsletters: 6

## Errors

None
```

---

## CLI Commands

Use argparse or Typer.

Required:

```bash
uv run gmail-agent
uv run gmail-agent --dry-run
uv run gmail-agent --apply
uv run gmail-agent --max-messages 10
```

Default should be dry-run unless `--apply` is passed.

---

## Safety Requirements

The agent must:

* Default to dry-run
* Never delete emails
* Never mark as spam
* Never permanently remove messages
* Never reply to emails
* Never forward emails
* Never process archived emails
* Never archive low-confidence messages
* Log all actions
* Email a summary every run

Archive means only:

```text
remove INBOX label
```

not delete.

---

## Testing Plan

Tests should cover:

* SQLite memory works
* Already-reviewed messages are skipped
* Classifier output validates against Pydantic model
* Dry-run mode does not call Gmail mutation methods
* Archive action only removes INBOX label
* Summary report includes highlighted emails

---

## Milestone 1 — Local Skeleton

Build:

* Project structure
* Config loading
* CLI
* SQLite memory setup

Acceptance:

```bash
uv run gmail-agent --dry-run
```

runs without Gmail integration.

---

## Milestone 2 — Gmail Read-Only

Build:

* Gmail OAuth flow
* Fetch inbox messages
* Parse subject/from/snippet/body
* Print messages locally

Acceptance:

* Agent can list recent inbox emails.
* No Gmail changes happen.

---

## Milestone 3 — LLM Classification

Build:

* OpenAI classification call
* Pydantic validation
* Dry-run summary

Acceptance:

* Agent classifies inbox emails.
* No Gmail changes happen.

---

## Milestone 4 — Gmail Labels

Build:

* Create missing labels
* Apply `ai-reviewed`
* Apply category labels

Acceptance:

* With `--apply`, processed messages get labels.

---

## Milestone 5 — Archive Low Priority

Build:

* Remove `INBOX` label for safe low-priority messages
* Only archive when confidence is high

Acceptance:

* Newsletters/promos can be archived.
* Important emails remain in inbox.

---

## Milestone 6 — Summary Email

Build:

* Generate markdown/plaintext summary
* Send summary email to user

Acceptance:

* Every run sends a report.

---

## Milestone 7 — Cron Setup

Document cron setup.

Example:

```bash
0 8 * * * cd /path/to/gmail-inbox-agent && uv run gmail-agent --apply
```

Recommended initial schedule:

```text
Week 1: manual dry-run only
Week 2: daily dry-run via cron
Week 3: apply labels only
Week 4: enable archiving
```

---

## Implementation Notes

Start conservative.

The agent should be useful before it is aggressive.

Recommended first behavior:

1. Dry-run classification
2. Apply labels only
3. Archive only newsletters/promos
4. Expand archiving rules later

---

## Final Acceptance Criteria

The project is complete when:

1. It runs locally with `uv run gmail-agent`.
2. It authenticates with Gmail.
3. It only reads Inbox messages.
4. It skips previously reviewed emails.
5. It classifies emails with structured output.
6. It applies labels safely.
7. It archives only low-risk emails.
8. It records memory in SQLite.
9. It sends a summary email.
10. It can be scheduled with cron.
