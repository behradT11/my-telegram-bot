import logging
import json
import os
import asyncio
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    MessageHandler,
    filters
)
from telegram.error import BadRequest, Forbidden

# ---------------------------------------------------------------------------
# تنظیمات اولیه
# ---------------------------------------------------------------------------

# ⚠️ توکن خود را در خط زیر وارد کنید
TOKEN = 'YOUR_TOKEN_HERE'  # <--- توکن خود را اینجا بگذارید

# نام فایل برای ذخیره اطلاعات کانال‌ها
DATA_FILE = 'bot_data.json'

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# بخش مدیریت داده‌ها (ذخیره و بازیابی)
# ---------------------------------------------------------------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# متغیر سراسری برای نگهداری داده‌ها در حافظه
CHANNELS_DB = load_data()

# ---------------------------------------------------------------------------
# تابع شبیه‌ساز قیمت طلا (جایگزین با API واقعی)
# ---------------------------------------------------------------------------
def get_gold_price():
    """
    این تابع فعلاً قیمت را شبیه‌سازی می‌کند.
    برای استفاده واقعی باید به یک API متصل شود یا Scrape کند.
    """
    base = 4300000  # قیمت پایه حدودی
    change = random.randint(-15000, 15000)
    price = base + change
    # فرمت سه رقم سه رقم
    return f"{price:,}"

# ---------------------------------------------------------------------------
# وظایف پس‌زمینه (Jobs)
# ---------------------------------------------------------------------------

async def update_price_job(context: ContextTypes.DEFAULT_TYPE):
    """این تابع طبق زمان‌بندی اجرا می‌شود و پیام پین شده را آپدیت می‌کند"""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    message_id = job_data.get('message_id')
    
    # دریافت اطلاعات کانال از دیتابیس
    channel_info = CHANNELS_DB.get(str(chat_id))
    
    if not channel_info or not channel_info.get('active', False):
        context.job.schedule_removal()
        return

    price = get_gold_price()
    time_now = datetime.now().strftime("%H:%M:%S")
    date_now = datetime.now().strftime("%Y-%m-%d")

    text = (
        f"🏆 **نرخ لحظه‌ای طلا ۱۸ عیار**\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 قیمت: `{price}` تومان\n"
        f"📅 تاریخ: {date_now}\n"
        f"⏰ ساعت: {time_now}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🆔 @{channel_info.get('username', 'Channel')}"
    )

    try:
        # اگر پیام قبلی وجود دارد، آن را ویرایش کن
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode='Markdown'
            )
        else:
            # اگر پیام وجود ندارد (مثلا پاک شده)، پیام جدید بفرست
            msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            try:
                await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
            except:
                pass # شاید دسترسی پین نداشته باشد
            
            # ذخیره ID پیام جدید
            CHANNELS_DB[str(chat_id)]['message_id'] = msg.message_id
            save_data(CHANNELS_DB)
            
            # آپدیت جاب فعلی با مسیج آیدی جدید
            job_data['message_id'] = msg.message_id

    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass  # محتوا تغییر نکرده، مشکلی نیست
        elif "Message to edit not found" in str(e):
             # پیام پاک شده، دفعه بعد جدید می‌سازیم
             CHANNELS_DB[str(chat_id)]['message_id'] = None
             save_data(CHANNELS_DB)
        else:
            logger.error(f"Update error in {chat_id}: {e}")
            # اگر دسترسی نداریم، غیرفعال کنیم
            # CHANNELS_DB[str(chat_id)]['active'] = False
            # save_data(CHANNELS_DB)

