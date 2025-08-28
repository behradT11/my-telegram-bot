# First, run these commands in your terminal to install necessary libraries:
# pip install python-telegram-bot
# pip install --upgrade python-telegram-bot # Make sure you have the latest version

import logging
import sqlite3
import asyncio
import telegram
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, ContextTypes, ChatMemberHandler, 
    CallbackQueryHandler, MessageHandler, filters
)

# --- CONFIGURATION ---
TOKEN = "8470707180:AAE8C8WISVBZAgS9Yw1M8Y1F6WBU2FXpuBc"
TARGET_CHANNEL_ID = "@fvtraders" 
BOT_USERNAME = "FVCounter_bot"
CHANNEL_LINK = "https://t.me/fvtraders" 
ADMIN_USER_ID = 7215817555 # Your User ID has been set

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DATABASE SETUP ---
def setup_database():
    """Creates/updates the database and tables."""
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    cursor = conn.cursor()
    # Main users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            username TEXT,
            score INTEGER DEFAULT 0,
            has_joined_channel INTEGER DEFAULT 0,
            join_date DATETIME
        )
    """)
    # Banned users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    
    # Migration for older database files
    try:
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'has_joined_channel' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN has_joined_channel INTEGER DEFAULT 0")
        if 'join_date' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN join_date DATETIME")
            cursor.execute("UPDATE users SET join_date = ? WHERE join_date IS NULL", (datetime.now(),))
    except Exception as e:
        logging.error(f"Error updating database schema: {e}")

    conn.commit()
    conn.close()

# --- KEYBOARDS ---
def get_main_menu_keyboard():
    """Returns the persistent main menu keyboard."""
    keyboard = [
        [KeyboardButton("🔗 دعوت به کانال"), KeyboardButton("📊 امتیاز من")],
        [KeyboardButton("🏆 رتبه بندی"), KeyboardButton("ℹ️ راهنما")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_force_join_keyboard():
    """Returns the inline keyboard that forces users to join the channel."""
    keyboard = [
        [InlineKeyboardButton("➡️ عضویت در کانال", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ عضویت را بررسی کن", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- MENU FUNCTIONS ---
async def send_help_message(update_or_query: Update | telegram.CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the welcome help message."""
    if isinstance(update_or_query, Update):
        chat_id = update_or_query.effective_chat.id
    elif isinstance(update_or_query, telegram.CallbackQuery):
        chat_id = update_or_query.message.chat.id
    else:
        return

    help_text = (
        "🎉 خوش آمدید!\n\n"
        "**راهنمای ربات:**\n\n"
        "🔹 **دعوت به کانال:**\n"
        "لینک کانال و ربات را برای دعوت دوستانتان دریافت کنید.\n\n"
        "🔹 **امتیاز من:**\n"
        "امتیاز و لیست کاربرانی که دعوت کرده‌اید را مشاهده کنید.\n\n"
        "🔹 **رتبه بندی:**\n"
        "لیست ۱۰ کاربر برتر را مشاهده کنید.\n\n"
        "موفق باشید!"
    )
    await context.bot.send_message(chat_id=chat_id, text=help_text, parse_mode='Markdown')

