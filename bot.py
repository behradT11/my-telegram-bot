import logging
import sqlite3
import datetime
import pytz
import os
from threading import Thread
from flask import Flask
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    JobQueue
)
from telegram.error import BadRequest

# ---------------------------------------------------------------------------
# تنظیمات و کانفیگ
# ---------------------------------------------------------------------------
BOT_TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
ADMIN_PASSWORD = "12345@Parstradecommunity"
CHANNEL_USERNAME = "@ParsTradeCommunity"  # کانال برای عضویت اجباری

# آیدی عددی گروه ادمین (باید عدد باشد، مثلا -100123456789)
# چون شما لینک خصوصی دادید، باید آیدی عددی آن را پیدا کنید و اینجا بگذارید.
# فعلاً یک متغیر میگذارم که باید جایگزین کنید.
# برای پیدا کردن آیدی گروه، ربات @userinfobot را در گروه اد کنید.
ADMIN_GROUP_ID = -1001234567890 # <--- این را حتما با آیدی واقعی گروه عوض کنید

# وضعیت‌های مکالمه
(
    GET_NAME,
    GET_SURNAME,
    GET_AGE,
    GET_PHONE,
    GET_EMAIL,
    MAIN_MENU,
    GET_ADMIN_PASS,
    SUPPORT_Handler,
    ADMIN_BROADCAST,
    ADMIN_DELETE_USER
) = range(10)

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------------------------
# وب‌سرور برای زنده نگه داشتن ربات در Render
# ---------------------------------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "I'm alive! Pars Trade Bot is running."

def run_flask():
    # دریافت پورت از متغیرهای محیطی رندر یا پیش‌فرض 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ---------------------------------------------------------------------------
# مدیریت دیتابیس (SQLite)
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            age INTEGER,
            phone_number TEXT,
            email TEXT,
            referral_count INTEGER DEFAULT 0,
            referrer_id INTEGER,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_user_db(user_data):
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO users (user_id, first_name, last_name, age, phone_number, email, referrer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_data['id'],
            user_data['first_name'],
            user_data['last_name'],
            user_data['age'],
            user_data['phone'],
            user_data['email'],
            user_data.get('referrer_id')
        ))
        conn.commit()
    except Exception as e:
        logging.error(f"Database error: {e}")
    finally:
        conn.close()

def increment_referral(referrer_id):
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?', (referrer_id,))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def get_all_users():
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    conn.close()
    return users

def delete_user_db(user_id):
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

