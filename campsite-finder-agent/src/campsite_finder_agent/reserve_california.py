from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
import re
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from campsite_finder_agent.availability import (
    campground_id_for_search,
    candidate_check_ins,
    campsite_matches_filters,
    merge_campsites,
)
from campsite_finder_agent.browser import require_playwright
from campsite_finder_agent.models import Campsite, Match, SearchConfig


RESERVE_CALIFORNIA_GRID_BATCH_DAYS = 21


@dataclass(frozen=True)
class ReserveCaliforniaLock:
    campsite_id: str
    campsite_name: str
    short_name: str
    date: date
    lock_at: str
    is_free: bool
    is_blocked: bool
    reservation_id: int
    site_type: str = ""
    max_vehicle_length: int | None = None
    accessible: bool | None = None
    raw: dict | None = None


@dataclass(frozen=True)
class ReserveCaliforniaGetSiteResult:
    action: str
    attempts: int
    states: list[dict[str, str]]
    book_now_clicked: bool = False
    popup_ok_clicked: bool = False
    reserve_unit_clicked: bool = False
    details: dict[str, object] | None = None


def fetch_campsites_for_search(
    search: SearchConfig,
    cdp_url: str,
    login_timeout_ms: int,
    request_delay_seconds: float = 2.5,
) -> list[Campsite]:
    place_id, facility_id = reserve_california_ids_from_url(str(search.campground.url))
    if not place_id or not facility_id:
        raise RuntimeError(
            f"Could not infer ReserveCalifornia place/facility ids from {search.campground.url}. "
            "Expected a URL like https://www.reservecalifornia.com/park/707/662."
        )
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        if search.require_login:
            page.bring_to_front()
            page.goto(str(search.campground.url), wait_until="domcontentloaded")
            _wait_for_reserve_california_page(page)
            wait_for_reserve_california_login(page, login_timeout_ms)
        try:
            campsites = fetch_grid_campsites(page, search, facility_id, request_delay_seconds)
        except Exception as exc:
            print(f"ReserveCalifornia grid API failed, falling back to visible-page scan: {exc}")
            page.bring_to_front()
            page.goto(str(search.campground.url), wait_until="domcontentloaded")
            _wait_for_reserve_california_page(page)
            if search.require_login:
                wait_for_reserve_california_login(page, login_timeout_ms)
            campsites = fetch_visible_campsites_by_date(page, search, request_delay_seconds)
        browser.close()
    return campsites


def fetch_locked_campsites(
    cdp_url: str,
    park_url: str,
    start: date,
    end: date,
    site_names: set[str] | None = None,
) -> list[ReserveCaliforniaLock]:
    _, facility_id = reserve_california_ids_from_url(park_url)
    if not facility_id:
        raise RuntimeError(
            f"Could not infer ReserveCalifornia facility id from {park_url}. "
            "Expected a URL like https://www.reservecalifornia.com/park/707/662."
        )
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        locks_by_batch: list[ReserveCaliforniaLock] = []
        for batch_start, batch_end in grid_date_batches(start, end):
            payload = reserve_california_grid_payload(facility_id, batch_start, batch_end)
            response = page.context.request.post(
                "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid",
                data=payload,
                headers={"content-type": "application/json"},
            )
            if not response.ok:
                raise RuntimeError(
                    f"grid API returned {response.status} for {batch_start.isoformat()} to {batch_end.isoformat()}"
                )
            locks_by_batch.extend(parse_grid_locks(response.json(), site_names=site_names))
        browser.close()
    return locks_by_batch


