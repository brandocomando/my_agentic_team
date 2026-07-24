from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console

from campsite_finder_agent.ai import analyze_match_windows_with_ollama, write_ai_summary
from campsite_finder_agent.alerts import alert_match_windows
from campsite_finder_agent.availability import find_matches
from campsite_finder_agent.cache import load_cached_campground_campsites, save_cached_campground_campsites
from campsite_finder_agent.config import load_config, load_settings
from campsite_finder_agent.models import AppConfig, DateWindow, Match, MatchWindow, SearchConfig
from campsite_finder_agent.outdoorithm import discover_campground_catalog_for_state, discover_searches_for_search_set
from campsite_finder_agent.providers import fetch_campsites_for_search
from campsite_finder_agent.reserve_california import capture_reserve_california_network
from campsite_finder_agent.results import aggregate_match_windows
from campsite_finder_agent.state import filter_stateful_match_windows, load_state


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Find open Recreation.gov campsites.")
    parser.add_argument("--config", type=Path, default=settings.config_path)
    parser.add_argument("--output", type=Path, default=settings.output_path)
    parser.add_argument("--csv-output", type=Path, default=settings.csv_output_path)
    parser.add_argument("--cache-path", type=Path, default=settings.cache_path)
    parser.add_argument("--raw-data-path", type=Path, default=settings.raw_data_path)
    parser.add_argument("--state-path", type=Path, default=settings.state_path)
    parser.add_argument("--discover-state", help="Discover Outdoorithm campground IDs for a state and write data/<STATE>.json.")
    parser.add_argument("--no-ai", action="store_true", help="Skip Ollama scoring, summary, and suggested state actions.")
    parser.add_argument("--ollama-base-url", default=settings.ollama_base_url)
    parser.add_argument("--ollama-model", default=settings.ollama_model)
    parser.add_argument("--save-data", action="store_true", help="Save fetched campsite availability for offline reruns.")
    parser.add_argument("--use-saved-data", action="store_true", help="Use saved campsite availability instead of crawling.")
    parser.add_argument("--save-raw-data", action="store_true", help="Save raw provider JSON responses for debugging.")
    parser.add_argument("--cdp-url", default=settings.cdp_url)
    parser.add_argument("--login-timeout-ms", type=int, default=settings.login_timeout_ms)
    parser.add_argument("--request-delay-seconds", type=float, default=settings.request_delay_seconds)
    parser.add_argument("--search-delay-seconds", type=float, default=settings.search_delay_seconds)
    parser.add_argument("--max-retries", type=int, default=settings.max_retries)
    parser.add_argument("--once", action="store_true", help="Run one scan and exit.")
    parser.add_argument("--watch", action="store_true", help="Keep scanning until interrupted.")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument(
        "--debug-reservecalifornia-network",
        action="store_true",
        help="Reload the open ReserveCalifornia tab and print captured JSON/API responses.",
    )
    args = parser.parse_args()

    if args.debug_reservecalifornia_network:
        print(json.dumps(capture_reserve_california_network(args.cdp_url), indent=2))
        return
    if args.discover_state:
        output_path = discover_state_catalog(args.discover_state)
        Console().print(f"Wrote campground catalog to {output_path}.")
        return

    run_forever = args.watch and not args.once
    while True:
        raw_matches = run_scan(
            args.config,
            args.cdp_url,
            args.login_timeout_ms,
            args.request_delay_seconds,
            args.search_delay_seconds,
            args.max_retries,
            args.cache_path,
            args.save_data,
            args.use_saved_data,
            args.raw_data_path,
            args.save_raw_data,
        )
        matches = aggregate_match_windows(raw_matches)
        state = load_state(args.state_path)
        visible_matches = filter_stateful_match_windows(matches, state)
        ai_summary = ""
        if visible_matches and not args.no_ai:
            try:
                ai_summary = analyze_match_windows_with_ollama(
                    visible_matches,
                    preferences_by_search(load_config(args.config)),
                    model=args.ollama_model,
                    base_url=args.ollama_base_url,
                )
                Console().print(ai_summary)
            except Exception as exc:
                Console().print(f"[yellow]Skipping AI analysis:[/yellow] {exc}")
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output_path = run_output_path(args.output, run_id)
        csv_output_path = run_output_path(args.csv_output, run_id)
        alert_match_windows(visible_matches)
        if visible_matches:
            write_matches(output_path, visible_matches)
            write_matches_csv(csv_output_path, visible_matches)
            write_matches(args.output, visible_matches)
            write_matches_csv(args.csv_output, visible_matches)
            if ai_summary:
                write_ai_summary(run_output_path(args.output.with_suffix(".ai.md"), run_id), ai_summary)
                write_ai_summary(args.output.with_suffix(".ai.md"), ai_summary)
            else:
                remove_matches_file(args.output.with_suffix(".ai.md"))
            Console().print(
                f"Wrote {len(visible_matches)} visible availability window(s) "
                f"from {len(matches)} total window(s) and {len(raw_matches)} raw site match(es) "
                f"to {output_path} and {csv_output_path}; updated latest at {args.output} and {args.csv_output}."
            )
        else:
            remove_matches_file(args.output)
            remove_matches_file(args.csv_output)
            remove_matches_file(args.output.with_suffix(".ai.md"))
            Console().print(
                f"No visible availability windows from {len(matches)} total window(s) "
                f"and {len(raw_matches)} raw site match(es); removed latest output files if present."
            )
        if not run_forever:
            break
        time.sleep(args.interval_seconds)


