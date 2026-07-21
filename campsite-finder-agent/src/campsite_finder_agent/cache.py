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
