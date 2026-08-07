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
from campsite_finder_agent.alerts import EmailAlertSettings, alert_match_windows, notify_ai_match_windows
from campsite_finder_agent.availability import find_matches
from campsite_finder_agent.cache import describe_cached_ranges, load_cached_campground_campsites, save_cached_campground_campsites
from campsite_finder_agent.config import load_config, load_settings
from campsite_finder_agent.models import AppConfig, DateWindow, LockedSearchConfig, Match, MatchWindow, SearchConfig
from campsite_finder_agent.outdoorithm import discover_campground_catalog_for_state, discover_searches_for_search_set
from campsite_finder_agent.providers import fetch_campsites_for_search
from campsite_finder_agent.recreation import get_recreation_site
from campsite_finder_agent.reserve_california import (
    ReserveCaliforniaLock,
    capture_reserve_california_network,
    find_locked_matches,
    fetch_locked_campsites,
    get_reserve_california_site,
)
from campsite_finder_agent.results import aggregate_match_windows
from campsite_finder_agent.state import filter_stateful_match_windows, load_state


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Find open Recreation.gov campsites.")
    parser.add_argument("--config", type=Path, default=settings.config_path)
    parser.add_argument("--output", type=Path, default=settings.output_path)
    parser.add_argument("--csv-output", type=Path, default=settings.csv_output_path)
    parser.add_argument("--lock-output", type=Path, default=settings.lock_output_path)
    parser.add_argument("--lock-csv-output", type=Path, default=settings.lock_csv_output_path)
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
        "--reservecalifornia-locks",
        action="store_true",
        help="Report ReserveCalifornia grid lock icons for a park URL/date range.",
    )
    parser.add_argument(
        "--park-url",
        help="ReserveCalifornia park URL, e.g. https://www.reservecalifornia.com/park/639/464.",
    )
    parser.add_argument(
        "--start-date",
        help="First date to inspect, e.g. 2026-08-07.",
    )
    parser.add_argument("--end-date", help="Last date to inspect, e.g. 2026-08-09.")
    parser.add_argument(
        "--nights",
        type=int,
        help="Expected ReserveCalifornia stay length in nights.",
    )
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help="Limit lock scan to a site number/name. Repeatable.",
    )
    parser.add_argument("--locks-output", type=Path, help="Optional JSON or CSV output path for one-off ReserveCalifornia locks.")
    parser.add_argument(
        "--get-site",
        action="store_true",
        help="Run the provider-specific get-site helper inferred from --park-url.",
    )
    parser.add_argument(
        "--get-reservecalifornia-site",
        action="store_true",
        help="Refresh a ReserveCalifornia grid and click a target site cell when it opens.",
    )
    parser.add_argument(
        "--get-recreation-site",
        action="store_true",
        help="Poll Recreation.gov release status for a target site and stay.",
    )
    parser.add_argument(
        "--refresh-window-start",
        help="Local refresh start time, HH:MM[:SS].",
    )
    parser.add_argument("--refresh-window-end", help="Local refresh end time, HH:MM[:SS].")
    parser.add_argument("--refresh-timezone")
    parser.add_argument("--refresh-interval-seconds", type=float)
    parser.add_argument("--max-run-seconds", type=float, help="Cap a get-site run after this many seconds.")
    parser.add_argument("--adults", type=int, default=settings.get_site_adults)
    parser.add_argument("--children", type=int, default=settings.get_site_children)
    parser.add_argument("--occupant-name", default=settings.get_site_occupant or settings.get_site_occupant_name)
    parser.add_argument("--camping-unit", default=settings.get_site_camping_unit)
    parser.add_argument("--trailer-length-feet", type=float, default=settings.get_site_trailer_length_feet)
    parser.add_argument("--vehicle-count", type=int, default=settings.get_site_vehicle_count)
    parser.add_argument("--phone-number", default=settings.get_site_phone_number)
    parser.add_argument("--street-1", default=settings.get_site_street_1)
    parser.add_argument("--city", default=settings.get_site_city)
    parser.add_argument("--state", default=settings.get_site_state)
    parser.add_argument("--postal-code", default=settings.get_site_postal_code or settings.get_site_zipcode)
    parser.add_argument("--zipcode", default=settings.get_site_zipcode)
    parser.add_argument("--no-click-book-now", action="store_true", help="Click only the site cell; do not click Book Now.")
    parser.add_argument("--no-click-reserve-unit", action="store_true", help="Fill reservation details but do not click Reserve Unit.")
    parser.add_argument(
        "--no-click-payment-next",
        action="store_true",
        help="For Recreation.gov, stop on the payment page instead of clicking Next.",
    )
    parser.add_argument(
        "--debug-reservecalifornia-network",
        action="store_true",
        help="Reload the open ReserveCalifornia tab and print captured JSON/API responses.",
    )
    args = parser.parse_args()

    if args.get_site:
        park_url = args.park_url or settings.get_site_campground_url
        if not park_url:
            raise RuntimeError("--park-url is required with --get-site.")
        if is_recreation_url(park_url):
            result = run_recreation_get_site(
                args.cdp_url,
                park_url,
                args.site or ([settings.get_site_site] if settings.get_site_site else []),
                args.start_date or settings.get_site_start_date,
                args.refresh_window_start or settings.get_site_refresh_window_start,
                args.refresh_window_end or settings.get_site_refresh_window_end,
                args.refresh_timezone or settings.get_site_refresh_timezone,
                args.refresh_interval_seconds
                if args.refresh_interval_seconds is not None
                else settings.get_site_refresh_interval_seconds,
                args.max_run_seconds if args.max_run_seconds is not None else settings.get_site_max_run_seconds,
                args.nights if args.nights is not None else settings.get_site_nights,
                not args.no_click_book_now,
                args.adults,
                args.children,
                args.camping_unit,
                args.trailer_length_feet,
                args.vehicle_count,
                args.phone_number,
                args.postal_code or args.zipcode,
                not args.no_click_reserve_unit,
                not args.no_click_payment_next,
            )
            Console().print(
                f"Recreation.gov get-site finished: {result.action} after {result.attempts} attempt(s); "
                f"site: {result.campsite_name or result.campsite_id or 'n/a'}; "
                f"Add to Cart clicked: {result.add_to_cart_clicked}."
            )
            return
        if is_reserve_california_url(park_url):
            result = run_reserve_california_get_site(
                args.cdp_url,
                park_url,
                args.site or ([settings.get_site_site] if settings.get_site_site else []),
                args.start_date or settings.get_site_start_date,
                args.refresh_window_start or settings.get_site_refresh_window_start,
                args.refresh_window_end or settings.get_site_refresh_window_end,
                args.refresh_timezone or settings.get_site_refresh_timezone,
                args.refresh_interval_seconds if args.refresh_interval_seconds is not None else settings.get_site_refresh_interval_seconds,
                args.max_run_seconds if args.max_run_seconds is not None else settings.get_site_max_run_seconds,
                args.nights if args.nights is not None else settings.get_site_nights,
                args.adults,
                args.children,
                args.occupant_name,
                args.camping_unit,
                args.trailer_length_feet,
                args.street_1,
                args.city,
                args.state,
                args.postal_code or args.zipcode,
                not args.no_click_book_now,
                not args.no_click_reserve_unit,
            )
            Console().print(
                f"ReserveCalifornia get-site finished: {result.action} "
                f"after {result.attempts} attempt(s); Book Now clicked: {result.book_now_clicked}; "
                f"Reserve Unit clicked: {result.reserve_unit_clicked}."
            )
            return
        raise RuntimeError("--get-site only supports recreation.gov and reservecalifornia.com campground URLs.")

    if args.get_recreation_site:
        result = run_recreation_get_site(
            args.cdp_url,
            args.park_url or settings.get_site_campground_url or None,
            args.site or ([settings.get_site_site] if settings.get_site_site else []),
            args.start_date or settings.get_site_start_date,
            args.refresh_window_start or settings.get_site_refresh_window_start,
            args.refresh_window_end or settings.get_site_refresh_window_end,
            args.refresh_timezone or settings.get_site_refresh_timezone,
            args.refresh_interval_seconds
            if args.refresh_interval_seconds is not None
            else settings.get_site_refresh_interval_seconds,
            args.max_run_seconds if args.max_run_seconds is not None else settings.get_site_max_run_seconds,
            args.nights if args.nights is not None else settings.get_site_nights,
            not args.no_click_book_now,
            args.adults,
            args.children,
            args.camping_unit,
            args.trailer_length_feet,
            args.vehicle_count,
            args.phone_number,
            args.postal_code or args.zipcode,
            not args.no_click_reserve_unit,
            not args.no_click_payment_next,
        )
        Console().print(
            f"Recreation.gov get-site finished: {result.action} after {result.attempts} attempt(s); "
            f"site: {result.campsite_name or result.campsite_id or 'n/a'}; "
            f"Add to Cart clicked: {result.add_to_cart_clicked}."
        )
        return
    if args.get_reservecalifornia_site:
        result = run_reserve_california_get_site(
            args.cdp_url,
            args.park_url or settings.get_site_campground_url or None,
            args.site or ([settings.get_site_site] if settings.get_site_site else []),
            args.start_date or settings.get_site_start_date,
            args.refresh_window_start or settings.get_site_refresh_window_start,
            args.refresh_window_end or settings.get_site_refresh_window_end,
            args.refresh_timezone or settings.get_site_refresh_timezone,
            args.refresh_interval_seconds if args.refresh_interval_seconds is not None else settings.get_site_refresh_interval_seconds,
            args.max_run_seconds if args.max_run_seconds is not None else settings.get_site_max_run_seconds,
            args.nights if args.nights is not None else settings.get_site_nights,
            args.adults,
            args.children,
            args.occupant_name,
            args.camping_unit,
            args.trailer_length_feet,
            args.street_1,
            args.city,
            args.state,
            args.postal_code or args.zipcode,
            not args.no_click_book_now,
            not args.no_click_reserve_unit,
        )
        Console().print(
            f"ReserveCalifornia get-site finished: {result.action} "
            f"after {result.attempts} attempt(s); Book Now clicked: {result.book_now_clicked}; "
            f"Reserve Unit clicked: {result.reserve_unit_clicked}."
        )
        return
    if args.debug_reservecalifornia_network:
        print(json.dumps(capture_reserve_california_network(args.cdp_url), indent=2))
        return
    if args.reservecalifornia_locks:
        if args.park_url:
            locks = run_reserve_california_lock_scan(
                args.cdp_url,
                args.park_url,
                args.start_date,
                args.end_date,
                set(args.site),
                args.locks_output,
            )
            Console(stderr=not bool(args.locks_output)).print(f"Found {len(locks)} ReserveCalifornia lock slice(s).")
        else:
            lock_matches = run_configured_reserve_california_lock_scan(
                args.config,
                args.cdp_url,
                args.search_delay_seconds,
            )
            lock_windows = aggregate_match_windows(lock_matches)
            ai_summary = ""
            if lock_windows and not args.no_ai:
                try:
                    ai_summary = analyze_match_windows_with_ollama(
                        lock_windows,
                        preferences_by_search(load_config(args.config)),
                        model=args.ollama_model,
                        base_url=args.ollama_base_url,
                    )
                    Console().print(ai_summary)
                except Exception as exc:
                    Console().print(f"[yellow]Skipping AI analysis:[/yellow] {exc}")
            write_matches(args.lock_output, lock_windows)
            write_matches_csv(args.lock_csv_output, lock_windows)
            if ai_summary:
                write_ai_summary(args.lock_output.with_suffix(".ai.md"), ai_summary)
                notify_ai_match_windows(lock_windows, email_alert_settings(settings))
            else:
                remove_matches_file(args.lock_output.with_suffix(".ai.md"))
            if lock_windows:
                Console().print(
                    f"Wrote {len(lock_windows)} ReserveCalifornia locked availability window(s) "
                    f"from {len(lock_matches)} raw locked site match(es) to {args.lock_output} and {args.lock_csv_output}."
                )
            else:
                Console().print("No configured ReserveCalifornia locked availability windows found.")
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
            if ai_summary:
                notify_ai_match_windows(visible_matches, email_alert_settings(settings))
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


