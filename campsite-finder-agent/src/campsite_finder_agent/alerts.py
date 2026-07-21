from __future__ import annotations

from rich.console import Console
from rich.table import Table

from campsite_finder_agent.models import Match, MatchWindow, SearchConfig


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
