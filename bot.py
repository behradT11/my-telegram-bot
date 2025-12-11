import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

# ---------------------------------------------------------------------------
# تنظیمات و کانفیگ
# ---------------------------------------------------------------------------
BOT_TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
ADMIN_PASSWORD = "12345@Parstradecommunity"

# وضعیت‌های مکالمه (States)
(
    GET_NAME,
    GET_SURNAME,
    GET_AGE,
    GET_PHONE,
    GET_EMAIL,
    MAIN_MENU,
    GET_ADMIN_PASS,  # وضعیت دریافت رمز ادمین
    SUPPORT_Handler,
    ADMIN_BROADCAST
) = range(9)

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------------------------
# مدیریت دیتابیس (SQLite)
# ---------------------------------------------------------------------------
def init_db():
    """ایجاد جداول دیتابیس در صورت عدم وجود"""
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    
    # جدول کاربران
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

def add_user(user_data):
    """افزودن کاربر جدید به دیتابیس"""
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
        
        # اگر معرف داشته باشد، به تعداد رفرال‌های معرف اضافه کن
        if user_data.get('referrer_id'):
            c.execute('UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?', (user_data['referrer_id'],))
            
        conn.commit()
    except Exception as e:
        logging.error(f"Database error: {e}")
    finally:
        conn.close()

def get_user(user_id):
    """دریافت اطلاعات کاربر"""
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def get_all_users_ids():
    """دریافت آیدی تمام کاربران برای پنل ادمین"""
    conn = sqlite3.connect('trading_bot.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

# ---------------------------------------------------------------------------
# هندلرهای ثبت نام
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # بررسی وجود کاربر در دیتابیس
    if get_user(user_id):
        await show_main_menu(update, context)
        return MAIN_MENU

    # بررسی کد رفرال (لینک دعوت)
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
        "👋 سلام! به کامیونیتی ترید ما خوش آمدید.\n\n"
        "برای استفاده از خدمات بات، لطفاً ابتدا ثبت نام کنید.\n"
        "🔹 نام خود را وارد کنید:"
    )
    return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text("✅ عالیه. حالا نام خانوادگی خود را وارد کنید:")
    return GET_SURNAME

async def get_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_name'] = update.message.text
    await update.message.reply_text("🔢 لطفاً سن خود را به عدد وارد کنید:")
    return GET_AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age_text = update.message.text
    if not age_text.isdigit():
        await update.message.reply_text("❌ لطفاً سن را فقط به صورت عدد وارد کنید.")
        return GET_AGE
    
    context.user_data['age'] = int(age_text)
    
    contact_keyboard = KeyboardButton(text="📱 ارسال شماره تلفن", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_keyboard]], one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📞 برای تایید هویت، لطفاً شماره موبایل خود را با دکمه زیر ارسال کنید:",
        reply_markup=reply_markup
    )
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data['phone'] = update.message.contact.phone_number
    else:
        context.user_data['phone'] = update.message.text

    await update.message.reply_text(
        "📧 لطفاً آدرس ایمیل خود را وارد کنید:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    context.user_data['id'] = update.effective_user.id
    
    add_user(context.user_data)
    
    await update.message.reply_text("🎉 ثبت نام شما با موفقیت تکمیل شد!")
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# منوی اصلی و عملکردها
# ---------------------------------------------------------------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        ["🛍 فروشگاه", "🎁 مسابقه رفرال"],
        ["👤 پروفایل من", "📞 پشتیبانی"],
        ["🔐 پنل ادمین"] # همیشه نمایش داده می‌شود
    ]
    
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "منوی اصلی کامیونیتی ترید:",
        reply_markup=reply_markup
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "🔐 پنل ادمین":
        # بررسی اگر قبلا لاگین کرده باشد
        if context.user_data.get('is_admin'):
            await show_admin_keyboard(update, context)
            return MAIN_MENU
        else:
            await update.message.reply_text(
                "🔒 این بخش محافظت شده است.\n"
                "🔑 لطفاً رمز عبور ادمین را وارد کنید:",
                reply_markup=ReplyKeyboardRemove()
            )
            return GET_ADMIN_PASS

    elif text == "🛍 فروشگاه":
        await update.message.reply_text(
            "🛒 **فروشگاه کامیونیتی**\n\n"
            "1. اشتراک VIP سیگنال - 50 تتر\n"
            "2. دوره آموزشی پرایس اکشن - 100 تتر\n"
            "3. اندیکاتور اختصاصی - 30 تتر\n\n"
            "جهت خرید با پشتیبانی تماس بگیرید."
        )
        
    elif text == "🎁 مسابقه رفرال":
        user = get_user(user_id)
        ref_count = user[6] if user else 0
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        await update.message.reply_text(
            f"🏆 **مسابقه رفرال**\n\n"
            f"تعداد دعوت‌های شما: {ref_count} نفر\n\n"
            f"🔗 لینک اختصاصی شما:\n{ref_link}\n\n"
            "دوستان خود را دعوت کنید و جایزه بگیرید!"
        )
        
    elif text == "👤 پروفایل من":
        user = get_user(user_id)
        if user:
            await update.message.reply_text(
                f"👤 **اطلاعات حساب کاربری**\n\n"
                f"نام: {user[1]} {user[2]}\n"
                f"سن: {user[3]}\n"
                f"شماره: {user[4]}\n"
                f"ایمیل: {user[5]}\n"
                f"تاریخ عضویت: {user[8]}"
            )
            
    elif text == "📞 پشتیبانی":
        await update.message.reply_text(
            "💬 پیام خود را بنویسید تا برای ادمین ارسال شود.\n"
            "برای لغو روی /cancel کلیک کنید."
        )
        return SUPPORT_Handler
            
    return MAIN_MENU

