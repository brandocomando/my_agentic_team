# Optional Services

The agent runs without these services, but they add AI ranking, email alerts, and external campground discovery.

## Ollama AI Scoring

When visible matches are found, the scan tries to score and summarize them with Ollama.

Install Ollama on macOS:

```bash
brew install ollama
ollama serve
```

In another Terminal window, pull the model:

```bash
ollama pull llama3.1
```

Configure `.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

AI analysis adds `ai_score`, `ai_fit`, reasons, concerns, and suggested state actions to the JSON and CSV outputs, plus `data/matches.ai.md`.

If Ollama is unavailable, the scan logs a warning and still writes normal match outputs.

Disable AI for a run with:

```bash
task scan -- --no-ai
```

## Gmail Alerts

AI-scored matches can send Gmail alerts. The agent uses Google OAuth credentials, not an SMTP password.

Configure `.env`:

```env
CAMPSITE_EMAIL_ALERTS_ENABLED=true
GMAIL_CREDENTIALS_PATH=./data/gmail_credentials.json
GMAIL_TOKEN_PATH=./data/gmail_token.json
CAMPSITE_EMAIL_TO=your_email@gmail.com
CAMPSITE_AI_NOTIFY_MIN_SCORE=8.0
CAMPSITE_AI_NOTIFY_ACTIONS=book
CAMPSITE_NOTIFICATION_STATE_PATH=./data/notifications.json
```

Create a Google Cloud OAuth client that can use the Gmail send scope, then save the downloaded OAuth client JSON as:

```text
data/gmail_credentials.json
```

On the first scan that needs to send an email, the app opens a browser consent flow and writes:

```text
data/gmail_token.json
```

An email is sent when a scored match meets the minimum score or has a suggested action in `CAMPSITE_AI_NOTIFY_ACTIONS`. Sent `state_key`s are recorded so hourly scans do not send the same alert repeatedly.

If Gmail auth fails, the scan logs a warning and still writes match outputs. If a copied token cannot refresh, delete `data/gmail_token.json` and run a scan once to complete a fresh OAuth flow.

## Outdoorithm

Outdoorithm can be used as an optional provider and for campground discovery when you have an API key.

Configure `.env`:

```env
OUTDOORITHM_API_KEY=your_api_key
```

Discover campground IDs for a state:

```bash
task discover -- CA
```

Outdoorithm requires attribution wherever its data is shown, and commercial use requires a license.
