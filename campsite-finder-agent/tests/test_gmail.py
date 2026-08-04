from __future__ import annotations

from campsite_finder_agent import gmail


class ExpiredCreds:
    valid = False
    expired = True
    refresh_token = "refresh-token"

    def refresh(self, request):
        raise RuntimeError("invalid_grant")

    def to_json(self):
        return "{}"


class FreshCreds:
    valid = True
    expired = False
    refresh_token = "refresh-token"

    def to_json(self):
        return "{\"token\": \"fresh\"}"


def test_build_gmail_service_reruns_oauth_when_refresh_fails(tmp_path, monkeypatch) -> None:
    credentials_path = tmp_path / "gmail_credentials.json"
    token_path = tmp_path / "gmail_token.json"
    credentials_path.write_text("{}")
    token_path.write_text("{}")
    fresh_creds = FreshCreds()

    class Credentials:
        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            assert path == str(token_path)
            return ExpiredCreds()

    monkeypatch.setattr("google.oauth2.credentials.Credentials", Credentials)
    monkeypatch.setattr("campsite_finder_agent.gmail.run_gmail_oauth_flow", lambda path: fresh_creds)
    monkeypatch.setattr("googleapiclient.discovery.build", lambda service, version, credentials: credentials)

    assert gmail.build_gmail_service(credentials_path, token_path) is fresh_creds
    assert token_path.read_text() == "{\"token\": \"fresh\"}"
