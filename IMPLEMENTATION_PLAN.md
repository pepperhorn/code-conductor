# Conductor Implementation Plan

This is the build plan for `plan.md`. It keeps v1 focused on a working local conductor for Claude Code, while leaving Codex behind the adapter boundary until the shared lifecycle is stable.

## Build Inputs

- Conductor install directory: `/home/shaun/conductor`
- Project picker root: `CONDUCTOR_PROJECT_ROOT`, set to `/home/shaun` on this box
- Telegram channel slot count: `CONDUCTOR_CHANNEL_SLOTS`, default `5`; target install uses `4`
- Primary CLI target for v1: Claude Code
- Codex target for v1: adapter stub only, unless the core lifecycle needs a neutral interface check

## Phase 0: Verify Drifting CLI Facts

Do this before writing behavior that depends on Claude or Codex internals.

1. Verify Claude Code launch behavior:
   - Confirm `claude --version`.
   - Confirm interactive launch from inside tmux works.
   - Confirm `claude --remote-control <name>` from tmux appears in Claude mobile or `claude.ai/code`.

2. Verify Claude bypass behavior:
   - Test `--permission-mode bypassPermissions` with Remote Control.
   - Test scoped `.claude/settings.local.json` allow-list behavior.
   - Use the least global option that suppresses prompts for this personal conductor.

3. Verify Claude transcript behavior:
   - Locate the current `~/.claude/projects/.../*.jsonl` path for a real session.
   - Confirm the cwd slug rule.
   - Confirm whether usage/context data is present.

4. Verify Telegram channel token injection:
   - Determine whether the Claude Telegram/channel plugin accepts a per-process bot token.
   - If not, keep Telegram slot leasing in state but degrade starts to app-only.

5. Verify Codex basics for later:
   - Confirm `codex --version`.
   - Confirm `codex --cd <dir>` and `codex resume <session_id>` syntax.
   - Do not block v1 on Codex data-plane features.

## Phase 1: Project Skeleton

Create the Python package and deployment files:

- `conductor/__main__.py`
- `conductor/config.py`
- `conductor/telegram/control_bot.py`
- `conductor/telegram/keyboards.py`
- `conductor/sessions/manager.py`
- `conductor/sessions/registry.py`
- `conductor/sessions/reaper.py`
- `conductor/monitor/transcript.py`
- `conductor/monitor/thresholds.py`
- `conductor/channels/bot_pool.py`
- `conductor/channels/remote_control.py`
- `conductor/adapters/base.py`
- `conductor/adapters/claude_code.py`
- `conductor/adapters/codex.py`
- `deploy/conductor.service`
- `deploy/setup-wsl.md`
- `config.example.toml`
- `.gitignore`
- `pyproject.toml`

Use Python 3.11+, `python-telegram-bot` v21+, `aiosqlite`, `watchfiles`, and either `libtmux` or subprocess calls to `tmux`.

## Phase 2: Configuration

Implement config loading before any runtime work.

- Read `config.toml`.
- Validate `config.toml` permissions or warn clearly if not `0600`.
- Resolve `[project].root_env`.
- Require `CONDUCTOR_PROJECT_ROOT` to be present, non-empty, and an existing directory.
- Reject any resolved project root that cannot be canonicalized.
- Resolve `[channels].slot_count_env`.
- Default `CONDUCTOR_CHANNEL_SLOTS` to `5` when unset.
- Reject non-integer, zero, or negative slot counts.
- Require `[[bot_slots]]` count to match resolved channel slot count.
- Require `telegram.allowed_chat_ids` to be non-empty.

Deliverable: a typed config object that all other modules consume.

## Phase 3: SQLite Registry

Implement persistence with explicit state transitions.

- Create tables: `sessions`, `bot_slots`, `audit`.
- Seed/update `bot_slots` from config at startup.
- Preserve existing leases when tokens/names still match.
- Fail fast on duplicate slot names.
- Provide methods for session create/update/list/mark-dead.
- Provide methods for slot lease/release/assign.
- Provide audit insertion for accepted commands and important lifecycle events.

Deliverable: registry unit tests using a temp SQLite database.

## Phase 4: Adapter Boundary

Implement the shared adapter interface first.

- `adapters/base.py`: `Usage`, `ResumableSession`, `CLIAdapter`.
- `adapters/claude_code.py`: verified launch/resume/transcript/bypass behavior.
- `adapters/codex.py`: explicit stub or minimal lifecycle implementation based on verified CLI syntax.

Claude launch rules:

- Always launch interactive Claude, never `-p`/`--print`.
- Include Remote Control for app data plane if verified.
- Apply scoped bypass behavior before launch when configured.
- For Telegram data plane, inject a leased bot token only if the plugin supports it.
- If Telegram injection is unsupported, return a clear unsupported capability result so the manager can degrade to app-only.

Codex rules:

- Remote Control and Claude Telegram channels are unsupported.
- Do not lease Telegram slots for Codex.
- Degrade Codex data plane to tmux instructions.

Deliverable: adapter tests for command construction and unsupported capability handling.

