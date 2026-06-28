from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from conductor.projects import ProjectEntry


def project_keyboard(
    projects: list[ProjectEntry],
    *,
    page: int = 0,
    page_size: int = 20,
) -> InlineKeyboardMarkup:
    start = page * page_size
    rows = []
    for idx, project in enumerate(projects[start : start + page_size], start=start + 1):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{idx}. {project.label}",
                    callback_data=f"project:{idx - 1}",
                )
            ]
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"projects_page:{page - 1}"))
    if start + page_size < len(projects):
        nav.append(InlineKeyboardButton("Next", callback_data=f"projects_page:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def cli_keyboard(project_idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Claude", callback_data=f"cli:{project_idx}:claude"),
                InlineKeyboardButton("Codex", callback_data=f"cli:{project_idx}:codex"),
            ]
        ]
    )


def data_plane_keyboard(project_idx: int, cli: str) -> InlineKeyboardMarkup:
    if cli == "codex":
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("tmux", callback_data=f"start:{project_idx}:{cli}:tmux")]]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("app", callback_data=f"start:{project_idx}:{cli}:app"),
                InlineKeyboardButton(
                    "telegram",
                    callback_data=f"start:{project_idx}:{cli}:telegram",
                ),
                InlineKeyboardButton("both", callback_data=f"start:{project_idx}:{cli}:both"),
            ]
        ]
    )
