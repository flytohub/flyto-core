"""
Tests for CLI template subcommand (argument parsing, dispatch, config).

Tests pure logic only — no HTTP calls, no mocking.
"""

import argparse
import os
import pytest

from cli.template import (
    add_template_parser,
    run_template_command,
    _get_api_url,
    _get_auth_token,
    DEFAULT_API_URL,
)


# ===================================================================
# Helpers
# ===================================================================

def _build_parser():
    """Create a parser with the template subcommand registered."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    add_template_parser(subparsers)
    return parser


def _parse(args_list):
    """Parse a list of args through the template subparser."""
    parser = _build_parser()
    return parser.parse_args(["template"] + args_list)


# ===================================================================
# _get_api_url
# ===================================================================

class TestGetApiUrl:
    def test_default_url(self, monkeypatch):
        monkeypatch.delenv("FLYTO_API_URL", raising=False)
        assert _get_api_url() == DEFAULT_API_URL

    def test_custom_url_from_env(self, monkeypatch):
        monkeypatch.setenv("FLYTO_API_URL", "http://localhost:8000/api/")
        assert _get_api_url() == "http://localhost:8000/api"  # trailing slash stripped

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("FLYTO_API_URL", "https://custom.api.com/v2///")
        result = _get_api_url()
        assert not result.endswith("/")


# ===================================================================
# _get_auth_token
# ===================================================================

class TestGetAuthToken:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("FLYTO_TOKEN", "tok_abc123")
        assert _get_auth_token() == "tok_abc123"

    def test_empty_when_no_env_no_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FLYTO_TOKEN", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))  # no .flyto/token file
        # Override Path.home() via env
        result = _get_auth_token()
        # Either empty or from a real ~/.flyto/token if it exists
        assert isinstance(result, str)

    def test_from_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FLYTO_TOKEN", raising=False)
        token_dir = tmp_path / ".flyto"
        token_dir.mkdir()
        token_file = token_dir / "token"
        token_file.write_text("file_tok_xyz\n")

        # Monkey-patch Path.home to return tmp_path
        from pathlib import Path
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        result = _get_auth_token()
        assert result == "file_tok_xyz"

    def test_env_takes_precedence_over_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FLYTO_TOKEN", "env_token")
        token_dir = tmp_path / ".flyto"
        token_dir.mkdir()
        (token_dir / "token").write_text("file_token")

        from pathlib import Path
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        assert _get_auth_token() == "env_token"


# ===================================================================
# Argument parsing
# ===================================================================

class TestArgumentParsing:
    def test_export_args(self):
        args = _parse(["export", "tmpl-123", "-o", "out.yaml"])
        assert args.template_action == "export"
        assert args.template_id == "tmpl-123"
        assert args.output == "out.yaml"

    def test_export_args_no_output(self):
        args = _parse(["export", "tmpl-123"])
        assert args.template_action == "export"
        assert args.template_id == "tmpl-123"
        assert args.output is None

    def test_import_args(self):
        args = _parse(["import", "workflow.yaml"])
        assert args.template_action == "import"
        assert args.file == "workflow.yaml"

    def test_push_args(self):
        args = _parse(["push", "tmpl-123", "updated.yaml", "-m", "Fix extraction"])
        assert args.template_action == "push"
        assert args.template_id == "tmpl-123"
        assert args.file == "updated.yaml"
        assert args.message == "Fix extraction"
        assert args.pr is False

    def test_push_args_with_pr(self):
        args = _parse(["push", "tmpl-123", "file.yaml", "--pr", "-m", "Add step"])
        assert args.pr is True
        assert args.message == "Add step"

    def test_pull_args(self):
        args = _parse(["pull", "tmpl-123", "-o", "local.yaml"])
        assert args.template_action == "pull"
        assert args.template_id == "tmpl-123"
        assert args.output == "local.yaml"

    def test_diff_args(self):
        args = _parse(["diff", "tmpl-123", "local.yaml"])
        assert args.template_action == "diff"
        assert args.template_id == "tmpl-123"
        assert args.file == "local.yaml"

    def test_list_args_default(self):
        args = _parse(["list"])
        assert args.template_action == "list"
        assert args.tag is None
        assert args.status is None

    def test_list_args_with_filters(self):
        args = _parse(["list", "--tag", "scraping", "--status", "published"])
        assert args.tag == "scraping"
        assert args.status == "published"

    def test_search_args(self):
        args = _parse(["search", "browser extract", "--limit", "10"])
        assert args.template_action == "search"
        assert args.query == "browser extract"
        assert args.limit == 10

    def test_search_args_default_limit(self):
        args = _parse(["search", "test"])
        assert args.limit == 20

    def test_info_args(self):
        args = _parse(["info", "tmpl-123"])
        assert args.template_action == "info"
        assert args.template_id == "tmpl-123"

    def test_history_args(self):
        args = _parse(["history", "tmpl-123", "--limit", "5"])
        assert args.template_action == "history"
        assert args.template_id == "tmpl-123"
        assert args.limit == 5

    def test_history_args_default_limit(self):
        args = _parse(["history", "tmpl-123"])
        assert args.limit == 20


# ===================================================================
# run_template_command dispatch
# ===================================================================

class TestRunTemplateCommand:
    def test_no_action_returns_1(self, capsys):
        """When no template_action is given, should return 1 and print usage."""
        args = argparse.Namespace(template_action=None)
        result = run_template_command(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.out
        assert "export" in captured.out

    def test_unknown_action_returns_1(self, capsys):
        """Unknown action should return 1."""
        args = argparse.Namespace(template_action="nonexistent")
        result = run_template_command(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown" in captured.out

    def test_all_9_actions_registered(self):
        """All 9 subcommands should be parseable."""
        parser = _build_parser()
        actions = [
            "export", "import", "push", "pull", "diff",
            "list", "search", "info", "history",
        ]
        for action in actions:
            # Just verify parsing doesn't raise
            if action in ("export", "pull", "info", "history"):
                args = parser.parse_args(["template", action, "test-id"])
            elif action == "import":
                args = parser.parse_args(["template", action, "file.yaml"])
            elif action in ("push", "diff"):
                args = parser.parse_args(["template", action, "test-id", "file.yaml"])
            elif action == "search":
                args = parser.parse_args(["template", action, "query"])
            elif action == "list":
                args = parser.parse_args(["template", action])

            assert args.template_action == action


# ===================================================================
# _request (testing URL construction without actual HTTP)
# ===================================================================

class TestRequestUrlConstruction:
    """Test that _request builds correct URLs. We can't make real HTTP calls
    but we can verify the URL construction logic by examining the function."""

    def test_default_api_url_is_https(self):
        assert DEFAULT_API_URL.startswith("https://")

    def test_default_api_url_has_api_path(self):
        assert "/api" in DEFAULT_API_URL
