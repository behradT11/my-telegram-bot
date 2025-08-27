# First, run these commands in your terminal to install necessary libraries:
# pip install python-telegram-bot
# pip install --upgrade python-telegram-bot # Make sure you have the latest version

import logging
import sqlite3
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler, CallbackQueryHandler, MessageHandler, filters

# --- CONFIGURATION ---
TOKEN = "8470707180:AAE8C8WISVBZAgS9Yw1M8Y1F6WBU2FXpuBc"
TARGET_CHANNEL_ID = -1002267992305
BOT_USERNAME = "FVCounter_bot"
CHANNEL_LINK = "https://t.me/+7UMWPY5mB2o2M2U0"

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DATABASE SETUP ---
def setup_database():
    """Creates/updates the database and the users table."""
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            username TEXT,
            score INTEGER DEFAULT 0,
            has_joined_channel INTEGER DEFAULT 0
        )
    """)
    try:
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'has_joined_channel' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN has_joined_channel INTEGER DEFAULT 0")
            logging.info("Updated database schema: Added 'has_joined_channel' column.")
    except Exception as e:
        logging.error(f"Error updating database schema: {e}")
    conn.commit()
    conn.close()

# --- KEYBOARDS ---
def get_main_menu_keyboard():
    """Returns the persistent main menu keyboard."""
    keyboard = [
        [KeyboardButton("🔗 دریافت لینک دعوت"), KeyboardButton("📊 امتیاز من")],
        [KeyboardButton("🏆 رتبه بندی"), KeyboardButton("ℹ️ راهنما")] # New Help Button
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_force_join_keyboard():
    """Returns the inline keyboard that forces users to join the channel."""
    keyboard = [
        [InlineKeyboardButton("➡️ عضویت در کانال", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ عضویت را بررسی کن", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- HELPER & MENU FUNCTIONS ---
async def send_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the welcome photo and help message."""
    chat_id = update.effective_chat.id
    help_caption = (
        "🎉 خوش آمدید!\n\n"
        "**راهنمای ربات:**\n\n"
        "🔹 **دریافت لینک دعوت:**\n"
        "با استفاده از این دکمه، لینک اختصاصی خود را برای دعوت دوستانتان دریافت کنید.\n\n"
        "🔹 **امتیاز من:**\n"
        "در این بخش می‌توانید امتیاز فعلی و لیست کاربرانی که دعوت کرده‌اید را مشاهده کنید.\n\n"
        "🔹 **رتبه بندی:**\n"
        "لیست ۱۰ کاربر برتر را مشاهده کنید.\n\n"
        "موفق باشید!"
    )
    # Using a more stable direct image link to prevent errors.
    # You can replace this with your own direct image URL (e.g., from postimages.org)
    photo_url = "https://i.postimg.cc/1X7XyC8D/welcome.png"
    await context.bot.send_photo(
        chat_id=chat_id, photo=photo_url, caption=help_caption, parse_mode='Markdown'
    )

