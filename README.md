# Code Conductor

Local control-plane service design for launching and supervising Claude Code and Codex CLI sessions from Telegram.

The conductor is intended to run as a personal WSL service. It starts interactive CLI sessions in tmux, tracks them in SQLite, monitors liveness out of band, and leaves each session's conversation on its own data plane.

## Current Status

This repository contains a working v1 scaffold plus the implementation specification and build prompts:

- `plan.md`: architecture and product spec.
- `IMPLEMENTATION_PLAN.md`: phased build plan.
- `prompts/`: CLI-ready prompts for Claude Code and Codex implementers.
- `conductor/`: Python control-plane package.
- `deploy/`: WSL systemd deployment files.

## Key Local Settings

- `CONDUCTOR_PROJECT_ROOT`: project discovery root. On the target box this is `/home/shaun`.
- `CONDUCTOR_CHANNEL_SLOTS`: Telegram session-bot pool size. Defaults to `5`.

## Customization

Session status/footer text is intended to be configurable in `config.toml` through `[session_footer]`. Footers can include fields such as CLI, model, project folder, context remaining, session id, context limit, data plane, and bot slot. Footer rendering should degrade cleanly when model/context metadata is unavailable.

## Development

```bash
uv venv --python /home/shaun/.local/bin/python3.11 .venv
uv pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check conductor tests
```

Run locally:

```bash
cp config.example.toml config.toml
chmod 600 config.toml
CONDUCTOR_PROJECT_ROOT=/home/shaun CONDUCTOR_CHANNEL_SLOTS=5 \
  .venv/bin/python -m conductor --config config.toml
```

## Non-Goals

- No public web server.
- No conversation proxying.
- No headless Claude `-p` sessions for managed conversations.
- No plan/account quota scraping.
