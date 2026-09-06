"""Exercise the installed ADK Runner separately from the fake-module unit tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", [
    "success", "refused_open", "refused_closed", "outage_open", "outage_closed",
    "end_refused", "end_outage", "preflight_refused", "preflight_outage",
    "signed_deny", "prior_before_response", "prior_before_error",
    "prior_after_response", "tool_error", "scalar_response", "none_response",
    "full_payload", "constructor_refused",
])
def test_readme_through_real_adk(case, tmp_path):
    result = subprocess.run(
        [sys.executable, __file__, case],
        env=dict(os.environ, TMPDIR=str(tmp_path)),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS installed ADK" in result.stdout
    print(result.stdout, end="")


def run_probe(case: str, *, disable_before: bool = False) -> dict:
    """Use real callbacks, model dispatch and SDK; replace only model and HTTP."""
    import functools
    import hashlib
    import json
    import re
    import socket
    from importlib.metadata import version
    from unittest.mock import patch

    os.environ.update(
        ASQAV_API_KEY="sk_test_no_network",
        ADK_MODEL="asqav-offline-test",
        OTEL_SDK_DISABLED="true",
    )

    import google.adk
    import httpx
    from asqav.canonicalize import canonicalize_action
    from asqav.client import APIError
    from google.adk.agents import LlmAgent
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.models.registry import LLMRegistry
    from google.adk.tools import BaseTool, ToolContext
    from google.adk.tools.function_tool import FunctionTool
    from google.genai import types

    from asqav_google_adk import AsqavCallbacks

    assert Path(google.adk.__file__).is_file(), "ADK must be an installed framework"
    state = {"tools": 0, "model_calls": 0, "requests": [], "order": [], "callbacks": []}
    closed = case in {"refused_closed", "outage_closed", "signed_deny"}
    blocked = case in {"refused_closed", "outage_closed"}
    error = RuntimeError("local callback or tool failure")
    replacement = {"substituted": "local response"}
    blocked_response = {"error": "blocked by Asqav: tool:start signature was refused"}
    expected_response = blocked_response if blocked else {"echo": "hello world"}
    if case in {"prior_before_response", "prior_after_response"}:
        expected_response = replacement
    elif case == "scalar_response":
        expected_response = {"result": "scalar"}
    elif case == "none_response":
        expected_response = {"result": None}

    class LocalModel(BaseLlm):
        @classmethod
        def supported_models(cls):
            return ["asqav-offline-test"]

        async def generate_content_async(self, llm_request, stream=False):
            state["model_calls"] += 1
            assert state["model_calls"] <= 2, "Unexpected model retry"
            if state["model_calls"] == 1:
                content = types.Content(role="model", parts=[types.Part.from_function_call(
                    name="echo_tool", args={"text": "hello world"},
                )])
            else:
                responses = [p.function_response.response for c in llm_request.contents
                             for p in c.parts or [] if p.function_response]
                if not disable_before:
                    assert responses[-1] == expected_response, responses
                content = types.Content(role="model", parts=[types.Part(text="checked")])
            yield LlmResponse(content=content)

    LLMRegistry.register(LocalModel)
    original_init = AsqavCallbacks.__init__
    original_before = AsqavCallbacks.before_tool_callback
    original_after = AsqavCallbacks.after_tool_callback
    original_tool = FunctionTool.run_async
    original_agent_init = LlmAgent.__init__

    def configure(callbacks, **kwargs):
        kwargs.setdefault("fail_closed", closed)
        original_init(callbacks, **kwargs)
        state["callbacks"].append(callbacks)

    @functools.wraps(original_before)
    def before(callbacks, tool, args, tool_context):
        assert isinstance(tool, BaseTool) and isinstance(tool_context, ToolContext)
        assert tool.name == "echo_tool" and args == {"text": "hello world"}
        state["order"].append("before")
        result = None if disable_before else original_before(callbacks, tool, args, tool_context)
        assert result == (blocked_response if blocked and not disable_before else None)
        return result

    @functools.wraps(original_after)
    def after(callbacks, tool, args, tool_context, tool_response):
        assert isinstance(tool, BaseTool) and isinstance(tool_context, ToolContext)
        assert tool.name == "echo_tool" and args == {"text": "hello world"}
        state["order"].append("after")
        state["after_response"] = tool_response
        assert original_after(callbacks, tool, args, tool_context, tool_response) is None

    async def counted_tool(tool, *, args, tool_context):
        state["tools"] += 1
        state["order"].append("tool")
        if case == "tool_error":
            raise error
        response = await original_tool(tool, args=args, tool_context=tool_context)
        if case == "scalar_response":
            return "scalar"
        return None if case == "none_response" else response

    def earlier_callback(**kwargs):
        if case == "prior_before_error":
            raise error
        return replacement

    def configure_agent(adk_agent, **kwargs):
        if case in {"prior_before_response", "prior_before_error"}:
            kwargs["before_tool_callback"] = [earlier_callback, kwargs["before_tool_callback"]]
        if case == "prior_after_response":
            kwargs["after_tool_callback"] = [earlier_callback, kwargs["after_tool_callback"]]
        original_agent_init(adk_agent, **kwargs)

    def send(_client, request, **kwargs):
        assert request.url.host == "api.asqav.com", request.url
        body = json.loads(request.content) if request.content else None
        state["requests"].append((request.method, request.url.path, body))
        if request.url.path.endswith("/status") or request.url.path.endswith("/policies"):
            if case == "preflight_outage":
                raise httpx.ConnectError("local preflight outage", request=request)
            return httpx.Response(403, json={"detail": "local preflight refusal"}, request=request)
        if request.url.path.endswith("/agents/create") or request.method == "GET":
            if case == "constructor_refused":
                return httpx.Response(403, json={"detail": "local create refusal"}, request=request)
            data = {
                "agent_id": "agent_test", "name": (body or {}).get("name", "test-agent"),
                "public_key": "test_key", "key_id": "test_kid", "algorithm": "ml-dsa-65",
                "capabilities": [], "created_at": 0,
            }
        else:
            assert request.url.path.endswith("/agents/agent_test/sign"), request.url
            action = body["action_type"]
            state["order"].append(action)
            if (action == "tool:start" and case.startswith("outage")) or (
                action == "tool:end" and case == "end_outage"
            ):
                raise httpx.ConnectError("local signing outage", request=request)
            if (action == "tool:start" and case.startswith("refused")) or (
                action == "tool:end" and case == "end_refused"
            ):
                return httpx.Response(403, json={"detail": "local sign refusal"}, request=request)
            data = {
                "signature": "test_signature", "signature_id": f"fixture_{action}",
                "action_id": "action_test", "timestamp": 0,
                "verification_url": "https://example.invalid/fixture",
                "policy_decision": "deny" if case == "signed_deny" else "permit",
            }
        return httpx.Response(200, json=data, request=request)

    readme = Path(__file__).resolve().parents[1] / "README.md"
    blocks = re.findall(r"```python\n(.*?)```", readme.read_text(), re.S)
    code = blocks[0]
    if case == "full_payload":
        code = code.replace('mode="hash-only"', 'mode="full-payload"')
    namespace = {}
    with (
        patch.object(AsqavCallbacks, "__init__", configure),
        patch.object(AsqavCallbacks, "before_tool_callback", before),
        patch.object(AsqavCallbacks, "after_tool_callback", after),
        patch.object(FunctionTool, "run_async", counted_tool),
        patch.object(LlmAgent, "__init__", configure_agent),
        patch.object(httpx.Client, "send", send),
        patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
        patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Network forbidden")),
    ):
        try:
            exec(compile(code, str(readme), "exec"), namespace)
        except (RuntimeError, APIError) as exc:
            if case in {"prior_before_error", "tool_error"}:
                assert exc is error
            else:
                assert case == "constructor_refused" and isinstance(exc, APIError)
        else:
            assert case not in {"prior_before_error", "tool_error", "constructor_refused"}
        if case == "success":
            for block in blocks[1:]:
                exec(compile(block, str(readme), "exec"), namespace)

    expected_tools = 0 if blocked or case.startswith("prior_before") or (
        case == "constructor_refused"
    ) else 1
    assert state["tools"] == expected_tools, state
    assert state["model_calls"] == (
        0 if case == "constructor_refused" else 1 if case in {
            "prior_before_error", "tool_error"
        } else 2
    ), state
    assert not any(path.endswith(("/status", "/policies")) for _, path, _ in state["requests"])
    start_expected = case not in {
        "prior_before_response", "prior_before_error", "constructor_refused"
    }
    end_expected = case not in {
        "prior_before_error", "prior_after_response", "tool_error", "constructor_refused"
    }
    expected_order = (["before", "tool:start"] if start_expected else [])
    if expected_tools:
        expected_order += ["tool"]
    if end_expected:
        expected_order += ["after", "tool:end"]
    assert state["order"] == expected_order, state
    signatures = state["callbacks"][0]._signatures if state["callbacks"] else []
    successful_start = start_expected and not case.startswith(("refused", "outage"))
    successful_end = end_expected and case not in {"end_refused", "end_outage"}
    expected_ids = (["fixture_tool:start"] if successful_start else [])
    expected_ids += ["fixture_tool:end"] if successful_end else []
    assert [sig.signature_id for sig in signatures] == expected_ids
    if case == "signed_deny":
        assert signatures[0].policy_decision == "deny"
    sign_bodies = [body for _, path, body in state["requests"] if path.endswith("/sign")]
    for body in sign_bodies:
        context = {"tool": "echo_tool", "input": "{'text': 'hello world'}"}
        if body["action_type"] == "tool:end":
            response = state["after_response"]
            context = {"tool": "echo_tool", "output_type": type(response).__name__,
                       "output_length": len(str(response))}
        if case == "full_payload":
            assert body["context"] == context
        else:
            expected_bytes = canonicalize_action(body["action_type"], context)
            assert "context" not in body
            assert body["hash"] == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()
            assert body["payload_size"] == len(expected_bytes)
    print(f"PASS installed ADK {version('google-adk')} / Asqav {version('asqav')}: "
          f"case={case} tools={state['tools']} order={state['order']} retained={expected_ids}")
    return state


if __name__ == "__main__":
    run_probe(sys.argv[1])
