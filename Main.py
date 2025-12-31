import logging
import sqlite3
import asyncio
import threading
from datetime import datetime
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ==================== تنظیمات ====================
TOKEN = "8582244459:AAHJuWSrJVO0NQS6vAukbY1IV5WT5uIPUlE"
ADMIN_PASSWORD = "123456"
CHANNEL_ID = -1002216477329  # آیدی عددی کانال
GROUP_ADMIN_ID = -1003351144029  # <<<--- آیدی واقعی گروه ادمین را اینجا بگذار !!!

# Flask برای Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

(
    ADMIN_AUTH, ADMIN_MENU,
    ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
    MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
    EDIT_TEXT_SELECT, EDIT_TEXT_INPUT,
    MANAGE_USER_INPUT, MANAGE_USER_ACTION,
    BROADCAST_MESSAGE
) = range(14)

# ==================== دیتابیس ====================
def init_db():
    conn = sqlite3.connect("parstrade.db", check_same_thread=False)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 join_date TEXT,
                 referrals_confirmed INTEGER DEFAULT 0
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pending_referrals (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 new_user_id INTEGER UNIQUE,
                 new_username TEXT,
                 new_first_name TEXT,
                 referrer_id INTEGER,
                 join_date TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS confirmed_referrals (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 new_user_id INTEGER,
                 new_first_name TEXT,
                 new_username TEXT,
                 referrer_id INTEGER,
                 confirm_date TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (
                 key TEXT PRIMARY KEY,
                 content TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER,
                 part INTEGER,
                 req_refs INTEGER,
                 content_type TEXT,
                 file_id TEXT,
                 caption TEXT
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lives (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT,
                 link TEXT,
                 file_id TEXT,
                 date_recorded TEXT,
                 is_active INTEGER DEFAULT 0
                 )''')

    defaults = {
        "welcome": "🌹 درود بر شما!\nبه کامیونیتی پارس ترید خوش آمدید.\n\nبرای دسترسی به تمام امکانات، حتماً عضو کانال اصلی باشید:",
        "about": "درباره پارس ترید..."
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade.db", check_same_thread=False)

def get_text(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,))
    res = cur.fetchone()
    conn.close()
    return res[0] if res else ""

# ==================== چک عضویت ====================
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        allowed_statuses = {"member", "administrator", "creator"}
        return member.status in allowed_statuses
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

# ==================== /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    conn = get_db()
    c = conn.cursor()

    c.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
              (user.id, user.username, datetime.now().strftime("%Y-%m-%d")))
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (user.username, user.id))
    conn.commit()

    referrer = None
    if args and args[0].isdigit() and int(args[0]) != user.id:
        referrer = int(args[0])

    if referrer:
        c.execute("SELECT 1 FROM pending_referrals WHERE new_user_id = ?", (user.id,))
        if not c.fetchone():
            c.execute("""INSERT INTO pending_referrals 
                         (new_user_id, new_username, new_first_name, referrer_id, join_date)
                         VALUES (?, ?, ?, ?, ?)""",
                      (user.id, user.username, user.first_name, referrer,
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تأیید رفرال", callback_data=f"approve_ref_{user.id}_{referrer}"),
                    InlineKeyboardButton("❌ رد رفرال", callback_data=f"reject_ref_{user.id}_{referrer}")
                ]
            ])

            try:
                await context.bot.send_message(
                    GROUP_ADMIN_ID,
                    f"🔔 **درخواست رفرال جدید**\n\n"
                    f"👤 نام: {user.first_name}\n"
                    f"📛 یوزرنیم: @{user.username or 'ندارد'}\n"
                    f"🆔 آیدی: `{user.id}`\n"
                    f"👨‍💼 دعوت‌کننده: `{referrer}`\n"
                    f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"خطا در ارسال به گروه ادمین: {e}")

    conn.close()

    if not await check_subscription(update, context):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 عضویت در کانال", url="https://t.me/ParsTradeCommunity")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
        ])
        await update.message.reply_text(
            "⛔️ برای استفاده از ربات حتماً باید عضو کانال باشید!\n\nدکمه زیر را پس از عضویت بزنید:",
            reply_markup=keyboard
        )
        return

    await show_main_menu(update, context)

# ==================== منوی اصلی ====================
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_text("welcome") + "\n\n📢 کانال اصلی: @ParsTradeCommunity"
    keyboard = [
        [InlineKeyboardButton("🎓 آموزش VIP", callback_data="menu_edu"), InlineKeyboardButton("🔴 لایو ترید", callback_data="menu_live")],
        [InlineKeyboardButton("🏆 تورنمنت", callback_data="menu_tour"), InlineKeyboardButton("👤 پروفایل", callback_data="menu_prof")],
        [InlineKeyboardButton("🌐 سایت", url="https://pars-trade.com"), InlineKeyboardButton("اینستاگرام", url="https://instagram.com/parstradecommunity")],
        [InlineKeyboardButton("ℹ️ درباره ما", callback_data="menu_about")]
    ]

    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

# ==================== Callback Handler کامل ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data != "check_join" and not await check_subscription(update, context):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 عضویت در کانال", url="https://t.me/ParsTradeCommunity")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
        ])
        await query.edit_message_text("⛔️ از کانال خارج شده‌اید! دوباره عضو شوید:", reply_markup=keyboard)
        return

    if data == "check_join":
        if await check_subscription(update, context):
            await show_main_menu(update, context)
        else:
            await query.edit_message_text("❌ هنوز عضو نیستید!")
        return

    # تأیید رفرال
    if data.startswith("approve_ref_"):
        _, _, new_id, ref_id = data.split("_")
        new_id, ref_id = int(new_id), int(ref_id)

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT new_first_name, new_username FROM pending_referrals WHERE new_user_id=?", (new_id,))
        pending = c.fetchone()
        if pending:
            first_name, username = pending
            c.execute("""INSERT INTO confirmed_referrals 
                         (new_user_id, new_first_name, new_username, referrer_id, confirm_date)
                         VALUES (?, ?, ?, ?, ?)""",
                      (new_id, first_name, username, ref_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.execute("DELETE FROM pending_referrals WHERE new_user_id=?", (new_id,))
        conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (ref_id,))
        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(ref_id, f"🎉 یکی از رفرال‌های شما تأیید شد!\nکاربر: {first_name} (@{username or 'ندارد'})")
            await context.bot.send_message(new_id, "✅ رفرال شما تأیید شد و حالا دسترسی کامل دارید!")
        except: pass

        await query.edit_message_text(query.message.text + "\n\n✅ **تأیید شد**", parse_mode=ParseMode.MARKDOWN)
        return

    # رد رفرال
    if data.startswith("reject_ref_"):
        _, _, new_id, _ = data.split("_")
        new_id = int(new_id)

        conn = get_db()
        conn.execute("DELETE FROM pending_referrals WHERE new_user_id=?", (new_id,))
        conn.commit()
        conn.close()

        try:
            await context.bot.send_message(new_id, "❌ رفرال شما رد شد.")
        except: pass

        await query.edit_message_text(query.message.text + "\n\n❌ **رد شد**", parse_mode=ParseMode.MARKDOWN)
        return

    # بازگشت به منوی اصلی
    if data == "back_to_start":
        await show_main_menu(update, context)
        return

    if data == "main_menu":
        await show_main_menu(update, context)

    elif data == "menu_prof":
        conn = get_db()
        res = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (user_id,)).fetchone()
        count = res[0] if res else 0

        c = conn.cursor()
        c.execute("""SELECT new_first_name, new_username, confirm_date 
                     FROM confirmed_referrals 
                     WHERE referrer_id = ? 
                     ORDER BY confirm_date DESC""", (user_id,))
        confirmed_list = c.fetchall()
        conn.close()

        link = f"https://t.me/{context.bot.username}?start={user_id}"

        text = f"👤 **پروفایل شما**\n\n"
        text += f"🆔 آیدی: `{user_id}`\n"
        text += f"👥 تعداد رفرال تأیید شده: **{count}**\n\n"
        text += f"🔗 لینک دعوت شما:\n`{link}`\n\n"

        if confirmed_list:
            text += "**لیست رفرال‌های تأیید شده شما:**\n"
            for i, (fname, uname, cdate) in enumerate(confirmed_list, 1):
                text += f"{i}. {fname} (@{uname or 'ندارد'}) - تأیید: {cdate}\n"
        else:
            text += "هنوز رفرالی تأیید نشده است."

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data == "menu_live":
        conn = get_db()
        active = conn.execute("SELECT title, link FROM lives WHERE is_active=1").fetchone()
        archives = conn.execute("SELECT id, title, date_recorded FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()

        msg = "🔴 **لایو ترید**\n\n"
        kb = []
        if active:
            msg += f"🔥 لایو زنده: {active[0]}\n"
            kb.append([InlineKeyboardButton("ورود به لایو", url=active[1])])
        else:
            msg += "لایو زنده‌ای در حال برگزاری نیست.\n"

        msg += "\n📂 **آرشیو لایوهای گذشته:**\n"
        for a in archives:
            kb.append([InlineKeyboardButton(f"🎥 {a[1]} ({a[2]})", callback_data=f"live_{a[0]}")])

        kb.append([InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")])

        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("live_"):
        lid = int(data.split("_")[1])
        conn = get_db()
        live = conn.execute("SELECT file_id, title, date_recorded FROM lives WHERE id=?", (lid,)).fetchone()
        conn.close()
        if live:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]
            ])
            await query.message.reply_video(live[0], caption=f"🎥 **{live[1]}**\n📅 {live[2]}\n@ParsTradeCommunity", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data == "menu_edu":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        kb = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row) == 3:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")])
        await query.message.edit_text("🎓 آموزش VIP\nروز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("day_"):
        day = int(data.split("_")[1])
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.close()
        kb = []
        for p in parts:
            status = "✅" if refs >= p[2] else f"🔒 ({p[2]})"
            cb = f"course_{p[0]}" if refs >= p[2] else f"need_{p[2]}"
            kb.append([InlineKeyboardButton(f"قسمت {p[1]} {status}", callback_data=cb)])
        kb.append([InlineKeyboardButton("🔙 بازگشت به آموزش‌ها", callback_data="menu_edu")])
        kb.append([InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")])
        await query.message.edit_text(f"📚 محتوای روز {day}\nتعداد رفرال شما: {refs}", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("need_"):
        req = data.split("_")[1]
        await query.answer(f"برای مشاهده نیاز به {req} رفرال تأیید شده دارید.", show_alert=True)

    elif data.startswith("course_"):
        cid = int(data.split("_")[1])
        conn = get_db()
        course = conn.execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (cid,)).fetchone()
        conn.close()
        if course:
            typ, fid, cap = course
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]
            ])
            if typ == "text":
                await query.message.reply_text(cap, reply_markup=keyboard)
            elif typ == "video":
                await query.message.reply_video(fid, caption=cap, reply_markup=keyboard)
            elif typ == "photo":
                await query.message.reply_photo(fid, caption=cap, reply_markup=keyboard)
            elif typ == "document":
                await query.message.reply_document(fid, caption=cap, reply_markup=keyboard)

    elif data == "menu_about":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_start")]
        ])
        await query.message.edit_text(get_text("about"), reply_markup=keyboard)

# ==================== پنل ادمین ====================
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔒 رمز عبور ادمین:")
    return ADMIN_AUTH

async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_PASSWORD:
        await admin_menu_show(update, context)
        return ADMIN_MENU
    await update.message.reply_text("❌ رمز اشتباه")
    return ConversationHandler.END

async def admin_menu_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        ["➕ افزودن آموزش", "🔴 مدیریت لایو"],
        ["👥 مدیریت کاربر/رفرال", "📝 ویرایش متون"],
        ["📢 پیام همگانی", "❌ خروج"]
    ]
    await update.message.reply_text("🔐 پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "❌ خروج":
        await update.message.reply_text("خروج.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    elif txt == "➕ افزودن آموزش":
        await update.message.reply_text("شماره روز:")
        return ADD_COURSE_DAY
    elif txt == "🔴 مدیریت لایو":
        kb = [["آپلود آرشیو لایو", "تنظیم لینک لایو زنده"], ["حذف لایو زنده", "بازگشت"]]
        await update.message.reply_text("مدیریت لایو:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MANAGE_LIVE_MENU
    elif txt == "📝 ویرایش متون":
        kb = [["welcome", "about"], ["بازگشت"]]
        await update.message.reply_text("کدام متن؟", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return EDIT_TEXT_SELECT
    elif txt == "👥 مدیریت کاربر/رفرال":
        await update.message.reply_text("آیدی عددی کاربر:")
        return MANAGE_USER_INPUT
    elif txt == "📢 پیام همگانی":
        await update.message.reply_text("پیام را بفرستید:")
        return BROADCAST_MESSAGE

async def add_course_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_day"] = update.message.text
    await update.message.reply_text("شماره قسمت:")
    return ADD_COURSE_PART

async def add_course_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_part"] = update.message.text
    await update.message.reply_text("تعداد رفرال لازم:")
    return ADD_COURSE_REFS

async def add_course_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["c_req"] = update.message.text
    await update.message.reply_text("محتوا را بفرستید:")
    return ADD_COURSE_CONTENT

async def add_course_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ctype = "text"
    fid = None
    cap = update.message.caption or update.message.text or ""
    if update.message.video: ctype, fid = "video", update.message.video.file_id
    elif update.message.photo: ctype, fid = "photo", update.message.photo[-1].file_id
    elif update.message.document: ctype, fid = "document", update.message.document.file_id
    conn = get_db()
    conn.execute("INSERT INTO courses (day, part, req_refs, content_type, file_id, caption) VALUES (?, ?, ?, ?, ?, ?)",
                 (context.user_data["c_day"], context.user_data["c_part"], context.user_data["c_req"], ctype, fid, cap))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ اضافه شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def manage_live_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "تنظیم لینک لایو زنده":
        await update.message.reply_text("عنوان\nلینک")
        return SET_LIVE_LINK
    elif txt == "آپلود آرشیو لایو":
        await update.message.reply_text("ویدیو با کپشن (عنوان):")
        return UPLOAD_LIVE_FILE
    elif txt == "حذف لایو زنده":
        conn = get_db()
        conn.execute("UPDATE lives SET is_active = 0")
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ حذف شد.")
        await admin_menu_show(update, context)
        return ADMIN_MENU
    elif txt == "بازگشت":
        await admin_menu_show(update, context)
        return ADMIN_MENU

async def set_live_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.strip().split("\n", 1)
    if len(lines) < 2:
        await update.message.reply_text("فرمت اشتباه: عنوان در خط اول، لینک در خط دوم.")
        return SET_LIVE_LINK
    title, link = lines[0].strip(), lines[1].strip()
    conn = get_db()
    conn.execute("UPDATE lives SET is_active = 0")
    conn.execute("INSERT INTO lives (title, link, is_active) VALUES (?, ?, 1)", (title, link))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ تنظیم شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def upload_live_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("ویدیو بفرستید!")
        return UPLOAD_LIVE_FILE
    fid = update.message.video.file_id
    title = update.message.caption or "لایو"
    date = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("INSERT INTO lives (title, file_id, date_recorded, is_active) VALUES (?, ?, ?, 0)", (title, fid, date))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ اضافه شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def manage_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid_text = update.message.text.strip()
    if not uid_text.isdigit():
        await update.message.reply_text("عدد وارد کنید.")
        return MANAGE_USER_INPUT
    uid = int(uid_text)
    context.user_data["target_uid"] = uid
    conn = get_db()
    user = conn.execute("SELECT username, referrals_confirmed FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not user:
        await update.message.reply_text("کاربر یافت نشد.")
        await admin_menu_show(update, context)
        return ADMIN_MENU
    kb = [["➕ افزایش رفرال", "➖ کاهش رفرال"], ["بازگشت"]]
    await update.message.reply_text(f"@{user[0] or 'ندارد'}\nرفرال: {user[1]}", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MANAGE_USER_ACTION

async def manage_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target = context.user_data["target_uid"]
    conn = get_db()
    if action == "➕ افزایش رفرال":
        conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (target,))
        msg = "+1 رفرال"
    elif action == "➖ کاهش رفرال":
        conn.execute("UPDATE users SET referrals_confirmed = MAX(0, referrals_confirmed - 1) WHERE user_id=?", (target,))
        msg = "-1 رفرال"
    else:
        await admin_menu_show(update, context)
        return ADMIN_MENU
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ {msg}")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def edit_text_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text
    if key == "بازگشت":
        await admin_menu_show(update, context)
        return ADMIN_MENU
    context.user_data["edit_key"] = key
    curr = get_text(key)
    await update.message.reply_text(f"متن فعلی:\n{curr}\n\nجدید:")
    return EDIT_TEXT_INPUT

async def edit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    key = context.user_data["edit_key"]
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO dynamic_texts (key, content) VALUES (?, ?)", (key, new_text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ بروز شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await update.message.reply_text(f"ارسال به {len(users)} نفر...")
    sent = 0
    for u in users:
        try:
            await update.message.copy(u[0])
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text(f"تمام شد. ({sent} نفر)")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# ==================== Main ====================
def main():
    init_db()
    keep_alive()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))

    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth)],
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handler)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_course_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_course_part)],
            ADD_COURSE_REFS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_course_refs)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL & ~filters.COMMAND, add_course_content)],
            MANAGE_LIVE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_live_menu)],
            SET_LIVE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_live_link)],
            UPLOAD_LIVE_FILE: [MessageHandler(filters.VIDEO, upload_live_file)],
            MANAGE_USER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_input)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_action)],
            EDIT_TEXT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_select)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text_input)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_msg)],
        },
        fallbacks=[],
    )
    application.add_handler(conv)

    print("🤖 بات پارس ترید با موفقیت اجرا شد!")
    application.run_polling()

if __name__ == "__main__":
    main()