# ---------------------------------------------------------------------------
# هندلرها و منوها
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    keyboard = [
        [
            InlineKeyboardButton("➕ افزودن ربات به کانال/گروه", url=f"https://t.me/{context.bot.username}?startgroup=true&admin=post_messages+edit_messages+pin_messages")
        ],
        [
            InlineKeyboardButton("📋 لیست کانال‌های من", callback_data='list_channels')
        ],
        [
            InlineKeyboardButton("📚 راهنما", callback_data='help')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"سلام {user.first_name} عزیز! 👋\n\n"
        "من ربات اعلام قیمت لحظه‌ای طلا هستم.\n"
        "من می‌توانم قیمت طلا را در کانال یا گروه شما به صورت خودکار پین و آپدیت کنم.\n\n"
        "👇 از گزینه‌های زیر استفاده کنید:"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "📚 **راهنمای استفاده از ربات**\n\n"
        "1️⃣ دکمه **«افزودن ربات به کانال»** را بزنید و کانال خود را انتخاب کنید.\n"
        "2️⃣ ربات به صورت خودکار دسترسی‌های لازم (ادمین) را درخواست می‌کند. تأیید کنید.\n"
        "3️⃣ به همین صفحه برگردید و دکمه **«لیست کانال‌های من»** را بزنید.\n"
        "4️⃣ کانال خود را انتخاب کنید و تنظیمات (زمان آپدیت) را انجام دهید.\n"
        "5️⃣ دکمه **«شروع نمایش قیمت»** را بزنید.\n\n"
        "⚠️ **نکته:** ربات برای کار کردن حتماً باید در کانال شما **ادمین** باشد (دسترسی ارسال پیام، ویرایش و پین کردن)."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- هندلر اضافه شدن ربات به کانال ---
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی وضعیت عضویت ربات در یک چت تغییر می‌کند (مثلا اد می‌شود)"""
    result = update.my_chat_member
    new_member = result.new_chat_member
    chat = result.chat
    
    # اگر ربات به کانال/گروه اضافه شد یا ادمین شد
    if new_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        chat_id = str(chat.id)
        
        # ذخیره اطلاعات اولیه کانال
        if chat_id not in CHANNELS_DB:
            CHANNELS_DB[chat_id] = {
                'title': chat.title,
                'username': chat.username,
                'interval': 60,  # پیش‌فرض ۶۰ ثانیه
                'active': False,
                'added_by': result.from_user.id,
                'message_id': None
            }
            save_data(CHANNELS_DB)
            
        logger.info(f"Bot added to chat: {chat.title} ({chat_id})")

    # اگر ربات از کانال حذف شد
    elif new_member.status in [ChatMember.LEFT, ChatMember.BANNED]:
        chat_id = str(chat.id)
        if chat_id in CHANNELS_DB:
            # پاک کردن جاب
            job_name = f"job_{chat_id}"
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in current_jobs:
                job.schedule_removal()
            
            # حذف از دیتابیس (اختیاری، شاید بخواهید نگه دارید)
            del CHANNELS_DB[chat_id]
            save_data(CHANNELS_DB)
            logger.info(f"Bot removed from chat: {chat.title}")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # پیدا کردن کانال‌هایی که این کاربر اد کرده است (برای امنیت ساده)
    # در نسخه ساده همه کانال‌ها را نشان می‌دهیم، اما بهتر است فیلتر شود
    user_channels = []
    for cid, data in CHANNELS_DB.items():
        # شرط: یا کاربر اد کننده باشد، یا ادمین اصلی (برای تست)
        if data.get('added_by') == user_id or True: # True گذاشتم تا فعلا همه را ببینید
            status_icon = "🟢" if data.get('active') else "🔴"
            user_channels.append(
                InlineKeyboardButton(f"{status_icon} {data.get('title', 'Unknown')}", callback_data=f"manage_{cid}")
            )

    if not user_channels:
        text = "❌ شما هنوز ربات را به هیچ کانالی اضافه نکرده‌اید.\nلطفا ابتدا دکمه «افزودن ربات» را بزنید."
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]
    else:
        text = "📢 کانال مورد نظر را برای مدیریت انتخاب کنید:"
        # چیدمان دکمه‌ها زیر هم
        keyboard = [[btn] for btn in user_channels]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data='main_menu')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def manage_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.data.replace("manage_", "")
    info = CHANNELS_DB.get(chat_id)
    
    if not info:
        await query.edit_message_text("❌ اطلاعات این کانال یافت نشد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='list_channels')]]))
        return

    # بررسی ادمین بودن به صورت زنده
    is_admin = False
    admin_text = "❓ نامشخص"
    try:
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if member.status == ChatMember.ADMINISTRATOR:
            is_admin = True
            admin_text = "✅ بله (ادمین است)"
        else:
            admin_text = "❌ خیر (دسترسی ندارد)"
    except Exception as e:
        admin_text = "⚠️ ربات در کانال نیست"

    status_text = "فعال 🟢" if info['active'] else "غیرفعال 🔴"
    interval_text = f"{info['interval']} ثانیه"

    text = (
        f"⚙️ **تنظیمات کانال: {info['title']}**\n\n"
        f"🆔 آیدی عددی: `{chat_id}`\n"
        f"👮 وضعیت ادمین: {admin_text}\n"
        f"⏱ بازه آپدیت: {interval_text}\n"
        f"📡 وضعیت ربات: {status_text}\n"
    )

    keyboard = []
    
    # دکمه استارت/استاپ
    if info['active']:
        keyboard.append([InlineKeyboardButton("🛑 توقف ربات", callback_data=f"stop_{chat_id}")])
    else:
        keyboard.append([InlineKeyboardButton("▶️ شروع نمایش قیمت", callback_data=f"startbot_{chat_id}")])
    
    # دکمه تنظیم زمان
    keyboard.append([InlineKeyboardButton("⏱ تغییر زمان آپدیت", callback_data=f"settime_{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔄 بررسی مجدد ادمین", callback_data=f"manage_{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='list_channels')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    await query.answer()

    text = "⏱ لطفاً بازه زمانی آپدیت قیمت را انتخاب کنید:"
    
    # گزینه‌های زمان
    times = [
        ("۳۰ ثانیه", 30),
        ("۱ دقیقه", 60),
        ("۵ دقیقه", 300),
        ("۳۰ دقیقه", 1800),
        ("۱ ساعت", 3600)
    ]
    
    keyboard = []
    row = []
    for label, seconds in times:
        row.append(InlineKeyboardButton(label, callback_data=f"savetime_{chat_id}_{seconds}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"manage_{chat_id}")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id, seconds = query.data.split("_")
    seconds = int(seconds)
    
    if chat_id in CHANNELS_DB:
        CHANNELS_DB[chat_id]['interval'] = seconds
        save_data(CHANNELS_DB)
        
        # اگر ربات فعال است، باید جاب را ریست کنیم تا با زمان جدید کار کند
        if CHANNELS_DB[chat_id]['active']:
            # توقف موقت برای اعمال تغییرات
            await stop_bot_logic(context, chat_id)
            # شروع مجدد
            await start_bot_logic(context, chat_id, query)
            await query.answer("✅ زمان ذخیره شد و اعمال گردید.")
        else:
            await query.answer("✅ زمان ذخیره شد.")
            
        # بازگشت به منوی مدیریت
        await manage_channel(update, context)

async def start_bot_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    
    await start_bot_logic(context, chat_id, query)
    await manage_channel(update, context) # رفرش کردن منو

async def start_bot_logic(context, chat_id, query=None):
    """منطق اصلی شروع ربات"""
    # 1. بررسی ادمین بودن
    try:
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if member.status != ChatMember.ADMINISTRATOR:
            if query: await query.answer("❌ خطا: ربات در کانال ادمین نیست!", show_alert=True)
            return
        if not member.can_pin_messages:
            if query: await query.answer("❌ خطا: ربات اجازه پین کردن پیام ندارد!", show_alert=True)
            return
    except Exception as e:
        if query: await query.answer(f"❌ خطا در دسترسی به کانال: {e}", show_alert=True)
        return

    # 2. فعال سازی
    info = CHANNELS_DB[chat_id]
    info['active'] = True
    save_data(CHANNELS_DB)
    
    if query: await query.answer("✅ ربات فعال شد.")

    # 3. ایجاد Job
    job_name = f"job_{chat_id}"
    
    # حذف جاب‌های قبلی اگر باشد
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        
    # ارسال پیام اولیه
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ در حال راه‌اندازی سیستم قیمت...")
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
        info['message_id'] = msg.message_id
        save_data(CHANNELS_DB)
        
        context.job_queue.run_repeating(
            update_price_job,
            interval=info['interval'],
            first=1, # اولین اجرا ۱ ثانیه بعد
            data={'chat_id': chat_id, 'message_id': msg.message_id},
            name=job_name
        )
    except Exception as e:
        logger.error(f"Error starting job: {e}")

async def stop_bot_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    
    await stop_bot_logic(context, chat_id)
    await query.answer("🛑 ربات متوقف شد.")
    await manage_channel(update, context)

async def stop_bot_logic(context, chat_id):
    if chat_id in CHANNELS_DB:
        CHANNELS_DB[chat_id]['active'] = False
        save_data(CHANNELS_DB)
        
        job_name = f"job_{chat_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

# ---------------------------------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # ساخت اپلیکیشن
    application = ApplicationBuilder().token(TOKEN).build()
    
    # هندلرهای دستورات
    application.add_handler(CommandHandler('start', start))
    
    # هندلر تشخیص اضافه شدن به کانال
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # هندلرهای دکمه‌ها
    application.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(list_channels, pattern='^list_channels$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(manage_channel, pattern='^manage_'))
    application.add_handler(CallbackQueryHandler(time_selection, pattern='^settime_'))
    application.add_handler(CallbackQueryHandler(save_time, pattern='^savetime_'))
    application.add_handler(CallbackQueryHandler(start_bot_action, pattern='^startbot_'))
    application.add_handler(CallbackQueryHandler(stop_bot_action, pattern='^stop_'))

    print("🤖 Bot is running...")
    application.run_polling()

