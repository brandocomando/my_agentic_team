from __future__ import annotations

import argparse

from rich.console import Console

from gmail_inbox_agent.config import load_settings
from gmail_inbox_agent.graph import run_agent

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Gmail inbox triage agent.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview actions without modifying Gmail.")
    mode.add_argument("--apply", action="store_true", help="Apply Gmail labels/archive actions and send summary.")
    parser.add_argument("--max-messages", type=int, default=None, help="Maximum inbox messages to review.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
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
