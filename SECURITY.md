# Security Policy

## Reporting Vulnerabilities

Email info@asqav.com with details. We will respond within 48 hours.

Do not open public issues for security vulnerabilities.

## Supported Versions

Only the latest published release is supported.

## Scope

This repository contains asqav-google-adk, the Google ADK integration for Asqav.

Report issues that affect:
- Callback registration and tool-call interception
- Tampering with payloads sent to the Asqav API
- Bypasses that let tool calls run without being signed
- Fail-closed mode failing to block a tool when a signature is refused

Cryptographic signing runs server-side via the Asqav API. Report signing or key-handling issues against [asqav-sdk](https://github.com/jagmarques/asqav-sdk).
