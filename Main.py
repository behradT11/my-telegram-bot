import logging
import json
import os
import asyncio
import random
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

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
# تنظیمات اصلی (Main Settings)
# ---------------------------------------------------------------------------

# توکن شما (از بات فادر)
TOKEN = '7813366410:AAFbOzXUBJwPYH9YI0WdAplmFRVYybXkPYc'

# فایل ذخیره دیتابیس کانال‌ها
DATA_FILE = 'bot_data.json'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# وب‌سرور برای جلوگیری از خاموش شدن در Render
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Health check server started on port {port}")
    server.serve_forever()

# ---------------------------------------------------------------------------
# مدیریت داده‌ها (Data Management)
# ---------------------------------------------------------------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving data: {e}")

CHANNELS_DB = load_data()

# ---------------------------------------------------------------------------
# دریافت قیمت (Gold Price Logic)
# ---------------------------------------------------------------------------
def get_gold_price():
    # قیمت نمایشی (در آینده می‌توانید به API متصل کنید)
    base = 4550000 
    change = random.randint(-15000, 15000)
    return f"{base + change:,}"

# ---------------------------------------------------------------------------
# وظایف ربات (Update Jobs)
# ---------------------------------------------------------------------------

async def update_price_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    message_id = job_data.get('message_id')
    
    channel_info = CHANNELS_DB.get(str(chat_id))
    if not channel_info or not channel_info.get('active', False):
        context.job.schedule_removal()
        return

    price = get_gold_price()
    time_now = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"🏆 **نرخ لحظه‌ای طلا ۱۸ عیار**\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 قیمت: `{price}` تومان\n"
        f"⏰ بروزرسانی: {time_now}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"📢 @{channel_info.get('username', 'Channel')}"
    )

    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error updating message in {chat_id}: {e}")

