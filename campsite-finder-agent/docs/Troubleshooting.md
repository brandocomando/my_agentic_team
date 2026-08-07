# Troubleshooting

## `task: command not found`

Install Task:

```bash
brew install go-task/tap/go-task
```

Then open a new Terminal window and verify:

```bash
task --version
```

## `uv: command not found`

Install `uv`:

```bash
brew install uv
```

Then open a new Terminal window and verify:

```bash
uv --version
```

## Chrome Does Not Start

`task chrome` expects Google Chrome here:

```text
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```

Install Chrome:

```bash
brew install --cask google-chrome
```

## Cannot Connect To `http://localhost:9222`

Start the dedicated Chrome session:

```bash
task chrome
```

Then check:

```bash
curl -fsS http://localhost:9222/json/version
```

If that fails, another process may be using port `9222`, or the dedicated Chrome window may not be running.

## Playwright Is Missing

Install browser dependencies:

```bash
task sync
```

If you are running commands directly, include the browser extra:

```bash
uv run --extra browser python app.py --once
```

## Recreation.gov Or ReserveCalifornia Login Times Out

Make sure you logged in inside the Chrome window opened by:

```bash
task chrome
```

A normal Chrome window does not share that dedicated profile.

## Ollama Is Unavailable

Run scans without AI:

```bash
task scan -- --no-ai
```

Or start Ollama:

```bash
ollama serve
```

In another Terminal window:

```bash
ollama pull llama3.1
```

## Gmail OAuth Fails

Check:

- `CAMPSITE_EMAIL_ALERTS_ENABLED=true` is set in `.env`.
- `CAMPSITE_EMAIL_TO` is set.
- `data/gmail_credentials.json` exists.
- Your OAuth client allows the Gmail send scope.

If a copied token cannot refresh, delete:

```text
data/gmail_token.json
```

Then run a scan once to complete a fresh OAuth flow.

## Scheduled Jobs Do Not Run

Check whether your repo path matches the paths inside:

- `scripts/hourly_scan.sh`
- `scripts/daily_lock_scan.sh`
- `launchd/com.bfoster.campsite-finder-agent.hourly.plist`
- `launchd/com.bfoster.campsite-finder-agent.daily-locks.plist`

Also verify tool paths:

```bash
which uv
which task
```

Inspect logs:

```bash
tail -n 80 data/logs/hourly-scan.log
tail -n 80 data/logs/launchd.err.log
tail -n 80 data/logs/daily-lock-scan.log
tail -n 80 data/logs/daily-lock-launchd.err.log
```

## `launchctl bootstrap` Says The Service Already Exists

Unload the job, then bootstrap it again:

```bash
launchctl bootout gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.hourly.plist
```

For the daily lock job:

```bash
launchctl bootout gui/$(id -u)/com.bfoster.campsite-finder-agent.daily-locks
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.daily-locks.plist
```
