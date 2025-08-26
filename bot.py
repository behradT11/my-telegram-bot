# First, run these commands in your terminal to install necessary libraries:
# pip install python-telegram-bot
# pip install --upgrade python-telegram-bot # Make sure you have the latest version

import logging
import sqlite3
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler, CallbackQueryHandler

# --- CONFIGURATION (Updated with your info) ---
TOKEN = "8470707180:AAE8C8WISVBZAgS9Yw1M8Y1F6WBU2FXpuBc"
TARGET_CHANNEL_ID = -1002267992305
BOT_USERNAME = "FVCounter_bot"
# Your new channel link
CHANNEL_LINK = "https://t.me/+7UMWPY5mB2o2M2U0"

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DATABASE SETUP ---
def setup_database():
    """Creates the database and the users table, and adds missing columns if necessary."""
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    # The full, correct schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            username TEXT,
            score INTEGER DEFAULT 0,
            has_joined_channel INTEGER DEFAULT 0
        )
    """)
    
    # This part is for migrating older database files that might be missing the column.
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

# --- HELPER FUNCTIONS ---
def get_main_menu_keyboard():
    """Returns the main menu keyboard for verified users."""
    keyboard = [
        [InlineKeyboardButton("🔗 دریافت لینک دعوت", callback_data="my_link")],
        [InlineKeyboardButton("📊 امتیاز و زیرمجموعه‌ها", callback_data="my_score")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_force_join_keyboard():
    """Returns the keyboard that forces users to join the channel."""
    keyboard = [
        [InlineKeyboardButton("➡️ عضویت در کانال", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ عضویت را بررسی کن", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command. Checks if user has joined the channel before proceeding."""
    user = update.effective_user
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()

    # Query format: user_id, referrer_id, username, score, has_joined_channel
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        # New user registration
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
        
        # Force the new user to join the channel
        await update.message.reply_text(
            "خوش آمدید! برای استفاده از امکانات ربات، لطفاً ابتدا در کانال ما عضو شوید و سپس عضویت خود را بررسی کنید.",
            reply_markup=get_force_join_keyboard()
        )
    else:
        # Existing user
        # Access by index: existing_user[4] corresponds to has_joined_channel
        if existing_user[4]:
            await update.message.reply_text("سلام مجدد! شما عضو کانال هستید و می‌توانید از ربات استفاده کنید.", reply_markup=get_main_menu_keyboard())
        else:
            await update.message.reply_text("شما هنوز عضو کانال نشده‌اید. لطفاً ابتدا در کانال عضو شوید و سپس عضویت خود را بررسی کنید.", reply_markup=get_force_join_keyboard())
    
    conn.close()

# --- CALLBACK QUERY HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all button clicks."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "my_link":
        referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        text = (
            "این لینک دعوت اختصاصی شماست. آن را برای دوستانتان ارسال کنید.\n\n"
            "✅ **مهم:** دوستان شما باید ربات را با این لینک استارت کنند و سپس عضو کانال شوند تا امتیاز برای شما ثبت شود.\n\n"
            f"`{referral_link}`"
        )
        await query.message.reply_text(text=text, parse_mode='Markdown')

    elif data == "my_score":
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
        await query.message.reply_text(text=message, parse_mode='Markdown')

    elif data == "verify_join":
        conn = sqlite3.connect("referrals.db", check_same_thread=False)
        cursor = conn.cursor()
        # Query format: referrer_id, has_joined_channel
        cursor.execute("SELECT referrer_id, has_joined_channel FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if not result:
            await query.edit_message_text("خطا: اطلاعات شما یافت نشد. لطفاً ربات را با /start راه‌اندازی کنید.")
            conn.close()
            return
            
        # Access by index: result[0] is referrer_id, result[1] is has_joined_channel
        referrer_id, has_joined = result[0], result[1]
        
        if has_joined:
            await query.edit_message_text("شما قبلاً عضویت خود را تایید کرده‌اید.", reply_markup=get_main_menu_keyboard())
            conn.close()
            return

        try:
            member = await context.bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
            status = getattr(member, 'status', 'STATUS_NOT_FOUND')
            
            # --- BUG FIX ---
            # Using plain strings for comparison to avoid rare enum-related errors.
            if status in ["member", "administrator", "creator"]:
                # User is a member, award point and unlock bot
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
                
                await query.edit_message_text("عضویت شما با موفقیت تایید شد! اکنون می‌توانید از ربات استفاده کنید.", reply_markup=get_main_menu_keyboard())
            else:
                await query.message.reply_text("شما هنوز عضو کانال نیستید. لطفاً ابتدا در کانال عضو شوید و سپس دوباره دکمه را فشار دهید.")
        
        except TelegramError as e:
            logging.error(f"Telegram API Error checking chat member: {e}")
            await query.message.reply_text(
                f"❌ خطای تلگرام در بررسی عضویت: `{e}`\n\n"
                "لطفاً مطمئن شوید شناسه کانال صحیح است و ربات در کانال ادمین است."
            )
        except Exception as e:
            logging.error(f"Generic Error checking chat member: {e}")
            error_type = type(e).__name__
            error_details = str(e)
            await query.message.reply_text(
                "❌ خطایی در بررسی عضویت شما رخ داد.\n\n"
                "**اطلاعات فنی برای رفع مشکل:**\n"
                f"نوع خطا: `{error_type}`\n"
                f"جزئیات: `{error_details}`"
            )
        finally:
            conn.close()

# --- CHANNEL MEMBER TRACKER (FOR LEAVING) ---
async def track_channel_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Only tracks when a user LEAVES the channel to deduct points."""
    if update.chat_member.chat.id != TARGET_CHANNEL_ID:
        return

    was_member = update.chat_member.old_chat_member.status in ["member", "administrator", "creator"]
    is_member = update.chat_member.new_chat_member.status in ["member", "administrator", "creator"]

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
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(ChatMemberHandler(track_channel_members, ChatMemberHandler.CHAT_MEMBER))
    
    print("Bot starting...")
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