def email_alert_settings(settings) -> EmailAlertSettings:
    return EmailAlertSettings(
        enabled=settings.email_alerts_enabled,
        gmail_credentials_path=settings.gmail_credentials_path,
        gmail_token_path=settings.gmail_token_path,
        recipient=settings.email_to,
        min_score=settings.ai_notify_min_score,
        actions=parse_actions(settings.ai_notify_actions),
        state_path=settings.notification_state_path,
    )


def parse_actions(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


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
                cache_hint = describe_cached_ranges(cache_path, group.campground_url)
                console.print(
                    f"[yellow]Saved data missing for {group.campground_name} "
                    f"({group.start.isoformat()} to {group.end.isoformat()}); {cache_hint}; fetching it now.[/yellow]"
                )
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


def run_reserve_california_get_site(
    cdp_url: str,
    park_url: str | None,
    sites: list[str],
    start_date: str | None,
    refresh_window_start: str,
    refresh_window_end: str,
    refresh_timezone: str,
    refresh_interval_seconds: float,
    max_run_seconds: float | None,
    nights: int | None,
    adults: int,
    children: int,
    occupant_name: str,
    camping_unit: str,
    trailer_length_feet: float | None,
    street_1: str,
    city: str,
    state: str,
    postal_code: str,
    click_book_now: bool,
    click_reserve_unit: bool,
):
    if not park_url:
        raise RuntimeError("--park-url is required with --get-reservecalifornia-site.")
    if not sites:
        raise RuntimeError("--site is required with --get-reservecalifornia-site.")
    if not start_date:
        raise RuntimeError("--start-date is required with --get-reservecalifornia-site.")
    if nights is None:
        raise RuntimeError("--nights is required with --get-reservecalifornia-site.")
    if not occupant_name.strip():
        raise RuntimeError("--occupant-name is required with --get-reservecalifornia-site.")
    address_values = [street_1.strip(), city.strip(), state.strip(), postal_code.strip()]
    if any(address_values) and not all(address_values):
        raise RuntimeError("--street-1, --city, --state, and --postal-code are all required when filling checkout address details.")
    return get_reserve_california_site(
        cdp_url=cdp_url,
        park_url=park_url,
        site=sites[0],
        start_date=parse_cli_date(start_date),
        nights=nights,
        refresh_window_start=refresh_window_start,
        refresh_window_end=refresh_window_end,
        timezone_name=refresh_timezone,
        refresh_interval_seconds=refresh_interval_seconds,
        max_run_seconds=max_run_seconds,
        click_book_now=click_book_now,
        adults=adults,
        children=children,
        occupant_name=occupant_name,
        camping_unit=camping_unit,
        trailer_length_feet=trailer_length_feet,
        street_1=street_1,
        city=city,
        state=state,
        postal_code=postal_code,
        click_reserve_unit=click_reserve_unit,
    )


def run_recreation_get_site(
    cdp_url: str,
    campground_url: str | None,
    sites: list[str],
    start_date: str | None,
    refresh_window_start: str,
    refresh_window_end: str,
    refresh_timezone: str,
    refresh_interval_seconds: float,
    max_run_seconds: float | None,
    nights: int | None,
    click_add_to_cart: bool,
    adults: int,
    children: int,
    camping_unit: str,
    trailer_length_feet: float | None,
    vehicle_count: int | None,
    phone_number: str,
    postal_code: str,
    click_proceed_to_cart: bool,
    click_payment_next: bool,
):
    if not campground_url:
        raise RuntimeError("--park-url is required with --get-recreation-site.")
    if not sites:
        raise RuntimeError("--site is required with --get-recreation-site.")
    if not start_date:
        raise RuntimeError("--start-date is required with --get-recreation-site.")
    if nights is None:
        raise RuntimeError("--nights is required with --get-recreation-site.")
    return get_recreation_site(
        cdp_url=cdp_url,
        campground_url=campground_url,
        site=sites[0],
        start_date=parse_cli_date(start_date),
        nights=nights,
        refresh_window_start=refresh_window_start,
        refresh_window_end=refresh_window_end,
        timezone_name=refresh_timezone,
        refresh_interval_seconds=refresh_interval_seconds,
        max_run_seconds=max_run_seconds,
        click_add_to_cart=click_add_to_cart,
        adults=adults,
        children=children,
        camping_unit=camping_unit,
        trailer_length_feet=trailer_length_feet,
        vehicle_count=vehicle_count,
        phone_number=phone_number,
        postal_code=postal_code,
        click_proceed_to_cart=click_proceed_to_cart,
        click_payment_next=click_payment_next,
    )


def is_recreation_url(value: str) -> bool:
    host = urlparse(value).hostname or ""
    return host == "recreation.gov" or host.endswith(".recreation.gov")


def is_reserve_california_url(value: str) -> bool:
    host = urlparse(value).hostname or ""
    return host == "reservecalifornia.com" or host.endswith(".reservecalifornia.com")


def parse_cli_date(value: str) -> date:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for format_ in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, format_).date()
        except ValueError:
            continue
    raise RuntimeError(f"Expected date as YYYY-MM-DD, M/D/YY, or M/D/YYYY; got {value!r}.")