def run_scan(
    config_path: Path,
    cdp_url: str,
    login_timeout_ms: int,
    request_delay_seconds: float,
    search_delay_seconds: float,
    max_retries: int,
    cache_path: Path,
    save_data: bool,
    use_saved_data: bool,
    raw_data_path: Path | None = None,
    save_raw_data: bool = False,
) -> list[Match]:
    console = Console()
    config = load_config(config_path)
    raw_output_path = raw_data_path if save_raw_data else None
    searches = expand_searches(config, console, raw_output_path)
    all_matches: list[Match] = []
    last_network_domain: str | None = None
    for group in interleave_search_groups_by_domain(group_searches_by_campground(searches)):
        console.print(
            f"Scanning [bold]{group.campground_name}[/bold] "
            f"({len(group.searches)} search rule(s), {group.start.isoformat()} to {group.end.isoformat()})..."
        )
        search_domain = domain_for_url(group.campground_url)
        if use_saved_data:
            try:
                campsites = load_cached_campground_campsites(cache_path, group.campground_url, group.start, group.end)
                console.print(f"Loaded saved data for {group.campground_name}.")
            except Exception as exc:
                if not save_data:
                    console.print(f"[yellow]Skipping {group.campground_name}; saved data unavailable:[/yellow] {exc}")
                    continue
                console.print(f"[yellow]Saved data missing for {group.campground_name}; fetching it now.[/yellow]")
                try:
                    maybe_wait_between_network_searches(
                        console,
                        search_delay_seconds,
                        last_network_domain,
                        search_domain,
                    )
                    campsites = fetch_campsites_for_search(
                        group.fetch_search,
                        cdp_url,
                        login_timeout_ms,
                        request_delay_seconds=request_delay_seconds,
                        max_retries=max_retries,
                        raw_data_path=raw_output_path,
                        retry_logger=lambda message: console.print(f"[yellow]{message}[/yellow]"),
                    )
                    last_network_domain = search_domain
                    path = save_cached_campground_campsites(
                        cache_path,
                        group.campground_url,
                        group.start,
                        group.end,
                        campsites,
                    )
                    console.print(f"Saved data for {group.campground_name} to {path}.")
                except Exception as fetch_exc:
                    console.print(f"[yellow]Skipping {group.campground_name} after fetch error:[/yellow] {fetch_exc}")
                    continue
        else:
            try:
                maybe_wait_between_network_searches(
                    console,
                    search_delay_seconds,
                    last_network_domain,
                    search_domain,
                )
                campsites = fetch_campsites_for_search(
                    group.fetch_search,
                    cdp_url,
                    login_timeout_ms,
                    request_delay_seconds=request_delay_seconds,
                    max_retries=max_retries,
                    raw_data_path=raw_output_path,
                    retry_logger=lambda message: console.print(f"[yellow]{message}[/yellow]"),
                )
                last_network_domain = search_domain
                if save_data:
                    path = save_cached_campground_campsites(
                        cache_path,
                        group.campground_url,
                        group.start,
                        group.end,
                        campsites,
                    )
                    console.print(f"Saved data for {group.campground_name} to {path}.")
            except Exception as exc:
                console.print(f"[yellow]Skipping {group.campground_name} after error:[/yellow] {exc}")
                continue
        for search in group.searches:
            matches = find_matches(search, campsites)
            if not matches:
                console.print(f"No matches for {search.name}.")
            else:
                console.print(f"{len(matches)} raw site match(es) for {search.name}.")
            all_matches.extend(matches)
    return all_matches


def expand_searches(config: AppConfig, console: Console, raw_data_path: Path | None = None) -> list[SearchConfig]:
    searches = list(config.searches)
    for search_set in config.search_sets:
        discovered = [
            search.model_copy(update={"filters": config.filters.merged_with(search.filters)})
            for search in discover_searches_for_search_set(search_set, raw_data_path)
        ]
        console.print(f"Discovered {len(discovered)} campground(s) for search set [bold]{search_set.name}[/bold].")
        searches.extend(discovered)
    return searches


def discover_state_catalog(state: str) -> Path:
    clean_state = state.strip().upper()
    if not clean_state:
        raise RuntimeError("State is required.")
    api_key = os.getenv("OUTDOORITHM_API_KEY", "")
    if not api_key:
        raise RuntimeError("OUTDOORITHM_API_KEY is required for --discover-state.")
    rows = discover_campground_catalog_for_state(clean_state, api_key)
    output_path = Path("data") / f"{clean_state}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")
    return output_path


