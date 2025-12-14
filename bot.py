import logging
import sqlite3
import datetime
import pytz
import os
import time
import signal
import sys
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
from telegram.error import BadRequest, Conflict, NetworkError

# ---------------------------------------------------------------------------
# تنظیمات و کانفیگ
# ---------------------------------------------------------------------------
BOT_TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
ADMIN_PASSWORD = "12345@Parstradecommunity"
CHANNEL_USERNAME = "@ParsTradeCommunity" 

# ⚠️ آیدی عددی گروه ادمین را اینجا بگذارید (از دستور /getid استفاده کنید)
ADMIN_GROUP_ID = -1001234567890 

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
    # دریافت پورت از متغیرهای محیطی رندر یا پیش‌فرض 10000
    port = int(os.environ.get("PORT", 10000))
    try:
        app.run(host='0.0.0.0', port=port)
    except:
        pass

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
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
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except BadRequest:
        logging.error("Bot is not admin in the channel or channel invalid.")
        return True 

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_id = chat.id
    chat_title = chat.title or chat.username or "Private Chat"
    print(f"--- GET ID REQUEST --- Chat ID: {chat_id}")
    await update.message.reply_text(
        f"🆔 **Chat ID:** `{chat_id}`\n"
        f"📛 **Title:** {chat_title}\n\n"
        f"⚠️ این عدد `{chat_id}` را کپی کنید و در خط 38 کد به جای `ADMIN_GROUP_ID` قرار دهید.",
        parse_mode='Markdown'
    )

