# Conductor — Local Session Orchestrator for Claude Code / Codex

**Audience:** a Claude Code instance implementing this. **Author intent:** a personal, single-user control-plane service running in WSL that starts, tracks, monitors, and reaps CLI agent sessions (Claude Code now, Codex next), while each session's *conversation* lives on its own data plane (Claude mobile app via Remote Control, and/or a dedicated Telegram bot). The conductor never sits in a session's message path.

---

## 1. Design principle: control plane vs data plane

- **Control plane = the Conductor.** One dedicated Telegram bot. Lists projects, starts/resumes/stops sessions, lists what's live, monitors health + context usage out-of-band, reaps idle sessions, manages a configurable pool of Telegram "session bots." It does **not** read or relay session conversation.
- **Data plane = per session.** Each session is reachable independently via:
  - **Remote Control** → appears in the Claude mobile app / `claude.ai/code` (Claude Code only), and/or
  - **A leased Telegram bot slot** (from the configured channel-slot pool), giving that session its own Telegram chat.
- The conductor launches each session as an **interactive** process inside its own **tmux** target (Remote Control only attaches to interactive processes; tmux makes it survive detach and conductor restarts), then steps out. Monitoring is done by reading the session's **transcript JSONL on disk**, not by being in the pipe.

**Non-goals (v1):** the conductor does not proxy conversation; does not run sessions headless/`-p` (that breaks Remote Control); does not attempt to read plan/account quota (no reliable programmatic source — see §8); does not manage Codex's data plane (Claude-only features don't apply to Codex — see §6).

---

## 2. Recommended stack

- Python 3.11+, `python-telegram-bot` v21+ (async, long-polling — outbound only, fine behind Tailscale/WSL, no inbound ports).
- `aiosqlite` for state; `watchfiles` for transcript tailing; `libtmux` (or `subprocess` + `tmux` CLI) for session processes.
- Keep dependencies minimal. No web server, no public endpoint.

(If the implementer prefers Node/grammY to stay close to `github.com/RichardAtCT/claude-code-telegram`, the architecture is identical — keep the module boundaries below.)

---

## 3. Repo layout

```
conductor/
  __main__.py             # entrypoint, wires bot + monitor + reaper
  config.py               # load config.toml, validate
  config.example.toml
  telegram/
    control_bot.py        # control-plane command handlers
    keyboards.py          # inline keyboards (numbered project picker, CLI/data-plane choosers)
  sessions/
    manager.py            # start / resume / stop lifecycle
    registry.py           # SQLite state access
    reaper.py             # idle detection + kill, dead-process detection
  monitor/
    transcript.py         # tail transcript JSONL: last_activity (mtime) + usage parsing
    thresholds.py         # 50/25/15/10/5/2 crossing logic + reset
  channels/
    bot_pool.py           # Telegram bot slots: lease / assign / release
    remote_control.py     # verify/ensure RC auto-enable, helper text
  adapters/
    base.py               # CLIAdapter ABC  <-- PRIMARY HOOK POINT
    claude_code.py        # full implementation
    codex.py              # STUB with documented hooks (see §6)
  deploy/
    conductor.service     # systemd unit
    setup-wsl.md          # wsl.conf + Task Scheduler steps
```

---

## 4. Configuration (`config.toml`)

