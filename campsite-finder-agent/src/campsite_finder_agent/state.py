from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from campsite_finder_agent.models import MatchWindow


class ResultState(BaseModel):
    ignored: list[str | dict] = Field(default_factory=list)
    booked: list[str | dict] = Field(default_factory=list)

    @property
    def hidden_keys(self) -> set[str]:
        return state_keys_from_entries(self.ignored) | state_keys_from_entries(self.booked)


def load_state(path: Path) -> ResultState:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_state(path, ResultState())
        return ResultState()
    with path.open() as handle:
        payload = json.load(handle)
    return ResultState.model_validate(payload)


def write_state(path: Path, state: ResultState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        json.dump(state.model_dump(mode="json"), handle, indent=2)
        handle.write("\n")


def filter_stateful_match_windows(matches: list[MatchWindow], state: ResultState) -> list[MatchWindow]:
    hidden_keys = state.hidden_keys
    if not hidden_keys:
        return matches
    return [match for match in matches if match.state_key not in hidden_keys]


def state_keys_from_entries(entries: list[str | dict]) -> set[str]:
    keys: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            keys.add(entry.strip())
        elif isinstance(entry, dict):
            value = entry.get("state_key") or entry.get("key")
            if value:
                keys.add(str(value).strip())
    return keys
