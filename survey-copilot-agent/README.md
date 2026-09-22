# Survey Copilot Agent

A local-first survey copilot with two parts:

- A Chrome extension that reads visible survey questions, asks a local backend for an answer, fills the answer, and clicks the next/continue control only when it answered something.
- A local FastAPI backend that retrieves facts from a SQLite vector store built from your private local profile and Ollama embeddings.

The first target sites are `https://app.paidviewpoint.com/dashboard` and `https://app.usertesting.com/my_dashboard/*`. The extension is domain-scoped to those survey apps and is user-triggered by a floating button.

## Safety Model

- Private facts live in `config/profile.local.json`, which is ignored by Git.
- Runtime memory lives in `data/memory.sqlite`, which is ignored by Git.
- The backend returns `{"answer": null}` when no matching fact is found or confidence is below `ANSWER_MIN_CONFIDENCE`.
- If retrieval is confident but deterministic choice matching fails, the backend asks local Ollama to choose from the visible options using only the retrieved fact.
- LLM fallback choices are rejected when the chosen label is not supported by the retrieved fact.
- Exact repeat questions are cached in memory while the backend process is running.
- `Learn Visible` lets you manually answer a visible question once and save that answer into local memory for future runs.
- Facts loaded from `config/profile.local.json` are preferred over learned facts when relevance is tied.
- The extension does not fill or click when the backend returns `null`.
- On a normal survey page, the extension answers one visible question, clicks next/continue, waits for the next question, and repeats until it cannot safely answer.
- On UserTesting, `Run Survey Copilot` also works across the available-tests dashboard: it opens live qualifiers, answers what it can, leaves unanswered questions untouched, and continues to the next visible qualifier/question.
- The extension also has a `Check All` button for survey dashboards. It clicks visible qualification `Continue` controls only when nearby card text looks like a survey/qualification prompt.

## Prerequisites

- Python 3.11+
- `uv`
- Chrome
- Ollama running locally
- Ollama models:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## Setup

```bash
cd survey-copilot-agent
cp .env.example .env
cp config/profile.example.json config/profile.local.json
uv sync --extra dev
```

With Task:

```bash
task sync
```

Edit `config/profile.local.json` with your real facts. Keep facts short and explicit:

```json
{
  "facts": [
    {
      "key": "age",
      "value": "42",
      "text": "The user is 42 years old."
    }
  ]
}
```

You do not need to store both exact values and derived values. For example, if `age` is `36`, the backend can select a `35-44` radio option from that exact age.

## Run Backend

```bash
uv run survey-copilot-agent
```

With Task:

```bash
task run
```

In another terminal, load local profile facts into the vector store:

```bash
curl -X POST http://127.0.0.1:8765/profile/load
```

With Task:

```bash
task profile:load
```

Quick check:

```bash
curl -X POST http://127.0.0.1:8765/answer \
  -H 'Content-Type: application/json' \
  -d '{"question_text":"What is your exact age?","input_type":"text","choices":[]}'
```

With Task:

```bash
task answer:age
task answer:age-range
```

Teach one sample answer:

```bash
task learn:sample
```

List learned answers:

```bash
task learned:list
```

Delete one learned answer by key:

```bash
task learned:delete KEY=learned_provider_abc123
```

## Performance Notes

The fast path is deterministic retrieval and matching. The slower path is Ollama chat fallback for ambiguous choice questions. The backend keeps an in-process answer cache, so repeated identical questions with the same top fact are faster until the backend restarts.

## Install Extension

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `survey-copilot-agent/extension`.
5. Open `https://app.paidviewpoint.com/dashboard` or `https://app.usertesting.com/my_dashboard/`.
6. Press `Check All` on a dashboard with many qualification cards to open available screeners.
7. Press `Run Survey Copilot` to answer the active screener. On UserTesting, it will continue through available qualifiers and skip questions that need manual input.
8. If a question needs input, answer it manually and press `Learn Visible` before continuing. The learned answer is stored in `data/memory.sqlite`.

## Architecture

See [docs/Architecture.md](docs/Architecture.md).
