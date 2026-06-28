from __future__ import annotations

from pathlib import Path

import pytest

from conductor.projects import direct_child_projects, discover_projects, validate_project_path


def test_discover_projects_respects_max_depth(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "c").mkdir()

    projects = discover_projects(tmp_path, max_depth=1)
    paths = {project.path for project in projects}

    assert tmp_path.resolve() in paths
    assert (tmp_path / "a").resolve() in paths
    assert (tmp_path / "a" / "b").resolve() not in paths


def test_validate_project_path_rejects_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent

    with pytest.raises(ValueError, match="under"):
        validate_project_path(tmp_path, outside)


def test_direct_child_projects_only_returns_one_level(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "c").mkdir()

    projects = direct_child_projects(tmp_path, tmp_path)

    assert [project.path.name for project in projects] == ["a", "c"]
