from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from github_agent.config import GitHubAgentConfig
from github_agent.models import IssueProposal


@dataclass(frozen=True)
class PublishResult:
    proposal: IssueProposal
    action: str
    url: str | None = None


class GitHubIssuesClient:
    def __init__(self, config: GitHubAgentConfig, api_base: str = "https://api.github.com") -> None:
        if not config.token:
            raise ValueError("GITHUB_TOKEN is required when applying GitHub issue changes.")
        self.config = config
        self.api_base = api_base.rstrip("/")

    def list_open_issues(self, labels: list[str] | None = None) -> list[dict[str, Any]]:
        query = {"state": "open", "per_page": "100"}
        if labels:
            query["labels"] = ",".join(labels)
        path = f"/repos/{self.config.owner}/{self.config.repo}/issues?{urllib.parse.urlencode(query)}"
        return self._request("GET", path)

    def create_issue(self, proposal: IssueProposal) -> dict[str, Any]:
        body = {"title": proposal.title, "body": proposal.body, "labels": proposal.labels}
        return self._request("POST", f"/repos/{self.config.owner}/{self.config.repo}/issues", body)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
                "User-Agent": "github-agent",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {details}") from exc


def publish_issue_proposals(client: GitHubIssuesClient, proposals: list[IssueProposal]) -> list[PublishResult]:
    existing = client.list_open_issues(labels=["agent:github-agent"])
    existing_keys = {_dedupe_key_from_issue(issue) for issue in existing}
    results: list[PublishResult] = []
    for proposal in proposals:
        if proposal.dedupe_key in existing_keys:
            results.append(PublishResult(proposal=proposal, action="skipped_existing"))
            continue
        created = client.create_issue(proposal)
        results.append(PublishResult(proposal=proposal, action="created", url=created.get("html_url")))
    return results


def _dedupe_key_from_issue(issue: dict[str, Any]) -> str | None:
    body = issue.get("body") or ""
    prefix = "<!-- github-agent-dedupe-key: "
    suffix = " -->"
    start = body.find(prefix)
    if start == -1:
        return None
    start += len(prefix)
    end = body.find(suffix, start)
    if end == -1:
        return None
    return body[start:end].strip()

