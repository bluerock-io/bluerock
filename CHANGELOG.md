# Changelog

All notable changes to BlueRock are documented here.

## [0.1.0] - 2026-04-17

### Added
- MCP (Model Context Protocol) runtime monitoring -- 6 event types covering the full protocol lifecycle
- Server-side monitoring: tool/resource/prompt registration, request/response handling, session lifecycle
- Client-side monitoring: transport connections (stdio/http/sse/websocket), request/response, session lifecycle
- 10 protocol sub-types in `python_mcp_event`: all request/response/notification directions captured
- Import monitoring -- every module import recorded with file path, SHA-256 hash, and installed version
- Entity correlation via `meta.uuid` -- match client and server events across processes
- Session correlation via `session_id` -- trace full request lifecycle across client/server boundary
- Event spool with automatic file rotation -- 1MB per file, 10MB total cap, oldest files cleaned
- MCP examples: multi-transport client, test server, file server with auth, linux admin (SSE), weather server
- Pre-built wheels for Linux (x86_64 + aarch64) and macOS (x86_64 + arm64) across Python 3.10–3.13
- Sensor auto-discovers `~/.bluerock/bluerock-oss.json` config in OSS mode
- `pip install bluerock[oss]` installs both Python sensor and Rust DSO backend
