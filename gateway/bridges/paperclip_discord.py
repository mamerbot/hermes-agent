from __future__ import annotations

"""Route Discord replies to persona webhook messages into Paperclip.

This module is intentionally stdlib-only so the Discord adapter can use it in the
self-hosted gateway without adding runtime dependencies. It never logs or stores
Discord webhook URLs/tokens; routing is keyed by webhook IDs only.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

logger = logging.getLogger(__name__)

OPEN_ISSUE_STATUSES = {"backlog", "todo", "in_progress", "in_review", "blocked"}
PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class DiscordReplyContext:
    channel_id: str
    reply_message_id: str
    reply_text: str
    author_id: str
    author_name: str
    referenced_message_id: str
    referenced_webhook_id: str | None
    referenced_author_name: str | None = None
    guild_id: str | None = None
    thread_id: str | None = None
    attachment_count: int = 0


@dataclass(frozen=True)
class PaperclipDiscordReplyConfig:
    enabled: bool = False
    standup_channel_id: str | None = None
    company_id: str | None = None
    paperclip_base_url: str = "http://127.0.0.1:3100/api"
    paperclip_public_url: str | None = None
    webhook_agent_map: dict[str, str] = field(default_factory=dict)
    webhook_persona_map: dict[str, str] = field(default_factory=dict)
    fallback_issue_id: str | None = None
    wake_agent: bool = False
    source: str = "operator"
    interrupt: bool = False


@dataclass(frozen=True)
class PaperclipRouteResult:
    routed: bool
    reason: str
    agent_id: str | None = None
    issue_id: str | None = None
    comment_id: str | None = None
    persona: str | None = None


class PaperclipClientProtocol(Protocol):
    def list_agent_issues(self, agent_id: str) -> list[dict[str, Any]]: ...
    def create_issue_comment(self, issue_id: str, body: str, source: str = "operator", interrupt: bool = True) -> dict[str, Any]: ...
    def wake_agent(self, agent_id: str) -> dict[str, Any]: ...


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _coerce_mapping(value: Any) -> dict[str, str]:
    if not value:
        return {}
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items() if k is not None and v is not None}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON mapping for Discord/Paperclip bridge config")
            return {}
        return _coerce_mapping(parsed)
    return {}


def _nested_config(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    bridge = raw.get("paperclip_reply_bridge")
    if isinstance(bridge, Mapping):
        return bridge
    return raw


def build_config(raw: Mapping[str, Any] | None = None) -> PaperclipDiscordReplyConfig:
    data = _nested_config(raw or {})
    paperclip_base_url = str(data.get("paperclip_base_url") or "http://127.0.0.1:3100/api").rstrip("/")
    paperclip_public_url = str(data.get("paperclip_public_url") or data.get("paperclip_web_url") or "").rstrip("/")
    if not paperclip_public_url:
        paperclip_public_url = paperclip_base_url[:-4] if paperclip_base_url.endswith("/api") else paperclip_base_url
    return PaperclipDiscordReplyConfig(
        enabled=_coerce_bool(data.get("enabled"), default=False),
        standup_channel_id=str(data.get("standup_channel_id") or data.get("channel_id") or "") or None,
        company_id=str(data.get("company_id") or "") or None,
        paperclip_base_url=paperclip_base_url,
        paperclip_public_url=paperclip_public_url,
        webhook_agent_map=_coerce_mapping(data.get("webhook_agent_map")),
        webhook_persona_map=_coerce_mapping(data.get("webhook_persona_map")),
        fallback_issue_id=str(data.get("fallback_issue_id") or "") or None,
        wake_agent=_coerce_bool(data.get("wake_agent"), default=False),
        source=str(data.get("source") or "operator"),
        interrupt=_coerce_bool(data.get("interrupt"), default=False),
    )


class PaperclipApiClient:
    def __init__(self, base_url: str, company_id: str | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.company_id = company_id
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": "Hermes-Discord-Paperclip-Bridge/1.0"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}

    def list_agent_issues(self, agent_id: str) -> list[dict[str, Any]]:
        if not self.company_id:
            return []
        data = self._request("GET", f"/companies/{self.company_id}/issues")
        if not isinstance(data, list):
            return []
        return [issue for issue in data if issue.get("assigneeAgentId") == agent_id]

    def create_issue_comment(self, issue_id: str, body: str, source: str = "operator", interrupt: bool = True) -> dict[str, Any]:
        data = self._request(
            "POST",
            f"/issues/{issue_id}/comments",
            {"body": body, "source": source, "interrupt": interrupt},
        )
        return data if isinstance(data, dict) else {}

    def wake_agent(self, agent_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/agents/{agent_id}/wakeup", {})
        return data if isinstance(data, dict) else {}


def context_from_discord_message(message: Any) -> DiscordReplyContext | None:
    """Build bridge context from a Discord reply message using duck typing.

    Returns None for non-reply messages or replies whose referenced message is
    not available/resolved. The Discord adapter can call this before normal
    mention gating so webhook replies can be routed without requiring @mamerbot.
    """
    reference = getattr(message, "reference", None)
    if not reference:
        return None
    referenced = getattr(reference, "resolved", None)
    if not referenced:
        return None

    referenced_webhook_id = getattr(referenced, "webhook_id", None)
    if referenced_webhook_id is None:
        return None

    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    ref_author = getattr(referenced, "author", None)
    attachments = getattr(message, "attachments", []) or []
    return DiscordReplyContext(
        channel_id=str(getattr(channel, "id", "")),
        reply_message_id=str(getattr(message, "id", "")),
        reply_text=str(getattr(message, "content", "") or ""),
        author_id=str(getattr(author, "id", "")),
        author_name=str(getattr(author, "display_name", None) or getattr(author, "name", None) or getattr(author, "id", "unknown")),
        referenced_message_id=str(getattr(reference, "message_id", None) or getattr(referenced, "id", "")),
        referenced_webhook_id=str(referenced_webhook_id),
        referenced_author_name=(
            str(getattr(ref_author, "display_name", None) or getattr(ref_author, "name", "")) or None
        ),
        guild_id=str(getattr(guild, "id", "")) if guild else None,
        thread_id=str(getattr(channel, "id", "")) if channel and channel.__class__.__name__.lower().endswith("thread") else None,
        attachment_count=len(attachments),
    )


class PaperclipDiscordReplyBridge:
    def __init__(self, config: PaperclipDiscordReplyConfig, client: PaperclipClientProtocol | None = None):
        self.config = config
        self.client = client or PaperclipApiClient(config.paperclip_base_url, config.company_id)
        self._seen_reply_ids: set[str] = set()

    def route_reply(self, context: DiscordReplyContext) -> PaperclipRouteResult:
        if not self.config.enabled:
            return PaperclipRouteResult(False, "disabled")
        if self.config.standup_channel_id and context.channel_id != self.config.standup_channel_id:
            return PaperclipRouteResult(False, "channel_not_enabled")
        if not context.referenced_webhook_id:
            return PaperclipRouteResult(False, "not_webhook_reply")
        if context.reply_message_id in self._seen_reply_ids:
            return PaperclipRouteResult(False, "duplicate_reply")

        agent_id = self.config.webhook_agent_map.get(str(context.referenced_webhook_id))
        if not agent_id:
            return PaperclipRouteResult(False, "unmapped_webhook")

        persona = self.config.webhook_persona_map.get(str(context.referenced_webhook_id)) or context.referenced_author_name or "persona"
        issue = self._select_issue(agent_id)
        fallback = False
        if not issue:
            if not self.config.fallback_issue_id:
                return PaperclipRouteResult(False, "no_routeable_issue", agent_id=agent_id, persona=persona)
            issue = {"id": self.config.fallback_issue_id, "identifier": "fallback", "title": "coordination fallback"}
            fallback = True

        body = self._format_comment(context, persona, issue, fallback=fallback)
        try:
            comment = self.client.create_issue_comment(
                str(issue["id"]),
                body,
                source=self.config.source,
                interrupt=self.config.interrupt,
            )
            if self.config.wake_agent:
                self.client.wake_agent(agent_id)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("Discord/Paperclip reply bridge failed: %s", exc)
            return PaperclipRouteResult(False, "paperclip_api_error", agent_id=agent_id, issue_id=str(issue.get("id")), persona=persona)

        self._seen_reply_ids.add(context.reply_message_id)
        return PaperclipRouteResult(
            True,
            "routed",
            agent_id=agent_id,
            issue_id=str(issue.get("id")),
            comment_id=str(comment.get("id")) if isinstance(comment, dict) and comment.get("id") else None,
            persona=persona,
        )

    def _select_issue(self, agent_id: str) -> dict[str, Any] | None:
        issues = [i for i in self.client.list_agent_issues(agent_id) if i.get("status") in OPEN_ISSUE_STATUSES]
        if not issues:
            return None
        issues.sort(
            key=lambda issue: (
                PRIORITY_RANK.get(str(issue.get("priority") or "low"), 9),
                0 if issue.get("status") == "in_progress" else 1,
                int(issue.get("issueNumber") or 999999),
            )
        )
        return issues[0]

    def _format_comment(self, context: DiscordReplyContext, persona: str, issue: Mapping[str, Any], fallback: bool = False) -> str:
        note = "\n\nRouting note: used fallback coordination route because no open issue was found for the persona agent." if fallback else ""
        text = context.reply_text.strip() or "(The Discord reply had no text content.)"
        attachment_note = f"\nAttachments: {context.attachment_count}" if context.attachment_count else ""
        issue_label = str(issue.get("identifier") or issue.get("id") or "unknown")
        issue_id = str(issue.get("id") or "")
        ticket_url = f"{self.config.paperclip_public_url}/issues/{issue_id}" if self.config.paperclip_public_url and issue_id else ""
        ticket_line = f"Paperclip ticket: [{issue_label}]({ticket_url})" if ticket_url else f"Paperclip ticket: `{issue_label}`"
        return (
            "[DISCORD_REPLY_REQUIRES_AGENT_RESPONSE]\n"
            f"Operator directive from {context.author_name} via Discord reply to {persona}.\n\n"
            "Action required:\n"
            "- Treat this as a direct question or directive to you.\n"
            "- Answer Mark directly in this issue thread before routine heartbeat work.\n"
            "- Keep the answer short, specific, and grounded in the current issue/project state.\n"
            f"- Include a link back to the ticket when you answer: {ticket_line}\n\n"
            "Discord reply:\n"
            f"> {text}\n\n"
            f"{ticket_line}\n\n"
            "Source metadata:\n"
            f"- Discord reply message: `{context.reply_message_id}`\n"
            f"- Referenced standup message: `{context.referenced_message_id}`\n"
            f"- Referenced webhook ID: `{context.referenced_webhook_id}`\n"
            f"- Routed issue: `{issue_label}`{attachment_note}{note}"
        )
