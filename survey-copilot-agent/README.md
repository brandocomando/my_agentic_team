# Survey Copilot Agent

A local-first Chrome extension that detects visible survey questions, suggests answers from local memory, and fills a field only after you confirm that specific answer.

This is a copilot, not an autonomous survey bot.

The extension works without an LLM. Optional phase-two LLM suggestions are provided by a local helper process so API keys stay out of Chrome.

## Documentation

- [Architecture](docs/Architecture.md)
- [Safety model](docs/Safety.md)
- [Contributing guide](CONTRIBUTING.md)

## What It Does

- Detects visible form questions on the active page.
- Extracts visible radio, checkbox, select, text, number, and textarea controls.
- Reads and fills only pages whose domains are in the Settings allowlist.
- Looks up previous confirmed answers and reusable profile facts from local Chrome storage.
- Optionally asks a local LLM helper for suggestions using Ollama or OpenAI.
- Shows suggested answers in a side panel.
- Requires a per-question `Fill` click before writing to the page.
- Stores confirmed answers with optional expiry.

## What It Does Not Do

- It does not answer hidden fields.

## Install For Local Testing

1. Open `chrome://extensions`.
2. Turn on Developer Mode.
3. Click Load unpacked.
4. Select:

```text
survey-copilot-agent/extension
```

Open a page with visible form questions, click the extension icon, then use the side panel to review questions and fill answers one at a time.

Each detected question has a local `Refresh` button beside `Fill`. After you approve and fill the visible answers, use the `Next Page` button at the bottom of the Questions tab to click a visible Next, Continue, Submit, Done, or Finish control on the page. Use `Refresh` after the survey advances so the panel can load the next visible question.

For a safe local test page, open:

```text
survey-copilot-agent/examples/sample-survey.html
```

The default allowed domains are:

```text
file:
localhost
127.0.0.1
```

Add real survey domains in the Settings tab before using the extension on them. Exact hosts such as `app.example.com` and wildcard hosts such as `*.example.com` are supported.

If Refresh says `No visible questions found`, the status line includes diagnostics:

- `native controls` are normal `input`, `select`, or `textarea` fields
- `custom choices` are visible ARIA widgets such as `role="radio"` or `role="option"`
- `iframes` means the survey may be rendered in an embedded frame
- `shadow roots` means the survey may be rendered inside web components

## Memory

Memory is stored in `chrome.storage.local` inside your browser profile.

The extension stores two kinds of memory:

- confirmed answers for specific questions
- reusable profile facts with simple question keyword matching

Confirmed answers are keyed by both the question text and the visible answer options. This prevents a saved answer for a repeated prompt like "Which of these is part of your job?" from being reused when the option set changes.

Each saved answer can expire after 7, 30, or 90 days, or never expire. Use shorter expiry for recent behavior such as shopping, travel, or product usage.

Use the Memory tab's Export Memory button to download the current confirmed answers and profile facts as a local JSON file. The export does not include helper settings or provider secrets.

## Optional LLM Helper

The extension uses saved memory by default. To enable LLM suggestions, run the local helper and turn on LLM suggestions in the extension Settings tab.

1. Copy local config:

```bash
cp .env.example .env
```

2. Configure `.env`.

For Ollama:

```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

For OpenAI:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

3. Start the helper:

```bash
npm run llm:serve
```

Or with Task:

```bash
task llm:ollama
task llm:openai
```

4. In the extension side panel, open Settings, enable LLM suggestions, and keep the helper URL as:

```text
http://127.0.0.1:8765
```

The deterministic matcher still runs first. Exact saved answers and profile facts win over LLM suggestions. The helper also rejects LLM answers that do not match non-expired confirmed answers or profile facts, even when the model picked a visible option.

When LLM suggestions are enabled, the helper receives visible questions/options plus non-expired confirmed answers and profile facts from local memory. The prompt labels confirmed answers separately from reusable profile facts so the model can explain which memory source supports a suggestion.

When using OpenAI, visible questions/options, confirmed answers, and profile facts are sent to the OpenAI API through the local helper. When using Ollama, the request stays on your machine as long as Ollama is local.

## Validation

```bash
npm test
```

Or with Task:

```bash
task test
```

## Public Repo Safety

Do not commit exported profile memory, logs, packaged extension keys, or local data. The agent `.gitignore` keeps local data, logs, packaged `.crx` files, and extension signing keys out of Git.
