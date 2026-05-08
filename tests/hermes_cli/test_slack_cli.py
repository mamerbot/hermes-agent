"""Tests for Slack manifest generation helpers."""

import json

from hermes_cli.slack_cli import _build_full_manifest, slack_manifest_command


class TestBuildFullManifest:
    def test_enables_app_home_messages(self):
        manifest = _build_full_manifest("mamerbot", "Hermes on Slack")

        assert manifest["features"]["app_home"] == {
            "home_tab_enabled": True,
            "messages_tab_enabled": True,
            "messages_tab_read_only_enabled": False,
        }

    def test_preserves_assistant_view_and_slash_commands(self):
        manifest = _build_full_manifest("mamerbot", "Hermes on Slack")

        assert manifest["features"]["assistant_view"]["assistant_description"]
        assert manifest["features"]["slash_commands"]


class Args:
    def __init__(self, *, write=None, name=None, description=None, slashes_only=False):
        self.write = write
        self.name = name
        self.description = description
        self.slashes_only = slashes_only


class TestSlackManifestCommand:
    def test_stdout_manifest_includes_app_home(self, capsys):
        rc = slack_manifest_command(Args(name="mamerbot", description="Hermes on Slack"))

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["features"]["app_home"]["messages_tab_enabled"] is True
        assert payload["features"]["app_home"]["messages_tab_read_only_enabled"] is False

    def test_slashes_only_omits_full_manifest_sections(self, capsys):
        rc = slack_manifest_command(Args(slashes_only=True))

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload
        assert all("command" in entry for entry in payload)
