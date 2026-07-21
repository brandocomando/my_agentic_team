from __future__ import annotations


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is required for browser scans. Install it with `uv sync --extra browser`."
        ) from exc
    return sync_playwright
