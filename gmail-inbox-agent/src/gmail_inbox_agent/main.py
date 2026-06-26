from __future__ import annotations

import argparse

from rich.console import Console

from gmail_inbox_agent.config import load_settings
from gmail_inbox_agent.gmail.auth import SCOPES, build_gmail_service
from gmail_inbox_agent.gmail.client import GmailClient
from gmail_inbox_agent.graph import run_agent

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Gmail inbox triage agent.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview actions without modifying Gmail.")
    mode.add_argument("--apply", action="store_true", help="Apply Gmail labels/archive actions and send summary.")
    mode.add_argument("--auth-check", action="store_true", help="Authenticate Gmail and print account profile.")
    parser.add_argument("--max-messages", type=int, default=None, help="Maximum inbox messages to review.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    if args.auth_check:
        run_auth_check(settings)
        return

    dry_run, max_messages = resolve_run_options(args, settings.max_messages_per_run)
    state = run_agent(dry_run=dry_run, max_messages=max_messages)
    console.print(
        f"[bold]Done.[/bold] Processed {len(state.processed)} message(s), "
        f"errors: {len(state.errors)}, dry_run: {str(state.dry_run).lower()}."
    )


def resolve_run_options(args: argparse.Namespace, default_max_messages: int) -> tuple[bool, int]:
    dry_run = not args.apply
    max_messages = args.max_messages or default_max_messages
    return dry_run, max_messages


def run_auth_check(settings) -> None:
    console.print("[bold]Checking Gmail OAuth access...[/bold]")
    service = build_gmail_service(settings.gmail_credentials_path, settings.gmail_token_path)
    profile = GmailClient(service).get_profile()
    console.print("[green]Gmail authentication succeeded.[/green]")
    console.print(f"Email: {profile.get('emailAddress', '(unknown)')}")
    console.print(f"Messages total: {profile.get('messagesTotal', '(unknown)')}")
    console.print("Scopes:")
    for scope in SCOPES:
        console.print(f"- {scope}")
