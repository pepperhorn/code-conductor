from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from conductor.config import AppConfig
from conductor.projects import ProjectEntry, direct_child_projects
from conductor.session_footer import render_session_footer
from conductor.sessions.manager import SessionManager
from conductor.sessions.registry import Registry, SessionRecord
from conductor.telegram.keyboards import cli_keyboard, data_plane_keyboard, project_keyboard

log = logging.getLogger(__name__)


@dataclass
class BotState:
    config: AppConfig
    registry: Registry
    manager: SessionManager
    projects: list[ProjectEntry]
    current_dir: Path
    selected_project: Path | None = None


def build_application(
    config: AppConfig,
    registry: Registry,
    manager: SessionManager,
) -> Application:
    app = Application.builder().token(config.telegram.control_bot_token).build()
    state = BotState(
        config=config,
        registry=registry,
        manager=manager,
        projects=[],
        current_dir=config.project.root,
    )
    app.bot_data["state"] = state
    app.add_handler(CommandHandler("start", _allowlisted(start)))
    app.add_handler(CommandHandler("help", _allowlisted(help_command)))
    app.add_handler(CommandHandler("new", _allowlisted(new_command)))
    app.add_handler(CommandHandler("projects", _allowlisted(new_command)))
    app.add_handler(CommandHandler("sessions", _allowlisted(sessions_command)))
    app.add_handler(CommandHandler("slots", _allowlisted(slots_command)))
    app.add_handler(CommandHandler("kill", _allowlisted(kill_command)))
    app.add_handler(CommandHandler("killall", _allowlisted(killall_command)))
    app.add_handler(CallbackQueryHandler(_allowlisted(callback_query)))
    app.add_error_handler(error_handler)
    return app


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/start")
    await update.effective_message.reply_text("Conductor ready. Use /new to start a session.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/help")
    await update.effective_message.reply_text(
        "/new - start a session\n"
        "/projects - list project picker\n"
        "/sessions - list sessions\n"
        "/slots - list Telegram channel slots\n"
        "/kill <id> - stop a session\n"
        "/killall - stop all live sessions"
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/new")
    state.current_dir = state.config.project.root
    state.selected_project = None
    state.projects = direct_child_projects(state.config.project.root, state.current_dir)
    await update.effective_message.reply_text(
        "Choose a top-level folder:",
        reply_markup=project_keyboard(state.projects),
    )


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/sessions")
    sessions = await state.registry.list_sessions()
    if not sessions:
        await update.effective_message.reply_text("No sessions.")
        return
    lines = []
    for session in sessions:
        lines.append(
            "\n".join(
                [
                    f"<b>{html.escape(session.id[:8])}</b> {html.escape(session.status)}",
                    f"cli: {html.escape(session.cli)}",
                    f"cwd: {html.escape(session.cwd)}",
                    f"data: {html.escape(session.data_plane)}",
                    f"slot: {html.escape(session.bot_slot or '-')}",
                ]
            )
        )
    await _reply_chunks(update, "\n\n".join(lines), parse_mode=ParseMode.HTML)


async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/slots")
    slots = await state.registry.list_slots()
    text = "\n".join(f"{slot.name}: {slot.leased_session_id or 'free'}" for slot in slots)
    await update.effective_message.reply_text(text or "No slots configured.")


async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/kill", " ".join(context.args))
    if not context.args:
        await update.effective_message.reply_text("Usage: /kill <session_id>")
        return
    stopped = await state.manager.stop(context.args[0])
    await update.effective_message.reply_text("Stopped." if stopped else "Session not found.")


async def killall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    await state.registry.audit(_chat_id(update), "/killall")
    sessions = await state.registry.list_sessions(statuses={"starting", "live", "idle"})
    count = 0
    for session in sessions:
        if await state.manager.stop(session.id):
            count += 1
    await update.effective_message.reply_text(f"Stopped {count} session(s).")


async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(context)
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    await state.registry.audit(_chat_id(update), "callback", data)

    if data.startswith("projects_page:"):
        page = int(data.split(":", 1)[1])
        await query.edit_message_reply_markup(
            reply_markup=_browser_keyboard(state, page=page)
        )
        return
    if data == "project_back":
        if state.current_dir != state.config.project.root:
            state.current_dir = state.current_dir.parent
        state.projects = direct_child_projects(state.config.project.root, state.current_dir)
        await query.edit_message_text(
            _browser_title(state),
            reply_markup=_browser_keyboard(state),
        )
        return
    if data.startswith("browse:"):
        idx = int(data.split(":", 1)[1])
        state.current_dir = state.projects[idx].path
        state.projects = direct_child_projects(state.config.project.root, state.current_dir)
        await query.edit_message_text(
            _browser_title(state),
            reply_markup=_browser_keyboard(state),
        )
        return
    if data == "project_here":
        state.selected_project = state.current_dir
        await query.edit_message_text(
            f"Start in {state.selected_project}.\nChoose CLI:",
            reply_markup=cli_keyboard(),
        )
        return
    if data.startswith("cli:"):
        _prefix, cli = data.split(":", 1)
        await query.edit_message_text(
            "Choose data plane:",
            reply_markup=data_plane_keyboard(cli),
        )
        return
    if data.startswith("start:"):
        _prefix, cli, data_plane = data.split(":", 2)
        if state.selected_project is None:
            await query.edit_message_text("No project selected. Use /new to start again.")
            return
        try:
            result = await state.manager.start(
                cwd=state.selected_project,
                cli=cli,
                data_plane=data_plane,
                bypass=state.config.defaults.bypass_permissions,
            )
        except ValueError as exc:
            await query.edit_message_text(str(exc))
            return
        text = _start_message(result.session)
        text += render_session_footer(state.config.session_footer, result.session)
        if result.degraded_reason:
            text += f"\n\n{result.degraded_reason}"
        await query.edit_message_text(text)


def _browser_title(state: BotState) -> str:
    rel = state.current_dir.relative_to(state.config.project.root)
    if str(rel) == ".":
        return "Choose a top-level folder:"
    return f"{rel}\nChoose New here or a subfolder:"


def _browser_keyboard(state: BotState, *, page: int = 0):
    at_root = state.current_dir == state.config.project.root
    return project_keyboard(
        state.projects,
        page=page,
        include_new_here=not at_root,
        include_back=not at_root,
    )


def _start_message(session: SessionRecord) -> str:
    cwd = Path(session.cwd)
    if session.data_plane == "tmux":
        return f"Started {session.id[:8]} in tmux for {cwd}."
    if session.data_plane == "telegram":
        return (
            f"Started {session.id[:8]} for {cwd}.\n"
            f"DM { _slot_link(session.bot_slot) } and send /status."
        )
    if session.data_plane == "both":
        return (
            f"Started {session.id[:8]} for {cwd}.\n"
            "It should appear in Claude Code Remote Control.\n"
            f"DM { _slot_link(session.bot_slot) } and send /status."
        )
    return f"Started {session.id[:8]} for {cwd}. It should appear in Claude Code Remote Control."


def _slot_link(bot_slot: str | None) -> str:
    if not bot_slot:
        return "the leased session bot"
    username = bot_slot.removeprefix("@")
    return f"@{username} https://t.me/{username}"


def _allowlisted(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        state = _state(context)
        if chat_id not in state.config.telegram.allowed_chat_ids:
            log.warning("dropped non-allowlisted chat_id=%s", chat_id)
            return
        await handler(update, context)

    return wrapped


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.application.bot_data["state"]


def _chat_id(update: Update) -> int:
    chat = update.effective_chat
    if chat is None:
        return 0
    return int(chat.id)


async def _reply_chunks(update: Update, text: str, *, parse_mode: str | None = None) -> None:
    for start in range(0, len(text), 3900):
        await update.effective_message.reply_text(text[start : start + 3900], parse_mode=parse_mode)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("telegram update failed", exc_info=context.error)
