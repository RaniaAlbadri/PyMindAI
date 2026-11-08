"""PyMind AI Telegram + Groq + SQLite (public access, lightweight abuse protection)."""

import asyncio
import logging
import os
import sqlite3

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AsyncGroq,
    AuthenticationError,
    RateLimitError,
)
from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot import MAX_HISTORY_MESSAGES, MODEL, build_messages
from chat_storage import ChatStore, DEFAULT_DB_PATH
from message_guard import MessageGuard

load_dotenv()
logging.basicConfig(level=logging.WARNING)

MAX_MESSAGE_CHARS = 5000   # Per-message text size only, NOT a daily message count.
MAX_PARALLEL_GROQ = 3       # Avoid flooding the free API with simultaneous requests.


def allowed_user_ids(raw: str) -> set[int]:
    """Blank means anybody may message the bot in a private Telegram chat."""
    return {int(item.strip()) for item in raw.split(",") if item.strip()}


def split_telegram_message(message: str, max_utf16_units: int = 3900) -> list[str]:
    """Keep chunks below Telegram's 4096 UTF-16 code-unit text limit."""
    pieces: list[str] = []
    current: list[str] = []
    units = 0
    for char in message:
        char_units = 2 if ord(char) > 0xFFFF else 1
        if current and units + char_units > max_utf16_units:
            pieces.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += char_units
    if current:
        pieces.append("".join(current))
    return pieces


