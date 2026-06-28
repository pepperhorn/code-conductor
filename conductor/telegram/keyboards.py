from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from conductor.projects import ProjectEntry


def project_keyboard(
    projects: list[ProjectEntry],
    *,
    page: int = 0,
    page_size: int = 20,
    include_new_here: bool = False,
    include_back: bool = False,
) -> InlineKeyboardMarkup:
    start = page * page_size
    rows = []
    if include_new_here:
        rows.append([InlineKeyboardButton("New here", callback_data="project_here")])
    if include_back:
        rows.append([InlineKeyboardButton("Back", callback_data="project_back")])
    for idx, project in enumerate(projects[start : start + page_size], start=start + 1):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{idx}. {project.label}",
                    callback_data=f"browse:{idx - 1}",
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


def cli_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Claude", callback_data="cli:claude"),
                InlineKeyboardButton("Codex", callback_data="cli:codex"),
            ]
        ]
    )


def data_plane_keyboard(cli: str) -> InlineKeyboardMarkup:
    if cli == "codex":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("tmux", callback_data=f"start:{cli}:tmux"),
                    InlineKeyboardButton("telegram", callback_data=f"start:{cli}:telegram"),
                ]
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("app", callback_data=f"start:{cli}:app"),
                InlineKeyboardButton(
                    "telegram",
                    callback_data=f"start:{cli}:telegram",
                ),
                InlineKeyboardButton("both", callback_data=f"start:{cli}:both"),
            ]
        ]
    )
