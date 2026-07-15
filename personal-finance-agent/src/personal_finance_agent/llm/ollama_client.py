from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib import request


def call_ollama(prompt: str, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434") -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    last_error: Exception | None = None
    for _ in range(2):
        try:
            req = request.Request(
                f"{normalize_ollama_base_url(base_url)}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            return _parse_json_response(body.get("response", "{}"))
        except HTTPError as exc:
            last_error = _format_http_error(exc, model=model, base_url=base_url)
            break
        except Exception as exc:
            last_error = exc
            payload["prompt"] = (
                f"{prompt}\n\nYour previous response was invalid. Return one valid JSON object only."
            )
    raise ValueError(f"invalid Ollama JSON response: {last_error}")


def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    try:
        with request.urlopen(f"{normalize_ollama_base_url(base_url)}/api/tags", timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {base_url}: {exc}") from exc
    return sorted(model["name"] for model in body.get("models", []) if model.get("name"))


def check_ollama_model(model: str = "llama3.1:8b", base_url: str = "http://localhost:11434") -> tuple[bool, list[str]]:
    models = list_ollama_models(base_url)
    return model in models, models


def normalize_ollama_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/api"):
        return base[:-4]
    if base.endswith("/v1"):
        return base[:-3]
    return base


def _parse_json_response(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Ollama response was not a JSON object")
    return parsed


def _format_http_error(exc: HTTPError, model: str, base_url: str) -> RuntimeError:
    body = exc.read().decode("utf-8", errors="replace")
    detail = body.strip() or exc.reason
    hint = ""
    if exc.code == 404:
        hint = (
            f" Hint: verify OLLAMA_BASE_URL={base_url!r} points to the Ollama root "
            f"and OLLAMA_MODEL={model!r} is installed. Run `ollama list` or `task llm-check`."
        )
    return RuntimeError(f"HTTP {exc.code} from Ollama /api/generate: {detail}.{hint}")
