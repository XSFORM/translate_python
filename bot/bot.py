#!/usr/bin/env python3
"""
bot.py  --  Telegram bot for managing the OpenVPN remote-IP update service.

Environment variables (all required unless noted):
  BOT_TOKEN           Telegram bot token from BotFather
  ALLOWED_IDS         Comma-separated Telegram user IDs allowed to use the bot
  IP_FILE             Path to the file served as /current_vpn_ip.txt
                      (default: /var/www/html/current_vpn_ip.txt)
  HISTORY_FILE        Path to history log (default: /var/lib/remote_refresh/history.log)
  IP_SCAN_FLAG        Path to ip_scan_off.txt flag (default: /var/www/html/ip_scan_off.txt)
  PORT_SCAN_FLAG      Path to port_scan_off.txt flag (default: /var/www/html/port_scan_off.txt)
  DOMAIN_LIST_FILE    Path to domain_list.txt (default: /var/www/html/router/domain_list.txt)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import textwrap
import warnings
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------- Config from environment --------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_IDS = {
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_IDS", "").split(",")
    if uid.strip().isdigit()
}
IP_FILE = os.environ.get("IP_FILE", "/var/www/html/current_vpn_ip.txt")
HISTORY_FILE = os.environ.get(
    "HISTORY_FILE", "/var/lib/remote_refresh/history.log"
)
IP_SCAN_FLAG = os.environ.get("IP_SCAN_FLAG", "/var/www/html/ip_scan_off.txt")
PORT_SCAN_FLAG = os.environ.get(
    "PORT_SCAN_FLAG", "/var/www/html/port_scan_off.txt"
)
DOMAIN_LIST_FILE = os.environ.get(
    "DOMAIN_LIST_FILE", "/var/www/html/router/domain_list.txt"
)

# Conversation states
(
    WAIT_NEW_IP,
    WAIT_DOMAIN_ACTION,
    WAIT_ADD_DOMAIN,
    WAIT_REMOVE_DOMAIN,
) = range(4)

DOMAIN_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$")

# -------- Auth --------
def allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in ALLOWED_IDS


def auth_required(func):
    """Decorator that rejects unauthorized users."""
    import functools

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not allowed(update):
            if update.message:
                await update.message.reply_text("Not authorized.")
            elif update.callback_query:
                await update.callback_query.answer("Not authorized.")
            return ConversationHandler.END

        return await func(update, context)

    return wrapper


# -------- File helpers --------
def read_file(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_sha256(path: str) -> None:
    """Write a companion <path>.sha256 file containing the sha256 of <path>."""
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        write_file(path + ".sha256", digest + "  " + os.path.basename(path) + "\n")
    except OSError as exc:
        logger.warning("sha256 write failed for %s: %s", path, exc)


def read_flag(path: str) -> bool:
    return read_file(path, "0").startswith("1")


def write_flag(path: str, value: bool) -> None:
    write_file(path, "1" if value else "0")


# -------- Domain list helpers --------
def read_domains() -> list[str]:
    raw = read_file(DOMAIN_LIST_FILE, "")
    domains = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        domains.append(line)
    return domains


def write_domains(domains: list[str]) -> None:
    header = (
        "# domain_list.txt\n"
        "# One domain per line. Lines starting with '#' are ignored.\n"
    )
    content = header + "\n".join(domains) + "\n"
    write_file(DOMAIN_LIST_FILE, content)
    write_sha256(DOMAIN_LIST_FILE)


# -------- History --------
def append_history(entry: str) -> None:
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {entry}\n"
    os.makedirs(os.path.dirname(HISTORY_FILE) or ".", exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def read_history(lines: int = 20) -> str:
    raw = read_file(HISTORY_FILE, "")
    if not raw:
        return "(no history yet)"
    all_lines = raw.splitlines()
    return "\n".join(all_lines[-lines:])


# -------- Keyboards --------
MAIN_KB = ReplyKeyboardMarkup(
    [
        ["📡 Current IP", "✏️ Set IP"],
        ["📋 History"],
        ["🔍 IP Scan toggle", "🔍 Port Scan toggle"],
        ["🌐 Domains"],
    ],
    resize_keyboard=True,
)


def main_kb_msg(text: str):
    return {"text": text, "reply_markup": MAIN_KB}


# -------- Handlers --------
@auth_required
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "VPN IP manager ready.", reply_markup=MAIN_KB
    )


@auth_required
async def handle_current_ip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ip = read_file(IP_FILE, "(not set)")
    await update.message.reply_text(f"Current IP: `{ip}`", parse_mode="Markdown")


@auth_required
async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hist = read_history()
    await update.message.reply_text(
        f"Recent changes:\n```\n{hist}\n```", parse_mode="Markdown"
    )


@auth_required
async def handle_ip_scan_toggle(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    current = read_flag(IP_SCAN_FLAG)
    new_val = not current
    write_flag(IP_SCAN_FLAG, new_val)
    state = "OFF (disabled)" if new_val else "ON (enabled)"
    await update.message.reply_text(f"IP scan is now {state}.")


@auth_required
async def handle_port_scan_toggle(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    current = read_flag(PORT_SCAN_FLAG)
    new_val = not current
    write_flag(PORT_SCAN_FLAG, new_val)
    state = "OFF (disabled)" if new_val else "ON (enabled)"
    await update.message.reply_text(f"Port scan is now {state}.")


# -------- Set IP conversation --------
@auth_required
async def set_ip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = read_file(IP_FILE, "(not set)")
    await update.message.reply_text(
        f"Current IP: `{current}`\nSend the new IP address:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
    )
    return WAIT_NEW_IP


async def set_ip_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_KB)
        return ConversationHandler.END

    # Basic IPv4 validation
    parts = text.split(".")
    valid = (
        len(parts) == 4
        and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
        and text not in ("0.0.0.0", "127.0.0.1")
    )
    if not valid:
        await update.message.reply_text("Invalid IP address. Try again or send ❌ Cancel.")
        return WAIT_NEW_IP

    old_ip = read_file(IP_FILE, "")
    write_file(IP_FILE, text + "\n")
    append_history(f"IP changed: {old_ip} -> {text}")
    await update.message.reply_text(
        f"IP updated: `{text}`", parse_mode="Markdown", reply_markup=MAIN_KB
    )
    return ConversationHandler.END


# -------- Domains conversation --------
def domains_list_text() -> str:
    domains = read_domains()
    if not domains:
        return "Domain list is empty."
    numbered = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(domains))
    return f"Current domains:\n```\n{numbered}\n```"


@auth_required
async def domains_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = domains_list_text()
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add domain", callback_data="dom_add"),
                InlineKeyboardButton("➖ Remove domain", callback_data="dom_remove"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="dom_cancel")],
        ]
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return WAIT_DOMAIN_ACTION


async def domains_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "dom_add":
        await query.edit_message_text(
            "Send the domain to add (e.g. `my-domain.com`):",
            parse_mode="Markdown",
        )
        return WAIT_ADD_DOMAIN

    if data == "dom_remove":
        domains = read_domains()
        if not domains:
            await query.edit_message_text("Domain list is empty.")
            return ConversationHandler.END
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(f"🗑 {d}", callback_data=f"dom_del:{d}")]
                for d in domains
            ]
            + [[InlineKeyboardButton("❌ Cancel", callback_data="dom_cancel")]]
        )
        await query.edit_message_text(
            "Select domain to remove:", reply_markup=kb
        )
        return WAIT_REMOVE_DOMAIN

    # dom_cancel
    await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


async def domains_add_receive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text.strip()
    if text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=MAIN_KB)
        return ConversationHandler.END

    if not DOMAIN_RE.match(text):
        await update.message.reply_text(
            "Invalid domain format. Only letters, digits, dots, and hyphens allowed. Try again:"
        )
        return WAIT_ADD_DOMAIN

    domains = read_domains()
    if text in domains:
        await update.message.reply_text(
            f"`{text}` is already in the list.", parse_mode="Markdown", reply_markup=MAIN_KB
        )
        return ConversationHandler.END

    domains.append(text)
    write_domains(domains)
    append_history(f"domain added: {text}")
    await update.message.reply_text(
        f"Added `{text}`.\n\n{domains_list_text()}",
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )
    return ConversationHandler.END


async def domains_remove_choose(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "dom_cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data.startswith("dom_del:"):
        domain = data[len("dom_del:"):]
        domains = read_domains()
        if domain in domains:
            domains.remove(domain)
            write_domains(domains)
            append_history(f"domain removed: {domain}")
            remaining = domains_list_text()
            await query.edit_message_text(
                f"Removed `{domain}`.\n\n{remaining}", parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"`{domain}` not found in list.", parse_mode="Markdown")
        return ConversationHandler.END

    await query.edit_message_text("Unknown action.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=MAIN_KB)
    return ConversationHandler.END


# -------- Application setup --------
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # Set IP conversation
    set_ip_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^✏️ Set IP$"), set_ip_start)],
        states={WAIT_NEW_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_ip_receive)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Domains conversation
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message\..*",
            category=PTBUserWarning,
        )
        domains_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(r"^🌐 Domains$"), domains_start)],
            states={
                WAIT_DOMAIN_ACTION: [CallbackQueryHandler(domains_action, pattern="^dom_")],
                WAIT_ADD_DOMAIN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, domains_add_receive)
                ],
                WAIT_REMOVE_DOMAIN: [
                    CallbackQueryHandler(domains_remove_choose, pattern="^dom_")
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            per_message=False,
        )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(set_ip_conv)
    app.add_handler(domains_conv)
    app.add_handler(
        MessageHandler(filters.Regex(r"^📡 Current IP$"), handle_current_ip)
    )
    app.add_handler(
        MessageHandler(filters.Regex(r"^📋 History$"), handle_history)
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^🔍 IP Scan toggle$"), handle_ip_scan_toggle
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^🔍 Port Scan toggle$"), handle_port_scan_toggle
        )
    )

    return app


def main() -> None:
    app = build_app()
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
