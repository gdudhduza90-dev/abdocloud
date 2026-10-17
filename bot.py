import os
import random
import secrets
import sqlite3
import string
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "abdo_cloud_v2.db")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# مكتبة httpx بتكتب رابط الطلب (وفيه التوكن) في السجل، فبنخفّض مستواها
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("abdo-cloud")


# ---------------------------------------------------------------
# سيرفر صغير للاستضافة (Health check)
# ---------------------------------------------------------------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Abdo Cloud OK")

    def log_message(self, *args):
        pass


def start_ping_server():
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), PingHandler)
    except OSError as e:
        logger.warning("ping server مش شغال: %s", e)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("ping server على بورت %s", port)


# ---------------------------------------------------------------
# قاعدة البيانات
# ---------------------------------------------------------------
def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_unique_id TEXT NOT NULL UNIQUE,
            file_name TEXT,
            file_type TEXT,
            file_size INTEGER,
            saved_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def save_file(file_id, unique_id, name, ftype, size):
    conn = db()
    cur = conn.execute(
        "INSERT OR IGNORE INTO files "
        "(file_id, file_unique_id, file_name, file_type, file_size) "
        "VALUES (?, ?, ?, ?, ?)",
        (file_id, unique_id, name, ftype, size),
    )
    conn.commit()
    added = cur.rowcount > 0
    conn.close()
    return added


