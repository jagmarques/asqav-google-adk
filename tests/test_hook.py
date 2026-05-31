"""Tests for asqav-google-adk callbacks. No network, no real google-adk."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _install_fake_adk() -> None:
    """Stub google.adk.tools so the package imports without the real framework."""
    if "google.adk.tools" in sys.modules:
        return
    google_pkg = sys.modules.get("google") or types.ModuleType("google")
    adk_pkg = types.ModuleType("google.adk")
    tools_mod = types.ModuleType("google.adk.tools")

    class BaseTool:
        def __init__(self, name="search"):
            self.name = name

    class ToolContext:
        pass

    tools_mod.BaseTool = BaseTool
    tools_mod.ToolContext = ToolContext
    adk_pkg.tools = tools_mod
    google_pkg.adk = adk_pkg
    sys.modules["google"] = google_pkg
    sys.modules["google.adk"] = adk_pkg
    sys.modules["google.adk.tools"] = tools_mod


_install_fake_adk()


@pytest.fixture()
def mock_asqav():
    """Mock asqav so no real API calls are made."""
    mock_agent = MagicMock()
    mock_agent.sign.return_value = MagicMock(signature="mock-sig", timestamp=1.0)
    with (
        patch("asqav.client._api_key", "sk_test_key"),
        patch("asqav.client.Agent.create", return_value=mock_agent),
        patch("asqav.client.Agent.get", return_value=mock_agent),
    ):
        yield mock_agent


def _tool(name="search"):
    from google.adk.tools import BaseTool

    return BaseTool(name=name)


def _ctx():
    from google.adk.tools import ToolContext

    return ToolContext()


class TestAsqavCallbacks:
    def test_before_tool_signs_start_and_allows(self, mock_asqav: MagicMock):
        from asqav_google_adk import AsqavCallbacks

        cb = AsqavCallbacks(agent_name="test-agent")
        result = cb.before_tool_callback(_tool("search"), {"q": "hi"}, _ctx())

        assert result is None  # fail-open allows execution
        mock_asqav.sign.assert_called_once()
        action_type, context = mock_asqav.sign.call_args[0][:2]
        assert action_type == "tool:start"
        assert context["tool"] == "search"

    def test_after_tool_signs_end(self, mock_asqav: MagicMock):
        from asqav_google_adk import AsqavCallbacks

        cb = AsqavCallbacks(agent_name="test-agent")
        result = cb.after_tool_callback(_tool(), {}, _ctx(), {"out": "done"})

        assert result is None  # keep original response
        assert mock_asqav.sign.call_args[0][0] == "tool:end"

    def test_fail_closed_blocks_when_sign_refused(self, mock_asqav: MagicMock):
        from asqav.client import AsqavError

        from asqav_google_adk import AsqavCallbacks

        cb = AsqavCallbacks(agent_name="test-agent", fail_closed=True)
        mock_asqav.sign.side_effect = AsqavError("network error")

        # refused sign -> returns a dict, which ADK uses to skip the tool
        result = cb.before_tool_callback(_tool("delete_file"), {}, _ctx())
        assert isinstance(result, dict)
        assert "error" in result

    def test_fail_open_allows_when_sign_refused(self, mock_asqav: MagicMock):
        from asqav.client import AsqavError

        from asqav_google_adk import AsqavCallbacks

        cb = AsqavCallbacks(agent_name="test-agent")
        mock_asqav.sign.side_effect = AsqavError("network error")

        assert cb.before_tool_callback(_tool("delete_file"), {}, _ctx()) is None
