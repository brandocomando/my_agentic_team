from __future__ import annotations

from pathlib import Path


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is required for browser exporters. Install it with `uv sync --extra export`."
        ) from exc
    return sync_playwright


def ensure_download_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
