from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import HttpUrl

from campsite_finder_agent.models import (
    CampgroundConfig,
    Campsite,
    DiscoveryConfig,
    Provider,
    SearchConfig,
    SearchSetConfig,
)


OUTDOORITHM_BASE_URL = "https://outdoorithm.com/api/v1"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
AVAILABILITY_SUPPORTED_PROVIDERS = {
    "ArizonaStateParks",
    "ArkansasStateParks",
    "ClackamasCountyParks",
    "ColoradoStateParks",
    "DonPedroLake",
    "FairfaxCountyParks",
    "FloridaStateParks",
    "GoingToCamp",
    "HawaiiStateParks",
    "IllinoisStateParks",
    "Itinio",
    "KernCountyParks",
    "LouisianaStateParks",
    "MaineStateParks",
    "Michigan",
    "MinnesotaStateParks",
    "MississippiStateParks",
    "MissouriStateParks",
    "NevadaStateParks",
    "NewJerseyStateParks",
    "NorthDakotaStateParks",
    "OCParksCA",
    "OhioStateParks",
    "OregonMetro",
    "PGERecreation",
    "RecreationDotGov",
    "ReserveAmerica",
    "ReserveCalifornia",
    "SanBernardinoCountyParks",
    "SanDiegoCountyParks",
    "SanMateoCountyParks",
    "SantaBarbaraCountyParks",
    "SantaClaraCountyParks",
    "SnohomishCountyParks",
    "SolanoCountyParks",
    "SonomaCountyParks",
    "SouthDakotaStateParks",
    "VirginiaStateParks",
    "VistaRecreation",
    "WashingtonCountyParks",
    "WestVirginiaStateParks",
    "WyomingStateParks",
    "Yellowstone",
    "YoloCountyParks",
}


def fetch_campsites_for_search(
    search: SearchConfig,
    cdp_url: str = "",
    login_timeout_ms: int = 0,
    request_delay_seconds: float = 0,
    max_retries: int = 0,
    raw_data_path: Path | None = None,
    retry_logger: Callable[[str], None] | None = None,
) -> list[Campsite]:
    if not search.campground.outdoorithm_id:
        raise RuntimeError(
            f"{search.name} uses provider outdoorithm but campground.outdoorithm_id is not set."
        )
    api_key = os.getenv("OUTDOORITHM_API_KEY", "")
    if not api_key:
        raise RuntimeError("OUTDOORITHM_API_KEY is required for provider outdoorithm.")
    campsites_by_id: dict[str, Campsite] = {}
    for index, (start, end) in enumerate(availability_date_chunks(search.date_window.start, search.date_window.end)):
        if index and request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
        payload = fetch_availability(
            search.campground.outdoorithm_id,
            start,
            end,
            api_key,
            max_retries=max_retries,
            retry_logger=retry_logger,
        )
        if raw_data_path:
            write_raw_json(
                raw_data_path / "outdoorithm" / "availability" / slugify(search.name),
                f"{start.isoformat()}_{end.isoformat()}.json",
                payload,
            )
        for campsite in parse_availability(payload):
            existing = campsites_by_id.get(campsite.campsite_id)
            if not existing:
                campsites_by_id[campsite.campsite_id] = campsite
                continue
            existing.availabilities.update(campsite.availabilities)
    return list(campsites_by_id.values())


def availability_date_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=30), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