# ---------------------------------------------------------------------------
# منوهای کاربری و مدیریت (UI Handlers)
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ افزودن به کانال/گروه", url=f"https://t.me/{context.bot.username}?startgroup=true&admin=post_messages+edit_messages+pin_messages")],
        [InlineKeyboardButton("📋 لیست کانال‌های من", callback_data='list_channels')],
        [InlineKeyboardButton("📚 راهنمای استفاده", callback_data='help')]
    ]
    text = "👋 سلام! به پنل مدیریت ربات قیمت طلا خوش آمدید.\n\nمن می‌توانم قیمت‌ها را در کانال شما پین کرده و خودکار آپدیت کنم."
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **راهنمای گام‌به‌گام:**\n\n"
        "1️⃣ ابتدا ربات را به کانال خود اضافه کنید.\n"
        "2️⃣ مطمئن شوید ربات **ادمین** است و دسترسی 'Pin Messages' دارد.\n"
        "3️⃣ از دکمه «لیست کانال‌ها» در همینجا، کانال خود را انتخاب کنید.\n"
        "4️⃣ زمان آپدیت را تعیین کرده و دکمه **شروع** را بزنید.\n\n"
        "✅ ربات پیامی را ارسال، پین و در بازه زمانی شما آپدیت می‌کند."
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره خودکار کانالی که ربات به آن اضافه می‌شود"""
    result = update.my_chat_member
    if result.new_chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        chat_id = str(result.chat.id)
        if chat_id not in CHANNELS_DB:
            CHANNELS_DB[chat_id] = {
                'title': result.chat.title,
                'username': result.chat.username or "PrivateChat",
                'interval': 60,
                'active': False,
                'added_by': result.from_user.id,
                'message_id': None
            }
            save_data(CHANNELS_DB)

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    buttons = []
    found = False
    for cid, data in CHANNELS_DB.items():
        if data.get('added_by') == user_id:
            found = True
            status = "🟢" if data['active'] else "🔴"
            buttons.append([InlineKeyboardButton(f"{status} {data['title']}", callback_data=f"manage_{cid}")])
    
    if not found:
        await query.edit_message_text("❌ شما هنوز ربات را در کانالی ادمین نکرده‌اید.", 
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]))
        return

    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')])
    await query.edit_message_text("📢 لیست کانال‌های تحت مدیریت شما:", reply_markup=InlineKeyboardMarkup(buttons))

async def manage_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    info = CHANNELS_DB.get(chat_id)
    
    if not info:
        await query.answer("اطلاعات یافت نشد.")
        return

    # چک کردن وضعیت ادمین به صورت زنده
    try:
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        admin_status = "✅ ادمین است" if member.status == ChatMember.ADMINISTRATOR else "❌ ادمین نیست"
    except:
        admin_status = "⚠️ عدم دسترسی"

    text = (
        f"⚙️ **مدیریت کانال: {info['title']}**\n\n"
        f"🛡 وضعیت ادمین: {admin_status}\n"
        f"⏱ زمان آپدیت: {info['interval']} ثانیه\n"
        f"📡 فعالیت: {'فعال 🟢' if info['active'] else 'متوقف 🔴'}"
    )
    
    buttons = [
        [InlineKeyboardButton("⏱ تنظیم زمان", callback_data=f"time_{chat_id}")],
        [InlineKeyboardButton("▶️ شروع فعالیت" if not info['active'] else "🛑 توقف فعالیت", callback_data=f"toggle_{chat_id}")],
        [InlineKeyboardButton("🔄 بروزرسانی وضعیت ادمین", callback_data=f"manage_{chat_id}")],
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='list_channels')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')

async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    info = CHANNELS_DB[chat_id]
    
    if not info['active']:
        try:
            # بررسی ادمین بودن قبل از شروع
            member = await context.bot.get_chat_member(chat_id, context.bot.id)
            if member.status != ChatMember.ADMINISTRATOR:
                await query.answer("❌ خطا: ابتدا ربات را در کانال ادمین کنید!", show_alert=True)
                return
            
            # ارسال پیام اولیه و پین کردن
            msg = await context.bot.send_message(chat_id, "⏳ سیستم اعلام قیمت در حال راه‌اندازی...")
            try:
                await context.bot.pin_chat_message(chat_id, msg.message_id)
            except:
                pass # اگر دسترسی پین نباشد فقط مسیج می‌دهد
                
            info['active'] = True
            info['message_id'] = msg.message_id
            
            # ثبت جاب تکرار شونده
            context.job_queue.run_repeating(
                update_price_job,
                interval=info['interval'],
                first=1,
                data={'chat_id': chat_id, 'message_id': msg.message_id},
                name=f"job_{chat_id}"
            )
            await query.answer("✅ ربات فعال و پیام پین شد.")
        except Exception as e:
            await query.answer(f"خطا در شروع: {e}", show_alert=True)
            return
    else:
        # متوقف کردن
        info['active'] = False
        jobs = context.job_queue.get_jobs_by_name(f"job_{chat_id}")
        for j in jobs: j.schedule_removal()
        await query.answer("🛑 فعالیت در این کانال متوقف شد.")
    
    save_data(CHANNELS_DB)
    await manage_channel(update, context)

async def set_time_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.callback_query.data.split("_")[1]
    times = [("30 ثانیه", 30), ("1 دقیقه", 60), ("5 دقیقه", 300), ("15 دقیقه", 900)]
    
    keyboard = []
    row = []
    for label, sec in times:
        row.append(InlineKeyboardButton(label, callback_data=f"save_{chat_id}_{sec}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"manage_{chat_id}")])
    
    await update.callback_query.edit_message_text("⏱ زمان بروزرسانی پیام را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id, sec = update.callback_query.data.split("_")
    CHANNELS_DB[chat_id]['interval'] = int(sec)
    save_data(CHANNELS_DB)
    await update.callback_query.answer("✅ زمان بروزرسانی ذخیره شد.")
    await manage_channel(update, context)

# ---------------------------------------------------------------------------
# نقطه شروع (Entry Point)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # اجرای وب‌سرور در ترد جداگانه (حیاتی برای رندر)
    Thread(target=run_health_server, daemon=True).start()
    
    # ساخت اپلیکیشن بات
    app = ApplicationBuilder().token(TOKEN).build()
    
    # ثبت هندلرها
    app.add_handler(CommandHandler('start', start))
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    app.add_handler(CallbackQueryHandler(help_ui, pattern='^help$'))
    app.add_handler(CallbackQueryHandler(list_channels, pattern='^list_channels$'))
    app.add_handler(CallbackQueryHandler(manage_channel, pattern='^manage_'))
    app.add_handler(CallbackQueryHandler(toggle_bot, pattern='^toggle_'))
    app.add_handler(CallbackQueryHandler(set_time_menu, pattern='^time_'))
    app.add_handler(CallbackQueryHandler(save_time, pattern='^save_'))

    print("--- Bot started successfully ---")
    app.run_polling()