async def get_my_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides the user with the channel link and their referral bot link."""
    user_id = update.effective_user.id
    referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    text = (
        "برای دعوت دوستانتان، مراحل زیر را دنبال کنید:\n\n"
        "1️⃣ **ابتدا لینک کانال را برایشان ارسال کنید:**\n"
        f"{CHANNEL_LINK}\n\n"
        "2️⃣ **سپس، این لینک ربات را بفرستید و از آنها بخواهید ربات را استارت کنند تا دعوت شما ثبت شود:**\n"
        f"`{referral_link}`"
    )
    await update.message.reply_text(text=text, parse_mode='Markdown')

async def show_my_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the user their score and referrals."""
    user_id = update.effective_user.id
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM users WHERE user_id = ?", (user_id,))
        score_result = cursor.fetchone()
        score = score_result[0] if score_result else 0
        cursor.execute("SELECT user_id, username FROM users WHERE referrer_id = ?", (user_id,))
        referrals = cursor.fetchall()
        
        message = f"امتیاز فعلی شما: *{score}*\n\n"
        if referrals:
            message += "کاربرانی که شما دعوت کرده‌اید:\n"
            for ref_id, ref_username in referrals:
                username_display = f"@{ref_username}" if ref_username else f"کاربر `{ref_id}`"
                message += f"- {username_display}\n"
        else:
            message += "شما هنوز کسی را دعوت نکرده‌اید."
        await update.message.reply_text(text=message, parse_mode='Markdown')
    finally:
        conn.close()

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the top 10 users with the highest scores."""
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, score FROM users ORDER BY score DESC LIMIT 10")
        leaderboard = cursor.fetchall()
        
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
    finally:
        conn.close()

# --- CORE BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM banned_users WHERE user_id = ?", (user.id,))
        if cursor.fetchone():
            return

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
                            chat_id=referrer_id, text=f"🔔 کاربر جدیدی ({user_mention}) از طریق لینک شما وارد ربات شد."
                        )
                except (ValueError, IndexError):
                    logging.warning(f"Invalid referral code: {context.args}")

            cursor.execute(
                "INSERT INTO users (user_id, username, referrer_id, join_date) VALUES (?, ?, ?, ?)",
                (user.id, user.username, referrer_id, datetime.now())
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
    finally:
        conn.close()

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'verify_join' button click."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT referrer_id, has_joined_channel FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if not result:
            await query.edit_message_text("خطا: اطلاعات شما یافت نشد. لطفاً ربات را با /start راه‌اندازی کنید.")
            return
            
        referrer_id, has_joined = result[0], result[1]
        
        if has_joined:
            await query.edit_message_text("شما قبلاً عضویت خود را تایید کرده‌اید.")
            await context.bot.send_message(chat_id=user_id, text="منوی اصلی:", reply_markup=get_main_menu_keyboard())
            return

        try:
            member = await context.bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
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
    
    try:
        member = await context.bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
        if member.status not in ["member", "administrator", "creator"]:
            await update.message.reply_text(
                "به نظر می‌رسد شما دیگر عضو کانال نیستید! برای استفاده از ربات، لطفاً مجدداً در کانال عضو شوید و عضویت خود را بررسی کنید.",
                reply_markup=get_force_join_keyboard()
            )
            return
    except TelegramError:
        await update.message.reply_text("خطایی در بررسی عضویت شما رخ داد. لطفاً لحظاتی بعد دوباره تلاش کنید.")
        return

    text = update.message.text
    if text == "🔗 دعوت به کانال":
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
        try:
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
        finally:
            conn.close()

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the main admin panel."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("شما اجازه دسترسی به این بخش را ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("👥 مشاهده تمام کاربران", callback_data="admin_view_users_0")],
        [InlineKeyboardButton("🚫 مدیریت کاربران مسدود", callback_data="admin_view_banned_0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("پنل مدیریت:", reply_markup=reply_markup)

async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles admin panel button clicks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id != ADMIN_USER_ID:
        await query.answer("شما اجازه دسترسی به این بخش را ندارید.", show_alert=True)
        return

    data = query.data.split('_')
    command = data[1]
    
    conn = sqlite3.connect("referrals.db", check_same_thread=False)
    try:
        cursor = conn.cursor()
        if command == "view":
            if data[2] == "users":
                page = int(data[3])
                users_per_page = 10
                offset = page * users_per_page
                
                cursor.execute("SELECT user_id, username, score FROM users ORDER BY score DESC LIMIT ? OFFSET ?", (users_per_page, offset))
                users = cursor.fetchall()
                cursor.execute("SELECT COUNT(user_id) FROM users")
                total_users = cursor.fetchone()[0]

                message = f"👥 *لیست تمام کاربران (صفحه {page + 1})*\n\n"
                keyboard = []
                if not users:
                    message += "کاربری یافت نشد."
                else:
                    for uid, uname, score in users:
                        uname_display = f"@{uname}" if uname else f"کاربر {uid}"
                        keyboard.append([InlineKeyboardButton(f"{uname_display} ({score} امتیاز)", callback_data=f"admin_user_{uid}")])
                
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_view_users_{page - 1}"))
                if (page + 1) * users_per_page < total_users:
                    nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_view_users_{page + 1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

            elif data[2] == "banned":
                page = int(data[3])
                users_per_page = 10
                offset = page * users_per_page
                
                cursor.execute("SELECT user_id FROM banned_users LIMIT ? OFFSET ?", (users_per_page, offset))
                banned_users = cursor.fetchall()
                cursor.execute("SELECT COUNT(user_id) FROM banned_users")
                total_banned = cursor.fetchone()[0]

                message = f"🚫 *لیست کاربران مسدود (صفحه {page + 1})*\n\n"
                keyboard = []
                if not banned_users:
                    message += "هیچ کاربر مسدودی یافت نشد."
                else:
                    for (uid,) in banned_users:
                        keyboard.append([InlineKeyboardButton(f"کاربر {uid}", callback_data=f"admin_banned_user_{uid}")])
                
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_view_banned_{page - 1}"))
                if (page + 1) * users_per_page < total_banned:
                    nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_view_banned_{page + 1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                keyboard.append([InlineKeyboardButton("⬅️ بازگشت به پنل", callback_data="admin_back_main")])
                await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif command == "user":
            target_user_id = int(data[2])
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            target_user = cursor.fetchone()
            
            if not target_user:
                await query.edit_message_text("کاربر یافت نشد.")
                return

            cursor.execute("SELECT user_id, username, join_date FROM users WHERE referrer_id = ?", (target_user_id,))
            referrals = cursor.fetchall()

            uname = target_user[2] or "ندارد"
            score = target_user[3]
            join_date_str = target_user[5]
            
            join_date = "نامشخص"
            if join_date_str:
                try:
                    join_date = datetime.strptime(join_date_str.split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
                except (ValueError, TypeError):
                    pass

            message = (
                f"👤 **جزئیات کاربر:** `@{uname}` (ID: `{target_user_id}`)\n"
                f"🗓 **تاریخ عضویت:** {join_date}\n"
                f"⭐️ **امتیاز:** {score}\n\n"
                f"👥 **کاربران دعوت شده ({len(referrals)} نفر):**\n"
            )
            if referrals:
                for ref_id, ref_uname, ref_join_date_str in referrals:
                    ref_uname_display = f"@{ref_uname}" if ref_uname else f"کاربر {ref_id}"
                    ref_join_date = "نامشخص"
                    if ref_join_date_str:
                        try:
                            ref_join_date = datetime.strptime(ref_join_date_str.split('.')[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
                        except (ValueError, TypeError):
                            pass
                    message += f"- {ref_uname_display} (در تاریخ: {ref_join_date})\n"
            else:
                message += "هنوز کسی را دعوت نکرده است."

            keyboard = [
                [
                    InlineKeyboardButton("🗑 حذف", callback_data=f"admin_delete_{target_user_id}"),
                    InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"admin_ban_{target_user_id}")
                ],
                [InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_view_users_0")]
            ]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif command == "banned":
            target_user_id = int(data[3])
            message = f"کاربر `{target_user_id}` مسدود شده است."
            keyboard = [
                [InlineKeyboardButton("✅ رفع مسدودی", callback_data=f"admin_unban_{target_user_id}")],
                [InlineKeyboardButton("⬅️ بازگشت به لیست مسدود", callback_data="admin_view_banned_0")]
            ]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif command == "delete":
            target_user_id = int(data[2])
            cursor.execute("DELETE FROM users WHERE user_id = ?", (target_user_id,))
            conn.commit()
            await query.edit_message_text(f"✅ کاربر `{target_user_id}` با موفقیت حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_view_users_0")]]), parse_mode='Markdown')

        elif command == "ban":
            target_user_id = int(data[2])
            cursor.execute("DELETE FROM users WHERE user_id = ?", (target_user_id,))
            cursor.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (target_user_id,))
            conn.commit()
            await query.edit_message_text(f"🚫 کاربر `{target_user_id}` با موفقیت مسدود و حذف شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_view_users_0")]]), parse_mode='Markdown')

        elif command == "unban":
            target_user_id = int(data[2])
            cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (target_user_id,))
            conn.commit()
            await query.edit_message_text(f"✅ کاربر `{target_user_id}` با موفقیت از مسدودیت خارج شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت به لیست مسدود", callback_data="admin_view_banned_0")]]), parse_mode='Markdown')

        elif command == "back" and data[2] == "main":
            keyboard = [
                [InlineKeyboardButton("👥 مشاهده تمام کاربران", callback_data="admin_view_users_0")],
                [InlineKeyboardButton("🚫 مدیریت کاربران مسدود", callback_data="admin_view_banned_0")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("پنل مدیریت:", reply_markup=reply_markup)
    finally:
        conn.close()

# --- MAIN FUNCTION ---
def main() -> None:
    """Sets up and runs the bot."""
    logging.info(f"Using python-telegram-bot version: {telegram.__version__}")
    setup_database()
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^admin_"))
    
    application.add_handler(ChatMemberHandler(track_channel_members, ChatMemberHandler.CHAT_MEMBER))
    
    print("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
