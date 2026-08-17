from __future__ import annotations

import argparse
import json

from github_agent.config import load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect GitHub Agent scaffold status.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("status", help="Print the current GitHub Agent evaluation status.")

    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if args.command == "status":
        config = load_config()
        print(
            json.dumps(
                {
                    "agent": "github-agent",
                    "status": "paused",
                    "repository": f"{config.owner}/{config.repo}",
                    "next_step": "Evaluate native GitHub security alerts before adding automation.",
                    "native_sources": ["dependabot", "code-scanning", "secret-scanning"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
