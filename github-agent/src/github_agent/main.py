from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from github_agent.config import load_config
from github_agent.github import GitHubIssuesClient, publish_issue_proposals
from github_agent.planner import build_issue_proposals
from github_agent.scanners.pip_audit import parse_pip_audit_report
from github_agent.scanners.pip_audit_runner import scan_python_agent
from github_agent.scanners.trivy import parse_trivy_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan GitHub maintenance issues from scanner findings.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    plan = subcommands.add_parser("plan-issues", help="Build issue proposals from scanner JSON.")
    plan.add_argument("--scanner", choices=["pip-audit", "trivy"], default="trivy", help="Scanner report format.")
    plan.add_argument("--input", type=Path, required=True, help="Path to scanner JSON output.")
    plan.add_argument("--target", default="repo", help="Repo path or agent name for scanner formats without target paths.")

    scan = subcommands.add_parser("scan-agent", help="Scan one agent directory and optionally open GitHub issues.")
    scan.add_argument("--agent", required=True, help="Agent directory name, such as gmail-inbox-agent.")
    scan.add_argument("--scanner", choices=["pip-audit"], default="pip-audit", help="Local scanner to run.")
    scan.add_argument("--repo-root", type=Path, default=Path(".."), help="Path to the repository root.")
    mode = scan.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print planned issues without creating GitHub issues.")
    mode.add_argument("--apply", action="store_true", help="Create missing GitHub issues.")
    scan.add_argument("--config", type=Path, default=None, help="Path to github-agent TOML config.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "plan-issues":
        proposals = plan_issues(args.scanner, args.input, args.target)
        print(json.dumps([asdict(proposal) for proposal in proposals], indent=2))
    if args.command == "scan-agent":
        result = scan_agent(
            agent=args.agent,
            scanner=args.scanner,
            repo_root=args.repo_root,
            apply=args.apply,
            config_path=args.config,
        )
        print(json.dumps(result, indent=2))


def plan_issues(scanner: str, input_path: Path, target: str = "repo"):
    if scanner == "pip-audit":
        findings = parse_pip_audit_report(input_path, target=target)
    elif scanner == "trivy":
        findings = parse_trivy_report(input_path)
    else:
        raise ValueError(f"Unsupported scanner: {scanner}")
    return build_issue_proposals(findings)


def scan_agent(agent: str, scanner: str, repo_root: Path, apply: bool = False, config_path: Path | None = None):
    agent_path = (repo_root / agent).resolve()
    if not agent_path.exists():
        raise ValueError(f"Agent path does not exist: {agent_path}")
    if scanner != "pip-audit":
        raise ValueError(f"Unsupported local scanner: {scanner}")

    findings = scan_python_agent(agent_path, agent_name=agent)
    proposals = build_issue_proposals(findings)
    if not apply:
        return {
            "dry_run": True,
            "agent": agent,
            "scanner": scanner,
            "issue_count": len(proposals),
            "issues": [asdict(proposal) for proposal in proposals],
        }
    if not proposals:
        return {
            "dry_run": False,
            "agent": agent,
            "scanner": scanner,
            "issue_count": 0,
            "results": [],
        }

    config = load_config(config_path)
    client = GitHubIssuesClient(config)
    results = publish_issue_proposals(client, proposals)
    return {
        "dry_run": False,
        "agent": agent,
        "scanner": scanner,
        "issue_count": len(proposals),
        "results": [asdict(result) for result in results],
    }


if __name__ == "__main__":
    main()
