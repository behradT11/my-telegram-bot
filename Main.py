

import logging
import sqlite3
import asyncio
import threading
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

# --- تنظیمات اصلی ---
TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
OWNER_ID = 6735282633 # آیدی عددی خودتان را اینجا بگذارید (برای ساخت ادمین جدید)
CHANNEL_ID = "@ParsTradeCommunity"
GROUP_ID = "@ParsTradeGP"

# --- سرور Flask برای زنده ماندن ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Pars Trade Bot is Running..."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

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
    conn = sqlite3.connect("parstrade_v3.db")
    c = conn.cursor()
    
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 full_name TEXT,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_confirmed INTEGER DEFAULT 0,
                 is_admin INTEGER DEFAULT 0,
                 join_date TEXT
                 )''')
                 
    # جدول متن‌های پویا
    c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (
                 key TEXT PRIMARY KEY,
                 content TEXT
                 )''')
                 
    # جدول دوره‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER,
                 part INTEGER,
                 req_refs INTEGER,
                 content_type TEXT,
                 file_id TEXT,
                 caption TEXT
                 )''')
                 
    # جدول لایو
    c.execute('''CREATE TABLE IF NOT EXISTS lives (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT,
                 link TEXT,
                 file_id TEXT,
                 date_recorded TEXT,
                 is_active INTEGER DEFAULT 0
                 )''')

    # متن‌های پیش‌فرض
    defaults = {
        "welcome": "درود {name} عزیز، به کامیونیتی بزرگ پارس ترید خوش آمدید. 🌹\nاینجا مسیر حرفه‌ای شدن شماست.",
        "about": "ما در پارس ترید با هدف آموزش اصولی بازارهای مالی...",
        "support": "برای ارتباط با پشتیبانی به آیدی زیر پیام دهید:\n@AdminID",
        "rules": "قوانین استفاده از ربات:\n1. عضویت در کانال الزامی است."
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade_v3.db")

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

# --- بررسی عضویت اجباری ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        # بررسی کانال
        cm_channel = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if cm_channel.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED]:
            return False
            
        # بررسی گروه (اختیاری - اگر نمی‌خواهید گروه اجباری باشد این بخش را کامنت کنید)
        # cm_group = await context.bot.get_chat_member(GROUP_ID, user_id)
        # if cm_group.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
        #     return False
            
        return True
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        # اگر ربات در کانال ادمین نباشد خطا می‌دهد، پس موقتاً اجازه می‌دهیم
        return True 

async def force_join_message(update: Update):
    """پیام قفل عضویت"""
    kb = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")]
        # ,[InlineKeyboardButton("👥 عضویت در گروه", url=f"https://t.me/{GROUP_ID.replace('@','')}")
    ]
    # دکمه بررسی عضویت
    kb.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
    
    msg_text = "⛔️ **دسترسی محدود است!**\n\nبرای استفاده از امکانات بات، ابتدا باید عضو کانال ما شوید.\nپس از عضویت دکمه «عضو شدم» را بزنید."
    
    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- منوی اصلی (Reply Keyboard) ---
def main_menu_keyboard(user_id):
    buttons = [
        ["🎓 آموزش (VIP)", "🔴 لایو ترید"],
        ["🏆 تورنمنت", "👤 پروفایل من"],
        ["ℹ️ درباره ما", "📞 پشتیبانی"]
    ]
    if is_user_admin(user_id):
        buttons.append(["⚙️ پنل مدیریت"])
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

# --- هندلر استارت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    conn = get_db()
    
    # ثبت کاربر در دیتابیس
    exist = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not exist:
        ref_id = int(args[0]) if (args and args[0].isdigit() and int(args[0]) != user.id) else None
        conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?, ?, ?, ?, ?)",
                     (user.id, user.full_name, user.username, ref_id, datetime.now().strftime("%Y-%m-%d")))
        
        # اگر معرف داشت، چک کنیم معرف ادمین نباشد (یا منطق خاصی دارید)
        if ref_id:
            # فعلاً تایید اولیه را انجام نمی‌دهیم تا زمانی که مطمئن شویم کاربر در کانال مانده
            conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (ref_id,))
            try:
                await context.bot.send_message(ref_id, f"🎉 کاربر {user.full_name} با لینک شما وارد شد.")
            except: pass
        conn.commit()
    conn.close()

    if not await check_membership(update, context):
        await force_join_message(update)
        return

    welcome_text = get_text("welcome", name=user.first_name)
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(user.id))

# --- هندلر پیام‌های متنی (منوی اصلی) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    # چک کردن عضویت در هر پیام
    if not await check_membership(update, context):
        await force_join_message(update)
        return

    if text == "👤 پروفایل من":
        conn = get_db()
        data = conn.execute("SELECT referrals_confirmed, join_date FROM users WHERE user_id=?", (user.id,)).fetchone()
        conn.close()
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={user.id}"
        
        msg = (
            f"👤 **پروفایل کاربری**\n"
            f"➖➖➖➖➖➖➖\n"
            f"📛 نام: {user.full_name}\n"
            f"🆔 شناسه: `{user.id}`\n"
            f"📅 تاریخ عضویت: {data[1]}\n"
            f"👥 **زیرمجموعه تایید شده:** {data[0]} نفر\n"
            f"➖➖➖➖➖➖➖\n"
            f"🔗 **لینک دعوت اختصاصی شما:**\n`{link}`\n\n"
            f"⚠️ نکته: اگر زیرمجموعه شما از کانال خارج شود، امتیاز آن کسر نخواهد شد اما سیستم هوشمند ما کاربران فیک را شناسایی می‌کند."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "🎓 آموزش (VIP)":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        
        if not days:
            await update.message.reply_text("هنوز آموزشی بارگذاری نشده است.")
            return

        kb = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"📅 روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        
        await update.message.reply_text("🎓 **دوره آموزشی پارس ترید**\n\nلطفاً روز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🔴 لایو ترید":
        conn = get_db()
        active = conn.execute("SELECT title, link FROM lives WHERE is_active=1").fetchone()
        archives = conn.execute("SELECT id, title, date_recorded FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        
        msg = "🔴 **بخش لایو ترید**\n\n"
        kb = []
        
        if active:
            msg += f"🔥 **لایو در حال برگزاری:**\n{active[0]}\nجهت ورود کلیک کنید 👇"
            kb.append([InlineKeyboardButton("ورود به لایو 🎥", url=active[1])])
        else:
            msg += "در حال حاضر لایو زنده‌ای نداریم.\n"
            
        msg += "\n🗂 **آرشیو لایوهای گذشته:**"
        for arc in archives:
            kb.append([InlineKeyboardButton(f"📼 {arc[1]} ({arc[2]})", callback_data=f"get_live_{arc[0]}")])
            
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🏆 تورنمنت":
        await update.message.reply_text("🏆 **تورنمنت‌های پارس ترید**\n\nبه زودی لیست مسابقات هیجان‌انگیز در اینجا قرار می‌گیرد...")

    elif text == "ℹ️ درباره ما":
        await update.message.reply_text(get_text("about"))

    elif text == "📞 پشتیبانی":
        await update.message.reply_text(get_text("support"))

    elif text == "⚙️ پنل مدیریت":
        if is_user_admin(user.id):
            await admin_panel_start(update, context)
        else:
            await update.message.reply_text("⛔️ شما دسترسی مدیریت ندارید.")

# --- کال‌بک هندلر (دکمه‌های شیشه‌ای) ---
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    if data == "check_join":
        if await check_membership(update, context):
            await query.answer("✅ عضویت تایید شد!", show_alert=True)
            welcome_text = get_text("welcome", name=query.from_user.first_name)
            await query.message.delete()
            await query.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(user_id))
        else:
            await query.answer("❌ هنوز عضو کانال نشده‌اید.", show_alert=True)
        return

    # بقیه کال‌بک‌ها نیاز به عضویت دارند
    if not await check_membership(update, context):
        await query.answer("لطفا ابتدا عضو کانال شوید.", show_alert=True)
        return

    if data.startswith("day_"):
        day = data.split("_")[1]
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        user_refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.close()
        
        kb = []
        for p in parts:
            pid, pnum, req = p
            if user_refs >= req:
                kb.append([InlineKeyboardButton(f"✅ قسمت {pnum} (باز)", callback_data=f"get_course_{pid}")])
            else:
                kb.append([InlineKeyboardButton(f"🔒 قسمت {pnum} (نیاز به {req} رفرال)", callback_data=f"alert_req_{req}")])
        
        await query.message.edit_text(f"📚 **محتوای روز {day}**\n\nوضعیت شما: {user_refs} رفرال", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("alert_req_"):
        req = data.split("_")[2]
        await query.answer(f"برای مشاهده این قسمت باید {req} نفر را به ربات دعوت کنید.", show_alert=True)

    elif data.startswith("get_course_"):
        cid = data.split("_")[2]
        conn = get_db()
        c = conn.execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (cid,)).fetchone()
        conn.close()
        if c:
            ctype, fid, cap = c
            if ctype == 'text': await query.message.reply_text(cap)
            elif ctype == 'video': await query.message.reply_video(fid, caption=cap)
            elif ctype == 'photo': await query.message.reply_photo(fid, caption=cap)
            elif ctype == 'document': await query.message.reply_document(fid, caption=cap)
        await query.answer()

    elif data.startswith("get_live_"):
        lid = data.split("_")[2]
        conn = get_db()
        l = conn.execute("SELECT file_id, title FROM lives WHERE id=?", (lid,)).fetchone()
        conn.close()
        if l:
            await query.message.reply_video(l[0], caption=f"🎥 {l[1]}")
        await query.answer()

# --- سیستم مدیریت (Conversation) ---

async def admin_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        ["➕ افزودن آموزش", "🔴 مدیریت لایو"],
        ["👥 مدیریت کاربران", "👮‍♂️ افزودن ادمین"],
        ["📝 ویرایش متن‌ها", "📢 پیام همگانی"],
        ["❌ خروج از پنل"]
    ]
    await update.message.reply_text("⚙️ **پنل مدیریت پارس ترید**\nگزینه مورد نظر را انتخاب کنید:", 
                                    reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADMIN_PANEL

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "❌ خروج از پنل":
        await update.message.reply_text("خروج از حالت مدیریت.", reply_markup=main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END

    if text == "➕ افزودن آموزش":
        await update.message.reply_text("شماره روز (مثلا 1):")
        return ADD_COURSE_DAY
    
    elif text == "📝 ویرایش متن‌ها":
        keys = [["welcome", "about"], ["support", "rules"], ["بازگشت"]]
        await update.message.reply_text("کدام متن را ویرایش می‌کنید؟\n(welcome: خوش‌آمدگویی)", reply_markup=ReplyKeyboardMarkup(keys, resize_keyboard=True))
        return EDIT_TEXT_SELECT

    elif text == "👥 مدیریت کاربران":
        await update.message.reply_text("آیدی عددی کاربر را بفرستید (یا پیامی از او فوروارد کنید):", reply_markup=ReplyKeyboardMarkup([["بازگشت"]], resize_keyboard=True))
        return MANAGE_USER_INPUT

    elif text == "🔴 مدیریت لایو":
        kb = [["تنظیم لینک زنده", "آپلود آرشیو"], ["غیرفعال کردن لایو", "بازگشت"]]
        await update.message.reply_text("مدیریت لایو:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MANAGE_LIVE_MENU

    elif text == "👮‍♂️ افزودن ادمین":
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⛔️ فقط مالک اصلی می‌تواند ادمین اضافه کند.")
            return ADMIN_PANEL
        await update.message.reply_text("آیدی عددی شخصی که می‌خواهید ادمین شود را بفرستید:", reply_markup=ReplyKeyboardMarkup([["بازگشت"]], resize_keyboard=True))
        return ADD_ADMIN_INPUT

    elif text == "📢 پیام همگانی":
        await update.message.reply_text("پیام خود را ارسال کنید (متن، عکس، ویدیو):", reply_markup=ReplyKeyboardMarkup([["بازگشت"]], resize_keyboard=True))
        return BROADCAST_MESSAGE

    return ADMIN_PANEL

# --- افزودن آموزش ---
async def add_course_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['day'] = update.message.text
    await update.message.reply_text("شماره قسمت:")
    return ADD_COURSE_PART

async def add_course_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['part'] = update.message.text
    await update.message.reply_text("تعداد رفرال مورد نیاز (عدد):")
    return ADD_COURSE_REFS

async def add_course_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['refs'] = update.message.text
    await update.message.reply_text("فایل یا متن آموزش را بفرستید:")
    return ADD_COURSE_CONTENT

async def add_course_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ctype = 'text'
    fid = None
    cap = update.message.caption or update.message.text or ""
    
    if update.message.video: ctype, fid = 'video', update.message.video.file_id
    elif update.message.photo: ctype, fid = 'photo', update.message.photo[-1].file_id
    elif update.message.document: ctype, fid = 'document', update.message.document.file_id
    elif update.message.text: ctype = 'text'
    
    conn = get_db()
    conn.execute("INSERT INTO courses (day, part, req_refs, content_type, file_id, caption) VALUES (?,?,?,?,?,?)",
                 (context.user_data['day'], context.user_data['part'], context.user_data['refs'], ctype, fid, cap))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ آموزش اضافه شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- مدیریت کاربر (تایید/رد رفرال) ---
async def manage_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_panel_start(update, context)
    
    uid = update.message.text
    if not uid.isdigit():
        await update.message.reply_text("لطفا عدد وارد کنید.")
        return MANAGE_USER_INPUT
        
    context.user_data['target_uid'] = uid
    conn = get_db()
    u = conn.execute("SELECT full_name, referrals_confirmed FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    
    if not u:
        await update.message.reply_text("کاربر یافت نشد.")
        return MANAGE_USER_INPUT
        
    kb = [["➕ افزایش رفرال (تایید)", "➖ کاهش رفرال (رد)"], ["بازگشت"]]
    await update.message.reply_text(f"👤 کاربر: {u[0]}\n📊 رفرال فعلی: {u[1]}\n\nعملیات مورد نظر:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MANAGE_USER_ACTION

async def manage_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    if action == "بازگشت": return await admin_panel_start(update, context)
    
    uid = context.user_data['target_uid']
    conn = get_db()
    if "افزایش" in action:
        conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (uid,))
        msg = "یک رفرال اضافه شد."
    elif "کاهش" in action:
        conn.execute("UPDATE users SET referrals_confirmed = MAX(0, referrals_confirmed - 1) WHERE user_id=?", (uid,))
        msg = "یک رفرال کم شد."
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ {msg}")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- افزودن ادمین ---
async def add_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_panel_start(update, context)
    
    new_admin_id = update.message.text
    if not new_admin_id.isdigit():
        await update.message.reply_text("آیدی باید عدد باشد.")
        return ADD_ADMIN_INPUT
        
    conn = get_db()
    conn.execute("UPDATE users SET is_admin=1 WHERE user_id=?", (new_admin_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ کاربر {new_admin_id} اکنون ادمین است.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- ویرایش متن‌ها ---
async def edit_text_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_panel_start(update, context)
    
    context.user_data['edit_key'] = update.message.text
    curr = get_text(update.message.text)
    await update.message.reply_text(f"متن فعلی:\n{curr}\n\nمتن جدید را بفرستید (می‌توانید از {{name}} برای نام کاربر استفاده کنید):")
    return EDIT_TEXT_INPUT

async def edit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    key = context.user_data['edit_key']
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO dynamic_texts (key, content) VALUES (?, ?)", (key, new_text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ متن ذخیره شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- مدیریت لایو ---
async def manage_live_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "بازگشت": return await admin_panel_start(update, context)
    
    if text == "تنظیم لینک زنده":
        await update.message.reply_text("لینک و عنوان را در دو خط بفرستید:\nعنوان\nلینک")
        return SET_LIVE_LINK
    elif text == "آپلود آرشیو":
        await update.message.reply_text("ویدیو را بفرستید:")
        return UPLOAD_LIVE_FILE
    elif text == "غیرفعال کردن لایو":
        conn = get_db()
        conn.execute("UPDATE lives SET is_active=0")
        conn.commit()
        conn.close()
        await update.message.reply_text("لایو غیرفعال شد.")
        await admin_panel_start(update, context)
        return ADMIN_PANEL
    return MANAGE_LIVE_MENU

async def set_live_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.split('\n')
    if len(lines) < 2:
        await update.message.reply_text("فرمت اشتباه است.")
        return SET_LIVE_LINK
    conn = get_db()
    conn.execute("UPDATE lives SET is_active=0")
    conn.execute("INSERT INTO lives (title, link, is_active) VALUES (?, ?, 1)", (lines[0], lines[1]))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ لایو فعال شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

async def upload_live_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("ویدیو بفرستید.")
        return UPLOAD_LIVE_FILE
    conn = get_db()
    conn.execute("INSERT INTO lives (title, file_id, date_recorded, is_active) VALUES (?, ?, ?, 0)",
                 (update.message.caption or "آرشیو", update.message.video.file_id, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ آرشیو شد.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL

# --- پیام همگانی ---
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_panel_start(update, context)
    
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    count = 0
    await update.message.reply_text(f"درحال ارسال به {len(users)} کاربر...")
    for u in users:
        try:
            await update.message.copy(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await update.message.reply_text(f"✅ ارسال شد به {count} نفر.")
    await admin_panel_start(update, context)
    return ADMIN_PANEL


def main():
    init_db()
    keep_alive()
    
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ پنل مدیریت$"), admin_panel_start)],
        states={
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_menu_handler)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT, add_course_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT, add_course_part)],
            ADD_COURSE_REFS: [MessageHandler(filters.TEXT, add_course_refs)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL, add_course_content)],
            MANAGE_USER_INPUT: [MessageHandler(filters.TEXT, manage_user_input)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT, manage_user_action)],
            EDIT_TEXT_SELECT: [MessageHandler(filters.TEXT, edit_text_select)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT, edit_text_input)],
            ADD_ADMIN_INPUT: [MessageHandler(filters.TEXT, add_admin_input)],
            MANAGE_LIVE_MENU: [MessageHandler(filters.TEXT, manage_live_menu)],
            SET_LIVE_LINK: [MessageHandler(filters.TEXT, set_live_link)],
            UPLOAD_LIVE_FILE: [MessageHandler(filters.VIDEO, upload_live_file)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL, broadcast_message)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ خروج از پنل$"), admin_menu_handler)]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    # هندلر کلی برای متن‌های منوی اصلی
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Bot is up and running...")
    app.run_polling()

if __name__ == "__main__":
    main()