def run_reserve_california_lock_scan(
    cdp_url: str,
    park_url: str | None,
    start_date: str | None,
    end_date: str | None,
    sites: set[str],
    output_path: Path | None,
) -> list[ReserveCaliforniaLock]:
    if not park_url:
        raise RuntimeError("--park-url is required with --reservecalifornia-locks.")
    if not start_date or not end_date:
        raise RuntimeError("--start-date and --end-date are required with --reservecalifornia-locks.")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise RuntimeError("--end-date must be on or after --start-date.")
    locks = fetch_locked_campsites(cdp_url, park_url, start, end, site_names=sites or None)
    rows = [reserve_california_lock_row(lock) for lock in locks]
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() == ".csv":
            write_reserve_california_locks_csv(output_path, rows)
        else:
            with output_path.open("w") as handle:
                json.dump(rows, handle, indent=2)
                handle.write("\n")
        Console().print(f"Wrote ReserveCalifornia locks to {output_path}.")
    else:
        print(json.dumps(rows, indent=2))
    return locks


def run_configured_reserve_california_lock_scan(
    config_path: Path,
    cdp_url: str,
    search_delay_seconds: float,
) -> list[Match]:
    console = Console()
    config = load_config(config_path)
    searches = expand_locked_searches(config.locked_searches)
    if not searches:
        raise RuntimeError("No `locked_searches` are configured.")
    all_matches: list[Match] = []
    last_network_domain: str | None = None
    for group in interleave_search_groups_by_domain(group_searches_by_campground(searches)):
        search_domain = domain_for_url(group.campground_url)
        if search_domain != "reservecalifornia.com" and not search_domain.endswith(".reservecalifornia.com"):
            console.print(f"[yellow]Skipping non-ReserveCalifornia lock search:[/yellow] {group.campground_name}")
            continue
        maybe_wait_between_network_searches(console, search_delay_seconds, last_network_domain, search_domain)
        console.print(
            f"Scanning ReserveCalifornia locks for [bold]{group.campground_name}[/bold] "
            f"({len(group.searches)} search rule(s), {group.start.isoformat()} to {group.end.isoformat()})..."
        )
        locks = fetch_locked_campsites(cdp_url, group.campground_url, group.start, group.end)
        last_network_domain = search_domain
        for search in group.searches:
            matches = find_locked_matches(search, locks)
            if matches:
                console.print(f"{len(matches)} raw locked site match(es) for {search.name}.")
            else:
                console.print(f"No locked matches for {search.name}.")
            all_matches.extend(matches)
    return all_matches