def preferences_by_search(config: AppConfig) -> dict[str, object]:
    preferences = {search.name: search.preferences for search in config.searches}
    for search_set in config.search_sets:
        preferences[search_set.name] = search_set.preferences
    return preferences


@dataclass(frozen=True)
class SearchGroup:
    campground_url: str
    campground_name: str
    start: date
    end: date
    fetch_search: SearchConfig
    searches: list[SearchConfig]


def group_searches_by_campground(searches: list[SearchConfig]) -> list[SearchGroup]:
    grouped: dict[str, list[SearchConfig]] = {}
    for search in searches:
        grouped.setdefault(str(search.campground.url), []).append(search)

    search_groups: list[SearchGroup] = []
    for campground_url, group_searches in grouped.items():
        first = group_searches[0]
        start = min(search.date_window.start for search in group_searches)
        end = max(search.date_window.end for search in group_searches)
        max_nights = max(search.date_window.nights for search in group_searches)
        fetch_search = first.model_copy(
            update={
                "date_window": DateWindow(
                    start=start,
                    end=end,
                    nights=max_nights,
                    check_in_weekdays=[],
                ),
                "require_login": any(search.require_login for search in group_searches),
            }
        )
        search_groups.append(
            SearchGroup(
                campground_url=campground_url,
                campground_name=first.campground.name,
                start=start,
                end=end,
                fetch_search=fetch_search,
                searches=group_searches,
            )
        )
    return search_groups


def interleave_search_groups_by_domain(groups: list[SearchGroup]) -> list[SearchGroup]:
    by_domain: dict[str, list[SearchGroup]] = {}
    domain_order: list[str] = []
    for group in groups:
        domain = domain_for_url(group.campground_url)
        if domain not in by_domain:
            by_domain[domain] = []
            domain_order.append(domain)
        by_domain[domain].append(group)

    interleaved: list[SearchGroup] = []
    while any(by_domain.values()):
        for domain in domain_order:
            if by_domain[domain]:
                interleaved.append(by_domain[domain].pop(0))
    return interleaved


def domain_for_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def maybe_wait_between_network_searches(
    console: Console,
    search_delay_seconds: float,
    last_network_domain: str | None,
    search_domain: str,
) -> None:
    if search_domain == "outdoorithm.com":
        return
    if not last_network_domain or last_network_domain != search_domain or search_delay_seconds <= 0:
        return
    console.print(f"Waiting {search_delay_seconds:g}s before next {search_domain} network search...")
    time.sleep(search_delay_seconds)


def remove_matches_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def write_matches(path: Path, matches: list[MatchWindow]) -> None:
    if not matches:
        remove_matches_file(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [match.model_dump(mode="json") for match in matches]
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def run_output_path(path: Path, run_id: str) -> Path:
    return path.with_name(f"{path.stem}-{run_id}{path.suffix}")


def write_matches_csv(path: Path, matches: list[MatchWindow]) -> None:
    if not matches:
        remove_matches_file(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "state_key",
                "search_names",
                "campground_id",
                "campground_name",
                "campground_url",
                "check_in_window_start",
                "check_in_window_end",
                "earliest_check_out",
                "latest_check_out",
                "nights",
                "representative_campsite_id",
                "representative_campsite_name",
                "representative_site_type",
                "representative_loop",
                "matching_campsite_ids",
                "matching_start_count",
                "ai_score",
                "ai_fit",
                "ai_reasons",
                "ai_concerns",
                "ai_summary",
                "suggested_state_action",
                "suggested_state_reason",
                "unique_site_count",
            ],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "state_key": match.state_key,
                    "search_names": "; ".join(match.search_names),
                    "campground_id": match.campground_id,
                    "campground_name": match.campground_name,
                    "campground_url": match.campground_url,
                    "check_in_window_start": match.check_in_window_start.isoformat(),
                    "check_in_window_end": match.check_in_window_end.isoformat(),
                    "earliest_check_out": match.earliest_check_out.isoformat(),
                    "latest_check_out": match.latest_check_out.isoformat(),
                    "nights": match.nights,
                    "representative_campsite_id": match.representative_campsite_id,
                    "representative_campsite_name": match.representative_campsite_name,
                    "representative_site_type": match.representative_site_type,
                    "representative_loop": match.representative_loop,
                    "matching_campsite_ids": "; ".join(match.matching_campsite_ids),
                    "ai_score": match.ai_score,
                    "ai_fit": match.ai_fit,
                    "ai_reasons": "; ".join(match.ai_reasons),
                    "ai_concerns": "; ".join(match.ai_concerns),
                    "ai_summary": match.ai_summary,
                    "suggested_state_action": match.suggested_state_action,
                    "suggested_state_reason": match.suggested_state_reason,
                    "matching_start_count": match.matching_start_count,
                    "unique_site_count": match.unique_site_count,
                }
            )


if __name__ == "__main__":
    main()
