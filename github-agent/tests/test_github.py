from github_agent.github import publish_issue_proposals
from github_agent.models import IssueProposal


class FakeGitHubClient:
    def __init__(self, existing=None) -> None:
        self.existing = existing or []
        self.created = []

    def list_open_issues(self, labels=None):
        self.labels = labels
        return self.existing

    def create_issue(self, proposal):
        self.created.append(proposal)
        return {"html_url": f"https://example.com/issues/{len(self.created)}"}


def test_publish_issue_proposals_creates_missing_issue() -> None:
    proposal = IssueProposal(title="Issue", body="<!-- github-agent-dedupe-key: k1 -->", labels=[], dedupe_key="k1")
    client = FakeGitHubClient()

    results = publish_issue_proposals(client, [proposal])

    assert client.labels == ["agent:github-agent"]
    assert len(client.created) == 1
    assert results[0].action == "created"
    assert results[0].url == "https://example.com/issues/1"


def test_publish_issue_proposals_skips_existing_issue() -> None:
    proposal = IssueProposal(title="Issue", body="<!-- github-agent-dedupe-key: k1 -->", labels=[], dedupe_key="k1")
    existing = [{"body": "Existing\n<!-- github-agent-dedupe-key: k1 -->"}]
    client = FakeGitHubClient(existing=existing)

    results = publish_issue_proposals(client, [proposal])

    assert client.created == []
    assert results[0].action == "skipped_existing"

