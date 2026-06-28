# Claude Code CLI Prompt: Build Conductor v1

You are implementing `/home/shaun/conductor` from `plan.md`.

Before writing code, read `plan.md` fully and treat it as the source of truth. The target is a personal, single-user Python 3.11+ Telegram control-plane service that launches and supervises interactive Claude Code sessions in tmux. The conductor must not proxy session conversation.

Local facts already verified on 2026-06-28:

- `claude --version` returns `2.1.195 (Claude Code)`.
- `claude` starts an interactive session by default; do not use `-p`/`--print` for launched sessions.
- `claude` supports `--remote-control [name]`.
- `claude` supports `-r, --resume [value]`.
- `claude` supports `--permission-mode` values including `bypassPermissions`, plus `--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions`.
- `claude` supports `--plugin-dir`, `--plugin-url`, and `plugin` management commands.
- On this box, the conductor project-discovery root comes from `CONDUCTOR_PROJECT_ROOT=/home/shaun`; do not hardcode `/home/shaun/projects`.
- The Telegram session-bot pool size comes from `CONDUCTOR_CHANNEL_SLOTS`, defaulting to `5`; do not hardcode the slot count.

Build v1 only unless a dependency forces a small supporting piece:

- Config loading and validation: `config.toml`, `config.example.toml`, `CONDUCTOR_PROJECT_ROOT`, `CONDUCTOR_CHANNEL_SLOTS`, chmod-600 guidance, `.gitignore`.
- Telegram control bot with hard `allowed_chat_ids` allowlist.
- Numbered project picker rooted at configured `project.root`; reject traversal and resolved paths outside root.
- SQLite registry for `sessions`, `bot_slots`, and `audit`.
- Tmux-backed session lifecycle: start, stop, kill all, reconcile on conductor startup.
- Claude adapter implementing the `CLIAdapter` interface in `plan.md`.
- Bot-slot leasing for `CONDUCTOR_CHANNEL_SLOTS` Telegram session bots, default `5`, with graceful app-only fallback when no slot is available.
- Transcript and idle monitoring enough for v1 liveness and idle reaping.
- Systemd unit and WSL setup docs.
- Configurable session footer support can be implemented after v1 message flow is stable; keep it template-driven for public-repo customization.

Implementation constraints:

- Keep module boundaries from `plan.md`.
- Use `python-telegram-bot` v21+ async APIs, `aiosqlite`, and either `libtmux` or subprocess calls to `tmux`.
- Resolve the project picker root from the env var named by `[project].root_env`; fail fast if `CONDUCTOR_PROJECT_ROOT` is missing, empty, or resolves to an invalid path.
- Resolve channel-slot count from the env var named by `[channels].slot_count_env`; default to `5` if unset, fail fast if not a positive integer, and validate the `[[bot_slots]]` entries match the resolved count.
- Session context footers should be reusable and optional. They can include cli, model, cwd, context remaining, session id, context limit, data plane, and bot slot when known. Do not let missing model/context data block message delivery.
- Do not implement a web server.
- Do not make the conductor a message relay.
- Do not start Claude in non-interactive/print mode.
- Keep bypass scoped per project. Prefer a project `.claude/settings.local.json` merge or a verified current equivalent; do not rely blindly on global dangerous flags.
- Persist bot slot leases in SQLite and release slots on stop/reap.
- Log every accepted command to `audit`; silently drop non-allowlisted chats.
- Use one-session-per-directory locking.

Critical verification gates to complete before locking in implementation:

1. Verify the current Claude Code Remote Control launch behavior from tmux:
   - Start an interactive tmux-launched Claude process with Remote Control enabled.
   - Confirm it appears in Claude Code mobile/web remote-control surfaces.
   - Record the exact launch argv used in code comments or docs.

2. Verify bypass behavior under Remote Control:
   - Check whether `--permission-mode bypassPermissions` works with Remote Control in this installed version.
   - Check whether `.claude/settings.local.json` allow-listing is still needed.
   - Choose the least global mechanism that achieves bypass-by-default for this personal conductor.

3. Verify transcript path and schema:
   - Locate a real session JSONL under `~/.claude`.
   - Implement `transcript_path()` and `parse_usage()` from observed files, not guesses.
   - If context usage cannot be parsed reliably for v1, return `None` and make monitoring degrade cleanly.

4. Verify Telegram channel plugin token injection:
   - Determine whether the official Claude Telegram/channel plugin can be configured per launched process with a distinct bot token.
   - If yes, implement token injection in `ClaudeCodeAdapter.build_launch_cmd`.
   - If no, keep the v1 bot-slot registry and return clear "app-only for now" messages; document the bridge fallback as a v2 task instead of inventing an unsafe relay.

5. Verify new session ID capture:
   - Prefer watching for a new transcript JSONL after launch.
   - Fall back to CLI output parsing only if the transcript approach is unreliable.

Suggested build order:

1. Scaffold package layout, config, `.gitignore`, and `config.example.toml`.
2. Implement SQLite registry and bot slot persistence.
3. Implement Claude adapter with verified launch/resume/transcript behavior.
4. Implement tmux lifecycle manager and startup reconcile.
5. Implement Telegram command handlers for `/start`, `/help`, `/new`, `/projects`, `/sessions`, `/kill`, `/killall`, and `/slots`.
6. Implement idle monitor/reaper.
7. Add docs and systemd deployment files.
8. Run formatting, tests, and a smoke test using a temporary config where possible.

Acceptance checks:

- Non-allowlisted chat IDs receive no response and are logged or safely ignored according to the implemented audit policy.
- `/new` lists only projects under `PROJECT_ROOT` and prevents traversal.
- Starting `claude` with data plane `app` creates a tmux-backed interactive session and surfaces in Remote Control.
- Starting with `telegram` leases a slot when possible; if all slots are leased, the session still starts app-only with a clear message.
- `/sessions` shows cwd, uptime, data plane, and bot slot.
- Idle timeout warns then kills and releases any leased slot.
- Restart reconciles live tmux sessions instead of losing state.

When you finish, report:

- Files created or changed.
- Which verification gates passed.
- Which gates remain blocked by external credentials, Telegram bot tokens, or live Claude mobile setup.
- Exact commands used for tests/smoke checks.
