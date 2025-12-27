import logging
import sqlite3
import asyncio
import threading
import os
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telegram.error import BadRequest, Forbidden

# --- تنظیمات اصلی ---
TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
OWNER_ID = 6735282633  # آیدی عددی خودتان
CHANNEL_ID = "@ParsTradeCommunity"
GROUP_ID = "@ParsTradeGP"

# --- سرور Flask (اصلاح شده برای Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running..."

def run_flask():
    # دریافت پورت از محیط رندر یا استفاده از 10000 به عنوان پیش‌فرض
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- مراحل Conversation ---
(
    ADMIN_PANEL,
    ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
    MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
    MANAGE_USER_INPUT, MANAGE_USER_ACTION,
    EDIT_TEXT_SELECT, EDIT_TEXT_INPUT,
    ADD_ADMIN_INPUT,
    BROADCAST_MESSAGE
) = range(14)

# --- دیتابیس ---
def init_db():
    conn = sqlite3.connect("parstrade_v4.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 full_name TEXT,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_confirmed INTEGER DEFAULT 0,
                 is_admin INTEGER DEFAULT 0,
                 join_date TEXT
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
        "welcome": "درود {name} عزیز، به کامیونیتی بزرگ پارس ترید خوش آمدید. 🌹\nاینجا مسیر حرفه‌ای شدن شماست.",
        "about": "ما در پارس ترید با هدف آموزش اصولی بازارهای مالی فعالیت می‌کنیم.",
        "support": "برای ارتباط با پشتیبانی به آیدی زیر پیام دهید:\n@Behrise",
        "rules": "قوانین استفاده از ربات:\n1. عضویت در کانال الزامی است."
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade_v4.db")

def get_text(key, **kwargs):
    conn = get_db()
    res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone()
    conn.close()
    text = res[0] if res else ""
    try:
        return text.format(**kwargs)
    except:
        return text

def is_user_admin(user_id):
    if user_id == OWNER_ID: return True
    conn = get_db()
    res = conn.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res and res[0] == 1

# --- بررسی عضویت (اصلاح شده) ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        # بررسی کانال
        cm = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if cm.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED]:
            return False
        return True
    except BadRequest as e:
        logger.error(f"Error checking channel membership: {e} - Make sure bot is ADMIN in channel!")
        # اگر بات ادمین نباشد خطا میدهد. برای اینکه بات گیر نکند موقتا True میدهیم
        # اما در لاگ هشدار دادیم.
        return True 
    except Exception as e:
        logger.error(f"General error in check_membership: {e}")
        return True