async def get_my_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the user their referral link."""
    user_id = update.effective_user.id
    referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    text = (
        "این لینک دعوت اختصاصی شماست. آن را برای دوستانتان ارسال کنید.\n\n"
        "✅ **مهم:** دوستان شما باید ربات را با این لینک استارت کنند و سپس عضو کانال شوند تا امتیاز برای شما ثبت شود.\n\n"
        f"`{referral_link}`"
    )
    await update.message.reply_text(text=text, parse_mode='Markdown')

async def show_my_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user their score and referrals."""
    user_id = update.effective_user.id
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT score FROM users WHERE user_id = ?", (user_id,))
    score_result = cursor.fetchone()
    score = score_result[0] if score_result else 0
    cursor.execute("SELECT user_id, username FROM users WHERE referrer_id = ?", (user_id,))
    referrals = cursor.fetchall()
    conn.close()
    
    message = f"امتیاز فعلی شما: *{score}*\n\n"
    if referrals:
        message += "کاربرانی که شما دعوت کرده‌اید:\n"
        for ref_id, ref_username in referrals:
            username_display = f"@{ref_username}" if ref_username else f"کاربر `{ref_id}`"
            message += f"- {username_display}\n"
    else:
        message += "شما هنوز کسی را دعوت نکرده‌اید."
    await update.message.reply_text(text=message, parse_mode='Markdown')

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the top 10 users with the highest scores."""
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, score FROM users ORDER BY score DESC LIMIT 10")
    leaderboard = cursor.fetchall()
    conn.close()
    
    message = "🏆 *۱۰ نفر برتر کانال* 🏆\n\n"
    if leaderboard:
        rank_emojis = ["🥇", "🥈", "🥉"]
        for i, (user_id, username, score) in enumerate(leaderboard):
            rank = rank_emojis[i] if i < 3 else f"**{i + 1}.**"
            username_display = f"@{username}" if username else f"کاربر `{user_id}`"
            message += f"{rank} {username_display} - *{score}* امتیاز\n"
    else:
        message += "هنوز هیچ کاربری امتیازی کسب نکرده است."
    await update.message.reply_text(text=message, parse_mode='Markdown')

# --- CORE BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command. Checks if user has joined the channel before proceeding."""
    user = update.effective_user
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        referrer_id = None
        if context.args and len(context.args) > 0:
            try:
                potential_referrer_id = int(context.args[0])
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (potential_referrer_id,))
                if cursor.fetchone():
                    referrer_id = potential_referrer_id
                    user_mention = f"@{user.username}" if user.username else f"کاربر {user.id}"
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🔔 کاربر جدیدی ({user_mention}) از طریق لینک شما وارد ربات شد."
                    )
            except (ValueError, IndexError):
                logging.warning(f"Invalid referral code: {context.args}")

        cursor.execute(
            "INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)",
            (user.id, user.username, referrer_id)
        )
        conn.commit()
        await update.message.reply_text(
            "خوش آمدید! برای استفاده از امکانات ربات، لطفاً ابتدا در کانال ما عضو شوید و سپس عضویت خود را بررسی کنید.",
            reply_markup=get_force_join_keyboard()
        )
    else:
        if existing_user[4]: # has_joined_channel
            await update.message.reply_text("سلام مجدد! شما عضو کانال هستید و می‌توانید از ربات استفاده کنید.", reply_markup=get_main_menu_keyboard())
        else:
            await update.message.reply_text("شما هنوز عضو کانال نشده‌اید. لطفاً ابتدا در کانال عضو شوید و سپس عضویت خود را بررسی کنید.", reply_markup=get_force_join_keyboard())
    
    conn.close()

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'verify_join' button click."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT referrer_id, has_joined_channel FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        await query.edit_message_text("خطا: اطلاعات شما یافت نشد. لطفاً ربات را با /start راه‌اندازی کنید.")
        conn.close()
        return
        
    referrer_id, has_joined = result[0], result[1]
    
    if has_joined:
        await query.edit_message_text("شما قبلاً عضویت خود را تایید کرده‌اید.")
        await context.bot.send_message(chat_id=user_id, text="منوی اصلی:", reply_markup=get_main_menu_keyboard())
        conn.close()
        return

    try:
        member = await context.bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            if referrer_id:
                cursor.execute("UPDATE users SET score = score + 1 WHERE user_id = ?", (referrer_id,))
            cursor.execute("UPDATE users SET has_joined_channel = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            
            if referrer_id:
                cursor.execute("SELECT score FROM users WHERE user_id = ?", (referrer_id,))
                new_score = cursor.fetchone()[0]
                user_mention = f"@{query.from_user.username}" if query.from_user.username else f"کاربر {user_id}"
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"✅ کاربر دعوت شده ({user_mention}) عضو کانال شد. **یک امتیاز** به شما اضافه شد.\n\nامتیاز فعلی شما: {new_score}"
                )
            
            await query.delete_message()
            await send_help_message(query, context)
            await context.bot.send_message(
                chat_id=user_id, text="منوی اصلی برای شما فعال شد:", reply_markup=get_main_menu_keyboard()
            )
        else:
            await query.message.reply_text("شما هنوز عضو کانال نیستید. لطفاً ابتدا در کانال عضو شوید و سپس دوباره دکمه را فشار دهید.")
    except TelegramError as e:
        logging.error(f"Telegram API Error checking chat member: {e}")
        await query.message.reply_text(f"❌ خطای تلگرام در بررسی عضویت: `{e}`")
    finally:
        conn.close()

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles text messages from the persistent menu after checking channel membership."""
    user_id = update.effective_user.id
    
    # --- NEW: Membership check before every command ---
    try:
        member = await context.bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
        if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            await update.message.reply_text(
                "به نظر می‌رسد شما دیگر عضو کانال نیستید! برای استفاده از ربات، لطفاً مجدداً در کانال عضو شوید و عضویت خود را بررسی کنید.",
                reply_markup=get_force_join_keyboard()
            )
            return
    except TelegramError:
        await update.message.reply_text("خطایی در بررسی عضویت شما رخ داد. لطفاً لحظاتی بعد دوباره تلاش کنید.")
        return

    text = update.message.text
    if text == "🔗 دریافت لینک دعوت":
        await get_my_link(update, context)
    elif text == "📊 امتیاز من":
        await show_my_score(update, context)
    elif text == "🏆 رتبه بندی":
        await show_leaderboard(update, context)
    elif text == "ℹ️ راهنما":
        await send_help_message(update, context)

async def track_channel_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracks when a user LEAVES the channel to deduct points."""
    if update.chat_member.chat.id != TARGET_CHANNEL_ID:
        return

    old_status = getattr(update.chat_member.old_chat_member, 'status', None)
    new_status = getattr(update.chat_member.new_chat_member, 'status', None)
    
    was_member = old_status in ["member", "administrator", "creator"]
    is_member = new_status in ["member", "administrator", "creator"]

    if was_member and not is_member:
        user = update.chat_member.old_chat_member.user
        user_id = user.id
        conn = sqlite3.connect("referrals.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            referrer_id = result[0]
            logging.info(f"User {user_id} LEFT. Deducting point from {referrer_id}.")
            cursor.execute("UPDATE users SET score = score - 1 WHERE user_id = ?", (referrer_id,))
            cursor.execute("UPDATE users SET has_joined_channel = 0 WHERE user_id = ?", (user_id,))
            conn.commit()
            
            cursor.execute("SELECT score FROM users WHERE user_id = ?", (referrer_id,))
            new_score = cursor.fetchone()[0]
            user_mention = f"@{user.username}" if user.username else f"کاربر {user_id}"
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"❌ کاربر دعوت شده ({user_mention}) کانال را ترک کرد. **یک امتیاز** از شما کسر شد.\n\nامتیاز فعلی شما: {new_score}"
            )
        conn.close()

# --- MAIN FUNCTION ---
def main() -> None:
    """Sets up and runs the bot."""
    logging.info(f"Using python-telegram-bot version: {telegram.__version__}")
    setup_database()
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(ChatMemberHandler(track_channel_members, ChatMemberHandler.CHAT_MEMBER))
    
    print("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
