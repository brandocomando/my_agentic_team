from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from urllib.parse import urlparse

from campsite_finder_agent.models import Campsite, Match, SearchConfig, Weekday


AVAILABLE_STATUSES = {"available", "open", "a"}


def facility_id_from_url(url: str) -> str | None:
    path = urlparse(url).path
    match = re.search(r"/campgrounds/(\d+)", path)
    return match.group(1) if match else None


def month_starts(start: date, end: date) -> list[date]:
    current = date(start.year, start.month, 1)
    final = date(end.year, end.month, 1)
    months: list[date] = []
    while current <= final:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def availability_api_url(facility_id: str, month_start: date) -> str:
    timestamp = f"{month_start.isoformat()}T00%3A00%3A00.000Z"
    return f"https://www.recreation.gov/api/camps/availability/campground/{facility_id}/month?start_date={timestamp}"


def parse_campsites(payload: dict) -> list[Campsite]:
    raw_campsites = payload.get("campsites") or payload.get("campsite_availabilities") or {}
    campsites: list[Campsite] = []
    for campsite_id, raw in raw_campsites.items():
        if not isinstance(raw, dict):
            continue
        availabilities = {}
        for raw_day, status in (raw.get("availabilities") or {}).items():
            parsed_day = parse_recreation_date(raw_day)
            if parsed_day:
                availabilities[parsed_day] = str(status)
        campsite = Campsite(
            campsite_id=str(raw.get("campsite_id") or campsite_id),
            name=str(raw.get("site") or raw.get("campsite_id") or campsite_id),
            site_type=str(raw.get("campsite_type") or raw.get("site_type") or ""),
            loop=str(raw.get("loop") or raw.get("loop_name") or ""),
            type_of_use=str(raw.get("type_of_use") or ""),
            equipment=str(raw.get("equipment_name") or raw.get("equipment") or ""),
            max_vehicle_length=parse_optional_int(raw.get("max_vehicle_length") or raw.get("vehicle_length")),
            accessible=parse_optional_bool(raw.get("accessible")),
            availabilities=availabilities,
            raw=raw,
        )
        campsites.append(campsite)
    return campsites


def merge_campsites(monthly_campsites: list[list[Campsite]]) -> list[Campsite]:
    by_id: dict[str, Campsite] = {}
    for campsites in monthly_campsites:
        for campsite in campsites:
            existing = by_id.get(campsite.campsite_id)
            if existing is None:
                by_id[campsite.campsite_id] = campsite
            else:
                existing.availabilities.update(campsite.availabilities)
    return list(by_id.values())


def find_matches(search: SearchConfig, campsites: list[Campsite]) -> list[Match]:
    matches: list[Match] = []
    for check_in in candidate_check_ins(search):
        check_out = check_in + timedelta(days=search.date_window.nights)
        stay_dates = [check_in + timedelta(days=offset) for offset in range(search.date_window.nights)]
        for campsite in campsites:
            if not campsite_matches_filters(campsite, search):
                continue
            statuses = [campsite.availabilities.get(day, "") for day in stay_dates]
            if statuses and all(is_available(status) for status in statuses):
                matches.append(
                    Match(
                        search_name=search.name,
                        campground_id=campground_id_for_search(search),
                        campground_name=search.campground.name,
                        campground_url=str(search.campground.url),
                        campsite_id=campsite.campsite_id,
                        campsite_name=campsite.name,
                        check_in=check_in,
                        check_out=check_out,
                        nights=search.date_window.nights,
                        site_type=campsite.site_type,
                        loop=campsite.loop,
                        availability=statuses,
                    )
                )
    return matches


def campground_id_for_search(search: SearchConfig) -> str:
    return search.campground.outdoorithm_id or search.campground.facility_id or ""


def candidate_check_ins(search: SearchConfig) -> list[date]:
    latest_check_in = search.date_window.end - timedelta(days=search.date_window.nights)
    current = search.date_window.start
    weekdays = {weekday.value for weekday in search.date_window.check_in_weekdays}
    dates: list[date] = []
    while current <= latest_check_in:
        if not weekdays or Weekday(current.strftime("%A")).value in weekdays:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def campsite_matches_filters(campsite: Campsite, search: SearchConfig) -> bool:
    filters = search.filters
    if filters.site_types and normalized(campsite.site_type) not in {normalized(value) for value in filters.site_types}:
        return False
    if filters.site_type_exclude:
        haystack = site_filter_text(campsite)
        if any(normalized(value) in haystack for value in filters.site_type_exclude):
            return False
    if filters.loops and normalized(campsite.loop) not in {normalized(value) for value in filters.loops}:
        return False
    if filters.accessible is not None and campsite.accessible is not None and campsite.accessible != filters.accessible:
        return False
    if filters.min_vehicle_length is not None and campsite.max_vehicle_length is not None:
        if campsite.max_vehicle_length < filters.min_vehicle_length:
            return False
    if filters.equipment:
        haystack = normalized(" ".join([campsite.equipment, campsite.type_of_use, str(campsite.raw)]))
        if normalized(filters.equipment) not in haystack:
            return False
    return True


def site_filter_text(campsite: Campsite) -> str:
    return normalized(
        " ".join(
            [
                campsite.site_type,
                campsite.name,
                campsite.loop,
                campsite.equipment,
                campsite.type_of_use,
                str(campsite.raw),
            ]
        )
    )


def is_available(status: str) -> bool:
    clean = normalized(status)
    return clean in AVAILABLE_STATUSES or clean.startswith("available")


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def parse_recreation_date(value: str) -> date | None:
    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        return date.fromisoformat(match.group(1))
    return None


def parse_optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def parse_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    clean = str(value).strip().lower()
    if clean in {"true", "yes", "y", "1"}:
        return True
    if clean in {"false", "no", "n", "0"}:
        return False
    return None
