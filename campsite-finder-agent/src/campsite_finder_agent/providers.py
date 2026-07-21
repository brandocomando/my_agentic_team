from __future__ import annotations

from pathlib import Path
from typing import Callable

from campsite_finder_agent.models import Provider, SearchConfig
from campsite_finder_agent.outdoorithm import fetch_campsites_for_search as fetch_outdoorithm_campsites
from campsite_finder_agent.recreation import fetch_campsites_for_search as fetch_recreation_campsites
from campsite_finder_agent.reserve_california import fetch_campsites_for_search as fetch_reserve_california_campsites


def infer_provider(search: SearchConfig) -> Provider:
    if search.campground.provider:
        return search.campground.provider
    hostname = str(search.campground.url.host or "").lower()
    if "reservecalifornia.com" in hostname:
        return Provider.reserve_california
    if "recreation.gov" in hostname:
        return Provider.recreation_gov
    if "outdoorithm.com" in hostname:
        return Provider.outdoorithm
    raise RuntimeError(
        f"Could not infer provider for {search.campground.url}. "
        "Set campground.provider to `recreation.gov` or `reservecalifornia`."
    )


def fetch_campsites_for_search(
    search: SearchConfig,
    cdp_url: str,
    login_timeout_ms: int,
    request_delay_seconds: float = 2.5,
    max_retries: int = 4,
    raw_data_path: Path | None = None,
    retry_logger: Callable[[str], None] | None = None,
):
    provider = infer_provider(search)
    if provider == Provider.recreation_gov:
        return fetch_recreation_campsites(
            search,
            cdp_url,
            login_timeout_ms,
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            retry_logger=retry_logger,
        )
    if provider == Provider.reserve_california:
        return fetch_reserve_california_campsites(
            search,
            cdp_url,
            login_timeout_ms,
            request_delay_seconds=request_delay_seconds,
        )
    if provider == Provider.outdoorithm:
        return fetch_outdoorithm_campsites(
            search,
            cdp_url,
            login_timeout_ms,
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            raw_data_path=raw_data_path,
            retry_logger=retry_logger,
        )
    raise RuntimeError(f"Unsupported provider: {provider}")