async def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Only private chats; optional allowlist (leave blank for public)."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type != ChatType.PRIVATE or not user:
        return False
    allowlist: set[int] = context.application.bot_data["allowed_ids"]
    if allowlist and user.id not in allowlist:
        if update.effective_message:
            await update.effective_message.reply_text("هذا البوت خاص حالياً 🌷")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_authorized(update, context):
        return
    await update.effective_message.reply_text(
        "هلا! 🤖 آني PyMind AI، اسألني أي سؤال نصّي.\n\n"
        "/clear — مسح ذاكرة محادثتك\n"
        "/help — المساعدة\n"
        "/privacy — خصوصية المحادثات\n"
        "/id — رقم حسابك"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_authorized(update, context):
        return
    await update.effective_message.reply_text(
        "اكتب أي سؤال نصي حتى أجاوبك.\n"
        "ماكو حد يومي للرسائل من داخل البوت، بس حدود Groq المجانية تبقى سارية.\n"
        "إذا تريد ترسل نفس السؤال مرة ثانية، انتظر ثواني قليلة.\n\n"
        "/clear — مسح المحادثة المخزونة\n"
        "/privacy — كيفية حفظ الرسائل\n"
        "/id — رقم حسابك"
    )


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_authorized(update, context):
        return
    await update.effective_message.reply_text(
        "🔐 خصوصيتك: المحادثات تنحفظ بملف SQLite على حاسبة مشغّل البوت، "
        "والأسئلة وسياق المحادثة الحديث يُرسلون إلى Groq لإنتاج الرد. "
        "أمر /clear يمسح محادثتك من قاعدة بيانات البوت المحلية، "
        "لكنه ما يمسح رسائلك من تطبيق Telegram أو أي بيانات قد تحتفظ بها الخدمات الخارجية. "
        "لا ترسل معلومات حساسة."
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_authorized(update, context):
        return
    chat_id = update.effective_chat.id
    guard: MessageGuard = context.application.bot_data["message_guard"]
    if guard.is_busy(chat_id):
        await update.effective_message.reply_text("أكمل الرد الحالي أولاً، وبعدها ارسل /clear 🌷")
        return
    store: ChatStore = context.application.bot_data["chat_store"]
    try:
        store.clear(chat_id)
        guard.clear(chat_id)
    except sqlite3.Error:
        logging.exception("Failed to delete chat history")
        await update.effective_message.reply_text("تعذر مسح المحادثة من قاعدة البيانات. راجعي PowerShell.")
        return
    await update.effective_message.reply_text("تم مسح محادثتك المخزونة! بدينا من جديد 🧹")


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE and update.effective_user:
        await update.effective_message.reply_text(f"رقم حسابك في Telegram: {update.effective_user.id}")


async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_authorized(update, context):
        return
    message = update.effective_message
    question = (message.text or "").strip()
    if not question:
        return
    if len(question) > MAX_MESSAGE_CHARS:
        await message.reply_text(
            f"الرسالة طويلة، خليها أقل من {MAX_MESSAGE_CHARS} حرف. "
            "هذا حد طول الرسالة مو عدد الرسائل اليومية 🌷"
        )
        return

    chat_id = update.effective_chat.id
    guard: MessageGuard = context.application.bot_data["message_guard"]
    denial = guard.begin(chat_id, question)
    if denial == "busy":
        await message.reply_text("بعدني دا أجهز ردك السابق 🌷 من أكمله ابعث رسالتك الجديدة.")
        return
    if denial == "duplicate":
        await message.reply_text("وصلني نفس السؤال قبل ثواني 😄 انتظر شوي إذا تريد تعيده.")
        return

    success = False
    try:
        store: ChatStore = context.application.bot_data["chat_store"]
        try:
            history = store.recent(chat_id, MAX_HISTORY_MESSAGES)
        except sqlite3.Error:
            logging.exception("Could not read history")
            await message.reply_text("تعذر قراءة المحادثة من قاعدة البيانات. راجعي PowerShell.")
            return

        client: AsyncGroq = context.application.bot_data["groq_client"]
        semaphore: asyncio.Semaphore = context.application.bot_data["groq_semaphore"]
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            async with semaphore:
                completion = await client.chat.completions.create(
                    model=MODEL,
                    messages=build_messages(history, question),
                    temperature=0.6,
                    max_completion_tokens=1500,
                    reasoning_effort="low",
                    include_reasoning=False,
                )
            answer = (completion.choices[0].message.content or "").strip()
        except AuthenticationError:
            await message.reply_text("مفتاح Groq غير صالح. راجعي GROQ_API_KEY في .env")
            return
        except RateLimitError:
            await message.reply_text("وصلنا مؤقتاً لحد Groq المجاني. جرب بعد شوية 🌷")
            return
        except APIConnectionError:
            await message.reply_text("تعذّر الاتصال بـ Groq. تأكد من الإنترنت وجرب مرة ثانية.")
            return
        except APIStatusError:
            await message.reply_text("صار خطأ بخدمة الذكاء الاصطناعي. جرب مرة ثانية.")
            return
        except Exception:
            logging.exception("Unexpected error while asking Groq")
            await message.reply_text("صار خطأ غير متوقع، راجعي PowerShell.")
            return

        if not answer:
            await message.reply_text("ما وصل رد من النموذج. جرّب مرة ثانية.")
            return

        for piece in split_telegram_message(answer):
            await message.reply_text(piece)

        try:
            store.save_exchange(chat_id, question, answer)
        except sqlite3.Error:
            logging.exception("Could not save answer to SQLite")
            await message.reply_text("تنبيه: الرد وصل، بس تعذر حفظه بالذاكرة الدائمة.")
            return
        success = True
    finally:
        guard.finish(chat_id, question, successful=success)


async def close_groq(application: Application) -> None:
    await application.bot_data["groq_client"].close()


def main() -> None:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not groq_key or groq_key == "paste_your_groq_key_here":
        raise SystemExit("Add your existing GROQ_API_KEY to .env")
    if not telegram_token or telegram_token == "paste_your_telegram_bot_token_here":
        raise SystemExit("Add TELEGRAM_BOT_TOKEN from @BotFather to .env")

    try:
        allowlist = allowed_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    except ValueError as exc:
        raise SystemExit("TELEGRAM_ALLOWED_USER_IDS must be a comma-separated list of IDs") from exc

    app = (
        ApplicationBuilder()
        .token(telegram_token)
        .concurrent_updates(8)
        .post_shutdown(close_groq)
        .build()
    )
    store = ChatStore(DEFAULT_DB_PATH)
    try:
        store.initialize()
    except sqlite3.Error as exc:
        raise SystemExit(f"Unable to initialize SQLite database: {exc}") from exc

    app.bot_data["groq_client"] = AsyncGroq(api_key=groq_key, timeout=60.0)
    app.bot_data["chat_store"] = store
    app.bot_data["allowed_ids"] = allowlist
    app.bot_data["message_guard"] = MessageGuard(duplicate_window_seconds=8)
    app.bot_data["groq_semaphore"] = asyncio.Semaphore(MAX_PARALLEL_GROQ)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))

    print("PyMind AI Telegram running. Press Ctrl+C to stop.")
    print(f"SQLite history file: {store.db_path}")
    if allowlist:
        print("Private allowlist enabled: bot is NOT public. Clear TELEGRAM_ALLOWED_USER_IDS to open it.")
    else:
        print("Public access is ON for private chats. No daily per-user message quota.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
