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
# تنظیمات اصلی
# ---------------------------------------------------------------------------

TOKEN = '7813366410:AAFbOzXUBJwPYH9YI0WdAplmFRVYybXkPYc'
DATA_FILE = 'bot_data.json'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# وب‌سرور برای رندر
# ---------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ---------------------------------------------------------------------------
# مدیریت داده‌ها
# ---------------------------------------------------------------------------
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

CHANNELS_DB = load_data()

# ---------------------------------------------------------------------------
# منطق قیمت و آپدیت
# ---------------------------------------------------------------------------
def get_gold_price():
    base = 4550000 
    return f"{base + random.randint(-10000, 10000):,}"

async def update_price_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id, message_id = job_data['chat_id'], job_data['message_id']
    info = CHANNELS_DB.get(str(chat_id))
    
    if not info or not info.get('active'):
        context.job.schedule_removal()
        return

    text = (
        f"🏆 **نرخ لحظه‌ای طلا ۱۸ عیار**\n"
        f"💰 قیمت: `{get_gold_price()}` تومان\n"
        f"⏰ بروزرسانی: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📢 @{info.get('username', 'Channel')}"
    )
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Job Error: {e}")

# ---------------------------------------------------------------------------
# هندلرهای پنل
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ افزودن به کانال/گروه", url=f"https://t.me/{context.bot.username}?startgroup=true&admin=post_messages+edit_messages+pin_messages")],
        [InlineKeyboardButton("📋 لیست کانال‌ها", callback_data='list_channels')],
        [InlineKeyboardButton("📚 راهنما", callback_data='help')]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text("پنل مدیریت:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("سلام! به پنل مدیریت خوش آمدید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result.new_chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR]:
        chat_id = str(result.chat.id)
        if chat_id not in CHANNELS_DB:
            CHANNELS_DB[chat_id] = {'title': result.chat.title, 'username': result.chat.username, 'interval': 60, 'active': False, 'added_by': result.from_user.id, 'message_id': None}
            save_data(CHANNELS_DB)

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    btns = [[InlineKeyboardButton(f"{'🟢' if d['active'] else '🔴'} {d['title']}", callback_data=f"manage_{c}")] for c, d in CHANNELS_DB.items() if d.get('added_by') == query.from_user.id]
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')])
    await query.edit_message_text("کانال‌های شما:", reply_markup=InlineKeyboardMarkup(btns))

async def manage_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    info = CHANNELS_DB.get(chat_id)
    text = f"⚙️ **مدیریت: {info['title']}**\n⏱ زمان: {info['interval']} ثانیه\n📡 فعالیت: {'فعال' if info['active'] else 'متوقف'}"
    btns = [
        [InlineKeyboardButton("⏱ تنظیم زمان", callback_data=f"time_{chat_id}")],
        [InlineKeyboardButton("▶️ شروع" if not info['active'] else "🛑 توقف", callback_data=f"toggle_{chat_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='list_channels')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

async def toggle_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.data.split("_")[1]
    info = CHANNELS_DB[chat_id]
    
    if not info['active']:
        try:
            msg = await context.bot.send_message(chat_id, "⏳ در حال شروع...")
            await context.bot.pin_chat_message(chat_id, msg.message_id)
            info['active'], info['message_id'] = True, msg.message_id
            context.job_queue.run_repeating(update_price_job, interval=info['interval'], first=1, data={'chat_id': chat_id, 'message_id': msg.message_id}, name=f"job_{chat_id}")
            await query.answer("✅ فعال شد")
        except Exception as e:
            await query.answer(f"خطا در شروع: {e}", show_alert=True)
            return
    else:
        info['active'] = False
        for j in context.job_queue.get_jobs_by_name(f"job_{chat_id}"): j.schedule_removal()
        await query.answer("🛑 متوقف شد")
    
    save_data(CHANNELS_DB)
    await manage_channel(update, context)

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id, sec = update.callback_query.data.split("_")
    CHANNELS_DB[chat_id]['interval'] = int(sec)
    save_data(CHANNELS_DB)
    await query.answer("زمان ذخیره شد")
    await manage_channel(update, context)

if __name__ == '__main__':
    Thread(target=run_health_server, daemon=True).start()
    # استفاده از build() استاندارد برای فعالسازی JobQueue
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    app.add_handler(CallbackQueryHandler(list_channels, pattern='^list_channels$'))
    app.add_handler(CallbackQueryHandler(manage_channel, pattern='^manage_'))
    app.add_handler(CallbackQueryHandler(toggle_bot, pattern='^toggle_'))
    
    app.run_polling()
