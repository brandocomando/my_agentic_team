from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
from itertools import groupby

from campsite_finder_agent.models import Match, MatchWindow


@dataclass
class StartDateMatch:
    campground_id: str
    campground_name: str
    campground_url: str
    check_in: date
    nights: int
    representative: Match
    search_names: set[str] = field(default_factory=set)
    site_ids: set[str] = field(default_factory=set)
    unlock_times: set[str] = field(default_factory=set)


def aggregate_match_windows(matches: list[Match]) -> list[MatchWindow]:
    starts = one_match_per_campground_start(matches)
    windows: list[MatchWindow] = []
    grouped = groupby(
        sorted(starts, key=lambda item: (item.campground_url, item.nights, item.check_in)),
        key=lambda item: (item.campground_url, item.nights),
    )
    for _, group in grouped:
        current: list[StartDateMatch] = []
        for item in group:
            if current and item.check_in != current[-1].check_in + timedelta(days=1):
                windows.append(build_window(current))
                current = []
            current.append(item)
        if current:
            windows.append(build_window(current))
    return sorted(windows, key=lambda item: (item.check_in_window_start, item.campground_name, item.nights))


def one_match_per_campground_start(matches: list[Match]) -> list[StartDateMatch]:
    by_start: dict[tuple[str, int, date], StartDateMatch] = {}
    for match in sorted(matches, key=lambda item: (item.campsite_name, item.campsite_id)):
        key = (match.campground_url, match.nights, match.check_in)
        existing = by_start.get(key)
        if existing is None:
            existing = StartDateMatch(
                campground_id=match.campground_id,
                campground_name=match.campground_name,
                campground_url=match.campground_url,
                check_in=match.check_in,
                nights=match.nights,
                representative=match,
            )
            by_start[key] = existing
        existing.search_names.add(match.search_name)
        existing.site_ids.add(match.campsite_id)
        existing.unlock_times.update(match.unlock_times)
    return list(by_start.values())


def build_window(starts: list[StartDateMatch]) -> MatchWindow:
    first = starts[0]
    last = starts[-1]
    representative = first.representative
    search_names = sorted({name for item in starts for name in item.search_names})
    site_ids = {site_id for item in starts for site_id in item.site_ids}
    unlock_times = {unlock_time for item in starts for unlock_time in item.unlock_times}
    return MatchWindow(
        state_key=state_key_for_window(
            first.campground_url,
            first.check_in,
            last.check_in,
            first.nights,
        ),
        search_names=search_names,
        campground_id=first.campground_id,
        campground_name=first.campground_name,
        campground_url=first.campground_url,
        check_in_window_start=first.check_in,
        check_in_window_end=last.check_in,
        earliest_check_out=first.check_in + timedelta(days=first.nights),
        latest_check_out=last.check_in + timedelta(days=last.nights),
        nights=first.nights,
        representative_campsite_id=representative.campsite_id,
        representative_campsite_name=representative.campsite_name,
        representative_site_type=representative.site_type,
        representative_loop=representative.loop,
        matching_campsite_ids=sorted(site_ids),
        unlock_times=sorted(unlock_times),
        matching_start_count=len(starts),
        unique_site_count=len(site_ids),
    )


def state_key_for_window(campground_url: str, check_in_start: date, check_in_end: date, nights: int) -> str:
    payload = "|".join(
        [
            campground_url,
            check_in_start.isoformat(),
            check_in_end.isoformat(),
            str(nights),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