```toml
[telegram]
control_bot_token = "PASTE_CONDUCTOR_BOT_TOKEN"   # the conductor's own bot (BotFather)
allowed_chat_ids  = [123456789]                   # HARD allowlist — only auth boundary (see §9)

[project]
root_env  = "CONDUCTOR_PROJECT_ROOT"              # must resolve to PROJECT_ROOT; on this box: /home/shaun
max_depth = 2                                      # list dirs + one level of subdirs

[channels]
slot_count_env = "CONDUCTOR_CHANNEL_SLOTS"        # default 5 if unset; token entries must match

[defaults]
cli                  = "claude"                    # "claude" | "codex"
bypass_permissions   = true                        # default ON (implemented via allow-list, see §5.3)
idle_warning_minutes = 25
idle_timeout_minutes = 30

[remote_control]
auto_enable = true                                 # conductor verifies the global CC setting is on

# --- Telegram session-bot slots (pre-create bots in BotFather; default count is 5) ---
[[bot_slots]]
name  = "session-bot-1"
token = "PASTE_BOT_1_TOKEN"
[[bot_slots]]
name  = "session-bot-2"
token = "PASTE_BOT_2_TOKEN"
[[bot_slots]]
name  = "session-bot-3"
token = "PASTE_BOT_3_TOKEN"
[[bot_slots]]
name  = "session-bot-4"
token = "PASTE_BOT_4_TOKEN"
[[bot_slots]]
name  = "session-bot-5"
token = "PASTE_BOT_5_TOKEN"
```

`config.toml` is chmod 600 and gitignored. Provide `config.example.toml` with placeholders. `CONDUCTOR_PROJECT_ROOT` must be set in the service environment; fail fast if it is missing, empty, or resolves to an invalid path. On this box, set `CONDUCTOR_PROJECT_ROOT=/home/shaun`. `CONDUCTOR_CHANNEL_SLOTS` controls how many Telegram session-bot channels to manage and defaults to `5` when unset; fail fast if it is not a positive integer or if the configured `[[bot_slots]]` count does not match the resolved slot count.

---

## 5. Core mechanisms

### 5.1 Project picker
Walk `PROJECT_ROOT` to `max_depth` (dirs + one subdir level). Reject any path containing `..` or resolving outside `PROJECT_ROOT`. Render as a **numbered inline keyboard** (tap to drill into subfolders, tap to select). Nice-to-have: show git branch + dirty flag per entry; warn before starting in a dirty repo.

### 5.2 Session launch flow
1. `/new` (or tap a project) → numbered project picker.
2. After project selected → choose **CLI** (`claude` / `codex`) and **data plane** (`app` / `telegram` / `both`). Bypass defaults ON.
3. Conductor resolves the adapter (§6), then for the Claude path:
   - Ensure Remote Control global auto-enable is on (`channels/remote_control.py` verifies; document the manual `/config` → "Enable Remote Control for all sessions: true" step as a prerequisite).
   - Apply bypass via allow-list (§5.3).
   - If data plane includes telegram → **lease a bot slot** (§5.4); fail soft if none free.
   - Create a tmux target; launch the **interactive** CLI inside it via `adapter.build_launch_cmd(...)`.
   - Capture the new `session_id` (watch the transcript dir for the new JSONL file; fall back to parsing CLI output).
4. Register the session in SQLite (§7). Reply with reach-instructions:
   - app: "appears in the Code tab as <cwd>";
   - telegram: "DM @<slot bot username>, send any message, approve the pairing code."
5. Conductor steps out. It now only monitors + reaps.

### 5.3 Bypass-by-default — important
`--dangerously-skip-permissions` is reported **not to work with Remote Control** (approvals still prompt). So do **not** rely on that flag. Instead, the Claude adapter writes a permissive allow-list to the project's `.claude/settings.local.json` at launch (`adapter.settings_bypass_patch(cwd)`), which yields de-facto bypass that survives Remote Control. Verify on the installed CC version; if the flag later works with RC, make it a config toggle. Keep the allow-list **scoped per project**, never a global dangerous flag.

### 5.4 Telegram bot slots
`channels/bot_pool.py` manages `CONDUCTOR_CHANNEL_SLOTS` slots, default `5`, each `(name, token, leased_session_id|None)`, persisted in SQLite.

- **Auto-lease:** on a session start that requests a telegram data plane, lease the first free slot, inject its token into that session's launch (see hook in §6 / open question §10), record the lease.
- **Graceful degrade:** if no slot is free, start the session **app-only** (Remote Control) and reply: "No Telegram slots free — reachable in the app; assign a slot later with `/assign`." Do **not** block the start.
- **Manual control:** `/slots` shows allocation; `/assign <session_id> <slot_name>` moves/attaches a slot; `/release <slot_name>` frees one.
- **Release on stop/reap.**

