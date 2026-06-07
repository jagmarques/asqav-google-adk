<p align="center">
  <a href="https://asqav.com">
    <img src="https://asqav.com/logo-text-white.png" alt="Asqav" width="200">
  </a>
</p>
<p align="center">
  Stop a rogue agent before it acts, and prove what it tried.
</p>
<p align="center">
  <a href="https://www.asqav.com/">Website</a> |
  <a href="https://www.asqav.com/docs">Docs</a> |
  <a href="https://github.com/jagmarques/asqav-sdk">SDK</a>
</p>

# Asqav for Google ADK

Stop a rogue agent before it acts, and prove what it tried.

Uses the Google Agent Development Kit [tool callbacks](https://adk.dev/callbacks/types-of-callbacks/) (`before_tool_callback` and `after_tool_callback`) to sign every tool invocation with [Asqav](https://asqav.com), producing a tamper-evident record of what your agent attempted. By default the integration observes and records (fail-open, never blocks). Turn on fail-closed mode to block a tool the moment Asqav refuses to sign its start event.

## Install

Not yet on PyPI. Install from GitHub:

```bash
pip install "git+https://github.com/jagmarques/asqav-google-adk.git"
```

Once published, the install will be:

```bash
pip install asqav-google-adk
```

This pulls in the `asqav` SDK. Google ADK itself is a peer dependency you install separately (or via the `adk` extra):

```bash
pip install "asqav-google-adk[adk]"
```

## Usage

```python
import asqav
from google.adk.agents import LlmAgent
from asqav_google_adk import AsqavCallbacks

asqav.init(api_key="sk_...")

cb = AsqavCallbacks(agent_name="my-agent")

agent = LlmAgent(
    model="gemini-2.0-flash",
    name="assistant",
    tools=[...],
    before_tool_callback=cb.before_tool_callback,
    after_tool_callback=cb.after_tool_callback,
)
```

Every tool call your agent makes produces signed `tool:start` and `tool:end` events through the Asqav API. Signing runs server-side with NIST FIPS 204 ML-DSA cryptography, so the audit trail is tamper-evident and holds up for EU AI Act, DORA, and SOC 2 evidence.

## Fail-open vs fail-closed

By default signing is fail-open. If the Asqav API is unreachable, a warning is logged but the tool call proceeds normally. Your agent never breaks because of governance:

```python
cb = AsqavCallbacks(agent_name="my-agent")  # observe and record only
```

To stop a rogue agent before it acts, enable fail-closed mode. When Asqav refuses to sign a tool's start event, `before_tool_callback` returns a response dict. In ADK, a dict returned from `before_tool_callback` is used in place of running the tool, so execution is skipped. The attempt is still recorded:

```python
cb = AsqavCallbacks(agent_name="my-agent", fail_closed=True)  # block on refused sign
```

## How it works

`AsqavCallbacks` extends the Asqav adapter base class and exposes two ADK callbacks:

- `before_tool_callback(tool, args, tool_context)` - signs `tool:start` with tool name and an input preview. Returns `None` to allow the tool to run, or a dict to block it (fail-closed).
- `after_tool_callback(tool, args, tool_context, tool_response)` - signs `tool:end` with tool name and output metadata. Returns `None` so the original tool response is kept unchanged.

These signatures match the ADK `BeforeToolCallback` and `AfterToolCallback` type aliases: returning `None` from `before_tool_callback` lets execution proceed, and returning a non-empty dict skips the tool and uses that dict as its response.

## Data handling

`asqav-google-adk` is a thin wrapper around the `asqav` Python SDK and inherits its mode behavior:

- Asqav cloud (`*.asqav.com`): the SDK hashes your action context locally and sends only the hash plus a small metadata bag. Raw prompts and tool arguments never leave your infrastructure.
- Self-hosted: the SDK sends the full context so the server can run policy checks, PII redaction, and richer audit views.

You can override per call:

```python
import asqav

asqav.init(api_key="sk_...", base_url="https://api.asqav.com", mode="hash-only")
```

See the [SDK fingerprint spec](https://github.com/jagmarques/asqav-sdk/blob/main/docs/fingerprint-spec.md) for the canonicalization and conformance vectors.

## Configuration

```python
# Use an existing Asqav agent by ID
cb = AsqavCallbacks(agent_id="ag_abc123")

# Override the API key
cb = AsqavCallbacks(api_key="sk_other", agent_name="audit-agent")
```

## License

MIT
