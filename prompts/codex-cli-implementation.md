# Codex CLI Prompt: Implement Codex Adapter for Conductor

You are implementing the Codex-specific side of `/home/shaun/conductor` from `plan.md`. Read `plan.md` fully before editing.

Scope: implement `adapters/codex.py` and any small shared changes needed so the conductor can manage Codex CLI session lifecycle through the same `CLIAdapter` interface as Claude. Do not add Claude-only Remote Control or Telegram channel behavior to Codex.

Local facts already verified on 2026-06-28:

- `codex --version` returns `codex-cli 0.142.0`.
- Running `codex [OPTIONS] [PROMPT]` without a subcommand starts the interactive CLI.
- `codex resume [SESSION_ID] [PROMPT]` resumes a previous interactive session.
- `codex resume --last` resumes the most recent session.
- `codex resume --all` shows all sessions and disables cwd filtering.
- `codex` supports `-C, --cd <DIR>`.
- `codex` supports `-s, --sandbox <read-only|workspace-write|danger-full-access>`.
- `codex` supports `-a, --ask-for-approval <untrusted|on-failure|on-request|never>`.
- `codex` supports `--dangerously-bypass-approvals-and-sandbox`.
- `codex` supports `--remote <ADDR>` and `remote-control`/`app-server` experimental commands, but these are Codex-specific and not the same as Claude Code Remote Control.
- On this box, the conductor project-discovery root comes from `CONDUCTOR_PROJECT_ROOT=/home/shaun`; do not hardcode `/home/shaun/projects`.

Behavior to implement:

- `CodexAdapter.name = "codex"`.
- `build_launch_cmd(cwd, *, bypass, data_plane, bot_token)` returns argv for an interactive Codex TUI session.
- `build_resume_cmd(session_id, cwd, *, bypass, data_plane, bot_token)` returns argv for interactive resume.
- `list_resumable(cwd)` returns known prior sessions for that cwd if the installed Codex exposes a reliable non-interactive listing; otherwise return an empty list and document why.
- `transcript_path(cwd, session_id)` returns the saved session/log path if verified; otherwise `None`.
- `parse_usage(transcript_path)` returns `None` unless the current Codex session files expose reliable context-window usage.
- `supports_remote_control()` returns `False` for Claude-style Remote Control.
- `settings_bypass_patch(cwd)` should be a no-op unless Codex has a verified scoped per-project equivalent.

Suggested argv mapping for the installed CLI, subject to verification:

```python
cmd = ["codex", "--cd", str(cwd)]
if bypass:
    cmd += ["--dangerously-bypass-approvals-and-sandbox"]
else:
    cmd += ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]
```

For resume:

```python
cmd = ["codex", "resume", "--cd", str(cwd)]
if bypass:
    cmd += ["--dangerously-bypass-approvals-and-sandbox"]
else:
    cmd += ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]
cmd += [session_id]
```

Verify the exact option ordering before committing; if `codex resume --cd` is not accepted in that position, adjust to the observed working syntax.

Data-plane rules:

- `data_plane="app"` means "not supported for Codex" in the Claude Remote Control sense. The conductor may still start the tmux session and report tmux attach instructions.
- `data_plane="telegram"` and `data_plane="both"` are not supported by Codex unless a separate Codex-specific bridge exists. Do not consume a Claude Telegram bot slot for Codex.
- Prefer representing Codex reachability as `data_plane="tmux"` in registry/status output.
- Make unsupported requested data planes degrade to tmux with a clear status message rather than failing the session start.

Critical verification gates:

1. Confirm exact interactive launch argv:
   - Run `codex --help` and one harmless interactive launch in a scratch directory.
   - Confirm `--cd` works and that tmux launch remains interactive.

2. Confirm bypass mode:
   - Verify `--dangerously-bypass-approvals-and-sandbox` is accepted for interactive runs.
   - If using safer defaults, verify `--ask-for-approval never --sandbox danger-full-access` or the chosen equivalent actually suppresses prompts.

3. Confirm resume syntax:
   - Verify `codex resume --cd <dir> <session_id>` or the correct equivalent.
   - Implement based on observed behavior.

4. Confirm session storage:
   - Locate current Codex session files under `$CODEX_HOME` or `~/.codex`.
   - Determine whether sessions can be listed without opening the TUI.
   - Determine whether session files contain cwd, session id, timestamps, and context usage.

5. Confirm monitoring fallback:
   - If transcript usage is unavailable, make conductor idle detection use tmux/process activity and skip context nudges for Codex.

Acceptance checks:

- Choosing Codex from the conductor launches an interactive Codex TUI in tmux at the selected cwd.
- Unsupported app/telegram data planes degrade to tmux instructions and do not lease a Telegram slot.
- `/sessions` can show Codex sessions with cwd, uptime, status, and `data_plane=tmux`.
- `/kill` and idle reaping work for Codex tmux sessions.
- Resume works when a valid Codex session id is supplied.
- Usage/context monitoring is either implemented from verified Codex session data or explicitly skipped without errors.

When you finish, report:

- Exact Codex version and help output facts used.
- Files changed.
- Commands used to test launch, resume, kill, and monitoring.
- Any behavior left as degraded/unsupported because Codex does not expose the needed data.