def get_reserve_california_site(
    cdp_url: str,
    park_url: str,
    site: str,
    start_date: date,
    nights: int,
    refresh_window_start: str = "07:59:30",
    refresh_window_end: str = "08:01:00",
    timezone_name: str = "America/Los_Angeles",
    refresh_interval_seconds: float = 1.0,
    click_book_now: bool = True,
    max_run_seconds: float | None = None,
    adults: int = 2,
    children: int = 2,
    occupant_name: str = "",
    camping_unit: str = "Trailer",
    trailer_length_feet: float | None = None,
    street_1: str = "",
    city: str = "",
    state: str = "",
    postal_code: str = "",
    click_reserve_unit: bool = True,
) -> ReserveCaliforniaGetSiteResult:
    sync_playwright = require_playwright()
    timezone = ZoneInfo(timezone_name)
    window_start = _today_at_time(refresh_window_start, timezone)
    window_end = _today_at_time(refresh_window_end, timezone)
    now = datetime.now(timezone)
    if window_end < window_start:
        window_end += timedelta(days=1)
    if now > window_end:
        window_start = now
        window_end = now + timedelta(seconds=90)
    if max_run_seconds is not None:
        capped_end = max(now, window_start) + timedelta(seconds=max_run_seconds)
        window_end = min(window_end, capped_end)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        page.bring_to_front()
        if park_url and not _same_reserve_california_park_url(page.url, park_url):
            page.goto(park_url, wait_until="domcontentloaded")
            _wait_for_reserve_california_page(page)
        set_result = set_reserve_california_search_dates(page, start_date - timedelta(days=1), 1)

        print(
            f"Armed ReserveCalifornia get-site for site {site} on {start_date.isoformat()}; "
            f"refresh window {window_start:%H:%M:%S} -> {window_end:%H:%M:%S} {timezone_name}; "
            f"date picker: {set_result}."
        )
        while datetime.now(timezone) < window_start:
            time.sleep(min(1.0, (window_start - datetime.now(timezone)).total_seconds()))

        attempts = 0
        last_states: list[dict[str, str]] = []
        while datetime.now(timezone) <= window_end:
            attempts += 1
            # The in-page refresh can retain stale release availability.
            page.reload(wait_until="domcontentloaded")
            set_reserve_california_search_dates(page, start_date - timedelta(days=1), 1)
            if datetime.now(timezone) > window_end:
                break
            result = page.evaluate(
                """
                async ({
                  site,
                  startDate,
                  nights,
                  clickBookNow,
                  adults,
                  children,
                  occupantName,
                  campingUnit,
                  trailerLengthFeet,
                  clickReserveUnit,
                }) => {
                  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                  const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
                  const normalizeSite = (value) => norm(value)
                    .toLowerCase()
                    .replace(/^premium\\s+/, "")
                    .replace(/^standard\\s+/, "")
                    .replace(/^hook\\s*up\\s+/, "")
                    .replace(/^campsite\\s*#?\\s*/, "")
                    .replace(/^site\\s*#?\\s*/, "")
                    .replace(/^#/, "");
                  const wantedSite = normalizeSite(site);
                  const siteFromLabel = (value) => {
                    const clean = norm(value);
                    const match = clean.match(/(?:premium\\s+|standard\\s+|hook\\s*up\\s+)?(?:campsite|site)\\s*#?\\s*([A-Za-z0-9-]+)/i);
                    return match ? normalizeSite(match[1]) : normalizeSite(clean);
                  };
                  const [year, month, day] = startDate.split("-");
                  const targetDate = `${month}/${day}/${year}`;
                  const setNativeValue = (element, value) => {
                    const setter = Object.getOwnPropertyDescriptor(element.constructor.prototype, "value")?.set;
                    setter ? setter.call(element, value) : element.value = value;
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                  };
                  const selectOption = (selector, wanted, { numericSmallest = false } = {}) => {
                    const select = document.querySelector(selector);
                    if (!select) return { ok: false, reason: `${selector} not found` };
                    let option = [...select.options].find((candidate) => (
                      norm(candidate.text).toLowerCase() === String(wanted).toLowerCase()
                      || String(candidate.value) === String(wanted)
                    ));
                    if (!option && numericSmallest) {
                      const numericOptions = [...select.options]
                        .map((candidate) => ({
                          option: candidate,
                          number: Number((candidate.text.match(/\\d+/) || candidate.value.match(/\\d+/) || [])[0]),
                          text: norm(candidate.text).toLowerCase(),
                        }))
                        .filter((item) => Number.isFinite(item.number) && !item.text.includes("no vehicle"));
                      numericOptions.sort((a, b) => a.number - b.number);
                      option = numericOptions[0]?.option;
                    }
                    if (!option) return { ok: false, reason: `${selector} has no option ${wanted}` };
                    select.value = option.value;
                    select.dispatchEvent(new Event("input", { bubbles: true }));
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return { ok: true, text: norm(option.text), value: option.value };
                  };
                  const selectVehicleLength = (selector, trailerLength) => {
                    const select = document.querySelector(selector);
                    if (!select) return { ok: false, reason: `${selector} not found` };
                    const options = [...select.options]
                      .map((option) => {
                        const text = norm(option.text);
                        const lower = text.toLowerCase();
                        const numbers = [...text.matchAll(/\\d+(?:\\.\\d+)?/g)].map((match) => Number(match[0]));
                        const capacity = numbers.length ? Math.max(...numbers) : Number.NaN;
                        return { option, text, value: option.value, lower, capacity };
                      })
                      .filter((item) => Number.isFinite(item.capacity) && !item.lower.includes("no vehicle"));
                    if (!options.length) return { ok: false, reason: "no numeric vehicle length options" };
                    options.sort((a, b) => a.capacity - b.capacity);
                    const length = Number(trailerLength);
                    const selected = Number.isFinite(length)
                      ? options.find((item) => item.capacity >= length)
                      : options[0];
                    if (!selected) {
                      return {
                        ok: false,
                        reason: `no vehicle length option fits ${trailerLength} ft`,
                        options: options.map((item) => item.text),
                      };
                    }
                    select.value = selected.value;
                    select.dispatchEvent(new Event("input", { bubbles: true }));
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return {
                      ok: true,
                      text: selected.text,
                      value: selected.value,
                      trailerLengthFeet: Number.isFinite(length) ? length : null,
                      capacityFeet: selected.capacity,
                    };
                  };
                  const clickPopupOk = async () => {
                    for (let okIndex = 0; okIndex < 30; okIndex += 1) {
                      const okButton = document.querySelector("#alertOkBtn")
                        || [...document.querySelectorAll("[role='dialog'] button, .modal button")]
                          .find((candidate) => /^ok$/i.test(norm(candidate.textContent)));
                      const okDisabled = !okButton || okButton.disabled
                        || okButton.hasAttribute("disabled")
                        || okButton.getAttribute("aria-disabled") === "true";
                      if (!okDisabled) {
                        okButton.scrollIntoView({ block: "center", inline: "center" });
                        await wait(30);
                        okButton.click();
                        await wait(300);
                        return true;
                      }
                      await wait(100);
                    }
                    return false;
                  };
                  const completeReservationDetails = async () => {
                    for (let index = 0; index < 50; index += 1) {
                      if (document.querySelector("#preCart_Arrival_Date") && document.querySelector("#preCart_Night")) break;
                      await wait(100);
                    }
                    const arrival = document.querySelector("#preCart_Arrival_Date");
                    const nightSelect = document.querySelector("#preCart_Night");
                    const foundArrival = norm(arrival?.value);
                    const foundNights = norm(nightSelect?.value);
                    if (foundArrival !== targetDate || foundNights !== String(nights)) {
                      return {
                        action: "details-validation-failed",
                        arrival: foundArrival,
                        expectedArrival: targetDate,
                        nights: foundNights,
                        expectedNights: String(nights),
                      };
                    }

                    const addVehicle = [...document.querySelectorAll("button")]
                      .find((button) => /add vehicle/i.test(norm(button.textContent)) && !button.disabled);
                    if (addVehicle) {
                      addVehicle.scrollIntoView({ block: "center", inline: "center" });
                      await wait(30);
                      addVehicle.click();
                      await wait(300);
                    }
                    const vehicleLength = selectVehicleLength("#precart_pad_length", trailerLengthFeet);
                    if (!vehicleLength.ok) {
                      return {
                        action: "details-validation-failed",
                        arrival: foundArrival,
                        expectedArrival: targetDate,
                        nights: foundNights,
                        expectedNights: String(nights),
                        vehicleLength,
                      };
                    }
                    const adultSelection = selectOption("#precart_Adults", adults);
                    const childSelection = selectOption("#precart_Children", children);
                    const nameInput = document.querySelector("#precart_Occupant_Name");
                    const resolvedOccupantName = occupantName || norm(document.querySelector(".user-name, .profile-name")?.textContent)
                      || norm([...document.querySelectorAll("a, button, span, div")]
                        .map((element) => element.textContent)
                        .find((text) => /^[A-Z][A-Z\\s'-]{1,40}$/.test(norm(text)))) || "";
                    if (nameInput && resolvedOccupantName) setNativeValue(nameInput, resolvedOccupantName);
                    const campingSelection = selectOption("#precart_camping", campingUnit);
                    const terms = document.querySelector("#receiveCheckBox");
                    if (terms && !terms.checked) {
                      terms.scrollIntoView({ block: "center", inline: "center" });
                      await wait(30);
                      terms.click();
                      terms.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                    const reserveButton = document.querySelector("#precart_sumbit_btn");
                    const reserveReady = reserveButton && !reserveButton.disabled && !reserveButton.hasAttribute("disabled");
                    const clickGoToCheckout = async () => {
                      const findCheckout = () => [...document.querySelectorAll("button, a, [role='button']")]
                        .find((element) => {
                          const text = norm(element.textContent || element.getAttribute("aria-label") || "");
                          const visible = !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
                          const disabled = element.disabled || element.hasAttribute("disabled")
                            || element.getAttribute("aria-disabled") === "true";
                          return visible && !disabled && /go\\s*to\\s*checkout/i.test(text);
                        });
                      let clicks = 0;
                      for (let attempt = 0; attempt < 2; attempt += 1) {
                        for (let index = 0; index < 50; index += 1) {
                          const checkout = findCheckout();
                          if (checkout) {
                            checkout.scrollIntoView({ block: "center", inline: "center" });
                            await wait(40);
                            checkout.click();
                            clicks += 1;
                            await wait(700);
                            break;
                          }
                          await wait(100);
                        }
                      }
                      return clicks;
                    };
                    if (clickReserveUnit && reserveReady) {
                      reserveButton.scrollIntoView({ block: "center", inline: "center" });
                      await wait(30);
                      reserveButton.click();
                      const goToCheckoutClicks = await clickGoToCheckout();
                      return {
                        action: goToCheckoutClicks > 0 ? "reserve-unit-and-go-to-checkout-clicked" : "reserve-unit-clicked",
                        arrival: foundArrival,
                        nights: foundNights,
                        vehicleLength,
                        adults: adultSelection,
                        children: childSelection,
                        occupantName: resolvedOccupantName,
                        campingUnit: campingSelection,
                        termsChecked: !!terms?.checked,
                        goToCheckoutClicks,
                      };
                    }
                    return {
                      action: "details-filled",
                      arrival: foundArrival,
                      nights: foundNights,
                      vehicleLength,
                      adults: adultSelection,
                      children: childSelection,
                      occupantName: resolvedOccupantName,
                      campingUnit: campingSelection,
                      termsChecked: !!terms?.checked,
                      reserveReady: !!reserveReady,
                    };
                  };
                  const cells = [...document.querySelectorAll("a.unit-slice, a[aria-label], a[title]")]
                    .filter((element) => {
                      const label = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""}`;
                      return label.includes(targetDate) && siteFromLabel(label) === wantedSite;
                    });
                  const states = cells.map((element) => ({
                    text: element.getAttribute("aria-label") || element.getAttribute("title") || norm(element.textContent),
                    cls: String(element.className || ""),
                    href: element.href || "",
                  }));
                  const selectable = cells.find((element) => {
                    const label = (
                      `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""} ${element.className || ""}`
                    ).toLowerCase();
                    return !/not available|not-available|booked|locked|outside|drawing|walk-in/.test(label);
                  });
                  if (selectable) {
                    selectable.scrollIntoView({ block: "center", inline: "center" });
                    await wait(25);
                    selectable.click();
                    let durationReady = false;
                    for (let index = 0; index < 30; index += 1) {
                      const duration = document.querySelector("#nights-select");
                      const option = duration && [...duration.options].find((item) => (
                        item.value === String(nights) && !item.disabled
                      ));
                      if (duration && !duration.disabled && option) {
                        setNativeValue(duration, String(nights));
                        await wait(250);
                        durationReady = document.querySelector("#nights-select")?.value === String(nights);
                        if (durationReady) break;
                      }
                      await wait(100);
                    }
                    if (!durationReady) {
                      return { action: "requested-nights-unavailable", states, bookNowClicked: false };
                    }
                    if (!clickBookNow) {
                      return { action: "clicked-site-cell", states, bookNowClicked: false };
                    }
                    for (let index = 0; index < 30; index += 1) {
                      const button = document.querySelector("#checkout-button");
                      const disabled = !button || button.disabled || button.getAttribute("aria-disabled") === "true"
                        || button.hasAttribute("disabled");
                      if (!disabled && document.querySelector("#nights-select")?.value === String(nights)) {
                        button.scrollIntoView({ block: "center", inline: "center" });
                        await wait(30);
                        button.click();
                        const popupOkClicked = await clickPopupOk();
                        const details = await completeReservationDetails();
                        return {
                          action: details.action,
                          states,
                          bookNowClicked: true,
                          popupOkClicked,
                          details,
                        };
                      }
                      await wait(100);
                    }
                    return { action: "clicked-site-cell-book-now-not-ready", states, bookNowClicked: false };
                  }
                  return { action: "waiting-for-availability", states, bookNowClicked: false };
                }
                """,
                {
                    "site": str(site),
                    "startDate": start_date.isoformat(),
                    "nights": nights,
                    "clickBookNow": click_book_now,
                    "adults": adults,
                    "children": children,
                    "occupantName": occupant_name,
                    "campingUnit": camping_unit,
                    "trailerLengthFeet": trailer_length_feet,
                    "clickReserveUnit": click_reserve_unit,
                },
            )
            action = str(result.get("action"))
            last_states = result.get("states") or []
            print(f"{datetime.now(timezone):%H:%M:%S} {action}: {_summarize_get_site_states(last_states)}")
            if action.startswith("clicked-site-cell") or action in {
                "details-filled",
                "requested-nights-unavailable",
                "details-validation-failed",
                "reserve-unit-clicked",
                "reserve-unit-and-go-to-checkout-clicked",
            }:
                details = result.get("details")
                if (
                    action == "reserve-unit-and-go-to-checkout-clicked"
                    and all(value.strip() for value in (street_1, city, state, postal_code))
                ):
                    checkout_address = fill_reserve_california_checkout_address(
                        page,
                        street_1=street_1,
                        city=city,
                        state=state,
                        postal_code=postal_code,
                    )
                    details = details if isinstance(details, dict) else {}
                    details = {**details, "checkoutAddress": checkout_address}
                browser.close()
                return ReserveCaliforniaGetSiteResult(
                    action=action,
                    attempts=attempts,
                    states=last_states,
                    book_now_clicked=bool(result.get("bookNowClicked")),
                    popup_ok_clicked=bool(result.get("popupOkClicked")),
                    reserve_unit_clicked=action in {"reserve-unit-clicked", "reserve-unit-and-go-to-checkout-clicked"},
                    details=details,
                )
            page.wait_for_timeout(int(refresh_interval_seconds * 1000))
        browser.close()
    return ReserveCaliforniaGetSiteResult(action="timed-out", attempts=attempts, states=last_states)


