from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from campsite_finder_agent.gmail import send_gmail_email
from campsite_finder_agent.models import Match, MatchWindow, SearchConfig


@dataclass(frozen=True)
class EmailAlertSettings:
    enabled: bool
    gmail_credentials_path: Path
    gmail_token_path: Path
    recipient: str
    min_score: float
    actions: set[str]
    state_path: Path


def alert_matches(search: SearchConfig, matches: list[Match]) -> None:
    if not matches:
        return
    methods = {method.lower() for method in search.alert.methods}
    if "terminal" in methods:
        Console().print(f"[green]{len(matches)} open campsite match(es)[/green] for {search.name}.")
    if "bell" in methods:
        print("\a", end="")


def print_matches(matches: list[Match]) -> None:
    console = Console()
    table = Table(title="Open Campsites")
    table.add_column("Search")
    table.add_column("Site")
    table.add_column("Loop")
    table.add_column("Check-in")
    table.add_column("Check-out")
    table.add_column("Type")
    for match in matches:
        table.add_row(
            match.search_name,
            f"{match.campsite_name} ({match.campsite_id})",
            match.loop,
            match.check_in.isoformat(),
            match.check_out.isoformat(),
            match.site_type,
        )
    console.print(table)


def alert_match_windows(matches: list[MatchWindow]) -> None:
    if not matches:
        return
    Console().print(f"[green]{len(matches)} campground availability window(s)[/green] found.")
    print("\a", end="")


def notify_ai_match_windows(matches: list[MatchWindow], settings: EmailAlertSettings) -> int:
    if not settings.enabled:
        return 0
    missing = missing_email_settings(settings)
    if missing:
        Console().print(f"[yellow]Skipping email alert; missing {', '.join(missing)}.[/yellow]")
        return 0

    candidates = [match for match in matches if is_ai_notification_candidate(match, settings)]
    if not candidates:
        return 0

    notification_state = load_notification_state(settings.state_path)
    sent_keys = set(notification_state.get("sent_ai_match_keys", {}))
    new_matches = [match for match in candidates if match.state_key not in sent_keys]
    if not new_matches:
        return 0

    try:
        send_ai_match_email(new_matches, settings)
    except Exception as exc:
        Console().print(f"[yellow]Skipping email alert after error:[/yellow] {exc}")
        return 0
    sent_at = datetime.now(timezone.utc).isoformat()
    sent = notification_state.setdefault("sent_ai_match_keys", {})
    for match in new_matches:
        sent[match.state_key] = sent_at
    write_notification_state(settings.state_path, notification_state)
    Console().print(f"[green]Sent email alert for {len(new_matches)} AI match(es).[/green]")
    return len(new_matches)


def is_ai_notification_candidate(match: MatchWindow, settings: EmailAlertSettings) -> bool:
    action = match.suggested_state_action.strip().lower()
    if action and action in settings.actions:
        return True
    return match.ai_score is not None and match.ai_score >= settings.min_score


def missing_email_settings(settings: EmailAlertSettings) -> list[str]:
    missing: list[str] = []
    if not settings.gmail_credentials_path:
        missing.append("GMAIL_CREDENTIALS_PATH")
    if not settings.gmail_token_path:
        missing.append("GMAIL_TOKEN_PATH")
    if not settings.recipient:
        missing.append("CAMPSITE_EMAIL_TO")
    return missing


def send_ai_match_email(matches: list[MatchWindow], settings: EmailAlertSettings) -> None:
    top_match = max(matches, key=lambda match: match.ai_score or 0)
    send_gmail_email(
        settings.gmail_credentials_path,
        settings.gmail_token_path,
        settings.recipient,
        email_subject(matches, top_match),
        render_email_body(matches),
    )


def email_subject(matches: list[MatchWindow], top_match: MatchWindow) -> str:
    score = "n/a" if top_match.ai_score is None else f"{top_match.ai_score:g}/10"
    if len(matches) == 1:
        return f"Campsite match: {top_match.campground_name} ({score})"
    return f"{len(matches)} campsite matches found; best is {top_match.campground_name} ({score})"


def render_email_body(matches: list[MatchWindow]) -> str:
    lines = ["AI campsite matches", ""]
    for match in sorted(matches, key=lambda item: (-(item.ai_score or 0), item.campground_name)):
        score = "n/a" if match.ai_score is None else f"{match.ai_score:g}/10"
        lines.extend(
            [
                f"{match.campground_name} - {score} {match.ai_fit}".rstrip(),
                f"Dates: {match.check_in_window_start.isoformat()} to {match.latest_check_out.isoformat()} ({match.nights} nights)",
                f"Searches: {', '.join(match.search_names)}",
                f"URL: {match.campground_url}",
            ]
        )
        if match.ai_summary:
            lines.append(f"Summary: {match.ai_summary}")
        if match.ai_reasons:
            lines.append(f"Reasons: {', '.join(match.ai_reasons)}")
        if match.ai_concerns:
            lines.append(f"Concerns: {', '.join(match.ai_concerns)}")
        if match.suggested_state_action:
            lines.append(f"Suggested state: {match.suggested_state_action} - {match.suggested_state_reason}")
        lines.append(f"State key: {match.state_key}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def load_notification_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"sent_ai_match_keys": {}}
    with path.open() as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {"sent_ai_match_keys": {}}
    sent = payload.get("sent_ai_match_keys")
    if not isinstance(sent, dict):
        payload["sent_ai_match_keys"] = {}
    return payload


def write_notification_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
