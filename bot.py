import os
import logging
import sqlite3

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# إعدادات البوت
# =========================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8942561054:AAGyjDdafbUbNeO_-fhqPcZL5_Y1cgE78Nc").strip()
OWNER_ID = os.getenv("TELEGRAM_OWNER_ID","8374709753").strip()

DB_PATH = Path(__file__).resolve().parent / "abdo_cloud.db"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# تقليل ظهور تفاصيل الطلبات في السجل
logging.getLogger("httpx").setLevel(logging.WARNING)


# =========================
# قاعدة البيانات
# =========================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT,
                caption TEXT,
                saved_at TEXT NOT NULL
            )
        """)


def save_file(file_id, file_type, file_name, caption):
    saved_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            INSERT INTO files
            (file_id, file_type, file_name, caption, saved_at)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, file_type, file_name, caption, saved_at))

        return cursor.lastrowid


def get_file(file_number):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM files WHERE id = ?",
            (file_number,),
        ).fetchone()


def list_files(limit=20):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT * FROM files
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()


def search_files(query, limit=20):
    pattern = f"%{query}%"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT * FROM files
            WHERE COALESCE(file_name, '') LIKE ?
               OR COALESCE(caption, '') LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (pattern, pattern, limit)).fetchall()


# =========================
# الأمان
# =========================

def is_owner(update: Update) -> bool:
    user = update.effective_user

    return (
        user is not None
        and OWNER_ID.isdigit()
        and user.id == int(OWNER_ID)
    )


async def owner_only(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not is_owner(update):
        return False

    return True


# =========================
# الأوامر
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    await update.effective_message.reply_text(
        "al3oo"
        "☁️ أهلاً بيك في Abdo Cloud!\n\n"
        "ابعتلي أي ملف عشان أحفظ بياناته.\n\n"
        "📂 /list - عرض آخر الملفات\n"
        "🔎 /find كلمة - البحث عن ملف\n"
        "📥 /get رقم - استرجاع ملف\n"
        "🗑 /delete رقم - حذف سجل الملف\n"
        "🆔 /myid - معرفة رقم حسابك\n"
        "ℹ️ /help - المساعدة"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    await update.effective_message.reply_text(
        "طريقة الاستخدام:\n\n"
        "1. ابعت صورة أو فيديو أو مستند للبوت.\n"
        "2. البوت هيسجل الملف في قاعدة البيانات.\n"
        "3. استخدم /list لعرض آخر 20 ملف.\n"
        "4. استخدم /find تقرير للبحث عن كلمة.\n"
        "5. استخدم /get 3 لاسترجاع الملف رقم 3.\n"
        "6. استخدم /delete 3 لحذف سجل الملف رقم 3.\n\n"
        "حذف السجل لا يحذف الملف الأصلي من تليجرام."
    )


async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    if user is None:
        return

    if not await owner_only(update, context):
        return

    await update.effective_message.reply_text(
        f"Telegram User ID: {user.id}"
    )


async def list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    rows = list_files()

    if not rows:
        await update.effective_message.reply_text(
            "لسه مفيش ملفات محفوظة."
        )
        return

    lines = ["📂 آخر الملفات المحفوظة:"]

    for row in rows:
        name = row["file_name"] or row["caption"] or row["file_type"]
        name = name.replace("\n", " ")[:100]
        lines.append(f'{row["id"]}. {name}')

    await update.effective_message.reply_text("\n".join(lines))


async def find_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    query = " ".join(context.args).strip()

    if not query:
        await update.effective_message.reply_text(
            "اكتب كلمة للبحث، مثال:\n/find محاضرة"
        )
        return

    rows = search_files(query)

    if not rows:
        await update.effective_message.reply_text(
            "ملقتش ملفات مطابقة للكلمة دي."
        )
        return

    lines = ["🔎 نتائج البحث:"]

    for row in rows:
        name = row["file_name"] or row["caption"] or row["file_type"]
        name = name.replace("\n", " ")[:100]
        lines.append(f'{row["id"]}. {name}')

    await update.effective_message.reply_text("\n".join(lines))


async def get_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "اكتب رقم الملف، مثال:\n/get 3"
        )
        return

    row = get_file(int(context.args[0]))

    if row is None:
        await update.effective_message.reply_text(
            "مش لاقي الملف بالرقم ده."
        )
        return

    file_id = row["file_id"]
    file_type = row["file_type"]
    chat_id = update.effective_chat.id
    bot = context.bot

    try:
        if file_type == "photo":
            await bot.send_photo(chat_id, file_id)
        elif file_type == "video":
            await bot.send_video(chat_id, file_id)
        elif file_type == "animation":
            await bot.send_animation(chat_id, file_id)
        elif file_type == "audio":
            await bot.send_audio(chat_id, file_id)
        elif file_type == "voice":
            await bot.send_voice(chat_id, file_id)
        elif file_type == "video_note":
            await bot.send_video_note(chat_id, file_id)
        elif file_type == "sticker":
            await bot.send_sticker(chat_id, file_id)
        else:
            await bot.send_document(
                chat_id,
                file_id,
                caption=row["file_name"] or None,
            )

    except Exception:
        logger.exception("Failed to retrieve file id=%s", row["id"])
        await update.effective_message.reply_text(
            "معرفتش أرجع الملف. ممكن يكون الملف غير متاح "
            "أو حصل خطأ من تليجرام."
        )


async def delete_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "اكتب رقم السجل، مثال:\n/delete 3"
        )
        return

    file_number = int(context.args[0])

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "DELETE FROM files WHERE id = ?",
            (file_number,),
        )

    if cursor.rowcount:
        await update.effective_message.reply_text(
            "تم حذف سجل الملف من قاعدة البيانات. "
            "الملف الأصلي على تليجرام لم يُحذف."
        )
    else:
        await update.effective_message.reply_text(
            "مش لاقي سجل بالرقم ده."
        )


# =========================
# استقبال الملفات
# =========================

def extract_file(message):
    if message.photo:
        item = message.photo[-1]
        return item.file_id, "photo", None

    media_types = (
        ("document", message.document),
        ("video", message.video),
        ("animation", message.animation),
        ("audio", message.audio),
        ("voice", message.voice),
        ("video_note", message.video_note),
        ("sticker", message.sticker),
    )

    for file_type, item in media_types:
        if item:
            name = getattr(item, "file_name", None)
            return item.file_id, file_type, name

    return None


async def receive_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await owner_only(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    result = extract_file(message)

    if result is None:
        return

    file_id, file_type, file_name = result

    record_id = save_file(
        file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        caption=message.caption,
    )

    name = file_name or file_type

    await message.reply_text(
        f"✅ تم حفظ سجل الملف بنجاح!\n\n"
        f"🆔 رقم الملف: {record_id}\n"
        f"📄 النوع: {file_type}\n"
        f"📌 الاسم: {name}\n\n"
        f"لاسترجاعه اكتب:\n/get {record_id}"
    )


# =========================
# تشغيل البوت
# =========================

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Abdo Cloud is running")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_ping_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

def main():
    print("TOKEN:", TOKEN)
    print("OWNER_ID:", OWNER_ID)

    if not TOKEN:
        raise RuntimeError(
            "متغير TELEGRAM_BOT_TOKEN غير مضبوط."
        )

    if not OWNER_ID.isdigit():
        raise RuntimeError(
            "متغير TELEGRAM_OWNER_ID غير مضبوط. "
            "ضع رقم حسابك الصحيح."
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("get", get_command))
    app.add_handler(CommandHandler("delete", delete_command))

    media_filter = (
        filters.PHOTO
        | filters.Document.ALL
        | filters.VIDEO
        | filters.ANIMATION
        | filters.AUDIO
        | filters.VOICE
        | filters.VIDEO_NOTE
        | filters.Sticker.ALL
    )

    app.add_handler(
        MessageHandler(media_filter, receive_file)
    )

    logger.info("Abdo Cloud is starting...")
    start_ping_server()
    app.run_polling()



if __name__ == "__main__":
    main()
