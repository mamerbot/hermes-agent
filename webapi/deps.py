import os
import uuid
from functools import lru_cache
from typing import Any

from fastapi import HTTPException

from hermes_cli.config import load_config
from hermes_cli.runtime_provider import format_runtime_provider_error, resolve_runtime_provider

def _extract_model_string(model_value) -> str:
    """Extract the model string from config, handling both str and dict formats.

    Config can be either:
      model: "claude-opus-4-6"                    # flat string
      model: { default: "claude-opus-4-6", provider: "anthropic" }  # nested dict
    """
    if isinstance(model_value, str):
        return model_value
    if isinstance(model_value, dict):
        return model_value.get("default", model_value.get("model", ""))
    return ""


def _extract_provider_string(config: dict) -> str:
    """Extract provider from config, checking both top-level and nested model dict."""
    model_value = config.get("model")
    if isinstance(model_value, dict):
        provider = model_value.get("provider", "")
        if provider:
            return provider
    return config.get("provider", os.getenv("HERMES_PROVIDER", "anthropic"))


try:
    from gateway.run import _resolve_runtime_agent_kwargs as _gateway_resolve_runtime_agent_kwargs
except ImportError:
    _gateway_resolve_runtime_agent_kwargs = None


def _resolve_model() -> str:
    """Default model id for webapi agents — always a string (never the raw model dict)."""
    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        name = model_cfg.get("default") or model_cfg.get("model") or ""
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(model_cfg, str) and model_cfg.strip():
        return model_cfg.strip()
    return os.getenv("HERMES_MODEL", "claude-sonnet-4-5")


def _resolve_runtime_agent_kwargs() -> dict[str, Any]:
    if _gateway_resolve_runtime_agent_kwargs is not None:
        return _gateway_resolve_runtime_agent_kwargs()
    try:
        runtime = resolve_runtime_provider(
            requested=os.getenv("HERMES_INFERENCE_PROVIDER"),
        )
    except Exception as exc:
        raise RuntimeError(format_runtime_provider_error(exc)) from exc
    return {
        "api_key": runtime.get("api_key"),
        "base_url": runtime.get("base_url"),
        "provider": runtime.get("provider"),
        "api_mode": runtime.get("api_mode"),
        "command": runtime.get("command"),
        "args": list(runtime.get("args") or []),
        "credential_pool": runtime.get("credential_pool"),
    }

from hermes_state import SessionDB
from run_agent import AIAgent
from tools.memory_tool import MemoryStore


WEB_SOURCE = "web"


@lru_cache(maxsize=1)
def get_session_db() -> SessionDB:
    return SessionDB()


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    store = MemoryStore()
    store.load_from_disk()
    return store


def reload_memory_store() -> MemoryStore:
    store = get_memory_store()
    store.load_from_disk()
    return store


def get_config() -> dict[str, Any]:
    return load_config()


def get_runtime_model() -> str:
    """Return the configured model as a plain string, re-reading config each time.

    Some code paths return a dict {'default': '...', 'provider': '...'} instead
    of a bare string. We normalize here so callers always get a usable model ID.
    """
    raw = _resolve_model()
    return _extract_model_string(raw) or "claude-sonnet-4-5"


def get_runtime_agent_kwargs() -> dict[str, Any]:
    """Return runtime kwargs (provider, base_url, etc.), always fresh."""
    return _resolve_runtime_agent_kwargs()


def create_agent(
    *,
    session_id: str,
    session_db: SessionDB,
    model: str | None = None,
    ephemeral_system_prompt: str | None = None,
    enabled_toolsets: list[str] | None = None,
    disabled_toolsets: list[str] | None = None,
    skip_context_files: bool = False,
    skip_memory: bool = False,
    stream_callback=None,
    tool_progress_callback=None,
    thinking_callback=None,
    reasoning_callback=None,
    step_callback=None,
) -> AIAgent:
    runtime_kwargs = get_runtime_agent_kwargs()
    raw = model or get_runtime_model()
    if isinstance(raw, dict):
        raw = raw.get("default") or raw.get("model") or ""
    effective_model = (raw if isinstance(raw, str) else str(raw)).strip() or _resolve_model()
    max_iterations = int(os.getenv("HERMES_MAX_ITERATIONS", "90"))

    return AIAgent(
        model=effective_model,
        **runtime_kwargs,
        max_iterations=max_iterations,
        quiet_mode=True,
        verbose_logging=False,
        ephemeral_system_prompt=ephemeral_system_prompt,
        session_id=session_id,
        platform="webapi",
        session_db=session_db,
        enabled_toolsets=enabled_toolsets,
        disabled_toolsets=disabled_toolsets,
        skip_context_files=skip_context_files,
        skip_memory=skip_memory,
        tool_progress_callback=tool_progress_callback,
        thinking_callback=thinking_callback,
        reasoning_callback=reasoning_callback,
        step_callback=step_callback,
    )


def get_session_or_404(session_id: str, session_db: SessionDB | None = None) -> dict[str, Any]:
    db = session_db or get_session_db()
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


def ensure_session_title(session_db: SessionDB, title: str | None) -> str | None:
    cleaned = session_db.sanitize_title(title)
    if cleaned:
        return cleaned
    return session_db.get_next_title_in_lineage("New Chat")


def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex}"
