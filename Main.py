import logging
import sqlite3
import asyncio
import threading
import os
from datetime import datetime
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telegram.error import BadRequest

# --- تنظیمات امنیتی و کانال ---
TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
# رمز عبور مدیریت (حتما این را حفظ کنید یا تغییر دهید)
ADMIN_PASSWORD = "ParsTrade@2025!Secure#Admin" 
CHANNEL_ID = "@ParsTradeCommunity"
GROUP_ID = "@ParsTradeGP"

# --- سرور Flask (برای روشن ماندن در Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Pars Trade Bot V5 is Running..."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- مراحل Conversation ---
(
    ADMIN_AUTH,       # مرحله چک کردن رمز
    ADMIN_PANEL,      # منوی اصلی ادمین
    ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
    MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
    MANAGE_USER_INPUT, MANAGE_USER_ACTION,
    EDIT_TEXT_SELECT, EDIT_TEXT_INPUT,
    BROADCAST_MESSAGE
) = range(14)

# --- دیتابیس و متون پیش‌فرض حرفه‌ای ---
def init_db():
    conn = sqlite3.connect("parstrade_v5.db")
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 full_name TEXT,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_confirmed INTEGER DEFAULT 0,
                 join_date TEXT
                 )''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (
                 key TEXT PRIMARY KEY,
                 content TEXT
                 )''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER,
                 part INTEGER,
                 req_refs INTEGER,
                 content_type TEXT,
                 file_id TEXT,
                 caption TEXT
                 )''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS lives (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT,
                 link TEXT,
                 file_id TEXT,
                 date_recorded TEXT,
                 is_active INTEGER DEFAULT 0
                 )''')

    # متن‌های پیش‌فرض زیبا و طولانی
    welcome_msg = (
        "🌺 **درود بر شما {name} عزیز، به خانواده بزرگ پارس ترید خوش آمدید!** 🌺\n\n"
        "ما در **Pars Trade Community** مفتخریم که شما را در مسیر پرچالش اما شیرین معامله‌گری همراهی کنیم.\n"
        "این ربات دروازه ورود شما به دنیایی از آموزش‌های تخصصی، تحلیل‌های ناب و ابزارهای حرفه‌ای ترید است.\n\n"
        "💎 **خدمات ما:**\n"
        "├ 🎓 دوره‌های آموزشی VIP (صفر تا صد)\n"
        "├ 🔴 لایو تریدهای تخصصی و پرسود\n"
        "├ 🏆 تورنمنت‌های ترید با جوایز نفیس\n"
        "└ 👥 پشتیبانی و منتورینگ اختصاصی\n\n"
        "👇 برای شروع، از منوی زیر استفاده کنید:"
    )

    about_msg = (
        "🏢 **درباره پارس ترید (Pars Trade)**\n\n"
        "ما یک تیم متشکل از معامله‌گران حرفه‌ای و تحلیل‌گران بازارهای مالی هستیم که با هدف ارتقای سطح دانش تریدرهای ایرانی گرد هم آمده‌ایم.\n\n"
        "🎯 **رسالت ما:**\n"
        "پرورش معامله‌گرانی منضبط، صبور و سودده است که بتوانند در بازارهای پرنوسان فارکس، کریپتو و ... به استقلال مالی برسند.\n\n"
        "✨ **چرا پارس ترید؟**\n"
        "چون ما فقط سیگنال نمی‌دهیم؛ ما ماهیگیری را به شما می‌آموزیم. آموزش‌های ما حاصل سال‌ها تجربه و ضرر و سود در بازار واقعی است.\n\n"
        "🌐 وب‌سایت ما: pars-trade.com\n"
        "🆔 کانال تلگرام: @ParsTradeCommunity"
    )

    rules_msg = (
        "⚖️ **قوانین و مقررات استفاده از ربات**\n\n"
        "1️⃣ **عضویت اجباری:** استفاده از تمامی خدمات ربات منوط به عضویت دائمی در کانال تلگرام ماست.\n"
        "2️⃣ **صداقت در رفرال:** کاربرانی که با اکانت‌های فیک اقدام به زیرمجموعه‌گیری کنند، توسط سیستم هوشمند شناسایی و مسدود خواهند شد.\n"
        "3️⃣ **تکریم اعضا:** هرگونه بی‌احترامی در گروه پشتیبانی منجر به قطع دسترسی خواهد شد.\n\n"
        "با تشکر از همکاری شما 🙏"
    )

    defaults = {
        "welcome": welcome_msg,
        "about": about_msg,
        "rules": rules_msg,
        "support": "👨‍💻 **پشتیبانی اختصاصی پارس ترید**\n\nبرای رفع مشکلات فنی یا سوالات آموزشی، لطفاً به آیدی زیر پیام دهید:\n📩 @Behrise\n\n(ساعات پاسخگویی: ۱۰ صبح تا ۱۰ شب)"
    }
    
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade_v5.db")

def get_text(key, **kwargs):
    conn = get_db()
    res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone()
    conn.close()
    text = res[0] if res else ""
    try: return text.format(**kwargs)
    except: return text

# --- تابع سخت‌گیرانه بررسی عضویت ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        # بررسی عضویت کانال
        cm = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if cm.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED]:
            return False
        return True
    except BadRequest as e:
        # اگر این ارور بیاید یعنی بات در کانال ادمین نیست!
        logger.error(f"❌ ERROR: Bot is NOT Admin in {CHANNEL_ID}. Details: {e}")
        # در حالت سخت‌گیرانه، اگر نتوانیم چک کنیم، اجازه ورود نمی‌دهیم!
        return False
    except Exception as e:
        logger.error(f"General Check Error: {e}")
        return False

async def force_join_message(update: Update):
    kb = [
        [InlineKeyboardButton("📢 عضویت در کانال (الزامی)", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")]
    ]
    kb.append([InlineKeyboardButton("✅ عضو شدم و ادامه", callback_data="check_join")])
    
    msg = (
        "⛔️ **دسترسی غیرمجاز!**\n\n"
        "کاربر گرامی، برای استفاده از امکانات رایگان و VIP ربات **پارس ترید**، "
        "عضویت در کانال رسمی ما الزامی است.\n\n"
        "لطفاً ابتدا عضو شوید و سپس دکمه «عضو شدم» را بزنید. 👇"
    )
    
    if update.callback_query:
        # جلوگیری از خطای ویرایش تکراری
        try:
            await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        except: pass
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- کیبورد اصلی کاربر (بدون پنل ادمین) ---
def main_menu_keyboard():
    buttons = [
        ["🎓 آموزش (VIP)", "🔴 لایو ترید"],
        ["🏆 تورنمنت", "👤 پروفایل من"],
        ["ℹ️ درباره ما", "📞 پشتیبانی"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

# --- هندلر استارت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    conn = get_db()
    
    exist = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not exist:
        ref_id = int(args[0]) if (args and args[0].isdigit() and int(args[0]) != user.id) else None
        conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?, ?, ?, ?, ?)",
                     (user.id, user.full_name, user.username, ref_id, datetime.now().strftime("%Y-%m-%d")))
        if ref_id:
            try: await context.bot.send_message(ref_id, f"🎉 **تبریک!**\nکاربر {user.full_name} با لینک شما به خانواده پارس ترید پیوست.\n(پس از تایید فعالیت، امتیاز محاسبه می‌شود)")
            except: pass
        conn.commit()
    conn.close()

    if not await check_membership(update, context):
        await force_join_message(update)
        return

    txt = get_text("welcome", name=user.first_name)
    await update.message.reply_text(txt, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)

# --- هندلر پیام‌های کاربر ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    # قفل سخت‌گیرانه روی تمام پیام‌ها
    if not await check_membership(update, context):
        await force_join_message(update)
        return

    if text == "👤 پروفایل من":
        conn = get_db()
        data = conn.execute("SELECT referrals_confirmed, join_date FROM users WHERE user_id=?", (user.id,)).fetchone()
        conn.close()
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={user.id}"
        
        msg = (
            f"👤 **پروفایل کاربری شما**\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"📛 نام: **{user.full_name}**\n"
            f"🆔 شناسه عددی: `{user.id}`\n"
            f"📅 تاریخ عضویت: {data[1]}\n"
            f"📊 **تعداد زیرمجموعه تایید شده:** {data[0]} نفر\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🔗 **لینک دعوت اختصاصی شما:**\n`{link}`\n\n"
            f"💡 *با اشتراک‌گذاری این لینک، دوستانتان را دعوت کنید و دسترسی VIP بگیرید.*"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "🎓 آموزش (VIP)":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        if not days:
            await update.message.reply_text("😔 **متاسفانه هنوز آموزشی بارگذاری نشده است.**\nلطفاً بعداً تلاش کنید.")
            return
        kb = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"📅 روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row)==2: kb.append(row); row=[]
        if row: kb.append(row)
        await update.message.reply_text("🎓 **آکادمی آموزش پارس ترید**\n\nبرای دسترسی به محتوا، روز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🔴 لایو ترید":
        conn = get_db()
        active = conn.execute("SELECT title, link FROM lives WHERE is_active=1").fetchone()
        archives = conn.execute("SELECT id, title, date_recorded FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        
        msg = "🔴 **اتاق لایو ترید (Live Trading Room)**\n\n"
        kb = []
        if active:
            msg += f"🚨 **لایو زنده در حال برگزاری است!**\n📌 عنوان: {active[0]}\n\nجهت ورود روی دکمه زیر کلیک کنید 👇"
            kb.append([InlineKeyboardButton("🚀 ورود به لایو", url=active[1])])
        else:
            msg += "😴 در حال حاضر سشن لایو فعالی نداریم.\nزمان لایوهای بعدی در کانال اعلام می‌شود.\n"
            
        msg += "\n🎬 **آرشیو لایوهای ضبط شده:**"
        for a in archives: kb.append([InlineKeyboardButton(f"🎥 {a[1]} ({a[2]})", callback_data=f"glive_{a[0]}")])
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif text == "🏆 تورنمنت":
        await update.message.reply_text("🏆 **تالار افتخارات و تورنمنت‌ها**\n\n🔥 تورنمنت بزرگ پارس ترید به زودی آغاز می‌شود...\nمنتظر خبرهای داغ باشید!")

    elif text == "ℹ️ درباره ما":
        await update.message.reply_text(get_text("about"), parse_mode=ParseMode.MARKDOWN)
    elif text == "📞 پشتیبانی":
        await update.message.reply_text(get_text("support"), parse_mode=ParseMode.MARKDOWN)

# --- کال‌بک هندلر ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    if d == "check_join":
        if await check_membership(update, context):
            await q.answer("✅ عضویت شما تایید شد. خوش آمدید!", show_alert=True)
            await q.message.delete()
            txt = get_text("welcome", name=q.from_user.first_name)
            await q.message.reply_text(txt, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
        else:
            await q.answer("❌ خطا: سیستم هنوز عضویت شما را تایید نکرده است.\nمطمئن شوید که در کانال عضو شده‌اید.", show_alert=True)
        return

    # چک کردن مجدد برای بقیه دکمه‌ها
    if not await check_membership(update, context):
        await q.answer("⛔️ دسترسی محدود! ابتدا عضو کانال شوید.", show_alert=True)
        return

    if d.startswith("day_"):
        day = d.split("_")[1]
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        user_refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
        conn.close()
        
        kb = []
        for p in parts:
            if user_refs >= p[2]:
                kb.append([InlineKeyboardButton(f"✅ مشاهده قسمت {p[1]}", callback_data=f"gcourse_{p[0]}")])
            else:
                kb.append([InlineKeyboardButton(f"🔒 قسمت {p[1]} (نیاز: {p[2]} دعوت)", callback_data=f"alert_{p[2]}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="none")]) # دکمه بازگشت ساده (یا هندل شود)
        
        await q.message.edit_text(f"📚 **محتوای آموزشی - روز {day}**\n\n📊 تعداد دعوت‌های تایید شده شما: **{user_refs}** نفر", 
                                  reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif d.startswith("alert_"):
        req = d.split('_')[1]
        await q.answer(f"⛔️ قفل است!\nبرای باز شدن این قسمت باید {req} نفر را با لینک اختصاصی خود دعوت کنید.", show_alert=True)

    elif d.startswith("gcourse_"):
        cid = d.split("_")[1]
        conn = get_db()
        c = conn.execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (cid,)).fetchone()
        conn.close()
        if c:
            try:
                if c[0]=='text': await q.message.reply_text(c[2], parse_mode=ParseMode.MARKDOWN)
                elif c[0]=='video': await q.message.reply_video(c[1], caption=c[2], parse_mode=ParseMode.MARKDOWN)
                elif c[0]=='photo': await q.message.reply_photo(c[1], caption=c[2], parse_mode=ParseMode.MARKDOWN)
                elif c[0]=='document': await q.message.reply_document(c[1], caption=c[2], parse_mode=ParseMode.MARKDOWN)
            except:
                await q.answer("خطا در ارسال فایل. ممکن است فایل حذف شده باشد.", show_alert=True)
        await q.answer()

    elif d.startswith("glive_"):
        lid = d.split("_")[1]
        conn = get_db()
        l = conn.execute("SELECT file_id, title FROM lives WHERE id=?", (lid,)).fetchone()
        conn.close()
        if l: await q.message.reply_video(l[0], caption=f"🎥 **{l[1]}**", parse_mode=ParseMode.MARKDOWN)
        await q.answer()

# --- سیستم ادمین (رمزدار) ---
async def admin_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔒 **سیستم امنیتی پارس ترید**\n\nلطفاً رمز عبور مدیریت را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return ADMIN_AUTH

async def admin_auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    if password == ADMIN_PASSWORD:
        await admin_show_panel(update, context)
        return ADMIN_PANEL
    else:
        await update.message.reply_text("❌ **رمز عبور اشتباه است!**\nدسترسی غیرمجاز. دوباره تلاش کنید یا /cancel را بزنید.")
        return ADMIN_AUTH

async def admin_show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        ["➕ افزودن آموزش", "🔴 مدیریت لایو"],
        ["👥 مدیریت کاربر", "📝 ویرایش متن‌ها"],
        ["📢 پیام همگانی", "❌ خروج از مدیریت"]
    ]
    await update.message.reply_text("✅ **هویت تایید شد.**\nبه پنل مدیریت خوش آمدید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "❌ خروج از مدیریت":
        await update.message.reply_text("👋 خروج موفق.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    elif t == "➕ افزودن آموزش":
        await update.message.reply_text("📅 شماره روز آموزشی (مثلاً 1):")
        return ADD_COURSE_DAY
    elif t == "👥 مدیریت کاربر":
        await update.message.reply_text("🆔 آیدی عددی کاربر مورد نظر را وارد کنید:")
        return MANAGE_USER_INPUT
    elif t == "🔴 مدیریت لایو":
        kb = [["تنظیم لینک زنده", "آپلود آرشیو"], ["غیرفعال کردن لایو", "بازگشت"]]
        await update.message.reply_text("تنظیمات لایو:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return MANAGE_LIVE_MENU
    elif t == "📝 ویرایش متن‌ها":
        kb = [["welcome", "about"], ["rules", "support"], ["بازگشت"]]
        await update.message.reply_text("کدام متن ویرایش شود؟", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return EDIT_TEXT_SELECT
    elif t == "📢 پیام همگانی":
        await update.message.reply_text("📝 پیام خود را برای ارسال به تمام اعضا بنویسید (یا فوروارد کنید):")
        return BROADCAST_MESSAGE
    
    return ADMIN_PANEL

# --- هندلرهای عملیات ادمین ---
# افزودن آموزش
async def add_c_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['d'] = update.message.text
    await update.message.reply_text("🔢 شماره قسمت:")
    return ADD_COURSE_PART
async def add_c_part(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p'] = update.message.text
    await update.message.reply_text("👥 تعداد رفرال مورد نیاز (عدد):")
    return ADD_COURSE_REFS
async def add_c_refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r'] = update.message.text
    await update.message.reply_text("📥 فایل آموزش (ویدیو/عکس/پی دی اف) یا متن خالی را بفرستید (کپشن هم پشتیبانی می‌شود):")
    return ADD_COURSE_CONTENT
async def add_c_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    type, fid = 'text', None
    cap = update.message.caption or update.message.text or ""
    if update.message.video: type, fid = 'video', update.message.video.file_id
    elif update.message.photo: type, fid = 'photo', update.message.photo[-1].file_id
    elif update.message.document: type, fid = 'document', update.message.document.file_id
    
    conn = get_db()
    conn.execute("INSERT INTO courses (day, part, req_refs, content_type, file_id, caption) VALUES (?,?,?,?,?,?)",
                 (context.user_data['d'], context.user_data['p'], context.user_data['r'], type, fid, cap))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ آموزش با موفقیت ثبت شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL

# مدیریت کاربر
async def m_user_in(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_show_panel(update, context)
    uid = update.message.text
    if not uid.isdigit(): return await update.message.reply_text("عدد وارد کنید.")
    context.user_data['uid'] = uid
    conn = get_db()
    u = conn.execute("SELECT full_name, referrals_confirmed FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not u: return await update.message.reply_text("یافت نشد.")
    await update.message.reply_text(f"👤 {u[0]}\n📊 رفرال: {u[1]}", reply_markup=ReplyKeyboardMarkup([["➕ تایید (افزایش)", "➖ رد (کاهش)"], ["بازگشت"]], resize_keyboard=True))
    return MANAGE_USER_ACTION
async def m_user_act(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "بازگشت": return await admin_show_panel(update, context)
    conn = get_db()
    if "افزایش" in update.message.text:
        conn.execute("UPDATE users SET referrals_confirmed=referrals_confirmed+1 WHERE user_id=?", (context.user_data['uid'],))
    elif "کاهش" in update.message.text:
        conn.execute("UPDATE users SET referrals_confirmed=max(0, referrals_confirmed-1) WHERE user_id=?", (context.user_data['uid'],))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ انجام شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL

# ویرایش متن
async def edit_txt_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_show_panel(update, context)
    context.user_data['k'] = update.message.text
    await update.message.reply_text("✍️ متن جدید را وارد کنید:")
    return EDIT_TEXT_INPUT
async def edit_txt_inp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO dynamic_texts (key, content) VALUES (?, ?)", (context.user_data['k'], update.message.text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ متن بروزرسانی شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL

# لایو
async def m_live_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t=="بازگشت": return await admin_show_panel(update, context)
    if t=="غیرفعال کردن لایو":
        conn = get_db(); conn.execute("UPDATE lives SET is_active=0"); conn.commit(); conn.close()
        await update.message.reply_text("لایو بسته شد.")
        return await admin_show_panel(update, context)
    if t=="تنظیم لینک زنده":
        await update.message.reply_text("فرمت:\nعنوان لایو\nلینک لایو")
        return SET_LIVE_LINK
    if t=="آپلود آرشیو":
        await update.message.reply_text("ویدیو را بفرستید:")
        return UPLOAD_LIVE_FILE
    return MANAGE_LIVE_MENU
async def set_live_l(update: Update, context: ContextTypes.DEFAULT_TYPE):
    l = update.message.text.split('\n')
    conn = get_db(); conn.execute("UPDATE lives SET is_active=0")
    conn.execute("INSERT INTO lives (title, link, is_active) VALUES (?,?,1)", (l[0], l[1]))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ لایو فعال شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL
async def up_live_f(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute("INSERT INTO lives (title, file_id, date_recorded, is_active) VALUES (?,?,?,0)",
                 (update.message.caption or "Live", update.message.video.file_id, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ آرشیو شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL

# برودکست
async def broad_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="بازگشت": return await admin_show_panel(update, context)
    conn = get_db(); users = conn.execute("SELECT user_id FROM users").fetchall(); conn.close()
    await update.message.reply_text(f"⏳ در حال ارسال به {len(users)} نفر...")
    for u in users:
        try: await update.message.copy(u[0]); await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text("✅ تمام شد.")
    await admin_show_panel(update, context)
    return ADMIN_PANEL

def main():
    init_db()
    keep_alive()
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start_command)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth_check)],
            ADMIN_PANEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)],
            ADD_COURSE_DAY: [MessageHandler(filters.TEXT, add_c_day)],
            ADD_COURSE_PART: [MessageHandler(filters.TEXT, add_c_part)],
            ADD_COURSE_REFS: [MessageHandler(filters.TEXT, add_c_refs)],
            ADD_COURSE_CONTENT: [MessageHandler(filters.ALL, add_c_content)],
            MANAGE_USER_INPUT: [MessageHandler(filters.TEXT, m_user_in)],
            MANAGE_USER_ACTION: [MessageHandler(filters.TEXT, m_user_act)],
            EDIT_TEXT_SELECT: [MessageHandler(filters.TEXT, edit_txt_sel)],
            EDIT_TEXT_INPUT: [MessageHandler(filters.TEXT, edit_txt_inp)],
            MANAGE_LIVE_MENU: [MessageHandler(filters.TEXT, m_live_menu)],
            SET_LIVE_LINK: [MessageHandler(filters.TEXT, set_live_l)],
            UPLOAD_LIVE_FILE: [MessageHandler(filters.VIDEO, up_live_f)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL, broad_msg)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("لغو شد.", reply_markup=main_menu_keyboard()))]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Pars Trade Bot V5 Started...")
    app.run_polling()

if __name__ == "__main__":
    main()

