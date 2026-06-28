# WSL Deployment

This guide installs Code Conductor as a personal systemd service inside WSL.

## 1. Enable systemd in WSL

Create or edit `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

From Windows, restart WSL once:

```powershell
wsl --shutdown
```

## 2. Install Python dependencies

From `/home/shaun/conductor`:

```bash
uv venv --python /home/shaun/.local/bin/python3.11 .venv
uv pip install -e '.[dev]'
```

## 3. Create local config

```bash
cp config.example.toml config.toml
chmod 600 config.toml
```

Edit `config.toml`:

- Set `telegram.control_bot_token`.
- Set `telegram.allowed_chat_ids`.
- Add one `[[bot_slots]]` entry for each configured channel slot.

The service sets:

```bash
CONDUCTOR_PROJECT_ROOT=/home/shaun
CONDUCTOR_CHANNEL_SLOTS=4
```

If you change `CONDUCTOR_CHANNEL_SLOTS`, make sure `config.toml` has the same number of `[[bot_slots]]` entries.

## 4. Install service

```bash
mkdir -p ~/.config/systemd/user
cp deploy/conductor.service ~/.config/systemd/user/conductor.service
systemctl --user daemon-reload
systemctl --user enable --now conductor.service
```

Check status:

```bash
systemctl --user status conductor.service
journalctl --user -u conductor.service -f
```

## 5. Start WSL at Windows login

Create a Windows Task Scheduler task:

- Trigger: at log on
- Action: `wsl.exe -d <Distro> -u shaun --exec /bin/true`

Starting the distro starts user systemd, which starts Conductor.

## 6. Smoke checks

```bash
CONDUCTOR_PROJECT_ROOT=/home/shaun CONDUCTOR_CHANNEL_SLOTS=4 \
  .venv/bin/python -m conductor --config config.toml
```

Then message the control bot:

- `/start`
- `/projects`
- `/slots`
- `/sessions`

Claude Remote Control and Telegram session-bot token injection still need live verification against the installed Claude Code version and configured BotFather tokens.