# ---------------------------------------------------------------
# الحماية: صاحب البوت بس
# ---------------------------------------------------------------
def is_owner(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == OWNER_ID


async def guard(update: Update) -> bool:
    if is_owner(update):
        return True
    if update.callback_query:
        await update.callback_query.answer("⛔ البوت ده خاص", show_alert=True)
    elif update.message:
        await update.message.reply_text("⛔ البوت ده خاص، مش مسموحلك تستخدمه.")
    return False


# ---------------------------------------------------------------
# محتوى الأمن السيبراني (للتعلم والدفاع)
# ---------------------------------------------------------------
TOPICS = {
    "linux": (
        "🐧 أساسيات لينكس\n\n"
        "أوامر لازم تعرفها:\n"
        "pwd - إنت فين دلوقتي\n"
        "ls -la - عرض الملفات بالتفصيل\n"
        "cd مجلد - الدخول لمجلد\n"
        "cat ملف - عرض محتوى ملف\n"
        "grep كلمة ملف - بحث جوه ملف\n"
        "chmod / chown - صلاحيات الملفات\n"
        "sudo - تنفيذ بصلاحية الأدمن\n"
        "ps aux / top - العمليات الشغالة\n"
        "ip a - عناوين الشبكة\n"
        "ss -tulpn - البورتات المفتوحة على جهازك\n"
        "journalctl / tail -f /var/log/... - قراءة السجلات\n\n"
        "فكرة مهمة: الصلاحيات. رقم زي 640 معناه: صاحب الملف قراءة وكتابة، "
        "المجموعة قراءة، الباقي ممنوع.\n\n"
        "ابدأ تمرّن: ثبّت Ubuntu أو Kali على VirtualBox (عندك VirtualBox)."
    ),
    "network": (
        "🌐 أساسيات الشبكات\n\n"
        "- IP: عنوان الجهاز. Subnet: حدود الشبكة. Gateway: باب الخروج للنت.\n"
        "- TCP: اتصال مضمون (ويب، SSH). UDP: أسرع بس من غير ضمان (DNS، فيديو).\n"
        "- DNS: بيحوّل اسم الموقع لـ IP.\n"
        "- DHCP: بيدّي الأجهزة عناوين تلقائي.\n"
        "- NAT: بيخلي أجهزة كتير تشارك IP عام واحد.\n"
        "- Firewall: بيسمح أو يمنع الاتصالات حسب قواعد.\n\n"
        "بورتات شائعة:\n"
        "22 SSH | 53 DNS | 80 HTTP | 443 HTTPS | 3389 RDP | 3306 MySQL\n\n"
        "أوامر:\n"
        "ping, traceroute (tracert في ويندوز), nslookup, ipconfig / ip a\n\n"
        "أداة التعلم الأهم: Wireshark. حلّل حركة الشبكة بتاعتك انت وشوف "
        "الـ DNS والـ TCP handshake بنفسك."
    ),
    "kali": (
        "🐉 Kali Linux\n\n"
        "توزيعة لينكس متجهزة بأدوات اختبار الاختراق والتحليل الأمني، "
        "بتتستخدم من متخصصين بتصريح.\n\n"
        "أنواع الأدوات:\n"
        "- استكشاف الشبكة: nmap\n"
        "- تحليل الترافيك: Wireshark\n"
        "- اختبار تطبيقات الويب: Burp Suite\n"
        "- فحص الأنظمة: OpenVAS / Nikto\n"
        "- تحليل الأدلة الرقمية: Autopsy\n\n"
        "⚖️ قاعدة ذهبية: متجرّبش أي أداة إلا على جهازك أو معمل تعليمي أو "
        "نظام معاك تصريح مكتوب عليه. غير كده ده غير قانوني.\n\n"
        "أماكن تمرّن فيها بشكل قانوني:\n"
        "TryHackMe (للمبتدئين) - OverTheWire - picoCTF - Hack The Box - "
        "DVWA (موقع ضعيف مقصود تركّبه عندك)\n\n"
        "نصيحة: شغّل Kali على VirtualBox، مش على جهازك الأساسي."
    ),
    "security": (
        "🔐 أساسيات الأمن السيبراني\n\n"
        "مثلث CIA:\n"
        "- Confidentiality السرية: محدش يشوف إلا المسموح له\n"
        "- Integrity السلامة: البيانات متتغيرش من غير إذن\n"
        "- Availability الإتاحة: الخدمة شغالة وقت ما تحتاجها\n\n"
        "عادات حماية أساسية:\n"
        "1) باسورد طويل ومختلف لكل حساب + مدير باسوردات\n"
        "2) تفعيل التحقق بخطوتين (يفضل تطبيق مش SMS)\n"
        "3) تحديث النظام والبرامج\n"
        "4) نسخ احتياطي منتظم (قاعدة 3-2-1)\n"
        "5) أقل صلاحيات ممكنة (Least Privilege)\n"
        "6) متفتحش مرفقات أو روابط من مصدر مش متأكد منه\n\n"
        "ثغرات الويب الشائعة (OWASP Top 10): Injection, Broken Access Control, "
        "XSS, Misconfiguration, Vulnerable Components. اتعلم تحميها قبل ما تعرف تكسرها."
    ),
    "roadmap": (
        "🗺 خريطة تعلم الأمن السيبراني\n\n"
        "1) الشبكات: TCP/IP, DNS, HTTP, الفايروول\n"
        "2) لينكس: الأوامر والصلاحيات والسجلات\n"
        "3) بايثون: أتمتة وتحليل بسيط\n"
        "4) مفاهيم الأمن: CIA, التشفير, المصادقة, الهجمات الشائعة\n"
        "5) معامل عملية: TryHackMe ثم OverTheWire ثم picoCTF\n"
        "6) تخصص: الدفاع (SOC / Blue Team) أو الاختبار (Pentest / Red Team)\n"
        "7) شهادات: CompTIA Security+ (أساسي) ثم eJPT أو غيرها حسب مسارك\n\n"
        "الأهم: التمرين العملي كل يوم ولو نص ساعة، وتدوّن اللي اتعلمته."
    ),
    "phish": (
        "🎣 إزاي تكشف رسالة فيشينج\n\n"
        "علامات خطر:\n"
        "- استعجال أو تهديد (حسابك هيتقفل خلال ساعة)\n"
        "- رابط شكله قريب من الأصلي (paypa1.com بدل paypal.com)\n"
        "- مرسل غريب أو دومين مش رسمي\n"
        "- طلب باسورد أو كود تحقق أو بيانات بنك\n"
        "- مرفق غير متوقع (zip, exe, ملف ماكرو)\n"
        "- أخطاء لغوية أو تصميم مش مظبوط\n\n"
        "اعمل إيه:\n"
        "1) متدوسش على الرابط\n"
        "2) افتح الموقع بنفسك من المتصفح\n"
        "3) متديش أي كود وصلك لحد، حتى لو قال إنه من الدعم\n"
        "4) لو دخلت بياناتك: غيّر الباسورد فورًا وفعّل التحقق بخطوتين\n"
        "5) بلّغ عن الرسالة واحذفها"
    ),
}

TIPS = [
    "استخدم باسورد مختلف لكل حساب. لو واحد اتسرب، الباقي يفضل آمن.",
    "فعّل التحقق بخطوتين على إيميلك الأساسي الأول، لأنه مفتاح باقي حساباتك.",
    "ماتشحنش موبايلك من منافذ USB عامة غير موثوقة.",
    "الواي فاي العام مش مكان لدخول حسابات حساسة من غير حماية.",
    "حدّث الجهاز والبرامج، أغلب الاختراقات بتستغل ثغرات معروفة ومتصلحة.",
    "الشركات الجادة عمرها ما بتطلب باسوردك أو كود التحقق منك.",
    "اعمل نسخة احتياطية من ملفاتك المهمة في مكانين على الأقل.",
    "اقفل البورتات والخدمات اللي مش محتاجها على جهازك.",
    "اختبر أمن الأدوات على جهازك أو معمل تعليمي بس، مش على غيرك.",
    "قبل ما تثبت برنامج، حمّله من الموقع الرسمي بس.",
]

# (السؤال، الاختيارات، رقم الإجابة الصح، الشرح)
QUIZ = [
    ("إيه معنى الحرف C في مثلث CIA؟",
     ["Control", "Confidentiality", "Connection"], 1,
     "C = Confidentiality يعني السرية."),
    ("أي بورت بيستخدمه HTTPS؟",
     ["80", "22", "443"], 2,
     "HTTPS بيشتغل على 443، و80 لـ HTTP، و22 لـ SSH."),
    ("أي أمر بيعرض البورتات المفتوحة في لينكس؟",
     ["ss -tulpn", "ls -la", "cat /etc/passwd"], 0,
     "ss -tulpn بيعرض الاتصالات والبورتات المفتوحة."),
    ("أنسب حماية للحساب بعد الباسورد؟",
     ["نفس الباسورد في كل مكان", "التحقق بخطوتين", "كتابة الباسورد في ملاحظات الموبايل"], 1,
     "التحقق بخطوتين بيحمي حتى لو الباسورد اتسرب."),
    ("إيه هو الفيشينج؟",
     ["خداع المستخدم عشان يسلّم بياناته", "نوع من الفايروول", "أداة لتسريع النت"], 0,
     "الفيشينج هو انتحال جهة موثوقة لسرقة بيانات."),
    ("البروتوكول اللي بيحوّل اسم الموقع لـ IP؟",
     ["DHCP", "DNS", "NAT"], 1,
     "DNS هو دليل الأسماء للإنترنت."),
    ("قانونيًا، أنسب مكان تجرّب فيه أدوات الاختراق؟",
     ["موقع حد غريب", "معمل تعليمي أو جهازك الخاص", "شبكة الجامعة"], 1,
     "اتمرّن بس على أنظمة تملكها أو معاك تصريح، زي TryHackMe و DVWA."),
    ("مبدأ أقل صلاحية (Least Privilege) معناه؟",
     ["الكل أدمن", "كل مستخدم ياخد الصلاحيات اللي يحتاجها بس", "منع كل المستخدمين"], 1,
     "كل حساب ياخد أقل صلاحيات تخلّص شغله."),
    ("إيه الأداة المشهورة لتحليل حركة الشبكة؟",
     ["Wireshark", "Photoshop", "Notepad"], 0,
     "Wireshark بيلتقط ويحلل الحزم."),
    ("قاعدة النسخ الاحتياطي 3-2-1 معناها؟",
     ["3 نسخ، على نوعين تخزين، واحدة بعيدة", "3 باسوردات", "نسختين بس"], 0,
     "3 نسخ، على 2 نوع تخزين، ونسخة واحدة في مكان بعيد."),
]


def menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(
        [
            [b("🐧 لينكس", callback_data="t:linux"),
             b("🌐 الشبكات", callback_data="t:network")],
            [b("🐉 Kali", callback_data="t:kali"),
             b("🔐 أساسيات الأمن", callback_data="t:security")],
            [b("🗺 خريطة التعلم", callback_data="t:roadmap"),
             b("🎣 كشف الفيشينج", callback_data="t:phish")],
            [b("🧠 اختبر نفسك", callback_data="quiz:new")],
        ]
    )


# ---------------------------------------------------------------
# أوامر عامة
# ---------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.message.reply_text(
        "☁️ أهلاً بيك في Abdo Cloud\n\n"
        "📁 التخزين:\n"
        "ابعتلي أي ملف وأنا أحفظه.\n"
        "/list - آخر الملفات\n"
        "/search كلمة - بحث بالاسم\n"
        "/get رقم - استرجاع ملف\n\n"
        "🛡 الأمن السيبراني (للتعلم):\n"
        "/cyber - القائمة الرئيسية\n"
        "/quiz - سؤال اختبار\n"
        "/tip - نصيحة أمنية\n"
        "/genpass 16 - باسورد قوي\n"
        "/roadmap - خريطة التعلم"
    )