def fetch_availability(
    campground_id: str,
    start: date,
    end: date,
    api_key: str,
    max_retries: int = 0,
    retry_logger: Callable[[str], None] | None = None,
) -> dict:
    encoded_id = quote(campground_id, safe="")
    query = urlencode(
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "min_nights": 1,
        }
    )
    request = Request(
        f"{OUTDOORITHM_BASE_URL}/campgrounds/{encoded_id}/availability?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    for attempt in range(max_retries + 1):
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                delay_seconds = outdoorithm_retry_delay(exc, attempt)
                if retry_logger:
                    retry_logger(
                        f"Outdoorithm returned {exc.code} for {campground_id} "
                        f"{start.isoformat()} to {end.isoformat()}; "
                        f"retrying in {delay_seconds:g}s "
                        f"(attempt {attempt + 1}/{max_retries + 1})."
                    )
                time.sleep(delay_seconds)
                continue
            raise RuntimeError(
                f"Outdoorithm API returned {exc.code} after {attempt + 1} attempt(s): {detail}"
            ) from exc
    raise RuntimeError("Outdoorithm API request failed unexpectedly.")


def outdoorithm_retry_delay(exc: HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    return min(60.0, 5.0 * (attempt + 1))


def discover_searches_for_search_set(
    search_set: SearchSetConfig,
    raw_data_path: Path | None = None,
) -> list[SearchConfig]:
    api_key = os.getenv("OUTDOORITHM_API_KEY", "")
    if not api_key:
        raise RuntimeError("OUTDOORITHM_API_KEY is required for Outdoorithm search_sets.")
    campgrounds = (
        discover_campgrounds(search_set.discovery, api_key, raw_data_path, search_set.name)
        if search_set.discovery.has_criteria()
        else []
    )
    campgrounds = append_explicit_campground_ids(campgrounds, search_set.campground_ids)
    searches: list[SearchConfig] = []
    seen_ids: set[str] = set()
    excluded_ids = set(search_set.exclude_campground_ids)
    for campground in campgrounds:
        campground_id = str(campground.get("id") or "")
        if not campground_id or campground_id in seen_ids:
            continue
        seen_ids.add(campground_id)
        if campground_id in excluded_ids:
            continue
        if not availability_provider_is_supported(campground_id):
            continue
        campground_name = str(campground.get("name") or campground_id)
        campground_url = campground.get("url") or campground.get("link") or outdoorithm_campground_url(campground)
        if name_is_excluded(
            " ".join(
                [
                    campground_name,
                    str(campground_url),
                    str(campground.get("slug") or ""),
                ]
            ),
            search_set.discovery.name_exclude,
        ):
            continue
        searches.append(
            SearchConfig(
                name=f"{search_set.name}-{slugify(campground_name)}",
                campground=CampgroundConfig(
                    name=campground_name,
                    url=HttpUrl(str(campground_url)),
                    provider=Provider.outdoorithm,
                    outdoorithm_id=campground_id,
                ),
                date_window=search_set.availability,
                filters=search_set.filters,
                alert=search_set.alert,
                preferences=search_set.preferences,
                require_login=False,
            )
        )
    return searches


def append_explicit_campground_ids(campgrounds: list[dict], campground_ids: list[str]) -> list[dict]:
    explicit_campgrounds = [
        {
            "id": campground_id,
            "name": campground_id,
            "url": outdoorithm_campground_url({"id": campground_id}),
        }
        for campground_id in campground_ids
    ]
    return [*campgrounds, *explicit_campgrounds]


def availability_provider_is_supported(campground_id: str) -> bool:
    provider = campground_id.split(":", 1)[0]
    return provider in AVAILABILITY_SUPPORTED_PROVIDERS


def name_is_excluded(name: str, excluded_terms: list[str]) -> bool:
    normalized_name = name.casefold()
    return any(term.casefold() in normalized_name for term in excluded_terms)


def discover_campgrounds(
    discovery: DiscoveryConfig,
    api_key: str,
    raw_data_path: Path | None = None,
    search_set_name: str = "search-set",
) -> list[dict]:
    remaining = discovery.limit
    cursor: str | None = None
    campgrounds: list[dict] = []
    while remaining > 0:
        page_limit = min(remaining, 100)
        payload = fetch_campgrounds(discovery, api_key, page_limit, cursor)
        if raw_data_path:
            page_number = len(campgrounds) // 100 + 1
            write_raw_json(
                raw_data_path / "outdoorithm" / "discovery" / slugify(search_set_name),
                f"page-{page_number:03d}.json",
                payload,
            )
        data = payload.get("data", payload)
        if isinstance(data, dict):
            items = data.get("campgrounds") or data.get("items") or data.get("results") or []
            pagination = data.get("pagination") or {}
            cursor = data.get("next_cursor") or data.get("nextCursor") or pagination.get("next_cursor")
        elif isinstance(data, list):
            items = data
            cursor = None
        else:
            items = []
            cursor = None
        campgrounds.extend(item for item in items if isinstance(item, dict))
        remaining = discovery.limit - len(campgrounds)
        if not cursor or not items:
            break
    return campgrounds[: discovery.limit]


def discover_campground_catalog_for_state(state: str, api_key: str, limit: int = 1000) -> list[dict]:
    campgrounds = discover_campgrounds(
        DiscoveryConfig(states=[state.upper()], limit=limit),
        api_key,
    )
    return campground_catalog_rows(campgrounds)


def campground_catalog_rows(campgrounds: list[dict]) -> list[dict]:
    rows = [
        {
            "id": campground.get("id"),
            "slug": campground.get("slug"),
            "name": campground.get("name"),
            "nearest_city": campground.get("nearest_city"),
            "url": campground.get("url"),
        }
        for campground in campgrounds
        if isinstance(campground, dict)
    ]
    return sorted(rows, key=lambda item: ((item.get("name") or "").casefold(), item.get("id") or ""))


def fetch_campgrounds(discovery: DiscoveryConfig, api_key: str, limit: int, cursor: str | None = None) -> dict:
    query = urlencode(discovery_query_params(discovery, limit, cursor), doseq=True)
    request = Request(
        f"{OUTDOORITHM_BASE_URL}/campgrounds?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Outdoorithm API returned {exc.code}: {detail}") from exc


def discovery_query_params(discovery: DiscoveryConfig, limit: int, cursor: str | None = None) -> dict:
    params: dict[str, object] = {"limit": limit}
    if discovery.states:
        params["state"] = discovery.states
    optional_params = {
        "latitude": discovery.latitude,
        "longitude": discovery.longitude,
        "radius_miles": discovery.radius_miles,
        "camping_type": discovery.camping_type,
        "min_price": discovery.min_price_per_night,
        "max_price": discovery.max_price_per_night,
        "requires_potable_water": discovery.requires_potable_water,
        "requires_showers": discovery.requires_showers,
        "requires_flush_toilets": discovery.requires_flush_toilets,
        "requires_electric_hookups": discovery.requires_electric_hookups,
        "requires_water_hookups": discovery.requires_water_hookups,
        "requires_dump_station": discovery.requires_dump_station,
        "pets_allowed": discovery.pets_allowed,
        "greenbook_safe": discovery.greenbook_safe,
        "min_greenbook_vibe": discovery.min_greenbook_vibe,
        "min_review_count": discovery.min_review_count,
        "min_avg_sentiment": discovery.min_avg_sentiment,
        "cursor": cursor,
    }
    for key, value in optional_params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            params[key] = str(value).lower()
        else:
            params[key] = value
    return params


def outdoorithm_campground_url(campground: dict) -> str:
    slug = campground.get("slug")
    state = str(campground.get("state") or "ca").lower()
    if slug:
        return f"https://outdoorithm.com/campgrounds/{state}/{slug}"
    return f"https://outdoorithm.com/campgrounds/{quote(str(campground.get('id') or ''), safe='')}"


def write_raw_json(directory: Path, filename: str, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def slugify(value: str) -> str:
    slug = []
    last_was_dash = False
    for char in value.lower():
        if char.isalnum():
            slug.append(char)
            last_was_dash = False
        elif not last_was_dash:
            slug.append("-")
            last_was_dash = True
    return "".join(slug).strip("-") or "campground"


def parse_availability(payload: dict) -> list[Campsite]:
    data = payload.get("data", payload)
    campsites: list[Campsite] = []
    for raw in data.get("campsites", []):
        availability: dict[date, str] = {}
        for available_range in raw.get("available_dates", []):
            start = date.fromisoformat(str(available_range["start_date"]))
            nights = int(available_range.get("nights") or 0)
            for offset in range(nights):
                availability[start + timedelta(days=offset)] = "Available"
        equipment = raw.get("equipment") or []
        campsites.append(
            Campsite(
                campsite_id=str(raw.get("campsite_id") or ""),
                name=str(raw.get("campsite_name") or raw.get("campsite_id") or ""),
                site_type=str(raw.get("campsite_type") or ""),
                loop=str(raw.get("loop_name") or ""),
                equipment=", ".join(str(item) for item in equipment),
                max_vehicle_length=None,
                availabilities=availability,
                raw={"provider": "outdoorithm", "availability": raw},
            )
        )
    return campsites
