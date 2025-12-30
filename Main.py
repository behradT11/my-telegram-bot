import logging
import sqlite3
import asyncio
import threading
import time
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

# --- تنظیمات ---
TOKEN = "8582244459:AAHJuWSrJVO0NQS6vAukbY1IV5WT5uIPUlE"
ADMIN_PASSWORD = "123456" # رمز ادمین
CHANNEL_ID = "@ParsTradeCommunity" # آیدی کانال با @
GROUP_ID = "@ParsTradeGP" # آیدی گروه با @

# --- Flask Server برای جلوگیری از خاموشی در Render ---
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

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- وضعیت‌های Conversation ---
(
    ADMIN_AUTH, ADMIN_MENU, 
    ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
    MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
    EDIT_TEXT_SELECT, EDIT_TEXT_INPUT,
    MANAGE_USER_INPUT, MANAGE_USER_ACTION, MANAGE_USER_REASON,
    BROADCAST_MESSAGE
) = range(15)

# --- دیتابیس ---
def init_db():
    conn = sqlite3.connect("parstrade_v2.db")
    c = conn.cursor()
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_confirmed INTEGER DEFAULT 0,
                 join_date TEXT
                 )''')
    # جدول متون قابل ویرایش
    c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (
                 key TEXT PRIMARY KEY,
                 content TEXT
                 )''')
    # جدول دوره‌ها (با تعداد رفرال مخصوص هر دوره)
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER,
                 part INTEGER,
                 req_refs INTEGER,
                 content_type TEXT,
                 file_id TEXT,
                 caption TEXT
                 )''')
    # جدول لایو ترید
    c.execute('''CREATE TABLE IF NOT EXISTS lives (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT,
                 link TEXT,
                 file_id TEXT,
                 date_recorded TEXT,
                 is_active INTEGER DEFAULT 0
                 )''')
    
    # متون پیش‌فرض
    defaults = {
        "welcome": "درود به کامیونیتی پارس ترید خوش آمدید. 🌹",
        "rules": "قوانین استفاده از بات...",
        "about": "درباره پارس ترید..."
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade_v2.db")

# --- توابع کمکی ---
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی عضویت کاربر در کانال و گروه"""
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED]:
            return False
        # اگر نیاز به چک کردن گروه هم هست خطوط زیر را فعال کنید
        # group_member = await context.bot.get_chat_member(GROUP_ID, user_id)
        # if group_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
        #     return False
        return True
    except Exception as e:
        logger.error(f"Error checking sub: {e}")
        return True # در صورت خطا فرض بر عضویت میگیریم که بات گیر نکند (یا میتوانید False کنید)

async def delete_msg(context, chat_id, message_id):
    """حذف پیام برای تمیز کردن چت"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

def get_text(key):
    conn = get_db()
    res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone()
    conn.close()
    return res[0] if res else ""

# --- هندلرهای کاربر ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    conn = get_db()
    
    # ثبت کاربر
    exists = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not exists:
        referrer = int(args[0]) if (args and args[0].isdigit() and int(args[0]) != user.id) else None
        conn.execute("INSERT INTO users (user_id, username, referrer_id, join_date) VALUES (?, ?, ?, ?)",
                     (user.id, user.username, referrer, datetime.now().strftime("%Y-%m-%d")))
        
        # اگر معرف داشت، به صورت معلق اضافه می‌شود (ادمین می‌تواند مدیریت کند، اما اینجا فعلا اتوماتیک اضافه می‌کنیم)
        if referrer:
            conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (referrer,))
            try:
                await context.bot.send_message(referrer, f"🎉 کاربر {user.first_name} با لینک شما وارد شد.")
            except:
                pass
        conn.commit()
    conn.close()

    if not await check_subscription(update, context):
        keyboard = [
            [InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("عضویت در گروه", url=f"https://t.me/{GROUP_ID[1:]}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="main_menu")]
        ]
        await update.message.reply_text("⛔️ برای استفاده از ربات باید ابتدا عضو کانال و گروه ما شوید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = get_text("welcome")
    keyboard = [
        [InlineKeyboardButton("🎓 آموزش (VIP)", callback_data="menu_edu"), InlineKeyboardButton("🔴 لایو ترید", callback_data="menu_live")],
        [InlineKeyboardButton("🏆 تورنمنت", callback_data="menu_tour"), InlineKeyboardButton("👤 پروفایل", callback_data="menu_prof")],
        [InlineKeyboardButton("🌐 سایت", url="https://pars-trade.com"), InlineKeyboardButton("اینستاگرام", url="https://instagram.com/parstradecommunity")],
        [InlineKeyboardButton("ℹ️ درباره ما", callback_data="menu_about")]
    ]
    
    if update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    if not await check_subscription(update, context) and data != "main_menu":
        await query.answer("لطفا ابتدا عضو کانال شوید!", show_alert=True)
        return

    if data == "main_menu":
        await show_main_menu(update, context)
    
    elif data == "menu_prof":
        conn = get_db()
        info = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (user_id,)).fetchone()
        count = info[0] if info else 0
        conn.close()
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={user_id}"
        await query.message.edit_text(
            f"👤 **پروفایل کاربری**\n\n🆔 آیدی: `{user_id}`\n👥 تعداد دعوت‌های تایید شده: **{count}**\n\n🔗 لینک دعوت شما:\n`{link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 خانه", callback_data="main_menu")]]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_live":
        conn = get_db()
        # لایو فعال
        active = conn.execute("SELECT link, title FROM lives WHERE is_active=1").fetchone()
        archives = conn.execute("SELECT id, title, date_recorded FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        
        msg = "🔴 **بخش لایو ترید**\n\n"
        keyboard = []
        
        if active:
            msg += f"🔥 **لایو در حال برگزاری:**\n{active[1]}\n"
            keyboard.append([InlineKeyboardButton("ورود به لایو", url=active[0])])
        else:
            msg += "در حال حاضر لایوی برگزار نمی‌شود.\n"
            
        msg += "\n📂 **آرشیو لایوهای گذشته:**"
        for arc in archives:
            keyboard.append([InlineKeyboardButton(f"🎥 {arc[1]} ({arc[2]})", callback_data=f"get_live_{arc[0]}")])
            
        keyboard.append([InlineKeyboardButton("🔙 خانه", callback_data="main_menu")])
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("get_live_"):
        lid = data.split("_")[2]
        conn = get_db()
        live = conn.execute("SELECT file_id, title, date_recorded FROM lives WHERE id=?", (lid,)).fetchone()
        conn.close()
        if live:
            caption = f"🎥 **{live[1]}**\n📅 تاریخ: {live[2]}\n\n🆔 @ParsTradeCommunity"
            try:
                await query.message.reply_video(live[0], caption=caption, parse_mode=ParseMode.MARKDOWN)
            except:
                await query.answer("فایل یافت نشد.", show_alert=True)
        await query.answer()

    elif data == "menu_edu":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        keyboard = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 خانه", callback_data="main_menu")])
        await query.message.edit_text("🎓 دوره آموزشی\nروز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("day_"):
        day = data.split("_")[1]
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        conn.close()
        
        # چک کردن تعداد رفرال کاربر
        conn = get_db()
        u_refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.close()
        
        keyboard = []
        for p in parts:
            pid, pnum, req = p
            status = "✅" if u_refs >= req else f"🔒 ({req} رفرال)"
            callback = f"get_course_{pid}" if u_refs >= req else f"alert_req_{req}"
            keyboard.append([InlineKeyboardButton(f"قسمت {pnum} {status}", callback_data=callback)])
            
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_edu")])
        await query.message.edit_text(f"📚 محتوای روز {day}\nتعداد رفرال شما: {u_refs}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("alert_req_"):
        req = data.split("_")[2]
        await query.answer(f"برای مشاهده این قسمت نیاز به {req} رفرال دارید.", show_alert=True)

    elif data.startswith("get_course_"):
        cid = data.split("_")[2]
        conn = get_db()
        course = conn.execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (cid,)).fetchone()
        conn.close()
        
        if course:
            ctype, fid, cap = course
            # ارسال فایل
            if ctype == 'text': await query.message.reply_text(cap)
            elif ctype == 'video': await query.message.reply_video(fid, caption=cap)
            elif ctype == 'photo': await query.message.reply_photo(fid, caption=cap)
            elif ctype == 'document': await query.message.reply_document(fid, caption=cap)
        await query.answer()
        
    elif data == "menu_about":
        txt = get_text("about")
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 خانه", callback_data="main_menu")]]))

# --- پنل ادمین ---

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔒 رمز عبور:")
    return ADMIN_AUTH

async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_PASSWORD:
        await admin_menu_show(update, context)
        return ADMIN_MENU
    else:
        await update.message.reply_text("❌ اشتباه است.")
        return ConversationHandler.END

async def admin_menu_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        ["➕ افزودن آموزش", "🔴 مدیریت لایو"],
        ["👥 مدیریت کاربر/رفرال", "📝 ویرایش متون"],
        ["📢 پیام همگانی", "❌ خروج"]
    ]
    await update.message.reply_text("پنل مدیریت:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "❌ خروج":
        await update.message.reply_text("خروج.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    elif txt == "➕ افزودن آموزش":
        await update.message.reply_text("شماره روز (عدد):")
        return ADD_COURSE_DAY
    
    elif txt == "🔴 مدیریت لایو":
        kb = [["آپلود آرشیو لایو", "تنظیم لینک لایو زنده"], ["حذف لایو زنده", "بازگشت"]]
        await update.message.reply_text("بخش لایو:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MANAGE_LIVE_MENU
    
    elif txt == "📝 ویرایش متون":
        kb = [["welcome", "rules", "about"], ["بازگشت"]]
        await update.message.reply_text("کدام متن ویرایش شود؟\n(welcome: خوش آمد, about: درباره ما)", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return EDIT_TEXT_SELECT

    elif txt == "👥 مدیریت کاربر/رفرال":
        await update.message.reply_text("🆔 آیدی عددی کاربر را وارد کنید (یا فوروارد کنید):")
        return MANAGE_USER_INPUT

    elif txt == "📢 پیام همگانی":
        await update.message.reply_text("پیام خود را بفرستید:")
        return BROADCAST_MESSAGE
    
    else:
        await admin_menu_show(update, context)
        return ADMIN_MENU

# --- افزودن آموزش ---
async def add_course_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['c_day'] = update.message.text
    await update.message.reply_text("شماره قسمت (عدد):")
    return ADD_COURSE_PART

async def add_course_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['c_part'] = update.message.text
    await update.message.reply_text("🔢 تعداد رفرال مورد نیاز برای این قسمت:")
    return ADD_COURSE_REFS

async def add_course_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['c_req'] = update.message.text
    await update.message.reply_text("📥 فایل آموزش یا متن را ارسال کنید:")
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
                 (context.user_data['c_day'], context.user_data['c_part'], context.user_data['c_req'], ctype, fid, cap))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ ذخیره شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# --- مدیریت لایو ---
async def manage_live_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "تنظیم لینک لایو زنده":
        await update.message.reply_text("لینک و عنوان را به این صورت بفرستید:\nعنوان لایو\nلینک")
        return SET_LIVE_LINK
    elif txt == "آپلود آرشیو لایو":
        await update.message.reply_text("فیلم لایو ضبط شده را بفرستید (در کپشن عنوان را بنویسید):")
        return UPLOAD_LIVE_FILE
    elif txt == "حذف لایو زنده":
        conn = get_db()
        conn.execute("UPDATE lives SET is_active=0")
        conn.commit()
        conn.close()
        await update.message.reply_text("لایو غیرفعال شد.")
        await admin_menu_show(update, context)
        return ADMIN_MENU
    else:
        await admin_menu_show(update, context)
        return ADMIN_MENU

async def set_live_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.split('\n')
    if len(lines) < 2:
        await update.message.reply_text("فرمت اشتباه. خط اول عنوان، خط دوم لینک.")
        return SET_LIVE_LINK
    
    conn = get_db()
    conn.execute("UPDATE lives SET is_active=0") # غیرفعال کردن قبلی‌ها
    conn.execute("INSERT INTO lives (title, link, is_active) VALUES (?, ?, 1)", (lines[0], lines[1]))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ لایو زنده تنظیم شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

async def upload_live_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("لطفا ویدیو ارسال کنید.")
        return UPLOAD_LIVE_FILE
    
    fid = update.message.video.file_id
    title = update.message.caption or "لایو ضبط شده"
    date = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db()
    conn.execute("INSERT INTO lives (title, file_id, date_recorded, is_active) VALUES (?, ?, ?, 0)", (title, fid, date))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ به آرشیو اضافه شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# --- مدیریت کاربر ---
async def manage_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text
    if not uid.isdigit():
        await update.message.reply_text("عدد وارد کنید.")
        return MANAGE_USER_INPUT
    
    context.user_data['target_uid'] = uid
    conn = get_db()
    user = conn.execute("SELECT username, referrals_confirmed FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text("کاربر یافت نشد.")
        return ADMIN_MENU
    
    kb = [["➕ افزایش رفرال", "➖ کاهش رفرال"], ["بازگشت"]]
    await update.message.reply_text(f"👤 کاربر: {user[0]}\n📊 رفرال تایید شده: {user[1]}\n\nچه کاری انجام شود؟", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return MANAGE_USER_ACTION

async def manage_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target = context.user_data['target_uid']
    conn = get_db()
    
    if action == "➕ افزایش رفرال":
        conn.execute("UPDATE users SET referrals_confirmed = referrals_confirmed + 1 WHERE user_id=?", (target,))
        msg = "یک رفرال اضافه شد."
    elif action == "➖ کاهش رفرال":
        conn.execute("UPDATE users SET referrals_confirmed = max(0, referrals_confirmed - 1) WHERE user_id=?", (target,))
        msg = "یک رفرال کم شد (رد شد)."
    else:
        await admin_menu_show(update, context)
        return ADMIN_MENU
        
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ انجام شد: {msg}")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# --- ویرایش متن ---
async def edit_text_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text
    if key == "بازگشت": return await admin_menu_show(update, context)
    context.user_data['edit_key'] = key
    curr = get_text(key)
    await update.message.reply_text(f"متن فعلی:\n{curr}\n\nمتن جدید را بفرستید:")
    return EDIT_TEXT_INPUT

async def edit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    key = context.user_data['edit_key']
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO dynamic_texts (key, content) VALUES (?, ?)", (key, new_text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ متن آپدیت شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# --- برودکست ---
async def broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await update.message.reply_text(f"ارسال به {len(users)} نفر...")
    for u in users:
        try:
            await update.message.copy(u[0])
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text("تمام شد.")
    await admin_menu_show(update, context)
    return ADMIN_MENU

# --- Main ---
def main():
    init_db()
    keep_alive() # اجرای سرور Flask
    
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT, admin_auth)],
            ADMIN_MENU: [MessageHandler(filters.TEXT, admin_handler)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT, add_course_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT, add_course_part)],
            ADD_COURSE_REFS: [MessageHandler(filters.TEXT, add_course_refs)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL, add_course_content)],
            MANAGE_LIVE_MENU: [MessageHandler(filters.TEXT, manage_live_menu)],
            SET_LIVE_LINK: [MessageHandler(filters.TEXT, set_live_link)],
            UPLOAD_LIVE_FILE: [MessageHandler(filters.VIDEO, upload_live_file)],
            MANAGE_USER_INPUT: [MessageHandler(filters.TEXT, manage_user_input)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT, manage_user_action)],
            EDIT_TEXT_SELECT: [MessageHandler(filters.TEXT, edit_text_select)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT, edit_text_input)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL, broadcast_msg)],
        },
        fallbacks=[CommandHandler("cancel", admin_menu_show)]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("Bot Started...")
    app.run_polling()

if __name__ == "__main__":
    main()

