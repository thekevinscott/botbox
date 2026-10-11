"""Tests for the ``ci`` subcommand dispatcher."""

import pytest

from ci import cli


def test_check_changelog_dispatches_and_propagates_exit_code(monkeypatch):
    monkeypatch.setattr(cli.check_changelog, "main", lambda: 3)
    assert cli.main(["check-changelog"]) == 3


def test_unknown_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        cli.main(["no-such-gate"])
    assert exc.value.code == 2
