from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass


class TmuxError(RuntimeError):
    pass


@dataclass(frozen=True)
class TmuxTarget:
    session: str
    window: str = "agent"

    @property
    def value(self) -> str:
        return f"{self.session}:{self.window}"


class Tmux:
    async def exists(self, target: str) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            target,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait() == 0

    async def start(
        self,
        target: TmuxTarget,
        cwd: str,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> None:
        if await self.exists(target.session):
            raise TmuxError(f"tmux session already exists: {target.session}")
        command = " ".join(shlex.quote(part) for part in argv)
        tmux_args = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            target.session,
            "-n",
            target.window,
            "-c",
            cwd,
        ]
        for key, value in (env or {}).items():
            tmux_args += ["-e", f"{key}={value}"]
        tmux_args.append(command)
        proc = await asyncio.create_subprocess_exec(
            *tmux_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TmuxError(
                f"failed to start tmux target {target.value}: "
                f"{stderr.decode().strip() or stdout.decode().strip()}"
            )

    async def kill(self, target: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "kill-session",
            "-t",
            target.split(":", 1)[0],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def capture(self, target: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "capture-pane",
            "-p",
            "-t",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()
        return stdout.decode(errors="ignore")

    async def send_enter(self, target: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "send-keys",
            "-t",
            target,
            "Enter",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def send_text(self, target: str, text: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "set-buffer",
            "-b",
            "conductor-bridge",
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "paste-buffer",
            "-b",
            "conductor-bridge",
            "-t",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        await self.send_enter(target)
        # Some TUIs accept the paste but need a second Enter to submit the prompt.
        await asyncio.sleep(0.1)
        await self.send_enter(target)