def fill_reserve_california_checkout_address(
    page,
    street_1: str,
    city: str,
    state: str,
    postal_code: str,
) -> dict[str, object]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    page.wait_for_timeout(1_000)
    deadline = time.monotonic() + 15
    last_result: dict[str, object] = {"action": "checkout-address-frame-not-found"}
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                result = frame.evaluate(
                    """
                    ({ street1, city, state, postalCode }) => {
                  const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
                  const visible = (element) => !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
                  const labelFor = (element) => {
                    const id = element.id || "";
                    const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                    const parent = element.closest("label");
                    const describedBy = element.getAttribute("aria-describedby")
                      ? document.getElementById(element.getAttribute("aria-describedby"))?.innerText
                      : "";
                    return norm([
                      id,
                      element.getAttribute("name"),
                      element.getAttribute("placeholder"),
                      element.getAttribute("aria-label"),
                      element.getAttribute("autocomplete"),
                      label?.innerText,
                      parent?.innerText,
                      describedBy,
                    ].filter(Boolean).join(" "));
                  };
                  const controls = [...document.querySelectorAll("input, select, textarea")].filter(visible);
                  const setNativeValue = (element, value) => {
                    const setter = Object.getOwnPropertyDescriptor(element.constructor.prototype, "value")?.set;
                    setter ? setter.call(element, value) : element.value = value;
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                    element.dispatchEvent(new Event("blur", { bubbles: true }));
                  };
                  const findControl = (patterns, excludePatterns = []) => controls.find((control) => {
                    const haystack = labelFor(control).toLowerCase();
                    return patterns.some((pattern) => pattern.test(haystack))
                      && !excludePatterns.some((pattern) => pattern.test(haystack));
                  });
                  const fillInput = (field, value, patterns, excludePatterns = []) => {
                    const control = findControl(patterns, excludePatterns);
                    if (!control) return { field, ok: false, reason: "not found" };
                    setNativeValue(control, value);
                    return { field, ok: true, tag: control.tagName.toLowerCase(), id: control.id || "", name: control.getAttribute("name") || "" };
                  };
                  const selectState = () => {
                    const control = findControl(
                      [/\\bstate\\b/, /province/, /region/],
                      [/statement/, /card/, /expiration/, /status/],
                    );
                    if (!control) return { field: "state", ok: false, reason: "not found" };
                    if (control.tagName === "SELECT") {
                      const wanted = state.toLowerCase();
                      const option = [...control.options].find((candidate) => (
                        norm(candidate.value).toLowerCase() === wanted
                        || norm(candidate.text).toLowerCase() === wanted
                      ));
                      if (!option) return { field: "state", ok: false, reason: `no option ${state}` };
                      control.value = option.value;
                      control.dispatchEvent(new Event("input", { bubbles: true }));
                      control.dispatchEvent(new Event("change", { bubbles: true }));
                      return { field: "state", ok: true, tag: "select", id: control.id || "", name: control.getAttribute("name") || "", text: norm(option.text), value: option.value };
                    }
                    setNativeValue(control, state);
                    return { field: "state", ok: true, tag: control.tagName.toLowerCase(), id: control.id || "", name: control.getAttribute("name") || "" };
                  };
                  const results = [
                    fillInput("street_1", street1, [/street.*1/, /address.*1/, /address line 1/, /billing address/, /\\baddress\\b/], [/street.*2/, /address.*2/, /line 2/]),
                    fillInput("city", city, [/\\bcity\\b/, /locality/]),
                    selectState(),
                    fillInput("postal_code", postalCode, [/postal/, /zip/, /zipcode/, /post code/]),
                  ];
                  const filled = results.filter((result) => result.ok).length;
                  return {
                    action: filled === results.length
                      ? "checkout-address-filled"
                      : filled
                        ? "checkout-address-partially-filled"
                        : "checkout-address-fields-not-found",
                    filled,
                    expected: results.length,
                    results,
                  };
                }
                """,
                    {
                        "street1": street_1,
                        "city": city,
                        "state": state,
                        "postalCode": postal_code,
                    },
                )
            except Exception as exc:
                last_result = {"action": "checkout-address-frame-error", "error": str(exc)}
                continue
            if result.get("filled") == result.get("expected"):
                return result
            last_result = result
        page.wait_for_timeout(500)
    return last_result