# ---------------------------------------------------------------------------
# توابع کمکی
# ---------------------------------------------------------------------------
async def check_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    """بررسی عضویت کاربر در کانال"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except BadRequest:
        # اگر ربات در کانال ادمین نباشد یا کانال وجود نداشته باشد
        logging.error("Bot is not admin in the channel or channel invalid.")
        return True # موقتا اجازه می‌دهد تا باگ ندهد

# ---------------------------------------------------------------------------
# هندلرهای شروع و ثبت نام
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # بررسی عضویت در کانال
    if not await check_membership(user_id, context):
        keyboard = [[InlineKeyboardButton("عضویت در کانال 📢", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")]]
        # دکمه بررسی مجدد
        keyboard.append([InlineKeyboardButton("عضو شدم ✅", callback_data="check_join")])
        await update.message.reply_text(
            f"⛔ برای استفاده از ربات پارس ترید، ابتدا باید در کانال زیر عضو شوید:\n{CHANNEL_USERNAME}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    if get_user(user_id):
        await show_main_menu(update, context)
        return MAIN_MENU

    # بررسی رفرال
    args = context.args
    referrer_id = None
    if args:
        try:
            potential_referrer = int(args[0])
            if potential_referrer != user_id:
                referrer_id = potential_referrer
        except ValueError:
            pass
    
    context.user_data['referrer_id'] = referrer_id
    
    await update.message.reply_text(
        "👋 سلام! به کامیونیتی **پارس ترید** خوش آمدید.\n\n"
        "برای استفاده از خدمات بات، لطفاً ثبت نام کنید.\n"
        "🔹 نام خود را وارد کنید:"
    )
    return GET_NAME

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if await check_membership(user_id, context):
        await query.message.delete()
        await query.message.chat.send_message("✅ عضویت تایید شد. مجدد /start را بزنید.")
    else:
        await query.message.chat.send_message("❌ هنوز عضو کانال نشده‌اید.")

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text("✅ نام خانوادگی خود را وارد کنید:")
    return GET_SURNAME

async def get_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_name'] = update.message.text
    await update.message.reply_text("🔢 سن خود را وارد کنید:")
    return GET_AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ لطفاً سن را به عدد وارد کنید.")
        return GET_AGE
    context.user_data['age'] = int(update.message.text)
    
    kb = [[KeyboardButton("📱 ارسال شماره تلفن", request_contact=True)]]
    await update.message.reply_text(
        "📞 شماره موبایل خود را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data['phone'] = update.message.contact.phone_number
    else:
        context.user_data['phone'] = update.message.text
    await update.message.reply_text("📧 ایمیل خود را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    context.user_data['id'] = update.effective_user.id
    
    # ذخیره در دیتابیس
    add_user_db(context.user_data)
    
    # بررسی و ارسال گزارش رفرال به گروه ادمین
    ref_id = context.user_data.get('referrer_id')
    user_id = context.user_data['id']
    name = f"{context.user_data['first_name']} {context.user_data['last_name']}"
    
    if ref_id:
        try:
            # دکمه‌های تایید و رد
            # فرمت دیتا: action_referrerID_newUserID
            kb = [
                [
                    InlineKeyboardButton("تایید ✅", callback_data=f"confirm_{ref_id}_{user_id}"),
                    InlineKeyboardButton("رد ❌", callback_data=f"reject_{ref_id}_{user_id}")
                ]
            ]
            
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🚨 **رفرال جدید نیاز به تایید**\n\n"
                     f"👤 کاربر جدید: {name}\n"
                     f"🆔 آیدی: {user_id}\n"
                     f"📞 شماره: {context.user_data['phone']}\n\n"
                     f"🔗 دعوت شده توسط: {ref_id}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logging.error(f"Failed to send to admin group: {e}")

    await update.message.reply_text("🎉 ثبت نام شما تکمیل شد!")
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# مدیریت تایید رفرال (Callback)
# ---------------------------------------------------------------------------
async def referral_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action = data[0]
    ref_id = int(data[1])
    new_user_id = int(data[2])
    
    if action == "confirm":
        increment_referral(ref_id)
        new_text = f"✅ رفرال تایید شد.\nامتیاز به کاربر {ref_id} اضافه گردید."
        # ارسال پیام به معرف (اختیاری)
        try:
            await context.bot.send_message(ref_id, "✅ یکی از دعوت‌های شما توسط ادمین تایید شد و امتیاز گرفتید!")
        except:
            pass
    else:
        new_text = f"❌ رفرال رد شد.\nکاربر {new_user_id} فیک یا نامعتبر تشخیص داده شد."
        
    await query.edit_message_text(text=new_text, reply_markup=None)

# ---------------------------------------------------------------------------
# منوی اصلی
# ---------------------------------------------------------------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        ["🎁 مسابقه رفرال", "👤 پروفایل من"],
        ["📞 پشتیبانی"]
    ]
    await update.message.reply_text(
        "منوی اصلی پارس ترید:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    # چک کردن مجدد عضویت
    if not await check_membership(user_id, context):
        await start(update, context)
        return ConversationHandler.END

    if text == "🎁 مسابقه رفرال":
        user = get_user(user_id)
        ref_count = user[6] if user else 0
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        await update.message.reply_text(
            f"🏆 **مسابقه رفرال پارس ترید**\n\n"
            f"تعداد دعوت‌های تایید شده: {ref_count} نفر\n\n"
            f"🔗 لینک اختصاصی شما:\n{ref_link}\n\n"
            "دوستان خود را دعوت کنید. پس از تایید ادمین، امتیاز شما ثبت می‌شود."
        )
        
    elif text == "👤 پروفایل من":
        user = get_user(user_id)
        if user:
            await update.message.reply_text(
                f"👤 **پروفایل**\n"
                f"نام: {user[1]} {user[2]}\n"
                f"سن: {user[3]}\n"
                f"شماره: {user[4]}\n"
                f"ایمیل: {user[5]}"
            )
            
    elif text == "📞 پشتیبانی":
        await update.message.reply_text("💬 پیام خود را بنویسید (لغو: /cancel):")
        return SUPPORT_Handler
            
    return MAIN_MENU

async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    # ارسال به گروه ادمین
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"📩 **پیام پشتیبانی**\nاز: {user.first_name} (ID: {user.id})\n\n{msg}"
        )
        await update.message.reply_text("✅ پیام ارسال شد.")
    except:
        await update.message.reply_text("❌ خطا در ارسال (شاید ربات در گروه ادمین نیست).")
    
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# پنل ادمین (/admin)
# ---------------------------------------------------------------------------
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 رمز عبور ادمین را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return GET_ADMIN_PASS

async def verify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_PASSWORD:
        context.user_data['is_admin'] = True
        await show_admin_panel(update, context)
        return MAIN_MENU # هندلر ادمین روی MAIN_MENU سوار است
    else:
        await update.message.reply_text("❌ رمز اشتباه است.")
        await show_main_menu(update, context)
        return MAIN_MENU

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [
        ["📊 آمار کامل کاربران", "❌ حذف کاربر"],
        ["📢 پیام همگانی", "🔙 خروج از پنل"]
    ]
    await update.message.reply_text(
        "🔧 **پنل مدیریت پارس ترید**",
        reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True)
    )

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('is_admin'):
        return await menu_handler(update, context)
        
    text = update.message.text
    
    if text == "📊 آمار کامل کاربران":
        users = get_all_users()
        if not users:
            await update.message.reply_text("لیست خالی است.")
            return MAIN_MENU
            
        report = "📋 **لیست کاربران:**\n\n"
        # فرمت: ID | Name | Phone | Age
        for u in users:
            line = f"🆔 `{u[0]}` | {u[1]} {u[2]} | 📞 {u[4]} | 🎂 {u[3]}\n"
            if len(report + line) > 4000: # جلوگیری از ارور محدودیت طول پیام
                await update.message.reply_text(report, parse_mode='Markdown')
                report = ""
            report += line
            
        if report:
            await update.message.reply_text(report, parse_mode='Markdown')
            
    elif text == "❌ حذف کاربر":
        await update.message.reply_text("🆔 آیدی عددی کاربر مورد نظر را برای حذف وارد کنید:")
        return ADMIN_DELETE_USER
        
    elif text == "📢 پیام همگانی":
        await update.message.reply_text("متن پیام را وارد کنید:")
        return ADMIN_BROADCAST
        
    elif text == "🔙 خروج از پنل":
        context.user_data['is_admin'] = False
        await show_main_menu(update, context)
        
    return MAIN_MENU

async def delete_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        if delete_user_db(target_id):
            await update.message.reply_text(f"✅ کاربر {target_id} با موفقیت حذف شد.")
        else:
            await update.message.reply_text("❌ کاربر یافت نشد.")
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط عدد وارد کنید.")
    
    await show_admin_panel(update, context)
    return MAIN_MENU

async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    users = get_all_users()
    count = 0
    await update.message.reply_text("⏳ در حال ارسال...")
    for u in users:
        try:
            await context.bot.send_message(u[0], msg)
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ ارسال شد به {count} نفر.")
    await show_admin_panel(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# گزارش شبانه (JobQueue)
# ---------------------------------------------------------------------------
async def nightly_report(context: ContextTypes.DEFAULT_TYPE):
    """ارسال آمار کلی به گروه ادمین هر شب"""
    users = get_all_users()
    total_users = len(users)
    # محاسبه کل رفرال‌ها
    total_refs = sum([u[6] for u in users])
    
    msg = (
        "🌙 **گزارش شبانه پارس ترید**\n\n"
        f"👥 کل کاربران: {total_users}\n"
        f"🤝 کل دعوت‌های موفق: {total_refs}\n"
        f"📅 تاریخ: {datetime.datetime.now().strftime('%Y-%m-%d')}"
    )
    
    try:
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=msg)
    except Exception as e:
        logging.error(f"Nightly report failed: {e}")

# ---------------------------------------------------------------------------
# اجرا
# ---------------------------------------------------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)
    return MAIN_MENU

if __name__ == '__main__':
    # روشن کردن سرور وب برای زنده ماندن در رندر
    keep_alive()
    
    init_db()
    
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # تنظیم جاب برای گزارش شبانه (هر 24 ساعت - مثلا ساعت 22 به وقت سرور)
    # تذکر: ساعت سرور رندر UTC است.
    if app_bot.job_queue:
        app_bot.job_queue.run_daily(nightly_report, time=datetime.time(hour=22, minute=0, tzinfo=pytz.utc))

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('admin', admin_command)
        ],
        states={
            GET_NAME: [MessageHandler(filters.TEXT, get_name)],
            GET_SURNAME: [MessageHandler(filters.TEXT, get_surname)],
            GET_AGE: [MessageHandler(filters.TEXT, get_age)],
            GET_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, get_phone)],
            GET_EMAIL: [MessageHandler(filters.TEXT, get_email)],
            
            GET_ADMIN_PASS: [MessageHandler(filters.TEXT, verify_admin)],
            
            MAIN_MENU: [
                MessageHandler(filters.Regex('^(📊 آمار کامل کاربران|❌ حذف کاربر|📢 پیام همگانی|🔙 خروج از پنل)$'), admin_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
            ],
            
            SUPPORT_Handler: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive_message)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_handler)],
            ADMIN_DELETE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_user_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)]
    )

    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(join_callback, pattern='^check_join$'))
    app_bot.add_handler(CallbackQueryHandler(referral_action, pattern='^(confirm|reject)_'))
    
    print("Bot is running with Web Server...")
    app_bot.run_polling()
