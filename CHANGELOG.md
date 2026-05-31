# Changelog

All notable changes to `asqav-google-adk` are listed here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [SemVer](https://semver.org/) and track the PyPI release.

## [Unreleased]

## [0.1.0]

Initial release. Google ADK tool callbacks that sign `tool:start` and `tool:end` events on every agent tool call. Fail-open by default, with an optional fail-closed mode that blocks a tool when its start signature is refused.
