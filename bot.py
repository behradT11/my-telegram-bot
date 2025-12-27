import logging
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# --- تنظیمات اولیه ---
# توکن بات خود را در خط زیر جایگزین کنید
TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"

# رمز عبور پیش‌فرض ادمین (قابل تغییر در کد یا دیتابیس)
ADMIN_PASSWORD_DEFAULT = "123456"

# لینک‌های شبکه‌های اجتماعی
LINKS = {
    "channel": "https://t.me/ParsTradeCommunity",
    "group": "https://t.me/ParsTradeGP",
    "instagram": "https://www.instagram.com/parstradecommunity?igsh=MTdyZXBqMGloempzMQ==",
    "site": "https://pars-trade.com"
}

# وضعیت‌های Conversation (برای ادمین)
(
    ADMIN_AUTH,
    ADMIN_MENU,
    ADD_COURSE_DAY,
    ADD_COURSE_PART,
    ADD_COURSE_CONTENT,
    SET_REFERRAL_LIMIT,
    BROADCAST_MESSAGE
) = range(7)

# تنظیمات لاگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- مدیریت دیتابیس ---
def init_db():
    """ایجاد جداول دیتابیس در صورت عدم وجود"""
    conn = sqlite3.connect("parstrade.db")
    c = conn.cursor()
    
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_count INTEGER DEFAULT 0
                 )''')
    
    # جدول تنظیمات (مثل تعداد رفرال مورد نیاز)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                 key TEXT PRIMARY KEY,
                 value TEXT
                 )''')
    
    # جدول دوره‌های آموزشی
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER,
                 part INTEGER,
                 content_type TEXT,
                 file_id TEXT,
                 caption TEXT
                 )''')
                 
    # تنظیم پیش‌فرض برای تعداد رفرال اگر وجود نداشته باشد
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_req', '0')")
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect("parstrade.db")

# --- توابع کمکی ---
async def check_referral_status(user_id):
    """بررسی می‌کند آیا کاربر تعداد رفرال کافی دارد یا خیر"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # دریافت تعداد رفرال کاربر
    c.execute("SELECT referrals_count FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    user_refs = res[0] if res else 0
    
    # دریافت حد نصاب مورد نیاز
    c.execute("SELECT value FROM settings WHERE key = 'referral_req'")
    req_refs = int(c.fetchone()[0])
    
    conn.close()
    return user_refs >= req_refs, user_refs, req_refs

# --- هندلرهای کاربر ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام خوش‌آمدگویی و هندل کردن لینک رفرال"""
    user = update.effective_user
    args = context.args
    conn = get_db_connection()
    c = conn.cursor()
    
    # بررسی وجود کاربر
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
    if not c.fetchone():
        referrer_id = None
        # اگر با لینک دعوت آمده باشد
        if args and args[0].isdigit() and int(args[0]) != user.id:
            referrer_id = int(args[0])
            # بررسی اعتبار معرف
            c.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
            if c.fetchone():
                c.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
                try:
                    await context.bot.send_message(chat_id=referrer_id, text=f"🎉 یک کاربر جدید ({user.first_name}) با لینک شما عضو شد!")
                except:
                    pass
        
        c.execute("INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", 
                  (user.id, user.username, referrer_id))
        conn.commit()
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("🎓 آموزش (VIP)", callback_data="menu_education")],
        [InlineKeyboardButton("🏆 تورنمنت‌ها", callback_data="menu_tournament")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="menu_profile")],
        [InlineKeyboardButton("📢 کانال تلگرام", url=LINKS['channel']), InlineKeyboardButton("👥 گروه پرسش و پاسخ", url=LINKS['group'])],
        [InlineKeyboardButton("📸 اینستاگرام", url=LINKS['instagram']), InlineKeyboardButton("🌐 وب‌سایت", url=LINKS['site'])],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = (
        f"درود {user.first_name} عزیز، به کامیونیتی بزرگ **پارس ترید** خوش آمدید! 🌹\n\n"
        "ما اینجا هستیم تا مسیر معامله‌گری شما را هموار کنیم.\n"
        "از دکمه‌های زیر برای دسترسی به بخش‌های مختلف استفاده کنید."
    )
    
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های منوی اصلی"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "main_menu":
        await start(update, context)
        
    elif data == "menu_profile":
        user_id = query.from_user.id
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT referrals_count FROM users WHERE user_id = ?", (user_id,))
        ref_count = c.fetchone()[0]
        conn.close()
        
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        msg = (
            f"👤 **پروفایل کاربری**\n\n"
            f"🆔 شناسه عددی: `{user_id}`\n"
            f"👥 تعداد دعوت‌های شما: {ref_count} نفر\n\n"
            f"🔗 **لینک دعوت اختصاصی شما:**\n`{ref_link}`\n\n"
            "با دعوت دوستان خود می‌توانید به بخش‌های VIP دسترسی پیدا کنید."
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "menu_tournament":
        msg = (
            "🏆 **بخش تورنمنت‌های پارس ترید**\n\n"
            "در این بخش مسابقات ترید با جوایز نفیس برگزار می‌شود.\n"
            "لیست تورنمنت‌های فعال به زودی اعلام خواهد شد.\n\n"
            "منتظر خبرهای خوب باشید! 🔥"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data == "menu_education":
        user_id = query.from_user.id
        is_allowed, user_refs, req_refs = await check_referral_status(user_id)
        
        if not is_allowed:
            msg = (
                f"⛔️ **دسترسی محدود است**\n\n"
                f"برای دسترسی به بخش آموزش رایگان اما ارزشمند ما، شما باید {req_refs} نفر را به ربات دعوت کنید.\n\n"
                f"📊 وضعیت شما: {user_refs} / {req_refs}\n\n"
                "لینک دعوت خود را از بخش 'حساب کاربری' دریافت کنید."
            )
            keyboard = [[InlineKeyboardButton("👤 دریافت لینک دعوت", callback_data="menu_profile")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]
            await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # نمایش لیست روزهای آموزشی
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT day FROM courses ORDER BY day ASC")
        days = c.fetchall()
        conn.close()
        
        keyboard = []
        row = []
        for d in days:
            day_num = d[0]
            row.append(InlineKeyboardButton(f"📅 روز {day_num}", callback_data=f"course_day_{day_num}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")])
        
        msg = "🎓 **دوره آموزشی جامع فارکس**\n\nلطفاً روز مورد نظر را انتخاب کنید:"
        if not days:
            msg += "\n\n(هنوز آموزشی بارگذاری نشده است)"
            
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("course_day_"):
        day_num = int(data.split("_")[2])
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, part, content_type FROM courses WHERE day = ? ORDER BY part ASC", (day_num,))
        parts = c.fetchall()
        conn.close()
        
        keyboard = []
        for p in parts:
            p_id, p_num, p_type = p
            icon = "🎥" if p_type in ['video', 'document'] else "📝"
            keyboard.append([InlineKeyboardButton(f"{icon} قسمت {p_num}", callback_data=f"get_course_{p_id}")])
            
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست روزها", callback_data="menu_education")])
        
        await query.message.edit_text(f"📚 **محتوای روز {day_num}**\n\nیک قسمت را انتخاب کنید:", 
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("get_course_"):
        course_id = int(data.split("_")[2])
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT content_type, file_id, caption, day, part FROM courses WHERE id = ?", (course_id,))
        course = c.fetchone()
        conn.close()
        
        if course:
            ctype, file_id, caption, day, part = course
            text_caption = f"📅 **روز {day} - قسمت {part}**\n\n{caption}\n\n🆔 @ParsTradeCommunity"
            
            try:
                if ctype == 'text':
                    await query.message.reply_text(text_caption, parse_mode="Markdown")
                elif ctype == 'video':
                    await query.message.reply_video(video=file_id, caption=text_caption, parse_mode="Markdown")
                elif ctype == 'photo':
                    await query.message.reply_photo(photo=file_id, caption=text_caption, parse_mode="Markdown")
                elif ctype == 'document':
                    await query.message.reply_document(document=file_id, caption=text_caption, parse_mode="Markdown")
            except Exception as e:
                await query.message.reply_text("❌ خطایی در ارسال فایل رخ داد. ممکن است فایل حذف شده باشد.")
                logger.error(f"Error sending file: {e}")
        
        await query.answer()

# --- هندلرهای ادمین ---

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع پروسه ادمین"""
    user_id = update.effective_user.id
    # اینجا می‌توانید چک کنید که آیا یوزر آیدی جزو ادمین‌های ثابت هست یا خیر
    # فعلاً فقط رمز می‌پرسیم
    await update.message.reply_text("🔒 لطفاً رمز عبور مدیریت را وارد کنید:")
    return ADMIN_AUTH

async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    if password == ADMIN_PASSWORD_DEFAULT:
        await show_admin_menu(update, context)
        return ADMIN_MENU
    else:
        await update.message.reply_text("❌ رمز اشتباه است. دوباره تلاش کنید یا /cancel را بزنید.")
        return ADMIN_AUTH

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ افزودن آموزش", "📢 پیام همگانی"],
        ["⚙️ تنظیم تعداد رفرال", "❌ خروج"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    msg = "🔓 **پنل مدیریت پارس ترید**\n\nلطفاً یک گزینه را انتخاب کنید:"
    if update.message:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        # برای بازگشت از مراحل دیگر
        await update.effective_user.send_message(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "➕ افزودن آموزش":
        await update.message.reply_text("📅 شماره روز آموزشی را به عدد وارد کنید (مثلا 1):")
        return ADD_COURSE_DAY
    
    elif text == "📢 پیام همگانی":
        await update.message.reply_text("📝 متن یا پیامی که می‌خواهید برای همه کاربران ارسال شود را بفرستید (متن، عکس، ویدیو):")
        return BROADCAST_MESSAGE
        
    elif text == "⚙️ تنظیم تعداد رفرال":
        conn = get_db_connection()
        curr = conn.execute("SELECT value FROM settings WHERE key='referral_req'").fetchone()[0]
        conn.close()
        await update.message.reply_text(f"🔢 تعداد رفرال فعلی: {curr}\n\nعدد جدید را وارد کنید:")
        return SET_REFERRAL_LIMIT
        
    elif text == "❌ خروج":
        await update.message.reply_text("👋 خروج از پنل مدیریت.", reply_markup=None)
        return ConversationHandler.END
        
    else:
        await show_admin_menu(update, context)
        return ADMIN_MENU

# --- افزودن دوره ---
async def add_course_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADD_COURSE_DAY
    
    context.user_data['course_day'] = int(update.message.text)
    await update.message.reply_text("🔢 شماره قسمت را وارد کنید (مثلا 2):")
    return ADD_COURSE_PART

async def add_course_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADD_COURSE_PART
        
    context.user_data['course_part'] = int(update.message.text)
    await update.message.reply_text("📥 حالا فایل آموزش (ویدیو، عکس، فایل) یا متن آموزش را ارسال کنید.\nمی‌توانید برای فایل کپشن هم بنویسید.")
    return ADD_COURSE_CONTENT

async def add_course_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = context.user_data['course_day']
    part = context.user_data['course_part']
    
    content_type = 'text'
    file_id = None
    caption = update.message.caption or update.message.text or ""
    
    if update.message.video:
        content_type = 'video'
        file_id = update.message.video.file_id
    elif update.message.photo:
        content_type = 'photo'
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        content_type = 'document'
        file_id = update.message.document.file_id
    elif update.message.text:
        content_type = 'text'
        caption = update.message.text # For text only, content is in caption field logic
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO courses (day, part, content_type, file_id, caption) VALUES (?, ?, ?, ?, ?)",
              (day, part, content_type, file_id, caption))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ آموزش روز {day} قسمت {part} با موفقیت ذخیره شد.")
    await show_admin_menu(update, context)
    return ADMIN_MENU

# --- تنظیم رفرال ---
async def set_referral_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("لطفا عدد وارد کنید.")
        return SET_REFERRAL_LIMIT
        
    new_limit = update.message.text
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'referral_req'", (new_limit,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ حد نصاب رفرال به {new_limit} نفر تغییر یافت.")
    await show_admin_menu(update, context)
    return ADMIN_MENU

# --- برودکست ---
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    await update.message.reply_text(f"⏳ در حال ارسال پیام به {len(users)} کاربر...")
    
    success_count = 0
    fail_count = 0
    
    for user_row in users:
        user_id = user_row[0]
        try:
            await update.message.copy(chat_id=user_id)
            success_count += 1
            await asyncio.sleep(0.05) # جلوگیری از اسپم لیمیت تلگرام
        except Exception:
            fail_count += 1
            
    await update.message.reply_text(f"📊 گزارش ارسال:\n✅ موفق: {success_count}\n❌ ناموفق: {fail_count}")
    await show_admin_menu(update, context)
    return ADMIN_MENU

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# --- اجرای برنامه ---
def main():
    # ساخت دیتابیس
    init_db()
    
    application = Application.builder().token(TOKEN).build()

    # هندلر ادمین
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth)],
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_course_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_course_part)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL & ~filters.COMMAND, add_course_content)],
            SET_REFERRAL_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_referral_limit)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)]
    )
    
    application.add_handler(conv_handler)
    
    # هندلرهای عمومی
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_handler))

    # شروع بات
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()



