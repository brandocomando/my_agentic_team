from __future__ import annotations

import hashlib
import json
from pathlib import Path

from datetime import date

from campsite_finder_agent.models import Campsite, SearchConfig


def cache_file_for_search(cache_path: Path, search: SearchConfig) -> Path:
    key = "|".join(
        [
            search.name,
            str(search.campground.url),
            search.date_window.start.isoformat(),
            search.date_window.end.isoformat(),
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return cache_path / f"{safe_name(search.name)}-{digest}.json"


def load_cached_campsites(cache_path: Path, search: SearchConfig) -> list[Campsite]:
    path = cache_file_for_search(cache_path, search)
    if not path.exists():
        raise FileNotFoundError(f"No saved data for {search.name}: {path}")
    with path.open() as handle:
        payload = json.load(handle)
    return [Campsite.model_validate(item) for item in payload.get("campsites", [])]


def save_cached_campsites(cache_path: Path, search: SearchConfig, campsites: list[Campsite]) -> Path:
    cache_path.mkdir(parents=True, exist_ok=True)
    path = cache_file_for_search(cache_path, search)
    payload = {
        "search": search.model_dump(mode="json"),
        "campsites": [campsite.model_dump(mode="json") for campsite in campsites],
    }
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def cache_file_for_campground(cache_path: Path, campground_url: str, start: date, end: date) -> Path:
    key = "|".join([campground_url, start.isoformat(), end.isoformat()])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return cache_path / f"{safe_name(campground_url)}-{start.isoformat()}-to-{end.isoformat()}-{digest}.json"


def load_cached_campground_campsites(
    cache_path: Path,
    campground_url: str,
    start: date,
    end: date,
) -> list[Campsite]:
    path = cache_file_for_campground(cache_path, campground_url, start, end)
    if not path.exists():
        raise FileNotFoundError(f"No saved data for {campground_url} {start.isoformat()} to {end.isoformat()}: {path}")
    with path.open() as handle:
        payload = json.load(handle)
    return [Campsite.model_validate(item) for item in payload.get("campsites", [])]


def cached_ranges_for_campground(cache_path: Path, campground_url: str) -> list[tuple[date, date, Path]]:
    ranges: list[tuple[date, date, Path]] = []
    if not cache_path.exists():
        return ranges
    for path in cache_path.glob("*.json"):
        try:
            with path.open() as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("campground_url") != campground_url:
            continue
        start = payload.get("start")
        end = payload.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            ranges.append((date.fromisoformat(start), date.fromisoformat(end), path))
        except ValueError:
            continue
    return sorted(ranges, key=lambda item: (item[0], item[1], item[2].name))


def describe_cached_ranges(cache_path: Path, campground_url: str, limit: int = 3) -> str:
    ranges = cached_ranges_for_campground(cache_path, campground_url)
    if not ranges:
        return "no saved ranges for this campground"
    snippets = [f"{start.isoformat()} to {end.isoformat()}" for start, end, _path in ranges[-limit:]]
    extra = len(ranges) - len(snippets)
    suffix = f" (+{extra} older)" if extra > 0 else ""
    return f"saved ranges: {', '.join(snippets)}{suffix}"


def save_cached_campground_campsites(
    cache_path: Path,
    campground_url: str,
    start: date,
    end: date,
    campsites: list[Campsite],
) -> Path:
    cache_path.mkdir(parents=True, exist_ok=True)
    path = cache_file_for_campground(cache_path, campground_url, start, end)
    payload = {
        "campground_url": campground_url,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "campsites": [campsite.model_dump(mode="json") for campsite in campsites],
    }
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def safe_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.lower())
    return "-".join(part for part in safe.split("-") if part)[:80] or "search"