def reserve_california_ids_from_url(url: str) -> tuple[str | None, str | None]:
    match = re.search(r"/park/(\d+)/(\d+)", urlparse(url).path)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _same_reserve_california_park_url(current_url: str, park_url: str) -> bool:
    current = urlparse(current_url)
    target = urlparse(park_url)
    return current.netloc == target.netloc and current.path.rstrip("/") == target.path.rstrip("/")


def set_reserve_california_search_dates(page, start_date: date, nights: int) -> str:
    page.wait_for_function(
        """
        () => {
          const button = document.querySelector("#custom-datepicker-calendar") || document.querySelector(".mobile-input");
          const text = document.body?.innerText || "";
          return button && /Search Results|Site List|Rental Type|Nights?/i.test(text);
        }
        """,
        timeout=30_000,
    )
    end_date = start_date + timedelta(days=nights)
    result = page.evaluate(
        """
        async ({ startDate, endDate, nights }) => {
          const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const norm = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const parseIso = (value) => {
            const [year, month, day] = value.split("-").map(Number);
            return new Date(year, month - 1, day);
          };
          const monthName = (date) => date.toLocaleString("en-US", { month: "long" });
          const shortMonth = (date) => date.toLocaleString("en-US", { month: "short" });
          const shortWeekday = (date) => date.toLocaleString("en-US", { weekday: "short" });
          const summaryFor = (date) => `${shortWeekday(date)}, ${shortMonth(date)} ${date.getDate()}`;
          const nightLabel = Number(nights) === 1 ? "Night" : "Nights";
          const expectedSummary = `${nights}${nightLabel}${summaryFor(parseIso(startDate))} - ${summaryFor(parseIso(endDate))}`;
          const currentSummary = () => norm(
            document.querySelector("#custom-datepicker-calendar")?.textContent
            || document.querySelector(".mobile-input")?.textContent
            || ""
          );
          if (currentSummary().replace(/\\s+/g, "") === expectedSummary.replace(/\\s+/g, "")) {
            return { action: "already-set", summary: currentSummary() };
          }

          const findDay = (iso) => {
            const date = parseIso(iso);
            const monthLabel = `Month ${monthName(date)}, ${date.getFullYear()}`;
            const month = [...document.querySelectorAll(".react-datepicker__month")]
              .find((element) => element.getAttribute("aria-label") === monthLabel);
            if (!month) return null;
            return [...month.querySelectorAll(".react-datepicker__day[role='gridcell']")]
              .find((element) => {
                const disabled = element.getAttribute("aria-disabled") === "true"
                  || element.className.includes("react-datepicker__day--disabled");
                const outside = element.className.includes("react-datepicker__day--outside-month");
                return !disabled && !outside && norm(element.textContent) === String(date.getDate());
              });
          };
          const chooseRange = async () => {
            const pickerButton = document.querySelector("#custom-datepicker-calendar") || document.querySelector(".mobile-input");
            if (!pickerButton) return { ok: false, startFound: false, endFound: false, reason: "picker button not found" };
            pickerButton.scrollIntoView({ block: "center", inline: "center" });
            await wait(50);
            if (!document.querySelector(".react-datepicker__month")) pickerButton.click();
            for (let index = 0; index < 50; index += 1) {
              if (document.querySelector(".react-datepicker__month")) break;
              await wait(100);
            }
            const start = findDay(startDate);
            if (!start) return { ok: false, startFound: false, endFound: false };
            start.click();
            await wait(250);
            const end = findDay(endDate);
            if (!end) return { ok: false, startFound: true, endFound: false };
            end.click();
            await wait(800);
            return { ok: true, startFound: true, endFound: true };
          };
          let chosen = await chooseRange();
          if (!chosen.ok) {
            return { action: "date-cell-not-found", ...chosen, summary: currentSummary() };
          }
          let afterSummary = currentSummary();
          let matches = afterSummary.replace(/\\s+/g, "") === expectedSummary.replace(/\\s+/g, "");
          if (!matches) {
            chosen = await chooseRange();
            if (!chosen.ok) {
              return { action: "date-cell-not-found", ...chosen, summary: currentSummary() };
            }
            afterSummary = currentSummary();
            matches = afterSummary.replace(/\\s+/g, "") === expectedSummary.replace(/\\s+/g, "");
          }
          const refresh = document.querySelector("button.refresh-btn.btn");
          if (refresh) {
            refresh.click();
            await wait(800);
          }
          return {
            action: matches ? "set" : "set-summary-mismatch",
            expectedSummary,
            summary: afterSummary,
          };
        }
        """,
        {"startDate": start_date.isoformat(), "endDate": end_date.isoformat(), "nights": nights},
    )
    action = str(result.get("action"))
    if action in {"date-cell-not-found", "set-summary-mismatch"}:
        raise RuntimeError(f"Could not set ReserveCalifornia date picker: {result}")
    summary = str(result.get("summary") or "")
    return f"{action} ({summary})"