async def cyber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.message.reply_text(
        "🛡 Abdo Cyber Helper\nاختار موضوع تتعلمه:",
        reply_markup=menu_keyboard(),
    )


async def topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    name = update.message.text.split()[0].lstrip("/").split("@")[0]
    await update.message.reply_text(TOPICS.get(name, "الموضوع مش موجود."))


async def tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.message.reply_text("💡 " + random.choice(TIPS))


async def genpass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    length = 16
    if context.args and context.args[0].isdigit():
        length = max(8, min(64, int(context.args[0])))

    pools = [string.ascii_lowercase, string.ascii_uppercase,
             string.digits, "!@#$%^&*-_=+"]
    chars = [secrets.choice(p) for p in pools]
    allchars = "".join(pools)
    chars += [secrets.choice(allchars) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)

    await update.message.reply_text(
        "🔑 باسورد جديد (بيتولّد على السيرفر ومش بيتخزن):\n\n"
        + "".join(chars)
        + "\n\nانسخه في مدير باسوردات، وامسح الرسالة دي من المحادثة بعدها."
    )


# ---------------------------------------------------------------
# الاختبار
# ---------------------------------------------------------------
def quiz_markup(q_index: int) -> InlineKeyboardMarkup:
    options = QUIZ[q_index][1]
    rows = [
        [InlineKeyboardButton(opt, callback_data=f"qa:{q_index}:{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(rows)


async def send_quiz(message):
    idx = random.randrange(len(QUIZ))
    await message.reply_text(
        "🧠 " + QUIZ[idx][0], reply_markup=quiz_markup(idx)
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await send_quiz(update.message)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    query = update.callback_query
    data = query.data or ""
    await query.answer()

    if data.startswith("t:"):
        key = data[2:]
        await query.message.reply_text(TOPICS.get(key, "الموضوع مش موجود."))

    elif data == "quiz:new":
        await send_quiz(query.message)

    elif data.startswith("qa:"):
        try:
            _, q_str, a_str = data.split(":")
            q_index, answer = int(q_str), int(a_str)
            question, options, correct, explanation = QUIZ[q_index]
        except (ValueError, IndexError):
            return
        if answer == correct:
            result = "✅ إجابة صح!"
        else:
            result = f"❌ غلط. الصح: {options[correct]}"
        again = InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ سؤال تاني", callback_data="quiz:new")]]
        )
        await query.edit_message_text(
            f"🧠 {question}\n\n{result}\n{explanation}", reply_markup=again
        )


# ---------------------------------------------------------------
# التخزين
# ---------------------------------------------------------------
def extract_file_info(message):
    if message.document:
        f = message.document
        return f.file_id, f.file_unique_id, f.file_name or "document", "document", f.file_size
    if message.photo:
        f = message.photo[-1]
        return f.file_id, f.file_unique_id, f"photo_{f.file_unique_id}.jpg", "photo", f.file_size
    if message.video:
        f = message.video
        return f.file_id, f.file_unique_id, f.file_name or f"video_{f.file_unique_id}.mp4", "video", f.file_size
    if message.audio:
        f = message.audio
        return f.file_id, f.file_unique_id, f.file_name or f"audio_{f.file_unique_id}.mp3", "audio", f.file_size
    if message.voice:
        f = message.voice
        return f.file_id, f.file_unique_id, f"voice_{f.file_unique_id}.ogg", "voice", f.file_size
    return None


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    info = extract_file_info(update.message)
    if info is None:
        await update.message.reply_text("النوع ده مش مدعوم.")
        return
    file_id, unique_id, name, ftype, size = info
    if save_file(file_id, unique_id, name, ftype, size):
        await update.message.reply_text(f"✅ اتحفظ: {name}")
    else:
        await update.message.reply_text(f"ℹ️ الملف ده محفوظ قبل كده: {name}")


async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    conn = db()
    rows = conn.execute(
        "SELECT id, file_name, file_type FROM files ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("مفيش ملفات محفوظة لسه.")
        return
    lines = [f"{r[0]} - {r[1]} ({r[2]})" for r in rows]
    await update.message.reply_text("آخر الملفات:\n\n" + "\n".join(lines))


async def search_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    if not context.args:
        await update.message.reply_text("اكتب كلمة البحث، مثال: /search تقرير")
        return
    keyword = " ".join(context.args)
    conn = db()
    rows = conn.execute(
        "SELECT id, file_name, file_type FROM files "
        "WHERE file_name LIKE ? ORDER BY id DESC LIMIT 30",
        (f"%{keyword}%",),
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("مفيش نتايج.")
        return
    lines = [f"{r[0]} - {r[1]} ({r[2]})" for r in rows]
    await update.message.reply_text("نتايج البحث:\n\n" + "\n".join(lines))


SENDERS = {
    "photo": "reply_photo",
    "video": "reply_video",
    "audio": "reply_audio",
    "voice": "reply_voice",
}


async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("اكتب رقم الملف، مثال: /get 5")
        return
    conn = db()
    row = conn.execute(
        "SELECT file_id, file_type FROM files WHERE id = ?",
        (int(context.args[0]),),
    ).fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("مفيش ملف بالرقم ده.")
        return
    file_id, file_type = row
    sender = getattr(update.message, SENDERS.get(file_type, "reply_document"))
    await sender(file_id)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("خطأ: %s", context.error)


# ---------------------------------------------------------------
# التشغيل
# ---------------------------------------------------------------
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN مش موجود")
    if OWNER_ID == 0:
        raise SystemExit("OWNER_ID مش متظبط")

    init_db()
    start_ping_server()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("cyber", cyber))
    app.add_handler(CommandHandler(["linux", "network", "kali", "security", "roadmap", "phish"], topic_command))
    app.add_handler(CommandHandler("tip", tip))
    app.add_handler(CommandHandler("genpass", genpass))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("search", search_files))
    app.add_handler(CommandHandler("get", get_file))
    app.add_handler(CallbackQueryHandler(on_callback))

    media_filter = (
        filters.Document.ALL
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
    )
    app.add_handler(MessageHandler(media_filter, receive_file))
    app.add_error_handler(on_error)

    logger.info("Abdo Cloud is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
