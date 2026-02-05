import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- تنظیمات اصلی ---
TOKEN = "8268222524:AAEm3UkcZuSg0305IvggF44phnvCr0wDMvQ"
ADMIN_ID = 1949690541
CHANNEL_ID = "@ParsTradeCommunity"  # آیدی عمومی کانال
CHANNEL_URL = "https://t.me/ParsTradeCommunity"

# ذخیره آمار در حافظه (برای دائمی بودن بهتر است از دیتابیس استفاده کنید)
users = set()

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """بررسی عضویت کاربر در کانال"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users.add(user_id)
    
    if await is_subscribed(context, user_id):
        keyboard = [
            [InlineKeyboardButton("📊 مشاهده پروفایل", callback_data='profile')],
            [InlineKeyboardButton("📞 پشتیبانی", callback_data='support')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"سلام {update.effective_user.first_name} عزیز! خوش آمدید.\nشما عضو کانال هستید و تمام دسترسی‌ها باز است.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_URL)],
            [InlineKeyboardButton("✅ تایید عضویت", callback_data='check_sub')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ برای استفاده از این ربات، ابتدا باید در کانال ما عضو شوید:\n\n" + CHANNEL_URL,
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'check_sub':
        if await is_subscribed(context, user_id):
            await query.edit_message_text("✅ سپاس! عضویت شما تایید شد. حالا دوباره /start را بزنید.")
        else:
            await query.edit_message_text("❌ هنوز عضو نشدید! ابتدا عضو شوید و سپس دکمه تایید را بزنید.", 
                                         reply_markup=query.message.reply_markup)
            
    elif query.data == 'profile':
        await query.message.reply_text(f"👤 نام: {query.from_user.first_name}\n🆔 آیدی عددی: {user_id}")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل مدیریت"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    count = len(users)
    await update.message.reply_text(f"🛠 پنل مدیریت:\n\n👥 تعداد کل کاربران: {count}\n\nبرای ارسال پیام همگانی دستور زیر را استفاده کنید:\n`/sendall متن پیام`", parse_mode='Markdown')

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به تمام کاربران (توسط ادمین)"""
    if update.effective_user.id != ADMIN_ID: return
    
    text = ' '.join(context.args)
    if not text:
        await update.message.reply_text("لطفا متن پیام را وارد کنید.")
        return

    success = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user, text=text)
            success += 1
        except:
            continue
    
    await update.message.reply_text(f"✅ پیام به {success} نفر ارسال شد.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()

