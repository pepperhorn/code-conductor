from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Usage:
    used: int
    limit: int

    @property
    def pct_remaining(self) -> float:
        if self.limit <= 0:
            return 0.0
        return 100 * (self.limit - self.used) / self.limit


@dataclass(frozen=True)
class ResumableSession:
    id: str
    started_at: str
    summary: str


class UnsupportedDataPlane(RuntimeError):
    """Raised when an adapter cannot satisfy the requested data plane."""


class CLIAdapter(ABC):
    name: str

    @abstractmethod
    def build_launch_cmd(
        self,
        cwd: Path,
        *,
        bypass: bool,
        data_plane: str,
        bot_token: str | None,
    ) -> list[str]:
        """Argv for an interactive session."""

    @abstractmethod
    def build_resume_cmd(
        self,
        session_id: str,
        cwd: Path,
        *,
        bypass: bool,
        data_plane: str,
        bot_token: str | None,
    ) -> list[str]:
        """Argv for an interactive resume."""

    @abstractmethod
    def list_resumable(self, cwd: Path) -> list[ResumableSession]:
        """Return known resumable sessions for a cwd."""

    @abstractmethod
    def transcript_path(self, cwd: Path, session_id: str) -> Path | None:
        """Return a transcript path if the adapter exposes one."""

    @abstractmethod
    def parse_usage(self, transcript_path: Path) -> Usage | None:
        """Parse context usage if available."""

    @abstractmethod
    def supports_remote_control(self) -> bool:
        """Whether the adapter supports Claude-style Remote Control."""

    @abstractmethod
    def settings_bypass_patch(self, cwd: Path) -> None:
        """Apply scoped bypass configuration if supported."""