# ---------------------------------------------------------------------------
# هندلرها
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        keyboard = [[InlineKeyboardButton("عضویت در کانال 📢", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")]]
        keyboard.append([InlineKeyboardButton("عضو شدم ✅", callback_data="check_join")])
        await update.message.reply_text(
            f"⛔ برای استفاده از ربات پارس ترید، ابتدا باید در کانال زیر عضو شوید:\n{CHANNEL_USERNAME}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    if get_user(user_id):
        await show_main_menu(update, context)
        return MAIN_MENU

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
        "👋 سلام! به کامیونیتی **پارس ترید** خوش آمدید.\n"
        "برای ثبت نام، نام خود را وارد کنید:"
    )
    return GET_NAME

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_membership(query.from_user.id, context):
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
    await update.message.reply_text("📞 شماره موبایل خود را ارسال کنید:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.contact.phone_number if update.message.contact else update.message.text
    await update.message.reply_text("📧 ایمیل خود را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    context.user_data['id'] = update.effective_user.id
    add_user_db(context.user_data)
    
    ref_id = context.user_data.get('referrer_id')
    user_id = context.user_data['id']
    name = f"{context.user_data['first_name']} {context.user_data['last_name']}"
    
    if ref_id:
        try:
            kb = [[InlineKeyboardButton("تایید ✅", callback_data=f"confirm_{ref_id}_{user_id}"), InlineKeyboardButton("رد ❌", callback_data=f"reject_{ref_id}_{user_id}")]]
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"🚨 **رفرال جدید**\n👤: {name}\n🆔: {user_id}\n📞: {context.user_data['phone']}\n🔗 دعوت کننده: {ref_id}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logging.error(f"Failed to send to admin group: {e}")

    await update.message.reply_text("🎉 ثبت نام شما تکمیل شد!")
    await show_main_menu(update, context)
    return MAIN_MENU

async def referral_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action, ref_id, new_user_id = data[0], int(data[1]), int(data[2])
    
    if action == "confirm":
        increment_referral(ref_id)
        new_text = f"✅ رفرال تایید شد (معرف: {ref_id})"
        try:
            await context.bot.send_message(ref_id, "✅ دعوت شما تایید شد!")
        except: pass
    else:
        new_text = f"❌ رفرال رد شد (کاربر: {new_user_id})"
        
    await query.edit_message_text(text=new_text, reply_markup=None)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [["🎁 مسابقه رفرال", "👤 پروفایل من"], ["📞 پشتیبانی"]]
    await update.message.reply_text("منوی اصلی:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        await start(update, context)
        return ConversationHandler.END

    if text == "🎁 مسابقه رفرال":
        user = get_user(user_id)
        ref_count = user[6] if user else 0
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await update.message.reply_text(f"🏆 **مسابقه رفرال**\nتعداد دعوت: {ref_count}\n🔗 لینک شما:\n{ref_link}")
    elif text == "👤 پروفایل من":
        user = get_user(user_id)
        if user: await update.message.reply_text(f"👤 نام: {user[1]} {user[2]}\nسن: {user[3]}\nشماره: {user[4]}")
    elif text == "📞 پشتیبانی":
        await update.message.reply_text("💬 پیام خود را بنویسید:")
        return SUPPORT_Handler
    return MAIN_MENU

async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    user = update.effective_user
    try:
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"📩 **پشتیبانی**\nاز: {user.first_name} ({user.id})\n\n{msg}")
        await update.message.reply_text("✅ ارسال شد.")
    except:
        await update.message.reply_text("❌ خطا در ارسال.")
    await show_main_menu(update, context)
    return MAIN_MENU

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 رمز ادمین:", reply_markup=ReplyKeyboardRemove())
    return GET_ADMIN_PASS

async def verify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_PASSWORD:
        context.user_data['is_admin'] = True
        await show_admin_panel(update, context)
        return MAIN_MENU
    else:
        await update.message.reply_text("❌ رمز اشتباه.")
        await show_main_menu(update, context)
        return MAIN_MENU

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [["📊 آمار", "❌ حذف کاربر"], ["📢 پیام همگانی", "🔙 خروج"]]
    await update.message.reply_text("🔧 پنل ادمین", reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('is_admin'): return await menu_handler(update, context)
    text = update.message.text
    if text == "📊 آمار":
        users = get_all_users()
        report = "📋 **کاربران:**\n" + "\n".join([f"🆔 `{u[0]}` | {u[1]}" for u in users])
        if len(report) > 4000: report = report[:4000] + "..."
        await update.message.reply_text(report or "خالی", parse_mode='Markdown')
    elif text == "❌ حذف کاربر":
        await update.message.reply_text("🆔 آیدی کاربر:")
        return ADMIN_DELETE_USER
    elif text == "📢 پیام همگانی":
        await update.message.reply_text("متن پیام:")
        return ADMIN_BROADCAST
    elif text == "🔙 خروج":
        context.user_data['is_admin'] = False
        await show_main_menu(update, context)
    return MAIN_MENU

async def delete_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if delete_user_db(int(update.message.text)): await update.message.reply_text("✅ حذف شد.")
        else: await update.message.reply_text("❌ یافت نشد.")
    except: await update.message.reply_text("❌ فقط عدد.")
    await show_admin_panel(update, context)
    return MAIN_MENU

async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    count = 0
    await update.message.reply_text("⏳ ارسال...")
    for u in get_all_users():
        try:
            await context.bot.send_message(u[0], msg)
            count += 1
        except: pass
    await update.message.reply_text(f"✅ به {count} نفر ارسال شد.")
    await show_admin_panel(update, context)
    return MAIN_MENU

async def nightly_report(context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    msg = f"🌙 **گزارش شبانه**\n👥 کل: {len(users)}\n📅 {datetime.datetime.now().strftime('%Y-%m-%d')}"
    try: await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=msg)
    except Exception as e: logging.error(f"Report error: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(msg="Exception:", exc_info=context.error)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# اجرای اصلی با تأخیر برای جلوگیری از کانفلیکت
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # این بخش حیاتی است: ۱۵ ثانیه صبر می‌کند تا نسخه قبلی در رندر بمیرد
    print("⏳ Waiting 15s for the old instance to shut down...")
    time.sleep(15)
    
    keep_alive()
    init_db()
    
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_error_handler(error_handler)
    
    if app_bot.job_queue:
        app_bot.job_queue.run_daily(nightly_report, time=datetime.time(hour=22, minute=0, tzinfo=pytz.utc))

    app_bot.add_handler(CommandHandler('getid', get_chat_id))
    app_bot.add_handler(MessageHandler(filters.Regex(r'(?i)^(id|آیدی|getid)$'), get_chat_id))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('admin', admin_command)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT, get_name)],
            GET_SURNAME: [MessageHandler(filters.TEXT, get_surname)],
            GET_AGE: [MessageHandler(filters.TEXT, get_age)],
            GET_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, get_phone)],
            GET_EMAIL: [MessageHandler(filters.TEXT, get_email)],
            GET_ADMIN_PASS: [MessageHandler(filters.TEXT, verify_admin)],
            MAIN_MENU: [
                MessageHandler(filters.Regex('^(📊 آمار|❌ حذف کاربر|📢 پیام همگانی|🔙 خروج)$'), admin_handler),
                CommandHandler('admin', admin_command),
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
    
    print("🚀 Bot is starting polling...")
    # drop_pending_updates=True پیام‌های قدیمی را نادیده می‌گیرد تا سریع وصل شود
    app_bot.run_polling(drop_pending_updates=True)
