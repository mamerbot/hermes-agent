import json
import urllib.error

import pytest

from gateway.bridges.paperclip_discord import (
    DiscordReplyContext,
    PaperclipDiscordReplyBridge,
    build_config,
)


class FakePaperclipClient:
    def __init__(self, issues=None):
        self.issues = issues or []
        self.comments = []
        self.wakeups = []

    def list_agent_issues(self, agent_id):
        return [i for i in self.issues if i.get("assigneeAgentId") == agent_id]

    def create_issue_comment(self, issue_id, body, source="operator", interrupt=True):
        self.comments.append({"issue_id": issue_id, "body": body, "source": source, "interrupt": interrupt})
        return {"id": "comment-1"}

    def wake_agent(self, agent_id):
        self.wakeups.append(agent_id)
        return {"ok": True}


def test_routes_webhook_reply_to_highest_priority_open_issue_and_wakes_agent():
    config = build_config(
        {
            "paperclip_reply_bridge": {
                "enabled": True,
                "standup_channel_id": "chan-standup",
                "webhook_agent_map": {"wh-monica": "agent-monica"},
                "webhook_persona_map": {"wh-monica": "Monica"},
                "wake_agent": True,
            }
        }
    )
    client = FakePaperclipClient(
        issues=[
            {"id": "low", "identifier": "EMT-LOW", "title": "Low", "status": "todo", "priority": "low", "assigneeAgentId": "agent-monica"},
            {"id": "critical", "identifier": "EMT-CRIT", "title": "Critical coordination", "status": "in_progress", "priority": "critical", "assigneeAgentId": "agent-monica"},
        ]
    )
    bridge = PaperclipDiscordReplyBridge(config, client=client)

    result = bridge.route_reply(
        DiscordReplyContext(
            channel_id="chan-standup",
            reply_message_id="reply-1",
            reply_text="Please tighten the acceptance criteria.",
            author_id="8287422597",
            author_name="Mark",
            referenced_message_id="standup-1",
            referenced_webhook_id="wh-monica",
            referenced_author_name="Monica",
        )
    )

    assert result.routed is True
    assert result.issue_id == "critical"
    assert result.agent_id == "agent-monica"
    assert result.comment_id == "comment-1"
    assert client.wakeups == ["agent-monica"]
    body = client.comments[0]["body"]
    assert "[DISCORD_REPLY_REQUIRES_AGENT_RESPONSE]" in body
    assert "Operator directive from Mark via Discord reply to Monica" in body
    assert "Answer Mark directly in this issue thread before routine heartbeat work." in body
    assert "Please tighten the acceptance criteria." in body
    assert "Paperclip ticket: [EMT-CRIT](http://127.0.0.1:3100/issues/critical)" in body
    assert "standup-1" in body


def test_ignores_unconfigured_channel_or_webhook_without_calling_paperclip():
    config = build_config(
        {
            "paperclip_reply_bridge": {
                "enabled": True,
                "standup_channel_id": "chan-standup",
                "webhook_agent_map": {"wh-monica": "agent-monica"},
            }
        }
    )
    client = FakePaperclipClient()
    bridge = PaperclipDiscordReplyBridge(config, client=client)

    wrong_channel = bridge.route_reply(
        DiscordReplyContext(
            channel_id="other-channel",
            reply_message_id="reply-1",
            reply_text="hello",
            author_id="u1",
            author_name="Mark",
            referenced_message_id="m1",
            referenced_webhook_id="wh-monica",
            referenced_author_name="Monica",
        )
    )
    unknown_webhook = bridge.route_reply(
        DiscordReplyContext(
            channel_id="chan-standup",
            reply_message_id="reply-2",
            reply_text="hello",
            author_id="u1",
            author_name="Mark",
            referenced_message_id="m2",
            referenced_webhook_id="wh-richard",
            referenced_author_name="Richard",
        )
    )

    assert wrong_channel.routed is False
    assert wrong_channel.reason == "channel_not_enabled"
    assert unknown_webhook.routed is False
    assert unknown_webhook.reason == "unmapped_webhook"
    assert client.comments == []
    assert client.wakeups == []


def test_uses_fallback_issue_when_agent_has_no_open_issue():
    config = build_config(
        {
            "paperclip_reply_bridge": {
                "enabled": True,
                "standup_channel_id": "chan-standup",
                "fallback_issue_id": "fallback-issue",
                "webhook_agent_map": {"wh-ceo": "agent-ceo"},
                "webhook_persona_map": {"wh-ceo": "CEO"},
            }
        }
    )
    client = FakePaperclipClient(issues=[])
    bridge = PaperclipDiscordReplyBridge(config, client=client)

    result = bridge.route_reply(
        DiscordReplyContext(
            channel_id="chan-standup",
            reply_message_id="reply-1",
            reply_text="Noted.",
            author_id="u1",
            author_name="Mark",
            referenced_message_id="m1",
            referenced_webhook_id="wh-ceo",
            referenced_author_name="CEO",
        )
    )

    assert result.routed is True
    assert result.issue_id == "fallback-issue"
    assert "fallback coordination route" in client.comments[0]["body"]


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_builds_context_from_discord_reply_to_webhook_message():
    from gateway.bridges.paperclip_discord import context_from_discord_message

    referenced = Obj(id=111, content="standup", webhook_id=222, author=Obj(display_name="Monica", name="Monica"))
    message = Obj(
        id=333,
        content="Please clarify blocker.",
        author=Obj(id=444, display_name="Mark"),
        channel=Obj(id=555),
        guild=Obj(id=666),
        attachments=[Obj()],
        reference=Obj(message_id=111, resolved=referenced),
    )

    context = context_from_discord_message(message)

    assert context is not None
    assert context.channel_id == "555"
    assert context.reply_message_id == "333"
    assert context.reply_text == "Please clarify blocker."
    assert context.author_id == "444"
    assert context.author_name == "Mark"
    assert context.referenced_message_id == "111"
    assert context.referenced_webhook_id == "222"
    assert context.referenced_author_name == "Monica"
    assert context.guild_id == "666"
    assert context.attachment_count == 1


def test_dedupes_replayed_discord_reply_events():
    config = build_config(
        {
            "paperclip_reply_bridge": {
                "enabled": True,
                "standup_channel_id": "chan-standup",
                "fallback_issue_id": "fallback-issue",
                "webhook_agent_map": {"wh-ceo": "agent-ceo"},
            }
        }
    )
    client = FakePaperclipClient()
    bridge = PaperclipDiscordReplyBridge(config, client=client)
    context = DiscordReplyContext(
        channel_id="chan-standup",
        reply_message_id="same-reply",
        reply_text="Same event twice",
        author_id="u1",
        author_name="Mark",
        referenced_message_id="m1",
        referenced_webhook_id="wh-ceo",
        referenced_author_name="CEO",
    )

    first = bridge.route_reply(context)
    second = bridge.route_reply(context)

    assert first.routed is True
    assert second.routed is False
    assert second.reason == "duplicate_reply"
    assert len(client.comments) == 1