> Note: the official Telegram channel plugin is single-session per bot (two pollers on one token → 409). Distinct tokens are required for concurrent telegram sessions. How a distinct token is injected per session is the one real integration unknown — see §10.

---

## 6. CLI adapter interface (PRIMARY HOOK POINT)

All CLI-specific behavior lives behind one ABC so Codex (and future CLIs) plug in without touching the conductor. **`adapters/base.py`:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Usage:
    used: int
    limit: int
    @property
    def pct_remaining(self) -> float: return 100 * (self.limit - self.used) / self.limit

@dataclass
class ResumableSession:
    id: str
    started_at: str
    summary: str

class CLIAdapter(ABC):
    name: str

    @abstractmethod
    def build_launch_cmd(self, cwd: Path, *, bypass: bool, data_plane: str,
                         bot_token: str | None) -> list[str]:
        """Argv for an INTERACTIVE session (for tmux). data_plane in {app,telegram,both}."""

    @abstractmethod
    def build_resume_cmd(self, session_id: str, cwd: Path, *, bypass: bool,
                         data_plane: str, bot_token: str | None) -> list[str]: ...

    @abstractmethod
    def list_resumable(self, cwd: Path) -> list[ResumableSession]: ...

    @abstractmethod
    def transcript_path(self, cwd: Path, session_id: str) -> Path | None:
        """Location of the session's JSONL transcript, or None if unsupported."""

    @abstractmethod
    def parse_usage(self, transcript_path: Path) -> Usage | None:
        """Context-window usage from the transcript, or None if not exposed."""

    @abstractmethod
    def supports_remote_control(self) -> bool: ...

    @abstractmethod
    def settings_bypass_patch(self, cwd: Path) -> None:
        """Write a scoped permission allow-list for bypass-by-default."""
```

### 6.1 `adapters/claude_code.py` — full implementation
- `build_launch_cmd`: interactive `claude` (no `-p`). Rely on global RC auto-enable for the app data plane. For telegram, enable the channel plugin with the leased `bot_token` (see §10). Do not pass `--dangerously-skip-permissions`; use the allow-list instead.
- `build_resume_cmd`: `claude --resume <session_id>` in `cwd`.
- `transcript_path`: `~/.claude/projects/<slug(cwd)>/<session_id>.jsonl`. **Verify the current slug rule and schema at build time — it drifts.**
- `parse_usage`: read the latest assistant message's usage block; `used` = cumulative input+output context tokens, `limit` = model context window. Return `Usage`.
- `supports_remote_control`: `True`.
- `settings_bypass_patch`: write/merge `.claude/settings.local.json` permissive allow-list scoped to that project.

### 6.2 `adapters/codex.py` — STUB (hand to a Codex CLI to complete)
Implement the same ABC. Leave each method as `raise NotImplementedError` with an explicit `# HOOK:` describing what to fill:

```python
class CodexAdapter(CLIAdapter):
    name = "codex"

    def build_launch_cmd(self, cwd, *, bypass, data_plane, bot_token):
        # HOOK: codex interactive launch argv. Map bypass -> codex's auto-approval
        #       / full-auto / sandbox-bypass mode. Verify exact flag names.
        raise NotImplementedError

    def build_resume_cmd(self, session_id, cwd, *, bypass, data_plane, bot_token):
        # HOOK: codex resume syntax (verify).
        raise NotImplementedError

    def list_resumable(self, cwd):
        # HOOK: how codex enumerates prior sessions for this cwd.
        raise NotImplementedError

    def transcript_path(self, cwd, session_id):
        # HOOK: codex session log location (likely under ~/.codex/...). Verify.
        return None

    def parse_usage(self, transcript_path):
        # HOOK: codex usage exposure unknown — return None if not available;
        #       monitor will simply skip context nudges for codex sessions.
        return None

    def supports_remote_control(self):
        return False  # Remote Control + Anthropic Channels are Claude Code only.

    def settings_bypass_patch(self, cwd):
        # HOOK: codex equivalent of a scoped permission allow-list, if any.
        pass
```

