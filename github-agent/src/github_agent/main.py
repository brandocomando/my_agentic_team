from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from github_agent.planner import build_issue_proposals
from github_agent.scanners.pip_audit import parse_pip_audit_report
from github_agent.scanners.trivy import parse_trivy_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan GitHub maintenance issues from scanner findings.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    plan = subcommands.add_parser("plan-issues", help="Build issue proposals from scanner JSON.")
    plan.add_argument("--scanner", choices=["pip-audit", "trivy"], default="trivy", help="Scanner report format.")
    plan.add_argument("--input", type=Path, required=True, help="Path to scanner JSON output.")
    plan.add_argument("--target", default="repo", help="Repo path or agent name for scanner formats without target paths.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "plan-issues":
        proposals = plan_issues(args.scanner, args.input, args.target)
        print(json.dumps([asdict(proposal) for proposal in proposals], indent=2))


def plan_issues(scanner: str, input_path: Path, target: str = "repo"):
    if scanner == "pip-audit":
        findings = parse_pip_audit_report(input_path, target=target)
    elif scanner == "trivy":
        findings = parse_trivy_report(input_path)
    else:
        raise ValueError(f"Unsupported scanner: {scanner}")
    return build_issue_proposals(findings)


if __name__ == "__main__":
    main()
