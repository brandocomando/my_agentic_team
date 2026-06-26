from __future__ import annotations

import base64
from email.message import EmailMessage as MIMEEmailMessage
from typing import Any

from gmail_inbox_agent.models import EmailMessage


class GmailClient:
    def __init__(self, service: Any) -> None:
        self.service = service
        self._label_cache: dict[str, str] = {}

    def get_profile(self) -> dict[str, Any]:
        return self.service.users().getProfile(userId="me").execute()

    def fetch_inbox_messages(self, max_messages: int) -> list[EmailMessage]:
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q='in:inbox -label:"AI Reviewed"', maxResults=max_messages)
            .execute()
        )
        messages = response.get("messages", [])
        return [self.get_message(item["id"]) for item in messages]

    def get_message(self, message_id: str) -> EmailMessage:
        raw = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {h["name"].lower(): h.get("value", "") for h in raw.get("payload", {}).get("headers", [])}
        return EmailMessage(
            gmail_message_id=raw["id"],
            thread_id=raw.get("threadId", ""),
            subject=headers.get("subject", ""),
            from_email=headers.get("from", ""),
            to_email=headers.get("to"),
            date=headers.get("date"),
            snippet=raw.get("snippet", ""),
            body_text=_extract_body(raw.get("payload", {})),
            existing_labels=raw.get("labelIds", []),
        )

    def ensure_label(self, label_name: str) -> str:
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        labels = self.service.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label.get("name") == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]

        created = (
            self.service.users()
            .labels()
            .create(userId="me", body={"name": label_name, "labelListVisibility": "labelShow"})
            .execute()
        )
        self._label_cache[label_name] = created["id"]
        return created["id"]

    def modify_message(self, message_id: str, add_label_names: list[str], remove_label_ids: list[str]) -> None:
        add_label_ids = [self.ensure_label(label_name) for label_name in add_label_names]
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": add_label_ids, "removeLabelIds": remove_label_ids},
        ).execute()

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        message = MIMEEmailMessage()
        message["To"] = to_email
        message["From"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        self.service.users().messages().send(userId="me", body={"raw": encoded}).execute()


def _extract_body(payload: dict[str, Any]) -> str | None:
    if payload.get("mimeType") == "text/plain":
        return _decode_body(payload)
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain":
            return _decode_body(part)
        nested = _extract_body(part)
        if nested:
            return nested
    return None


def _decode_body(part: dict[str, Any]) -> str | None:
    data = part.get("body", {}).get("data")
    if not data:
        return None
    return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
