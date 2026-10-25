from github_agent.main import parse_args


def test_status_command_parses() -> None:
    args = parse_args(["status"])

    assert args.command == "status"
