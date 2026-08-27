from argparse import Namespace

from gmail_inbox_agent.main import resolve_run_options


def test_cli_defaults_to_dry_run() -> None:
    dry_run, max_messages = resolve_run_options(
        Namespace(apply=False, dry_run=False, max_messages=None),
        default_max_messages=25,
        mailbox_changes_enabled=True,
    )

    assert dry_run is True
    assert max_messages == 25


def test_cli_apply_without_mailbox_flag_defaults_to_blocked() -> None:
    dry_run, max_messages = resolve_run_options(
        Namespace(apply=True, dry_run=False, max_messages=10),
        default_max_messages=25,
    )

    assert dry_run is True
    assert max_messages == 10


def test_auth_check_does_not_change_run_options() -> None:
    dry_run, max_messages = resolve_run_options(
        Namespace(apply=False, dry_run=False, auth_check=True, max_messages=None),
        default_max_messages=25,
        mailbox_changes_enabled=True,
    )

    assert dry_run is True
    assert max_messages == 25


def test_cli_apply_blocked_when_mailbox_changes_disabled() -> None:
    dry_run, max_messages = resolve_run_options(
        Namespace(apply=True, dry_run=False, max_messages=10),
        default_max_messages=25,
        mailbox_changes_enabled=False,
    )

    assert dry_run is True
    assert max_messages == 10


def test_cli_apply_blocked_prints_warning(capsys) -> None:
    resolve_run_options(
        Namespace(apply=True, dry_run=False, max_messages=10),
        default_max_messages=25,
        mailbox_changes_enabled=False,
    )

    captured = capsys.readouterr()
    assert "GMAIL_ENABLE_MAILBOX_CHANGES" in captured.out


def test_cli_apply_enabled_does_not_print_warning(capsys) -> None:
    resolve_run_options(
        Namespace(apply=True, dry_run=False, max_messages=10),
        default_max_messages=25,
        mailbox_changes_enabled=True,
    )

    captured = capsys.readouterr()
    assert "GMAIL_ENABLE_MAILBOX_CHANGES" not in captured.out


def test_cli_apply_proceeds_when_mailbox_changes_enabled() -> None:
    dry_run, max_messages = resolve_run_options(
        Namespace(apply=True, dry_run=False, max_messages=10),
        default_max_messages=25,
        mailbox_changes_enabled=True,
    )

    assert dry_run is False
    assert max_messages == 10