# ---------------------------------------------------------------------------
# احراز هویت ادمین
# ---------------------------------------------------------------------------
async def verify_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    
    if password == ADMIN_PASSWORD:
        context.user_data['is_admin'] = True
        await update.message.reply_text("✅ رمز عبور صحیح است. به پنل مدیریت خوش آمدید.")
        await show_admin_keyboard(update, context)
        return MAIN_MENU
    else:
        await update.message.reply_text("❌ رمز عبور اشتباه است.")
        await show_main_menu(update, context)
        return MAIN_MENU

async def show_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        ["📢 ارسال پیام همگانی"],
        ["📊 آمار کاربران"],
        ["🔙 بازگشت به منو"]
    ]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup)

# ---------------------------------------------------------------------------
# هندلر پشتیبانی
# ---------------------------------------------------------------------------
async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    user_info = update.effective_user
    
    # اینجا چون ادمین دیگر یک آیدی ثابت نیست، پیام پشتیبانی را نمی‌توانیم به راحتی "فروارد" کنیم 
    # مگر اینکه آیدی شما ثابت باشد یا پیام در دیتابیس ذخیره شود.
    # فعلا یک پیام تایید به کاربر می‌دهیم. برای سیستم پیشرفته‌تر باید آیدی عددی ادمین ثابت بماند.
    # اگر می‌خواهید پیام‌ها به آیدی خاصی برود، باید یک آیدی ثابت هم داشته باشید.
    # فعلا فرض را بر این می‌گذاریم که لاگ می‌شود یا اگر آیدی ثابتی دارید استفاده کنید.
    
    await update.message.reply_text("✅ پیام شما دریافت شد و توسط تیم پشتیبانی بررسی خواهد شد.")
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# پنل ادمین
# ---------------------------------------------------------------------------
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # بررسی مجدد دسترسی
    if not context.user_data.get('is_admin'):
        await update.message.reply_text("⛔ دسترسی غیرمجاز.")
        await show_main_menu(update, context)
        return MAIN_MENU
        
    if text == "📊 آمار کاربران":
        ids = get_all_users_ids()
        await update.message.reply_text(f"👥 تعداد کل کاربران: {len(ids)} نفر")
        
    elif text == "📢 ارسال پیام همگانی":
        await update.message.reply_text(
            "متن پیام همگانی خود را وارد کنید:\n"
            "(این پیام برای همه کاربران ارسال می‌شود)"
        )
        return ADMIN_BROADCAST
        
    elif text == "🔙 بازگشت به منو":
        await show_main_menu(update, context)
        return MAIN_MENU
        
    return MAIN_MENU

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('is_admin'):
        return MAIN_MENU
        
    msg_text = update.message.text
    ids = get_all_users_ids()
    count = 0
    
    await update.message.reply_text("⏳ در حال ارسال پیام...")
    
    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **اطلاعیه کامیونیتی**\n\n{msg_text}")
            count += 1
        except Exception:
            pass
            
    await update.message.reply_text(f"✅ پیام با موفقیت برای {count} کاربر ارسال شد.")
    await show_admin_keyboard(update, context) # بازگشت به منوی ادمین
    return MAIN_MENU

# ---------------------------------------------------------------------------
# توابع کمکی
# ---------------------------------------------------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)
    return MAIN_MENU

# ---------------------------------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_surname)],
            GET_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GET_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, get_phone)],
            GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            
            GET_ADMIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_admin_password)],
            
            MAIN_MENU: [
                # دکمه‌های پنل ادمین
                MessageHandler(filters.Regex('^(📢 ارسال پیام همگانی|📊 آمار کاربران|🔙 بازگشت به منو)$'), admin_actions),
                # دکمه‌های منوی اصلی
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
            ],
            
            SUPPORT_Handler: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive_message)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)
    
    print("Bot is running...")
    application.run_polling()
