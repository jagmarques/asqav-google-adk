"""Google ADK tool callbacks that attempt to sign tool:start and tool:end via the
Asqav API. Signing is fail-open by default; an optional fail-closed mode blocks
the tool (returns a response dict, skipping execution) when a tool:start
signature is refused. See README for usage."""

from __future__ import annotations

import logging
from typing import Any

from asqav.extras._base import AsqavAdapter

try:
    from google.adk.tools import BaseTool, ToolContext
except ImportError as err:
    raise ImportError(
        "asqav-google-adk requires google-adk. "
        "Install with: pip install asqav-google-adk"
    ) from err

logger = logging.getLogger("asqav")

_MAX_LEN = 200


class AsqavCallbacks(AsqavAdapter):
    """Attempt to sign Google ADK tool-call events via the Asqav API.

    Signing errors allow execution by default. With ``fail_closed=True``, a
    signing attempt that returns no signature makes the before callback return
    an error dict for ADK to use instead of executing the tool. A failed request
    does not guarantee a receipt. Agent creation or lookup can raise during
    construction; ADK dispatch determines whether the callbacks run.

    Pass the methods as ``before_tool_callback`` and ``after_tool_callback``
    on an ``LlmAgent``.

    Args:
        api_key: Optional API key override (uses ``asqav.init()`` default).
        agent_name: Name for an Asqav agent (calls ``Agent.create``).
        agent_id: ID of an existing Asqav agent (calls ``Agent.get``).
        fail_closed: When True, block a tool if its tool:start sign is refused.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        agent_name: str | None = None,
        agent_id: str | None = None,
        fail_closed: bool = False,
    ) -> None:
        super().__init__(api_key=api_key, agent_name=agent_name, agent_id=agent_id)
        self._fail_closed = fail_closed

    def before_tool_callback(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict | None:
        """Sign tool:start. Returns None to allow; a dict to block (fail-closed)."""
        input_preview = str(args)[:_MAX_LEN] if args else ""
        try:
            sig = self._sign_action(
                "tool:start",
                {
                    "tool": tool.name,
                    "input": input_preview,
                },
            )
        except Exception as exc:
            logger.warning("asqav tool:start signing failed (fail-open): %s", exc)
            sig = None
        # fail-closed: returning a dict makes ADK skip the tool and use this as its result
        if self._fail_closed and sig is None:
            logger.warning("asqav blocked tool %s (fail-closed, sign refused)", tool.name)
            return {"error": "blocked by Asqav: tool:start signature was refused"}
        return None

    def after_tool_callback(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
        tool_response: dict,
    ) -> dict | None:
        """Sign tool:end with output metadata. Returns None to keep the response."""
        try:
            self._sign_action(
                "tool:end",
                {
                    "tool": tool.name,
                    "output_type": type(tool_response).__name__,
                    "output_length": len(str(tool_response)),
                },
            )
        except Exception as exc:
            logger.warning("asqav tool:end signing failed (fail-open): %s", exc)
        return None