def _today_at_time(value: str, timezone: ZoneInfo) -> datetime:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", value.strip())
    if not match:
        raise RuntimeError(f"Expected time as HH:MM or HH:MM:SS, got {value!r}.")
    return datetime.now(timezone).replace(
        hour=int(match.group(1)),
        minute=int(match.group(2)),
        second=int(match.group(3) or "0"),
        microsecond=0,
    )


def _summarize_get_site_states(states: list[dict[str, str]]) -> str:
    if not states:
        return "no matching site cell"
    return " | ".join(f"{state.get('text', '')} [{state.get('cls', '')}]" for state in states)


def fetch_grid_campsites(page, search: SearchConfig, facility_id: str, request_delay_seconds: float) -> list[Campsite]:
    batches = grid_date_batches(search.date_window.start, search.date_window.end)
    campsites_by_batch: list[list[Campsite]] = []
    for index, (start, end) in enumerate(batches):
        print(f"ReserveCalifornia grid search {index + 1}/{len(batches)}: {start.isoformat()} to {end.isoformat()}")
        if index > 0 and request_delay_seconds > 0:
            page.wait_for_timeout(int(request_delay_seconds * 1000))
        payload = reserve_california_grid_payload(facility_id, start, end)
        response = page.context.request.post(
            "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid",
            data=payload,
            headers={"content-type": "application/json"},
        )
        if not response.ok:
            raise RuntimeError(f"grid API returned {response.status} for {start.isoformat()} to {end.isoformat()}")
        campsites_by_batch.append(parse_grid_campsites(response.json()))
    return merge_campsites(campsites_by_batch)


