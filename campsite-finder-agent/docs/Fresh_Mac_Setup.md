# Fresh Mac Setup

Use this guide when starting from a new Mac with little or no Python or Playwright experience.

## 1. Install Mac Developer Tools

Open Terminal and run:

```bash
xcode-select --install
```

If macOS says the tools are already installed, continue.

## 2. Install Homebrew

Homebrew installs command-line tools on macOS.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After install, Homebrew may print one or two commands that add `brew` to your shell path. Run those commands if it tells you to.

Verify:

```bash
brew --version
```

## 3. Install Required Tools

```bash
brew install git uv go-task/tap/go-task
brew install --cask google-chrome
```

Verify:

```bash
git --version
uv --version
task --version
test -d "/Applications/Google Chrome.app" && echo "Chrome installed"
```

## 4. Clone The Repo

Choose a folder for local code:

```bash
mkdir -p ~/Code
cd ~/Code
git clone https://github.com/brandocomando/my_agentic_team.git
cd my_agentic_team/campsite-finder-agent
```

## 5. Create Local Config Files

```bash
cp .env.example .env
cp config/searches.example.yaml config/searches.yaml
```

These files are ignored by git and safe to customize locally.

## 6. Install Python Dependencies

```bash
task sync
```

This uses `uv` to install the Python dependencies, including the optional browser dependency used by Playwright.

## 7. Run Tests

```bash
task test
```

The tests do not require you to be logged in to campsite providers.

## 8. Start The Browser Session

```bash
task chrome
```

This opens a dedicated Google Chrome profile with remote debugging enabled on `http://localhost:9222`.

Important details:

- Keep this Chrome window open while scans or booking-assist tasks run.
- Log in to Recreation.gov or ReserveCalifornia inside this Chrome window when needed.
- A normal Chrome window is not the same thing as this dedicated debugging window.
- If another app is already using port `9222`, the browser-backed tasks may fail.

## 9. Run A Safe First Scan

```bash
task scan -- --no-ai
```

Use `--no-ai` for the first run so Ollama is not required.

When visible matches are found, the scan writes:

- `data/matches.json`
- `data/matches.csv`

When no visible matches are found, old latest match files may be removed so stale results are not mistaken for current results.

## Next Steps

- Edit searches in [Configuration](Configuration.md).
- Learn the task list in [Commands](Commands.md).
- Configure AI, Gmail, or Outdoorithm in [Optional Services](Optional_Services.md).
- Install scheduled jobs with [Scheduling](Scheduling.md).
