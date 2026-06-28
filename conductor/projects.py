from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectEntry:
    path: Path
    label: str
    depth: int
    git_branch: str | None = None
    dirty: bool = False


def discover_projects(root: Path, max_depth: int) -> list[ProjectEntry]:
    root = root.resolve()
    entries: list[ProjectEntry] = []
    for path in sorted(_walk_dirs(root, max_depth)):
        resolved = path.resolve()
        if resolved != root and root not in resolved.parents:
            continue
        rel = resolved.relative_to(root)
        depth = 0 if rel == Path(".") else len(rel.parts)
        branch, dirty = _git_status(resolved)
        label = str(rel) if str(rel) != "." else resolved.name
        if branch:
            label += f" [{branch}{'*' if dirty else ''}]"
        entries.append(
            ProjectEntry(
                path=resolved,
                label=label,
                depth=depth,
                git_branch=branch,
                dirty=dirty,
            )
        )
    return entries


def direct_child_projects(root: Path, current: Path) -> list[ProjectEntry]:
    root = root.resolve()
    current = validate_project_path(root, current)
    entries: list[ProjectEntry] = []
    try:
        children = [child for child in current.iterdir() if child.is_dir()]
    except OSError:
        return entries
    for child in sorted(children):
        if child.name.startswith("."):
            continue
        resolved = child.resolve()
        if root not in resolved.parents and resolved != root:
            continue
        branch, dirty = _git_status(resolved)
        label = child.name
        if branch:
            label += f" [{branch}{'*' if dirty else ''}]"
        entries.append(
            ProjectEntry(
                path=resolved,
                label=label,
                depth=len(resolved.relative_to(root).parts),
                git_branch=branch,
                dirty=dirty,
            )
        )
    return entries


def validate_project_path(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    if ".." in candidate.parts:
        raise ValueError("project path traversal is not allowed")
    resolved = candidate.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"project path must be under {root}")
    if not resolved.is_dir():
        raise ValueError(f"project path is not a directory: {resolved}")
    return resolved


def _walk_dirs(root: Path, max_depth: int) -> list[Path]:
    results = [root]
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = [child for child in current.iterdir() if child.is_dir()]
        except OSError:
            continue
        for child in sorted(children):
            if child.name.startswith("."):
                continue
            results.append(child)
            queue.append((child, depth + 1))
    return results


def _git_status(path: Path) -> tuple[str | None, bool]:
    try:
        branch = subprocess.run(
            ["git", "-C", str(path), "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if branch.returncode != 0:
            return None, False
        name = branch.stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        return name or "detached", bool(dirty.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return None, False