def reserve_california_grid_payload(facility_id: str, start: date, end: date) -> dict[str, object]:
    return {
        "FacilityId": facility_id,
        "UnitSort": "availability",
        "StartDate": start.isoformat(),
        "EndDate": end.isoformat(),
        "InSeasonOnly": True,
        "WebOnly": True,
        "MaxDate": f"{end.isoformat()}T00:00:00",
        "MinDate": f"{start.isoformat()}T00:00:00",
        "IsADA": False,
        "RestrictADA": False,
        "UnitCategoryId": 0,
        "SleepingUnitId": 0,
        "MinVehicleLength": 0,
        "UnitTypesGroupIds": [],
        "AmenityIds": [],
        "CustomerId": 0,
        "customerClassificationId": 0,
    }


def grid_date_batches(
    start: date,
    end: date,
    days: int = RESERVE_CALIFORNIA_GRID_BATCH_DAYS,
) -> list[tuple[date, date]]:
    batches: list[tuple[date, date]] = []
    current = start
    while current <= end:
        batch_end = min(current + timedelta(days=days - 1), end)
        batches.append((current, batch_end))
        current = batch_end + timedelta(days=1)
    return batches


def parse_grid_campsites(payload: dict) -> list[Campsite]:
    units = (payload.get("Facility") or {}).get("Units") or {}
    campsites: list[Campsite] = []
    for key, unit in units.items():
        if not isinstance(unit, dict):
            continue
        campsite_id = str(unit.get("UnitId") or key)
        availabilities = {}
        for raw_day, raw_slice in (unit.get("Slices") or {}).items():
            parsed_day = parse_grid_date(raw_day)
            if not parsed_day or not isinstance(raw_slice, dict):
                continue
            if raw_slice.get("IsFree") is True and raw_slice.get("IsBlocked") is not True:
                availabilities[parsed_day] = "Available"
            else:
                availabilities[parsed_day] = "Unavailable"
        campsites.append(
            Campsite(
                campsite_id=campsite_id,
                name=str(unit.get("Name") or unit.get("ShortName") or campsite_id),
                site_type=str(unit.get("UnitTypeId") or ""),
                max_vehicle_length=_parse_optional_int(unit.get("VehicleLength")),
                accessible=unit.get("IsAda") if isinstance(unit.get("IsAda"), bool) else None,
                availabilities=availabilities,
                raw={"provider": "reservecalifornia", "grid_key": key, "unit": unit},
            )
        )
    return campsites


