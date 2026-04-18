import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.modules.setdefault("fire", types.SimpleNamespace(Fire=lambda *a, **k: None))
sys.modules.setdefault("firecrawl", types.SimpleNamespace(Firecrawl=object))
sys.modules.setdefault("fal_client", types.SimpleNamespace())

from agent.copilot_acp_client import CopilotACPClient


def _build_client(tmp_path: Path) -> CopilotACPClient:
    client = CopilotACPClient(
        acp_command="copilot",
        acp_args=["--acp", "--stdio"],
        acp_cwd=str(tmp_path),
    )
    client.close = lambda: None  # keep the test isolated from process lifecycle
    return client


def test_copilot_acp_client_exposes_responses_namespace(tmp_path):
    client = _build_client(tmp_path)
    assert hasattr(client, "responses")
    assert hasattr(client.responses, "stream")
    assert hasattr(client.responses, "create")


def test_copilot_acp_responses_stream_yields_events_and_final_response(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    monkeypatch.setattr(client, "_run_prompt", lambda prompt_text, timeout_seconds: ("hello world", "thinking"))

    with client.responses.stream(model="gpt-5", input=[{"role": "user", "content": "Hi"}]) as stream:
        events = list(stream)
        final = stream.get_final_response()

    assert events[-1].type == "response.completed"
    assert final.status == "completed"
    assert final.output_text == "hello world"
    assert isinstance(final.output, list)
    assert final.output[0].type == "message"
    assert final.output[0].content[0].type == "output_text"
    assert final.output[0].content[0].text == "hello world"


def test_copilot_acp_responses_create_returns_responses_shape(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    monkeypatch.setattr(client, "_run_prompt", lambda prompt_text, timeout_seconds: ("done", ""))

    response = client.responses.create(model="gpt-5", input="Reply with done")

    assert response.status == "completed"
    assert response.output_text == "done"
    assert isinstance(response.output, list)
    assert response.output[0].type == "message"
    assert response.output[0].content[0].text == "done"


def test_copilot_acp_responses_create_stream_mode_returns_iterable_stream(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    monkeypatch.setattr(client, "_run_prompt", lambda prompt_text, timeout_seconds: ("streamed", ""))

    stream = client.responses.create(model="gpt-5", input="Reply with streamed", stream=True)
    events = list(stream)

    assert events[-1].type == "response.completed"
    assert stream.get_final_response().output_text == "streamed"
