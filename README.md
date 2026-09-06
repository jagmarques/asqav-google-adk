<p align="center">
  <a href="https://asqav.com">
    <img src="https://asqav.com/logo-text-white.png" alt="Asqav" width="200">
  </a>
</p>
<p align="center">Record Google ADK tool-call events with Asqav.</p>
<p align="center">
  <a href="https://www.asqav.com/">Website</a> |
  <a href="https://www.asqav.com/docs">Docs</a> |
  <a href="https://github.com/jagmarques/asqav-sdk">SDK</a>
</p>

# Asqav for Google ADK

Uses Google ADK's tool callbacks to attempt signing `tool:start` and `tool:end` events with [Asqav](https://asqav.com). Successful requests produce receipts signed on the Asqav server. Signing failures allow tool execution by default. With `fail_closed=True`, a signing attempt that returns no signature makes the before callback return an error dict, which ADK uses instead of executing the tool.

Asqav governs the agents you wire through it. An agent that never routes through the governed path produces no receipt and is not detected.

## Install

Install the integration and Google ADK from this repository:

```bash
pip install "asqav-google-adk[adk] @ git+https://github.com/jagmarques/asqav-google-adk.git"
```

To use a local checkout, run this from its root:

```bash
pip install ".[adk]"
```

The integration requires Asqav SDK 0.10.10 or newer in the 0.10 series and Google ADK 2.8.0 or newer. Google ADK is a peer dependency; the `[adk]` extra installs it.

## Run an agent

Set `ASQAV_API_KEY` and `ADK_MODEL`, then configure the model provider's credentials. The example calls both the model provider and the Asqav API.

```python
import asyncio
import os

import asqav
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from asqav_google_adk import AsqavCallbacks

asqav.init(api_key=os.environ["ASQAV_API_KEY"], mode="hash-only")
callbacks = AsqavCallbacks(agent_name="my-agent")


def echo_tool(text: str) -> dict:
    """Return the supplied text."""
    return {"echo": text}


agent = LlmAgent(
    model=os.environ["ADK_MODEL"],
    name="echo_agent",
    instruction="Use echo_tool to echo the user's message, then report its response.",
    tools=[echo_tool],
    before_tool_callback=callbacks.before_tool_callback,
    after_tool_callback=callbacks.after_tool_callback,
)


async def main():
    sessions = InMemorySessionService()
    await sessions.create_session(
        app_name="asqav_example", user_id="example_user", session_id="example_session"
    )
    runner = Runner(agent=agent, app_name="asqav_example", session_service=sessions)
    async for event in runner.run_async(
        user_id="example_user",
        session_id="example_session",
        new_message=types.Content(role="user", parts=[types.Part(text="hello world")]),
    ):
        if event.is_final_response() and event.content:
            print(event.content)


asyncio.run(main())
```

Callbacks cover calls dispatched to them by ADK. Model calls and direct calls to tool functions are outside their coverage. Earlier callbacks or plugins can substitute responses or raise before these methods run. Unhandled tool errors can prevent the after callback; a substituted response can still reach it.

The integration does not call `Agent.preflight`; it requests signing directly. Its local gate checks whether signing returned a response, without inspecting that response's policy decision. A signing response is not independent proof of tool execution or approval to perform a real-world action.

## Signing failures

The default callback logs a signing failure and returns `None`, allowing ADK to continue. This includes refused signing requests and outages. Failed requests do not guarantee receipts. Agent creation or lookup happens during `AsqavCallbacks` construction and can raise in either mode.

To have a missing start signature substitute an error response for the tool call:

```python
callbacks = AsqavCallbacks(agent_name="my-agent", fail_closed=True)
```

Pass its methods as `before_tool_callback` and `after_tool_callback` on the agent, as above. ADK controls callback dispatch and response substitution; this is a gate on that tool call, not a guarantee that the agent run stops.

## Callback data

`AsqavCallbacks` extends the Asqav adapter base class and exposes:

- `before_tool_callback(tool, args, tool_context)`: attempts to sign `tool:start` with the tool name and an input preview capped at 200 characters. It returns `None` to continue or an error dict when signing returns no signature in fail-closed mode.
- `after_tool_callback(tool, args, tool_context, tool_response)`: attempts to sign `tool:end` with the tool name, response type and length of its string representation. It returns `None` to preserve the response.

An end event describes the response seen by the after callback. It does not establish that a tool executed or succeeded. An end-signing failure cannot undo completed work.

## Data handling

Configure the SDK mode before constructing the callbacks:

- In `hash-only` mode, the SDK sends a digest of the action and callback context, its byte length, and SDK metadata. The input preview contributes to the digest and is not sent as context.
- In `full-payload` mode, the SDK sends the callback context, including the input preview.

These settings control requests to Asqav. Model providers and tools handle their own traffic separately.

## Configuration

```python
# Use an existing Asqav agent by ID.
callbacks = AsqavCallbacks(agent_id="ag_abc123")

# Set the SDK key and mode together before constructing callbacks.
asqav.init(api_key=os.environ["ASQAV_API_KEY"], mode="hash-only")
callbacks = AsqavCallbacks(agent_name="audit-agent")
```

## License

[Elastic License 2.0](LICENSE)
