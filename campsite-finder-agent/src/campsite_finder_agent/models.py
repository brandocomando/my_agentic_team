from __future__ import annotations

import calendar
from datetime import date, timedelta
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Weekday(StrEnum):
    monday = "Monday"
    tuesday = "Tuesday"
    wednesday = "Wednesday"
    thursday = "Thursday"
    friday = "Friday"
    saturday = "Saturday"
    sunday = "Sunday"


class Provider(StrEnum):
    recreation_gov = "recreation.gov"
    reserve_california = "reservecalifornia"
    outdoorithm = "outdoorithm"


class CampgroundConfig(BaseModel):
    name: str
    url: HttpUrl
    provider: Provider | None = None
    facility_id: str | None = None
    outdoorithm_id: str | None = None


RELATIVE_DATE_RE = re.compile(r"^([+-]\d+)\s*([a-zA-Z]+)$")


class DateWindow(BaseModel):
    start: date
    end: date
    nights: int = Field(gt=0)
    check_in_weekdays: list[Weekday] = Field(default_factory=list)

    @field_validator("start", "end", mode="before")
    @classmethod
    def resolve_friendly_date(cls, value: object) -> object:
        return resolve_config_date(value)

    @field_validator("end")
    @classmethod
    def end_must_be_after_start(cls, value: date, info) -> date:
        start = info.data.get("start")
        if start and value < start:
            raise ValueError("end must be on or after start")
        return value


def resolve_config_date(value: object, today: date | None = None) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower().replace(" ", "")
    current = today or date.today()
    if normalized == "today":
        return current
    if normalized == "tomorrow":
        return current + timedelta(days=1)
    match = RELATIVE_DATE_RE.match(normalized)
    if not match:
        return value
    amount = int(match.group(1))
    unit = match.group(2)
    if unit in {"d", "day", "days"}:
        return current + timedelta(days=amount)
    if unit in {"w", "week", "weeks"}:
        return current + timedelta(weeks=amount)
    if unit in {"m", "mo", "mon", "month", "months"}:
        return add_months(current, amount)
    return value


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class SiteFilters(BaseModel):
    site_types: list[str] = Field(default_factory=list)
    site_type_exclude: list[str] = Field(default_factory=list)
    equipment: str | None = None
    min_vehicle_length: int | None = None
    accessible: bool | None = None
    loops: list[str] = Field(default_factory=list)

    def merged_with(self, other: "SiteFilters") -> "SiteFilters":
        return SiteFilters(
            site_types=merge_unique(self.site_types, other.site_types),
            site_type_exclude=merge_unique(self.site_type_exclude, other.site_type_exclude),
            equipment=other.equipment or self.equipment,
            min_vehicle_length=other.min_vehicle_length if other.min_vehicle_length is not None else self.min_vehicle_length,
            accessible=other.accessible if other.accessible is not None else self.accessible,
            loops=merge_unique(self.loops, other.loops),
        )


class DiscoveryConfig(BaseModel):
    states: list[str] = Field(default_factory=list)
    name_exclude: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    radius_miles: float | None = Field(default=None, gt=0)
    camping_type: str | None = None
    min_price_per_night: float | None = Field(default=None, ge=0)
    max_price_per_night: float | None = Field(default=None, ge=0)
    requires_potable_water: bool | None = None
    requires_showers: bool | None = None
    requires_flush_toilets: bool | None = None
    requires_electric_hookups: bool | None = None
    requires_water_hookups: bool | None = None
    requires_dump_station: bool | None = None
    pets_allowed: bool | None = None
    greenbook_safe: bool | None = None
    min_greenbook_vibe: float | None = Field(default=None, ge=0)
    min_review_count: int | None = Field(default=None, ge=0)
    min_avg_sentiment: float | None = Field(default=None, ge=0)
    limit: int = Field(default=50, gt=0)

    def has_criteria(self) -> bool:
        return self != self.__class__()


def merge_unique(first: list[str], second: list[str]) -> list[str]:
    merged: list[str] = []
    for value in [*first, *second]:
        if value not in merged:
            merged.append(value)
    return merged


class AlertConfig(BaseModel):
    methods: list[str] = Field(default_factory=lambda: ["terminal"])


class AIPreferences(BaseModel):
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    must_haves: list[str] = Field(default_factory=list)
    nice_to_haves: list[str] = Field(default_factory=list)
    notes: str = ""


class SearchConfig(BaseModel):
    name: str
    campground: CampgroundConfig
    date_window: DateWindow
    filters: SiteFilters = Field(default_factory=SiteFilters)
    alert: AlertConfig = Field(default_factory=AlertConfig)
    preferences: AIPreferences = Field(default_factory=AIPreferences)
    require_login: bool = True


class SearchSetConfig(BaseModel):
    name: str
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    campground_ids: list[str] = Field(default_factory=list)
    exclude_campground_ids: list[str] = Field(default_factory=list)
    availability: DateWindow
    filters: SiteFilters = Field(default_factory=SiteFilters)
    alert: AlertConfig = Field(default_factory=AlertConfig)
    preferences: AIPreferences = Field(default_factory=AIPreferences)


class AppConfig(BaseModel):
    filters: SiteFilters = Field(default_factory=SiteFilters)
    searches: list[SearchConfig] = Field(default_factory=list)
    search_sets: list[SearchSetConfig] = Field(default_factory=list)


class Campsite(BaseModel):
    campsite_id: str
    name: str
    site_type: str = ""
    loop: str = ""
    type_of_use: str = ""
    equipment: str = ""
    max_vehicle_length: int | None = None
    accessible: bool | None = None
    availabilities: dict[date, str] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class Match(BaseModel):
    search_name: str
    campground_id: str = ""
    campground_name: str
    campground_url: str
    campsite_id: str
    campsite_name: str
    check_in: date
    check_out: date
    nights: int
    site_type: str = ""
    loop: str = ""
    availability: list[str]


class MatchWindow(BaseModel):
    state_key: str = ""
    search_names: list[str]
    campground_id: str = ""
    campground_name: str
    campground_url: str
    check_in_window_start: date
    check_in_window_end: date
    earliest_check_out: date
    latest_check_out: date
    nights: int
    representative_campsite_id: str
    representative_campsite_name: str
    representative_site_type: str = ""
    representative_loop: str = ""
    matching_campsite_ids: list[str] = Field(default_factory=list)
    ai_score: float | None = None
    ai_fit: str = ""
    ai_reasons: list[str] = Field(default_factory=list)
    ai_concerns: list[str] = Field(default_factory=list)
    ai_summary: str = ""
    suggested_state_action: str = ""
    suggested_state_reason: str = ""
    matching_start_count: int
    unique_site_count: int