## Phase 5: Tmux Lifecycle Manager

Build process control around tmux.

- Generate stable tmux session/window names from CLI, cwd, and session id.
- Enforce one live session per directory.
- Start a tmux target and send the adapter launch argv.
- Capture Claude session id by watching transcript creation first; use CLI output parsing only if verified.
- Stop sessions by killing the tmux target.
- Release any leased slot on stop.
- Mark missing tmux targets as dead.
- Reconcile registry state at startup.

Deliverable: lifecycle tests with tmux command calls isolated behind a small wrapper.

## Phase 6: Project Picker

Implement project discovery.

- Walk only under resolved `CONDUCTOR_PROJECT_ROOT`.
- Respect `max_depth`.
- Reject `..` and symlink/path escapes.
- Render numbered inline keyboards.
- Include git branch/dirty flag only if cheap and reliable.

Deliverable: tests for traversal rejection, max depth, and keyboard pagination.

## Phase 7: Telegram Control Bot

Implement the v1 command surface.

- Drop non-allowlisted chats silently.
- Audit accepted commands.
- `/start`
- `/help`
- `/new`
- `/projects`
- `/sessions`
- `/kill <id>`
- `/killall`
- `/slots`

Callback flows:

- Select project.
- Select CLI.
- Select data plane.
- Confirm start.
- Show reach instructions.

Output rules:

- Telegram messages over 4096 chars must be paginated or sent as a file.
- Status cards should be compact: cli, cwd, uptime, idle, data plane, bot slot.
- Add reusable footer formatting after the core message flow is stable.

Deliverable: handler tests for allowlist, command routing, and callback state.

## Phase 8: Monitoring And Reaper

Implement the minimum v1 monitor.

- Track liveness from tmux/process state.
- Track last activity from adapter transcript path when available.
- Fall back to tmux pane activity/mtime for Codex or unsupported transcripts.
- Warn after `idle_warning_minutes`.
- Kill after `idle_timeout_minutes`.
- Release bot slots on reaping.
- Detect dead processes and mark sessions dead.

Defer context threshold nudges to v2 unless transcript usage parsing is already verified and cheap.

Deliverable: reaper tests using fake sessions and fake clocks.

## Phase 8.5: Configurable Session Footers

Add this after the core message flow is stable.

- Add `[session_footer]` config with `enabled` and `template`.
- Support placeholders: `{cli}`, `{model}`, `{cwd}`, `{context_remaining}`, `{session_id}`, `{context_limit}`, `{data_plane}`, `{bot_slot}`.
- Render missing values as `unknown` or `-`.
- Keep footer rendering non-fatal; message delivery must continue if a field is unavailable.
- Use the footer on conductor-originated session messages first: start result, `/sessions`, `/status`, idle warnings, reaper notifications.
- Do not assume the conductor can modify official Claude Telegram channel messages. If the data plane is sent directly by Claude's plugin, footer support applies only to conductor messages until a conductor-managed bridge exists.

Deliverable: formatter tests covering complete metadata, missing metadata, disabled footers, and unknown template placeholders.

## Phase 9: Deployment

Make local WSL deployment repeatable.

- Write `deploy/conductor.service`.
- Include `Environment=CONDUCTOR_PROJECT_ROOT=/home/shaun`.
- Include `Environment=CONDUCTOR_CHANNEL_SLOTS=4` for the target install.
- Document optional `EnvironmentFile` override.
- Write `deploy/setup-wsl.md` with systemd, Task Scheduler, and smoke-check steps.

Deliverable: docs that can be followed from a fresh checkout on this box.

## Phase 10: End-To-End Validation

Run these checks before calling v1 done.

- Config loads with `CONDUCTOR_PROJECT_ROOT=/home/shaun`.
- Config defaults `CONDUCTOR_CHANNEL_SLOTS` to `5` when unset.
- Invalid slot count fails startup.
- Bot slot count mismatch fails startup.
- Non-allowlisted Telegram chat receives no response.
- `/new` lists projects under `/home/shaun`.
- Traversal outside `/home/shaun` is rejected.
- Claude app session starts in tmux.
- Claude Remote Control sees the session.
- Bypass works in the chosen verified mode.
- `/sessions` shows the live session.
- `/kill` kills tmux and releases the slot.
- Idle reaper warns, then kills, then releases the slot.
- Restart reconciliation preserves surviving tmux sessions and marks missing ones dead.

## Build Order Summary

1. Verify CLI drift points.
2. Scaffold package and config files.
3. Implement config parsing and validation.
4. Implement SQLite registry and bot slot model.
5. Implement adapter interface and Claude adapter.
6. Implement tmux lifecycle manager.
7. Implement project picker.
8. Implement Telegram control bot.
9. Implement monitor/reaper.
10. Add deployment docs and systemd unit.
11. Run unit tests and one live smoke test.

## Do Not Build In v1

- A conversation relay.
- A public web server.
- Headless Claude `-p` sessions.
- Plan/account quota scraping.
- Codex Remote Control parity.
- Telegram bridge fallback unless token injection is proven impossible and explicitly promoted to scope.