def parse_grid_locks(payload: dict, site_names: set[str] | None = None) -> list[ReserveCaliforniaLock]:
    wanted = {_normalize_site_name(site_name) for site_name in site_names or set()}
    units = (payload.get("Facility") or {}).get("Units") or {}
    locks: list[ReserveCaliforniaLock] = []
    for key, unit in units.items():
        if not isinstance(unit, dict):
            continue
        campsite_id = str(unit.get("UnitId") or key)
        campsite_name = str(unit.get("Name") or unit.get("ShortName") or campsite_id)
        short_name = str(unit.get("ShortName") or "")
        aliases = {
            _normalize_site_name(campsite_id),
            _normalize_site_name(campsite_name),
            _normalize_site_name(short_name),
        }
        if wanted and not aliases.intersection(wanted):
            continue
        for raw_day, raw_slice in (unit.get("Slices") or {}).items():
            parsed_day = parse_grid_date(raw_day)
            if not parsed_day or not isinstance(raw_slice, dict):
                continue
            lock_at = str(raw_slice.get("Lock") or "")
            if not lock_at:
                continue
            locks.append(
                ReserveCaliforniaLock(
                    campsite_id=campsite_id,
                    campsite_name=campsite_name,
                    short_name=short_name,
                    date=parsed_day,
                    lock_at=lock_at,
                    is_free=raw_slice.get("IsFree") is True,
                    is_blocked=raw_slice.get("IsBlocked") is True,
                    reservation_id=_parse_optional_int(raw_slice.get("ReservationId")) or 0,
                    site_type=str(unit.get("UnitTypeId") or ""),
                    max_vehicle_length=_parse_optional_int(unit.get("VehicleLength")),
                    accessible=unit.get("IsAda") if isinstance(unit.get("IsAda"), bool) else None,
                    raw={"provider": "reservecalifornia", "unit": unit, "slice": raw_slice},
                )
            )
    return sorted(locks, key=lambda item: (item.campsite_name, item.date))


def find_locked_matches(search: SearchConfig, locks: list[ReserveCaliforniaLock]) -> list[Match]:
    locks_by_site: dict[str, list[ReserveCaliforniaLock]] = {}
    for lock in locks:
        locks_by_site.setdefault(lock.campsite_id, []).append(lock)
    matches: list[Match] = []
    for site_locks in locks_by_site.values():
        first_lock = site_locks[0]
        campsite = Campsite(
            campsite_id=first_lock.campsite_id,
            name=first_lock.campsite_name,
            site_type=first_lock.site_type,
            max_vehicle_length=first_lock.max_vehicle_length,
            accessible=first_lock.accessible,
        )
        if not campsite_matches_filters(campsite, search):
            continue
        locks_by_date = {lock.date: lock for lock in site_locks}
        for check_in in candidate_check_ins(search):
            check_out = check_in + timedelta(days=search.date_window.nights)
            stay_dates = [
                check_in + timedelta(days=offset)
                for offset in range(search.date_window.nights + 1)
            ]
            stay_locks = [locks_by_date.get(day) for day in stay_dates]
            if all(stay_locks):
                matches.append(
                    Match(
                        search_name=search.name,
                        campground_id=campground_id_for_search(search),
                        campground_name=search.campground.name,
                        campground_url=str(search.campground.url),
                        campsite_id=first_lock.campsite_id,
                        campsite_name=first_lock.campsite_name,
                        check_in=check_in,
                        check_out=check_out,
                        nights=search.date_window.nights,
                        site_type=first_lock.site_type,
                        availability=[f"Locked until {lock.lock_at}" for lock in stay_locks if lock],
                        unlock_times=sorted({lock.lock_at for lock in stay_locks if lock}),
                    )
                )
    return matches


def _normalize_site_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^campsite\s*#?\s*", "", normalized)
    normalized = re.sub(r"^site\s*#?\s*", "", normalized)
    normalized = normalized.lstrip("#")
    return normalized


def parse_grid_date(value: str) -> date | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if not match:
        return None
    return date.fromisoformat(match.group(1))


def fetch_visible_campsites_by_date(page, search: SearchConfig, request_delay_seconds: float) -> list[Campsite]:
    check_ins = candidate_check_ins(search)
    campsites_by_date: list[list[Campsite]] = []
    for index, check_in in enumerate(check_ins):
        print(f"ReserveCalifornia date search {index + 1}/{len(check_ins)}: {check_in.isoformat()}")
        if index > 0 and request_delay_seconds > 0:
            page.wait_for_timeout(int(request_delay_seconds * 1000))
        _try_set_search_dates(page, search, check_in)
        page.wait_for_timeout(2_000)
        campsites_by_date.append(extract_visible_campsites(page, search, check_in))
    return merge_campsites(campsites_by_date)


def _parse_optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def capture_reserve_california_network(cdp_url: str, wait_ms: int = 8_000) -> list[dict[str, object]]:
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = _find_reserve_california_page(browser)
        captured: list[dict[str, object]] = []

        def on_response(response) -> None:
            url = response.url
            if not re.search(r"/rdr/|rdapi|avail|grid|place|facility|unit", url, re.I):
                return
            try:
                body = response.text()[:5_000]
            except Exception as exc:
                body = f"<body unavailable: {exc}>"
            captured.append(
                {
                    "url": url,
                    "status": response.status,
                    "method": response.request.method,
                    "post_data": response.request.post_data,
                    "content_type": response.headers.get("content-type", ""),
                    "body": body,
                }
            )

        page.on("response", on_response)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        browser.close()
    return captured


