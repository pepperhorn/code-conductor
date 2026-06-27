# Code Conductor

Local control-plane service design for launching and supervising Claude Code and Codex CLI sessions from Telegram.

The conductor is intended to run as a personal WSL service. It starts interactive CLI sessions in tmux, tracks them in SQLite, monitors liveness out of band, and leaves each session's conversation on its own data plane.

## Current Status

This repository currently contains the implementation specification and build prompts:

- `plan.md`: architecture and product spec.
- `IMPLEMENTATION_PLAN.md`: phased build plan.
- `prompts/`: CLI-ready prompts for Claude Code and Codex implementers.

## Key Local Settings

- `CONDUCTOR_PROJECT_ROOT`: project discovery root. On the target box this is `/home/shaun`.
- `CONDUCTOR_CHANNEL_SLOTS`: Telegram session-bot pool size. Defaults to `5`.

## Non-Goals

- No public web server.
- No conversation proxying.
- No headless Claude `-p` sessions for managed conversations.
- No plan/account quota scraping.
