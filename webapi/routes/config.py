from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hermes_cli.config import load_config, save_config
from webapi.deps import get_config, get_runtime_agent_kwargs, get_runtime_model
from webapi.models.config import ConfigResponse


router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigPatch(BaseModel):
    model: str | None = None
    provider: str | None = None
    base_url: str | None = None


@router.get("", response_model=ConfigResponse)
async def get_web_config() -> ConfigResponse:
    runtime = get_runtime_agent_kwargs()
    raw_model = get_runtime_model()
    # Upstream now returns dict {'default': 'model', 'provider': 'x'} instead of str
    if isinstance(raw_model, dict):
        model_str = raw_model.get("default", raw_model.get("model", str(raw_model)))
    else:
        model_str = raw_model
    return ConfigResponse(
        model=model_str,
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        base_url=runtime.get("base_url"),
        config=get_config(),
    )


@router.patch("")
async def patch_web_config(patch: ConfigPatch) -> dict[str, Any]:
    """Patch ~/.hermes/config.yaml with the provided model fields.
    Persist settings into the nested `model:` mapping used by current Hermes
    config, while preserving older string-style configs when possible.
    """
    try:
        config = load_config()
        model_cfg = config.get("model")
        if isinstance(model_cfg, dict):
            next_model = dict(model_cfg)
        elif isinstance(model_cfg, str) and model_cfg.strip():
            next_model = {"default": model_cfg.strip()}
        else:
            next_model = {}

        if patch.model is not None:
            next_model["default"] = patch.model
        if patch.provider is not None:
            if patch.provider.strip():
                next_model["provider"] = patch.provider.strip()
            else:
                next_model.pop("provider", None)
        if patch.base_url is not None:
            if patch.base_url.strip():
                next_model["base_url"] = patch.base_url.strip()
            else:
                next_model.pop("base_url", None)

        config["model"] = next_model
        save_config(config)
        return {
            "ok": True,
            "model": next_model.get("default"),
            "provider": next_model.get("provider"),
            "base_url": next_model.get("base_url"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
