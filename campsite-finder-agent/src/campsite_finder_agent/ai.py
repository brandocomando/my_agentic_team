from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from campsite_finder_agent.models import AIPreferences, MatchWindow


class AIMatchAnalysis(BaseModel):
    state_key: str
    score: float | None = Field(default=None, ge=0, le=10)
    fit: str = ""
    reasons: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    summary: str = ""
    suggested_state_action: str = ""
    suggested_state_reason: str = ""


class AIAnalysisResponse(BaseModel):
    summary: str = ""
    matches: list[AIMatchAnalysis] = Field(default_factory=list)


def analyze_match_windows_with_ollama(
    matches: list[MatchWindow],
    preferences_by_search: dict[str, AIPreferences],
    model: str,
    base_url: str,
) -> str:
    if not matches:
        return ""
    response = request_ollama_analysis(matches, preferences_by_search, model, base_url)
    analyses = {item.state_key: item for item in response.matches}
    for match in matches:
        analysis = analyses.get(match.state_key)
        if not analysis:
            continue
        match.ai_score = analysis.score
        match.ai_fit = analysis.fit
        match.ai_reasons = analysis.reasons
        match.ai_concerns = analysis.concerns
        match.ai_summary = analysis.summary
        match.suggested_state_action = analysis.suggested_state_action
        match.suggested_state_reason = analysis.suggested_state_reason
    return render_ai_summary(response, matches)


def request_ollama_analysis(
    matches: list[MatchWindow],
    preferences_by_search: dict[str, AIPreferences],
    model: str,
    base_url: str,
) -> AIAnalysisResponse:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "preferences_by_search": serialized_preferences(preferences_by_search),
                        "matches": [match_payload(match) for match in matches],
                    },
                    indent=2,
                ),
            },
        ],
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {base_url}: {exc}") from exc
    content = raw.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON content: {content[:300]}") from exc
    try:
        return AIAnalysisResponse.model_validate(parsed)
    except ValidationError as exc:
        raise RuntimeError(f"Ollama JSON did not match expected schema: {exc}") from exc


def system_prompt() -> str:
    return """
You rank campsite availability matches for a human reviewer.
Return only JSON matching this schema:
{
  "summary": "short digest of best options and tradeoffs",
  "matches": [
    {
      "state_key": "exact input state_key",
      "score": 0-10,
      "fit": "weak|okay|strong|excellent",
      "reasons": ["specific positive reasons"],
      "concerns": ["specific concerns"],
      "summary": "one sentence recommendation",
      "suggested_state_action": "watch|ignore|book|",
      "suggested_state_reason": "why this state action makes sense"
    }
  ]
}
Use preferences from any matching search name. Do not invent facts beyond the input.
Use "book" only for exceptionally strong fits; otherwise prefer "watch" or "ignore".
""".strip()


def serialized_preferences(preferences_by_search: dict[str, AIPreferences]) -> dict[str, dict[str, Any]]:
    return {name: preferences.model_dump(mode="json") for name, preferences in preferences_by_search.items()}


def match_payload(match: MatchWindow) -> dict[str, Any]:
    return {
        "state_key": match.state_key,
        "search_names": match.search_names,
        "campground_id": match.campground_id,
        "campground_name": match.campground_name,
        "campground_url": match.campground_url,
        "check_in_window_start": match.check_in_window_start.isoformat(),
        "check_in_window_end": match.check_in_window_end.isoformat(),
        "earliest_check_out": match.earliest_check_out.isoformat(),
        "latest_check_out": match.latest_check_out.isoformat(),
        "nights": match.nights,
        "representative_campsite_name": match.representative_campsite_name,
        "representative_site_type": match.representative_site_type,
        "representative_loop": match.representative_loop,
        "matching_start_count": match.matching_start_count,
        "unique_site_count": match.unique_site_count,
    }


def render_ai_summary(response: AIAnalysisResponse, matches: list[MatchWindow]) -> str:
    lines = ["AI campsite review", "", response.summary.strip() or "No summary returned.", ""]
    by_key = {match.state_key: match for match in matches}
    for analysis in sorted(response.matches, key=lambda item: (-(item.score or 0), item.state_key)):
        match = by_key.get(analysis.state_key)
        if not match:
            continue
        score = "n/a" if analysis.score is None else f"{analysis.score:g}/10"
        lines.append(f"- {match.campground_name}: {score} {analysis.fit}".rstrip())
        if analysis.summary:
            lines.append(f"  {analysis.summary}")
        if analysis.suggested_state_action:
            lines.append(f"  Suggested state: {analysis.suggested_state_action} - {analysis.suggested_state_reason}")
    return "\n".join(lines).strip() + "\n"


def write_ai_summary(path: Path, summary: str) -> None:
    if not summary:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary)