**Codex data-plane note for the implementer:** Codex cannot use Remote Control or Anthropic Telegram channels. Its data plane is either tmux-attach over SSH/Tailscale or a Codex-specific bridge. The conductor still manages Codex **lifecycle** (start/resume/stop/list) and idle reaping normally — only the per-session conversation surface differs. If `parse_usage`/`transcript_path` return `None`, the monitor skips usage nudges and falls back to tmux `capture-pane` mtime for idle detection.

---

## 7. State (SQLite)

```sql
CREATE TABLE sessions (
  id            TEXT PRIMARY KEY,   -- CLI session id
  cli           TEXT NOT NULL,      -- claude | codex
  cwd           TEXT NOT NULL,
  tmux_target   TEXT NOT NULL,      -- "session:window"
  data_plane    TEXT NOT NULL,      -- app | telegram | both | tmux
  bot_slot      TEXT,               -- leased slot name (nullable)
  status        TEXT NOT NULL,      -- starting|live|idle|stopping|dead
  started_at    TEXT NOT NULL,
  last_activity TEXT,               -- from transcript mtime / last message ts
  fired_thresholds TEXT DEFAULT '[]'-- JSON array, e.g. [50,25]
);
CREATE TABLE bot_slots (
  name TEXT PRIMARY KEY, token TEXT NOT NULL, leased_session_id TEXT
);
CREATE TABLE audit (
  ts TEXT, chat_id INTEGER, command TEXT, detail TEXT
);
```

On startup, reconcile: read state, check tmux targets still alive, and offer "resume these N sessions?" rather than silently dropping them.

---

## 8. Monitoring (out-of-band)

`monitor/transcript.py` watches `~/.claude/projects/**/*.jsonl` (and adapter-provided paths). For each tracked session:
- **Liveness:** tmux target alive + process running → `live`.
- **Idle:** `now - last_activity` (transcript mtime / last message ts) → `idle` thresholds feed the reaper.
- **Context %:** `adapter.parse_usage(...)` → `pct_remaining`.