async def force_join_message(update: Update):
    kb = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")]
    ]
    kb.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
    msg = "⛔️ **دسترسی محدود است!**\n\nبرای استفاده از امکانات بات، ابتدا باید عضو کانال شوید."
    
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- منوی اصلی ---
def main_menu_keyboard(user_id):
    buttons = [
        ["🎓 آموزش (VIP)", "🔴 لایو ترید"],
        ["🏆 تورنمنت", "👤 پروفایل من"],
        ["ℹ️ درباره ما", "📞 پشتیبانی"]
    ]
    if is_user_admin(user_id):
        buttons.append(["⚙️ پنل مدیریت"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    conn = get_db()
    
    exist = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not exist:
        ref_id = int(args[0]) if (args and args[0].isdigit() and int(args[0]) != user.id) else None
        conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?, ?, ?, ?, ?)",
                     (user.id, user.full_name, user.username, ref_id, datetime.now().strftime("%Y-%m-%d")))
        if ref_id:
            # اطلاع رسانی به معرف ولی تایید نمیکنیم (ادمین باید تایید کند یا سیستم خودکار بعدا)
            try:
                await context.bot.send_message(ref_id, f"🎉 کاربر {user.full_name} با لینک شما وارد شد (در انتظار تایید).")
            except: pass
        conn.commit()
    conn.close()

    if not await check_membership(update, context):
        await force_join_message(update)
        return

    txt = get_text("welcome", name=user.first_name)
    await update.message.reply_text(txt, reply_markup=main_menu_keyboard(user.id))

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    if not await check_membership(update, context):
        await force_join_message(update)
        return

    if text == "👤 پروفایل من":
        conn = get_db()
        data = conn.execute("SELECT referrals_confirmed, join_date FROM users WHERE user_id=?", (user.id,)).fetchone()
        conn.close()
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={user.id}"
        msg = (f"👤 **پروفایل کاربری**\n\n🆔 شناسه: `{user.id}`\n👥 **دعوت‌های تایید شده:** {data[0]}\n"
               f"📅 تاریخ عضویت: {data[1]}\n\n🔗 **لینک دعوت شما:**\n`{link}`")
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "🎓 آموزش (VIP)":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        if not days:
            await update.message.reply_text("هنوز آموزشی نیست.")
            return
        kb = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"📅 روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row)==2: 
                kb.append(row) 
                row=[]
        if row: kb.append(row)
        await update.message.reply_text("🎓 دوره آموزشی:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🔴 لایو ترید":
        conn = get_db()
        active = conn.execute("SELECT title, link FROM lives WHERE is_active=1").fetchone()
        archives = conn.execute("SELECT id, title, date_recorded FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        msg = "🔴 **لایو ترید**\n\n"
        kb = []
        if active:
            msg += f"🔥 **لایو زنده:** {active[0]}\n"
            kb.append([InlineKeyboardButton("ورود به لایو", url=active[1])])
        else: msg += "لایو زنده‌ای نداریم.\n"
        
        msg += "\n📂 آرشیو:"
        for a in archives: kb.append([InlineKeyboardButton(f"🎥 {a[1]}", callback_data=f"glive_{a[0]}")])
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif text == "🏆 تورنمنت":
        await update.message.reply_text("🏆 تورنمنت‌ها به زودی...")

    elif text == "ℹ️ درباره ما":
        await update.message.reply_text(get_text("about"))
    elif text == "📞 پشتیبانی":
        await update.message.reply_text(get_text("support"))
    elif text == "⚙️ پنل مدیریت":
        if is_user_admin(user.id): await admin_panel_start(update, context)
        else: await update.message.reply_text("دسترسی ندارید.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    if d == "check_join":
        if await check_membership(update, context):
            await q.answer("✅ تایید شد!")
            await q.message.delete()
            await q.message.reply_text(get_text("welcome", name=q.from_user.first_name), reply_markup=main_menu_keyboard(q.from_user.id))
        else: await q.answer("❌ هنوز عضو نیستید.", show_alert=True)
        return

    if not await check_membership(update, context):
        await q.answer("ابتدا عضو کانال شوید.", show_alert=True)
        return

    if d.startswith("day_"):
        day = d.split("_")[1]
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
        conn.close()
        kb = []
        for p in parts:
            if refs >= p[2]: kb.append([InlineKeyboardButton(f"✅ قسمت {p[1]}", callback_data=f"gcourse_{p[0]}")])
            else: kb.append([InlineKeyboardButton(f"🔒 قسمت {p[1]} ({p[2]} رفرال)", callback_data=f"alert_{p[2]}")])
        await q.message.edit_text(f"📚 روز {day} - وضعیت شما: {refs} رفرال", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("alert_"):
        await q.answer(f"نیاز به {d.split('_')[1]} رفرال دارید.", show_alert=True)

    elif d.startswith("gcourse_"):
        cid = d.split("_")[1]
        conn = get_db()
        c = conn.execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (cid,)).fetchone()
        conn.close()
        if c:
            if c[0]=='text': await q.message.reply_text(c[2])
            elif c[0]=='video': await q.message.reply_video(c[1], caption=c[2])
            elif c[0]=='photo': await q.message.reply_photo(c[1], caption=c[2])
            elif c[0]=='document': await q.message.reply_document(c[1], caption=c[2])
        await q.answer()

    elif d.startswith("glive_"):
        lid = d.split("_")[1]
        conn = get_db()
        l = conn.execute("SELECT file_id, title FROM lives WHERE id=?", (lid,)).fetchone()
        conn.close()
        if l: await q.message.reply_video(l[0], caption=l[1])
        await q.answer()

# --- پنل مدیریت ---
async def admin_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["➕ افزودن آموزش", "🔴 مدیریت لایو"], ["👥 مدیریت کاربر", "👮‍♂️ افزودن ادمین"], ["📝 ویرایش متن", "📢 پیام همگانی"], ["❌ خروج"]]
    await update.message.reply_text("⚙️ پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADMIN_PANEL

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t=="❌ خروج":
        await update.message.reply_text("خروج.", reply_markup=main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END
    elif t=="➕ افزودن آموزش":
        await update.message.reply_text("شماره روز:")
        return ADD_COURSE_DAY
    elif t=="👥 مدیریت کاربر":
        await update.message.reply_text("آیدی عددی کاربر:")
        return MANAGE_USER_INPUT
    elif t=="🔴 مدیریت لایو":
        await update.message.reply_text("گزینه:", reply_markup=ReplyKeyboardMarkup([["تنظیم لینک", "آپلود آرشیو"], ["بازگشت"]], resize_keyboard=True))
        return MANAGE_LIVE_MENU
    elif t=="👮‍♂️ افزودن ادمین":
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("فقط مالک!")
            return ADMIN_PANEL
        await update.message.reply_text("آیدی عددی:")
        return ADD_ADMIN_INPUT
    elif t=="📝 ویرایش متن":
        await update.message.reply_text("کدام متن (welcome, about, support, rules):")
        return EDIT_TEXT_SELECT
    elif t=="📢 پیام همگانی":
        await update.message.reply_text("پیام را بفرستید:")
        return BROADCAST_MESSAGE
    return ADMIN_PANEL

# --- افزودن آموزش ---
async def add_course_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['day'] = update.message.text
    await update.message.reply_text("شماره قسمت:")
    return ADD_COURSE_PART
async def add_course_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['part'] = update.message.text
    await update.message.reply_text("تعداد رفرال:")
    return ADD_COURSE_REFS
async def add_course_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['refs'] = update.message.text
    await update.message.reply_text("فایل/متن:")
    return ADD_COURSE_CONTENT
async def add_course_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    type, fid = 'text', None
    cap = update.message.caption or update.message.text or ""
    if update.message.video: type, fid = 'video', update.message.video.file_id
    elif update.message.photo: type, fid = 'photo', update.message.photo[-1].file_id
    elif update.message.document: type, fid = 'document', update.message.document.file_id
    
    conn = get_db()
    conn.execute("INSERT INTO courses (day, part, req_refs, content_type, file_id, caption) VALUES (?,?,?,?,?,?)",
                 (context.user_data['day'], context.user_data['part'], context.user_data['refs'], type, fid, cap))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- مدیریت کاربر ---
async def manage_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_panel_start(update, context)
    context.user_data['uid'] = update.message.text
    conn = get_db()
    u = conn.execute("SELECT full_name, referrals_confirmed FROM users WHERE user_id=?", (update.message.text,)).fetchone()
    conn.close()
    if not u:
        await update.message.reply_text("یافت نشد.")
        return ADMIN_PANEL
    await update.message.reply_text(f"👤 {u[0]} - رفرال: {u[1]}", reply_markup=ReplyKeyboardMarkup([["➕ تایید (افزایش)", "➖ رد (کاهش)"], ["بازگشت"]], resize_keyboard=True))
    return MANAGE_USER_ACTION
async def manage_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_panel_start(update, context)
    conn = get_db()
    if "افزایش" in update.message.text:
        conn.execute("UPDATE users SET referrals_confirmed=referrals_confirmed+1 WHERE user_id=?", (context.user_data['uid'],))
    elif "کاهش" in update.message.text:
        conn.execute("UPDATE users SET referrals_confirmed=max(0, referrals_confirmed-1) WHERE user_id=?", (context.user_data['uid'],))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ انجام شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- سایر بخش‌های مدیریت ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("UPDATE users SET is_admin=1 WHERE user_id=?", (update.message.text,))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ ادمین شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

async def edit_text_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['key'] = update.message.text
    await update.message.reply_text("متن جدید:")
    return EDIT_TEXT_INPUT
async def edit_text_inp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO dynamic_texts (key, content) VALUES (?, ?)", (context.user_data['key'], update.message.text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

async def manage_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_panel_start(update, context)
    if update.message.text=="تنظیم لینک":
        await update.message.reply_text("خط1: عنوان\nخط2: لینک")
        return SET_LIVE_LINK
    if update.message.text=="آپلود آرشیو":
        await update.message.reply_text("ویدیو:")
        return UPLOAD_LIVE_FILE
    return MANAGE_LIVE_MENU

async def set_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    l = update.message.text.split('\n')
    conn = get_db()
    conn.execute("UPDATE lives SET is_active=0")
    conn.execute("INSERT INTO lives (title, link, is_active) VALUES (?,?,1)", (l[0], l[1]))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

async def upload_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("INSERT INTO lives (title, file_id, date_recorded, is_active) VALUES (?,?,?,0)",
                 (update.message.caption or "Live", update.message.video.file_id, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_panel_start(update, context)
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await update.message.reply_text(f"ارسال به {len(users)} نفر...")
    for u in users:
        try: await update.message.copy(u[0])
        except: pass
    await update.message.reply_text("✅ پایان.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

def main():
    init_db()
    keep_alive()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ پنل مدیریت$"), admin_panel_start)],
        states={
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_menu)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT, add_course_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT, add_course_part)],
            ADD_COURSE_REFS: [MessageHandler(filters.TEXT, add_course_refs)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL, add_course_content)],
            MANAGE_USER_INPUT: [MessageHandler(filters.TEXT, manage_user_input)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT, manage_user_action)],
            ADD_ADMIN_INPUT: [MessageHandler(filters.TEXT, add_admin)],
            EDIT_TEXT_SELECT: [MessageHandler(filters.TEXT, edit_text_sel)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT, edit_text_inp)],
            MANAGE_LIVE_MENU: [MessageHandler(filters.TEXT, manage_live)],
            SET_LIVE_LINK: [MessageHandler(filters.TEXT, set_live)],
            UPLOAD_LIVE_FILE: [MessageHandler(filters.VIDEO, upload_live)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL, broadcast)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ خروج$"), admin_menu)]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Bot Started...")
    app.run_polling()

if __name__ == "__main__":
    main()

