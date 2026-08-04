from __future__ import annotations

import json
from datetime import date

from campsite_finder_agent.alerts import EmailAlertSettings, notify_ai_match_windows
from campsite_finder_agent.models import MatchWindow


def make_match_window(score: float = 8.5, action: str = "watch") -> MatchWindow:
    return MatchWindow(
        state_key="state-1",
        search_names=["beach-local-rv-sat-mon"],
        campground_id="SanDiegoCountyParks:south-carlsbad:CA",
        campground_name="South Carlsbad State Beach",
        campground_url="https://outdoorithm.com/campgrounds/ca/south-carlsbad",
        check_in_window_start=date(2026, 8, 8),
        check_in_window_end=date(2026, 8, 8),
        earliest_check_out=date(2026, 8, 10),
        latest_check_out=date(2026, 8, 10),
        nights=2,
        representative_campsite_id="101",
        representative_campsite_name="Site 101",
        representative_site_type="STANDARD",
        representative_loop="Beach Loop",
        matching_campsite_ids=["101", "102"],
        ai_score=score,
        ai_fit="strong",
        ai_reasons=["coastal", "rv-friendly"],
        ai_concerns=["popular"],
        ai_summary="Strong beach campground fit.",
        suggested_state_action=action,
        suggested_state_reason="Good fit.",
        matching_start_count=2,
        unique_site_count=2,
    )


def make_settings(tmp_path, actions: set[str] | None = None) -> EmailAlertSettings:
    return EmailAlertSettings(
        enabled=True,
        gmail_credentials_path=tmp_path / "gmail_credentials.json",
        gmail_token_path=tmp_path / "gmail_token.json",
        recipient="me@example.test",
        min_score=8.0,
        actions=actions or {"book"},
        state_path=tmp_path / "notifications.json",
    )


def test_notify_ai_match_windows_sends_email_and_records_state(tmp_path, monkeypatch) -> None:
    sent_messages = []

    def fake_send(credentials_path, token_path, recipient, subject, body):
        sent_messages.append((credentials_path, token_path, recipient, subject, body))

    monkeypatch.setattr("campsite_finder_agent.alerts.send_gmail_email", fake_send)

    sent_count = notify_ai_match_windows([make_match_window()], make_settings(tmp_path))

    assert sent_count == 1
    assert len(sent_messages) == 1
    credentials_path, token_path, recipient, subject, body = sent_messages[0]
    assert credentials_path == tmp_path / "gmail_credentials.json"
    assert token_path == tmp_path / "gmail_token.json"
    assert recipient == "me@example.test"
    assert "South Carlsbad State Beach" in subject
    assert "State key: state-1" in body
    assert json.loads((tmp_path / "notifications.json").read_text())["sent_ai_match_keys"]["state-1"]


def test_notify_ai_match_windows_skips_already_sent_state_key(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    settings.state_path.write_text(json.dumps({"sent_ai_match_keys": {"state-1": "2026-08-03T00:00:00Z"}}))
    monkeypatch.setattr(
        "campsite_finder_agent.alerts.send_gmail_email",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Gmail should not be called")),
    )

    assert notify_ai_match_windows([make_match_window()], settings) == 0


def test_notify_ai_match_windows_can_use_suggested_action_below_threshold(tmp_path, monkeypatch) -> None:
    sent_messages = []

    monkeypatch.setattr(
        "campsite_finder_agent.alerts.send_gmail_email",
        lambda *args: sent_messages.append(args),
    )

    sent_count = notify_ai_match_windows([make_match_window(score=6.5, action="book")], make_settings(tmp_path))

    assert sent_count == 1
    assert sent_messages

def test_notify_ai_match_windows_does_not_record_state_when_email_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "campsite_finder_agent.alerts.send_gmail_email",
        lambda *args: (_ for _ in ()).throw(RuntimeError("invalid_grant")),
    )

    sent_count = notify_ai_match_windows([make_match_window()], make_settings(tmp_path))

    assert sent_count == 0
    assert not (tmp_path / "notifications.json").exists()