`monitor/thresholds.py`: fire **once** on each downward crossing of `[50, 25, 15, 10, 5, 2]`; track `fired_thresholds` per session; **reset** when usage drops (post-`/compact`). Push the nudge to the control bot (and optionally into the session's own channel) with a suggested action (compact / clear / wrap up).

- **Caveat to encode:** Claude Code auto-compacts near the limit, so 5%/2% nudges will collide with auto-compact — treat low thresholds as informational; the 50/25 nudges are the actionable ones.
- **Plan/account quota is out of scope v1** — no reliable programmatic source. Only surface a rate-limit warning if one actually appears in the transcript/stderr.

---

## 9. Reaper

`sessions/reaper.py` periodic task:
- `live` and idle > `idle_warning_minutes` → warn into the session's channel + control bot.
- idle > `idle_timeout_minutes` → `stop()` (tmux kill → release bot slot → mark `dead`). Any new activity cancels.
- Detect dead processes (tmux gone, or Remote Control's ~10-min network timeout exiting the process) → mark `dead`, offer `resume`.
- Commands: `/kill <id>`, `/killall`.

---

## 10. Control-bot commands

`/start`, `/help`, `/new` (project picker), `/projects`, `/sessions` (status cards: cli, model, cwd, context %, uptime, idle, data plane, bot slot), `/resume <id>` (or pick from resumable list), `/status <id>`, `/kill <id>`, `/killall`, `/slots`, `/assign <id> <slot>`, `/release <slot>`, `/audit`.

Output > 4096 chars must paginate or attach as a file (Telegram limit).

---

## 11. Deployment (WSL)

`deploy/setup-wsl.md`:
1. **systemd in WSL:** `/etc/wsl.conf` → `[boot]\nsystemd=true`; then `wsl --shutdown` once.
2. **Conductor service** (`deploy/conductor.service`, `Restart=always`, `EnvironmentFile` or config path). Optional second unit: a persistent `claude remote-control` host if you also want to launch sessions directly from the phone (note: this overlaps with the conductor's launcher — the conductor adds the project picker, multi-CLI, reaping, and nudges on top).
3. **Auto-start the distro at logon:** Windows Task Scheduler task, trigger "at log on", action `wsl.exe -d <Distro> -u <user> --exec /bin/true`. Booting the distro starts systemd, which starts the conductor, which connects to Telegram.
4. Confirm Windows isn't shutting the WSL VM down under you (`vmIdleTimeout`); the always-on conductor process keeps it warm.

```ini
# deploy/conductor.service
[Unit]
Description=CLI Session Conductor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/shaun/conductor
Environment=CONDUCTOR_PROJECT_ROOT=/home/shaun
Environment=CONDUCTOR_CHANNEL_SLOTS=5
ExecStart=/home/shaun/conductor/.venv/bin/python -m conductor
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

---

## 12. Security

- **chat_id allowlist is the only auth boundary** (bypass-by-default = no per-action gate). Drop everything from non-allowlisted chats silently.
- Bypass via **scoped per-project allow-list**, never a global dangerous flag.
- **Audit log** every command + session start.
- Tokens chmod 600, gitignored.
- **One-session-per-directory lock** so two agents don't clobber the same files.

---

## 13. Phasing

**v1 (P0 — ship first):** control bot + chat allowlist; numbered project picker; Claude adapter (interactive + tmux + RC auto-enable + bypass allow-list); SQLite registry + startup reconcile; `/sessions` `/kill` `/killall`; configurable bot slots with auto-lease, graceful degrade, `/slots`; transcript-tail liveness + idle reaper.

**v2 (P1):** context-% thresholds + nudges with reset; resume-on-death; `/assign` `/release` `/status` cards; audit; per-session topic routing niceties.

**v3 (P2):** Codex adapter (hand `adapters/codex.py` to a Codex CLI); voice notes → transcription → prompt (Telegram-only advantage); additional CLIs via the same ABC.

---

## 14. v1 acceptance criteria

- [ ] Non-allowlisted chat IDs receive no response and are logged.
- [ ] `/new` lists projects under `PROJECT_ROOT` as a numbered keyboard; `..` traversal rejected.
- [ ] Selecting a project + `claude` + `app` starts an interactive tmux session that appears in the Claude mobile app within ~30s, with bypass effective (no approval prompts for allow-listed actions).
- [ ] Selecting `telegram` leases a bot slot and returns pairing instructions; with all configured slots leased, the session still starts app-only with a clear message.
- [ ] `/sessions` shows all live sessions with cwd + uptime + data plane + slot.
- [ ] A session idle past `idle_timeout_minutes` is warned, then killed, and its slot released.
- [ ] Conductor restart reconciles state and offers to resume surviving tmux sessions.

---

## 15. Open questions / build-time hooks to verify (these drift — check, don't assume)

1. **Telegram per-session token injection (the key unknown):** does the official `plugin:telegram@claude-plugins-official` channel read its bot token from an env var / per-invocation config so the conductor can run the configured number of distinct bot tokens? If not, fallback: the conductor runs a lightweight per-slot bridge for the telegram data plane (still out of the *conversation* logic — it only relays that one session). Decide this early; it shapes `channels/bot_pool.py` and the Claude adapter's `build_launch_cmd`.
2. **Claude transcript schema + path slug** for the installed CC version (`~/.claude/projects/<slug>/<id>.jsonl`) — confirm before writing `parse_usage`/`transcript_path`.
3. **RC + tmux + non-foreground:** confirm a tmux-launched interactive session reliably registers for Remote Control with global auto-enable, and that the bypass allow-list fully suppresses prompts under RC.
4. **New session_id capture at launch:** prefer watching the transcript dir for the new file over parsing stdout; verify which is reliable.
5. **Codex specifics (for the Codex implementer):** interactive launch argv, bypass/auto-approval flag, transcript location + usage exposure, resume syntax.