def expand_locked_searches(locked_searches: list[LockedSearchConfig]) -> list[SearchConfig]:
    searches: list[SearchConfig] = []
    for locked_search in locked_searches:
        for campground in locked_search.campgrounds:
            searches.append(
                SearchConfig(
                    name=locked_search.name,
                    campground=campground,
                    date_window=locked_search.date_window,
                    filters=locked_search.filters,
                    alert=locked_search.alert,
                    preferences=locked_search.preferences,
                    require_login=locked_search.require_login,
                )
            )
    return searches


def reserve_california_lock_row(lock: ReserveCaliforniaLock) -> dict[str, object]:
    return {
        "campsite_id": lock.campsite_id,
        "campsite_name": lock.campsite_name,
        "short_name": lock.short_name,
        "date": lock.date.isoformat(),
        "lock_at": lock.lock_at,
        "is_free": lock.is_free,
        "is_blocked": lock.is_blocked,
        "reservation_id": lock.reservation_id,
        "site_type": lock.site_type,
        "max_vehicle_length": lock.max_vehicle_length,
        "accessible": lock.accessible,
    }


def write_reserve_california_locks_csv(output_path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "campsite_id",
        "campsite_name",
        "short_name",
        "date",
        "lock_at",
        "is_free",
        "is_blocked",
        "reservation_id",
        "site_type",
        "max_vehicle_length",
        "accessible",
    ]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def preferences_by_search(config: AppConfig) -> dict[str, object]:
    preferences = {search.name: search.preferences for search in config.searches}
    preferences.update({search.name: search.preferences for search in config.locked_searches})
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
                "unlock_times",
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
                    "unlock_times": "; ".join(match.unlock_times),
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
