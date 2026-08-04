from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def build_gmail_service(credentials_path: Path, token_path: Path) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Gmail alerts need Google API dependencies. Run `uv sync` before enabling email alerts."
        ) from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = run_gmail_oauth_flow(credentials_path)
        else:
            creds = run_gmail_oauth_flow(credentials_path)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def run_gmail_oauth_flow(credentials_path: Path) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not credentials_path.exists():
        raise FileNotFoundError(f"Missing Gmail credentials file: {credentials_path}")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    return flow.run_local_server(port=0)


def send_gmail_email(
    credentials_path: Path,
    token_path: Path,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    service = build_gmail_service(credentials_path, token_path)
    message = EmailMessage()
    message["To"] = to_email
    message["From"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service.users().messages().send(userId="me", body={"raw": encoded}).execute()