def extract_visible_campsites(page, search: SearchConfig, check_in: date) -> list[Campsite]:
    payload = page.evaluate(
        """
        () => {
          const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
          const looksRelevant = (text) => {
            const value = text.toLowerCase();
            return value.includes("available") || value.includes("reserve") || value.includes("site");
          };
          const siteName = (text, index) => {
            const patterns = [
              /(?:site|campsite|unit)\\s*#?\\s*([A-Za-z0-9-]+)/i,
              /\\b([A-Z]?\\d{1,4}[A-Z]?)\\b/
            ];
            for (const pattern of patterns) {
              const match = text.match(pattern);
              if (match) return match[1];
            }
            return `visible-${index + 1}`;
          };
          const candidates = [
            ...document.querySelectorAll("tr, [role='row'], li, article, section, div[class*='site' i], div[class*='camp' i], div[class*='unit' i]")
          ]
            .map((element, index) => ({ index, text: clean(element.innerText || element.textContent || "") }))
            .filter((item) => item.text.length >= 20 && looksRelevant(item.text))
            .slice(0, 250);
          return candidates.map((item) => ({
            id: siteName(item.text, item.index),
            name: siteName(item.text, item.index),
            text: item.text
          }));
        }
        """
    )
    campsites: list[Campsite] = []
    seen: set[str] = set()
    for item in payload:
        raw_text = str(item.get("text", ""))
        if "available" not in raw_text.lower():
            continue
        campsite_id = str(item.get("id") or item.get("name") or f"visible-{len(campsites) + 1}")
        if campsite_id in seen:
            continue
        seen.add(campsite_id)
        availabilities = infer_selected_stay_availabilities(search, check_in)
        campsites.append(
            Campsite(
                campsite_id=campsite_id,
                name=str(item.get("name") or campsite_id),
                availabilities=availabilities,
                raw={"provider": "reservecalifornia", "visible_text": raw_text},
            )
        )
    return campsites


def infer_selected_stay_availabilities(search: SearchConfig, check_in: date) -> dict[date, str]:
    return {
        check_in + timedelta(days=offset): "Available"
        for offset in range(search.date_window.nights)
    }


def infer_visible_availabilities(text: str, check_ins: list[date]) -> dict[date, str]:
    normalized = text.lower()
    available_dates: dict[date, str] = {}
    for check_in in check_ins:
        tokens = {
            check_in.isoformat(),
            check_in.strftime("%m/%d/%Y"),
            check_in.strftime("%-m/%-d/%Y"),
            check_in.strftime("%b %-d").lower(),
            check_in.strftime("%B %-d").lower(),
        }
        if any(token in normalized for token in tokens):
            available_dates[check_in] = "Available"
    return available_dates


def wait_for_reserve_california_login(page, timeout_ms: int) -> None:
    if looks_logged_in(page):
        return
    print("Waiting for ReserveCalifornia login in Chrome...")
    try:
        page.wait_for_function(
            """
            () => {
              const text = document.body?.innerText?.toLowerCase() || "";
              const signInVisible = /\\b(sign in|login|log in)\\b/.test(text);
              const accountVisible = /\\b(account|profile|my reservations|logout|log out)\\b/.test(text);
              return accountVisible && !signInVisible;
            }
            """,
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise RuntimeError(
            "Timed out waiting for ReserveCalifornia login. Complete login in the Chrome window, "
            "or set `require_login: false` for availability-only scans."
        ) from exc


def looks_logged_in(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const text = document.body?.innerText?.toLowerCase() || "";
                  return /\\b(account|profile|my reservations|logout|log out)\\b/.test(text);
                }
                """
            )
        )
    except Exception:
        return False


def _try_set_search_dates(page, search: SearchConfig, check_in: date) -> None:
    check_out = check_in + timedelta(days=search.date_window.nights)
    for label, value in (
        ("arrival", check_in.strftime("%m/%d/%Y")),
        ("check in", check_in.strftime("%m/%d/%Y")),
        ("start", check_in.strftime("%m/%d/%Y")),
        ("departure", check_out.strftime("%m/%d/%Y")),
        ("check out", check_out.strftime("%m/%d/%Y")),
        ("end", check_out.strftime("%m/%d/%Y")),
    ):
        try:
            locator = page.get_by_label(re.compile(label, re.I))
            if locator.count() > 0:
                locator.first.fill(value, timeout=2_000)
        except Exception:
            continue
    for button_name in (re.compile("search", re.I), re.compile("update", re.I), re.compile("apply", re.I)):
        try:
            button = page.get_by_role("button", name=button_name)
            if button.count() > 0:
                button.first.click(timeout=2_000)
                page.wait_for_timeout(1_000)
                return
        except Exception:
            continue


def _wait_for_reserve_california_page(page) -> None:
    page.wait_for_function(
        """
        () => {
          const text = document.body?.innerText?.toLowerCase() || "";
          return text.includes("reservecalifornia") || text.includes("reserve california") || text.includes("camp");
        }
        """,
        timeout=30_000,
    )


def _find_reserve_california_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    if not pages:
        raise RuntimeError("No Chrome tabs are available through the CDP session.")
    for page in pages:
        host = (urlparse(page.url).hostname or "").lower()
        if host == "reservecalifornia.com" or host.endswith(".reservecalifornia.com"):
            return page
    return pages[0]
