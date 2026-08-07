# Scheduling

The repo includes scripts and macOS LaunchAgent plists for scheduled scans.

Important: the checked-in scripts and plists currently use this local project path:

```text
/opt/personal/my_agentic_team/campsite-finder-agent
```

If you cloned the repo somewhere else, edit the paths in:

- `scripts/hourly_scan.sh`
- `scripts/daily_lock_scan.sh`
- `launchd/com.bfoster.campsite-finder-agent.hourly.plist`
- `launchd/com.bfoster.campsite-finder-agent.daily-locks.plist`

The scripts also assume Homebrew-installed tools at:

```text
/opt/homebrew/bin/uv
/opt/homebrew/bin/task
```

On Apple Silicon Macs this is usually correct. Verify with:

```bash
which uv
which task
```

## Hourly Scan With launchd

On macOS, `launchd` is usually more reliable than cron.

Install the included hourly LaunchAgent:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.bfoster.campsite-finder-agent.hourly.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.hourly.plist
launchctl kickstart -k gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
```

Check it with:

```bash
launchctl print gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
tail -n 80 data/logs/hourly-scan.log
tail -n 80 data/logs/launchd.err.log
```

Unload it with:

```bash
launchctl bootout gui/$(id -u)/com.bfoster.campsite-finder-agent.hourly
```

The hourly job writes logs to:

```text
data/logs/hourly-scan.log
data/logs/launchd.out.log
data/logs/launchd.err.log
```

## Daily ReserveCalifornia Lock Scan

To run the ReserveCalifornia lock scan once per day at 7:00 AM local Mac time, install the daily LaunchAgent:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/com.bfoster.campsite-finder-agent.daily-locks.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.daily-locks.plist
```

The daily lock script starts `task chrome` only when Chrome CDP is not already responding, then runs:

```bash
task locks:reservecalifornia
```

Check it with:

```bash
launchctl print gui/$(id -u)/com.bfoster.campsite-finder-agent.daily-locks
tail -n 80 data/logs/daily-lock-scan.log
tail -n 80 data/logs/daily-lock-launchd.err.log
```

Unload it with:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.bfoster.campsite-finder-agent.daily-locks.plist
```

## Cron Alternative

For a system-scheduled hourly run, use cron with the included one-shot script:

```bash
crontab -e
```

Add a line like this, replacing the path if your repo lives somewhere else:

```cron
0 * * * * /opt/personal/my_agentic_team/campsite-finder-agent/scripts/hourly_scan.sh
```

The cron job writes logs to `data/logs/hourly-scan.log`.
