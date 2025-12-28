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

# --- تنظیمات حیاتی ---
TOKEN = "8582244459:AAEzfJr0b699OTJ9x4DS00bdG6CTFxIXDkA"
ADMIN_PASSWORD = "ParsTrade@2025!Secure#Admin"

# ⚠️ نکته مهم: اگر با آیدی @ کار نکرد، باید آیدی عددی کانال را بگذارید (که با -100 شروع می‌شود)
# برای پیدا کردن آیدی عددی، یک پیام از کانال به ربات @userinfobot فوروارد کنید.
CHANNEL_ID = "@ParsTradeCommunity" 
OWNER_ID = 6735282633  # آیدی شما (برای ورود بدون چک کردن عضویت)

# --- سرور Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Pars Trade Bot V6 is Running..."

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

# --- مراحل ---
(
    ADMIN_AUTH, ADMIN_PANEL,
    ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
    MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
    MANAGE_USER_INPUT, MANAGE_USER_ACTION,
    EDIT_TEXT_SELECT, EDIT_TEXT_INPUT,
    BROADCAST_MESSAGE
) = range(14)

# --- دیتابیس ---
def init_db():
    conn = sqlite3.connect("parstrade_v6.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 full_name TEXT,
                 username TEXT,
                 referrer_id INTEGER,
                 referrals_confirmed INTEGER DEFAULT 0,
                 join_date TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (key TEXT PRIMARY KEY, content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 day INTEGER, part INTEGER, req_refs INTEGER,
                 content_type TEXT, file_id TEXT, caption TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lives (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 title TEXT, link TEXT, file_id TEXT,
                 date_recorded TEXT, is_active INTEGER DEFAULT 0)''')

    # متون پیش‌فرض
    welcome_msg = (
        "🌺 **درود بر شما {name} عزیز، به خانواده بزرگ پارس ترید خوش آمدید!** 🌺\n\n"
        "ما در **Pars Trade Community** مفتخریم که شما را همراهی کنیم.\n"
        "برای دسترسی به آموزش‌ها و لایو ترید، از دکمه‌های زیر استفاده کنید:"
    )
    defaults = {
        "welcome": welcome_msg,
        "about": "🏢 **درباره پارس ترید**\nتیم ما متشکل از تریدرهای حرفه‌ای فارکس است...",
        "rules": "⚖️ **قوانین:**\n1. عضویت در کانال الزامی است.",
        "support": "👨‍💻 **پشتیبانی:**\nآیدی: @Behrise"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("parstrade_v6.db")

def get_text(key, **kwargs):
    conn = get_db()
    res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone()
    conn.close()
    text = res[0] if res else ""
    try: return text.format(**kwargs)
    except: return text

# --- تابع اصلاح شده بررسی عضویت (FIXED) ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. بای‌پس مالک (شما همیشه رد می‌شوید)
    if user_id == OWNER_ID:
        return True

    try:
        # دریافت وضعیت کاربر از کانال
        cm = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        
        # لاگ کردن وضعیت برای دیباگ (در کنسول رندر دیده می‌شود)
        print(f"DEBUG: User {user_id} Status in {CHANNEL_ID} is: {cm.status}")

        # لیست وضعیت‌های مجاز (Creator برای سازنده کانال است)
        VALID_STATUS = [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
        
        if cm.status in VALID_STATUS:
            return True
        else:
            return False

    except BadRequest as e:
        # اگر بات ادمین نباشد یا آیدی کانال اشتباه باشد این ارور می‌آید
        print(f"CRITICAL ERROR in check_membership: {e}")
        logger.error(f"Bot failed to check member status. Ensure Bot is Admin in {CHANNEL_ID}")
        return False
    except Exception as e:
        print(f"General Error: {e}")
        return False

async def force_join_message(update: Update):
    # پاک کردن @ از آیدی برای لینک
    clean_id = CHANNEL_ID.replace("@", "") if "@" in CHANNEL_ID else "ParsTradeCommunity" # فال‌بک
    
    kb = [
        [InlineKeyboardButton("📢 عضویت در کانال (الزامی)", url=f"https://t.me/{clean_id}")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
    ]
    msg = "⛔️ **دسترسی محدود!**\n\nبرای استفاده از ربات، عضویت در کانال الزامی است."
    
    if update.callback_query:
        try: await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        except: pass
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- منوی اصلی ---
def main_menu_keyboard():
    buttons = [["🎓 آموزش (VIP)", "🔴 لایو ترید"], ["🏆 تورنمنت", "👤 پروفایل من"], ["ℹ️ درباره ما", "📞 پشتیبانی"]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    if not conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone():
        args = context.args
        ref = int(args[0]) if (args and args[0].isdigit() and int(args[0])!=user.id) else None
        conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?,?,?,?,?)",
                     (user.id, user.full_name, user.username, ref, datetime.now().strftime("%Y-%m-%d")))
        if ref:
            try: await context.bot.send_message(ref, f"🎉 {user.full_name} با لینک شما وارد شد.")
            except: pass
        conn.commit()
    conn.close()

    if not await check_membership(update, context):
        await force_join_message(update)
        return

    await update.message.reply_text(get_text("welcome", name=user.first_name), reply_markup=main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update, context):
        await force_join_message(update)
        return
    
    t = update.message.text
    u = update.effective_user
    
    if t == "👤 پروفایل من":
        conn = get_db()
        d = conn.execute("SELECT referrals_confirmed, join_date FROM users WHERE user_id=?", (u.id,)).fetchone()
        conn.close()
        link = f"https://t.me/{context.bot.username}?start={u.id}"
        await update.message.reply_text(f"👤 **پروفایل**\n🆔 `{u.id}`\n📊 دعوت‌های تایید شده: {d[0]}\n🔗 `{link}`", parse_mode=ParseMode.MARKDOWN)
        
    elif t == "🎓 آموزش (VIP)":
        conn = get_db()
        days = conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall()
        conn.close()
        if not days: return await update.message.reply_text("آموزشی وجود ندارد.")
        kb = []
        row = []
        for d in days:
            row.append(InlineKeyboardButton(f"📅 روز {d[0]}", callback_data=f"day_{d[0]}"))
            if len(row)==2: kb.append(row); row=[]
        if row: kb.append(row)
        await update.message.reply_text("📚 انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))

    elif t == "🔴 لایو ترید":
        conn = get_db()
        act = conn.execute("SELECT title, link FROM lives WHERE is_active=1").fetchone()
        arc = conn.execute("SELECT id, title FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        msg = "🔴 **لایو ترید**\n"
        kb = []
        if act: 
            msg += f"\n🔥 **در حال برگزاری:** {act[0]}"
            kb.append([InlineKeyboardButton("ورود", url=act[1])])
        else: msg += "\nلایو فعالی نیست."
        msg += "\n\n📂 آرشیو:"
        for a in arc: kb.append([InlineKeyboardButton(f"📼 {a[1]}", callback_data=f"glive_{a[0]}")])
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        
    elif t == "🏆 تورنمنت": await update.message.reply_text("به زودی...")
    elif t == "ℹ️ درباره ما": await update.message.reply_text(get_text("about"), parse_mode=ParseMode.MARKDOWN)
    elif t == "📞 پشتیبانی": await update.message.reply_text(get_text("support"), parse_mode=ParseMode.MARKDOWN)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    if d == "check_join":
        if await check_membership(update, context):
            await q.answer("✅ تایید شد!")
            await q.message.delete()
            await q.message.reply_text(get_text("welcome", name=q.from_user.first_name), reply_markup=main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
        else:
            await q.answer("❌ هنوز عضو نیستید (یا ربات ادمین نیست).", show_alert=True)
        return

    if not await check_membership(update, context):
        await q.answer("عضو کانال شوید!", show_alert=True)
        return

    if d.startswith("day_"):
        day = d.split("_")[1]
        conn = get_db()
        parts = conn.execute("SELECT id, part, req_refs FROM courses WHERE day=? ORDER BY part", (day,)).fetchall()
        refs = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
        conn.close()
        kb = []
        for p in parts:
            if refs >= p[2]: kb.append([InlineKeyboardButton(f"✅ قسمت {p[1]}", callback_data=f"gc_{p[0]}")])
            else: kb.append([InlineKeyboardButton(f"🔒 قسمت {p[1]} (نیاز: {p[2]})", callback_data=f"al_{p[2]}")])
        await q.message.edit_text(f"روز {day} - دعوت‌های شما: {refs}", reply_markup=InlineKeyboardMarkup(kb))
        
    elif d.startswith("al_"): await q.answer(f"نیاز به {d.split('_')[1]} دعوت دارید.", show_alert=True)
    elif d.startswith("glive_"):
        l = get_db().execute("SELECT file_id, title FROM lives WHERE id=?", (d.split("_")[1],)).fetchone()
        if l: await q.message.reply_video(l[0], caption=l[1])
        await q.answer()
    elif d.startswith("gc_"):
        c = get_db().execute("SELECT content_type, file_id, caption FROM courses WHERE id=?", (d.split("_")[1],)).fetchone()
        if c:
            if c[0]=='text': await q.message.reply_text(c[2])
            elif c[0]=='video': await q.message.reply_video(c[1], caption=c[2])
            elif c[0]=='photo': await q.message.reply_photo(c[1], caption=c[2])
            elif c[0]=='document': await q.message.reply_document(c[1], caption=c[2])
        await q.answer()

# --- ادمین ---
async def admin_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("رمز:", reply_markup=ReplyKeyboardRemove())
    return ADMIN_AUTH
async def admin_auth(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == ADMIN_PASSWORD:
        await admin_panel(u, c)
        return ADMIN_PANEL
    await u.message.reply_text("غلط.")
    return ADMIN_AUTH
async def admin_panel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    kb = [["➕ آموزش", "🔴 لایو"], ["👥 کاربر", "📝 متن"], ["📢 پیام همگانی", "❌ خروج"]]
    await u.message.reply_text("پنل:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
async def admin_dispatch(u: Update, c: ContextTypes.DEFAULT_TYPE):
    t = u.message.text
    if t=="❌ خروج": await u.message.reply_text("بای", reply_markup=main_menu_keyboard()); return ConversationHandler.END
    elif t=="➕ آموزش": await u.message.reply_text("روز:"); return ADD_COURSE_DAY
    elif t=="👥 کاربر": await u.message.reply_text("آیدی:"); return MANAGE_USER_INPUT
    elif t=="🔴 لایو": await u.message.reply_text("انتخاب:", reply_markup=ReplyKeyboardMarkup([["تنظیم لینک", "آپلود آرشیو"],["بازگشت"]],resize_keyboard=True)); return MANAGE_LIVE_MENU
    elif t=="📝 متن": await u.message.reply_text("welcom/about/rules:", reply_markup=ReplyKeyboardMarkup([["welcome","about","rules"],["بازگشت"]],resize_keyboard=True)); return EDIT_TEXT_SELECT
    elif t=="📢 پیام همگانی": await u.message.reply_text("پیام:"); return BROADCAST_MESSAGE
    return ADMIN_PANEL

# توابع خلاصه شده ادمین (منطق تکراری)
async def add_c_d(u,c): c.user_data['d']=u.message.text; await u.message.reply_text("قسمت:"); return ADD_COURSE_PART
async def add_c_p(u,c): c.user_data['p']=u.message.text; await u.message.reply_text("رفرال:"); return ADD_COURSE_REFS
async def add_c_r(u,c): c.user_data['r']=u.message.text; await u.message.reply_text("فایل:"); return ADD_COURSE_CONTENT
async def add_c_c(u,c):
    tp, fid = 'text', None
    if u.message.video: tp,fid='video',u.message.video.file_id
    elif u.message.photo: tp,fid='photo',u.message.photo[-1].file_id
    elif u.message.document: tp,fid='document',u.message.document.file_id
    conn=get_db(); conn.execute("INSERT INTO courses (day,part,req_refs,content_type,file_id,caption) VALUES (?,?,?,?,?,?)",
        (c.user_data['d'],c.user_data['p'],c.user_data['r'],tp,fid,u.message.caption or u.message.text or "")); conn.commit(); conn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def m_usr_i(u,c): 
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    c.user_data['uid']=u.message.text; user=get_db().execute("SELECT full_name,referrals_confirmed FROM users WHERE user_id=?",(u.message.text,)).fetchone()
    if not user: await u.message.reply_text("نیست."); return ADMIN_PANEL
    await u.message.reply_text(f"{user[0]} - Ref: {user[1]}", reply_markup=ReplyKeyboardMarkup([["➕","➖"],["بازگشت"]],resize_keyboard=True)); return MANAGE_USER_ACTION
async def m_usr_a(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    cn=get_db(); change = 1 if u.message.text=="➕" else -1
    cn.execute("UPDATE users SET referrals_confirmed=max(0, referrals_confirmed+?) WHERE user_id=?", (change, c.user_data['uid'])); cn.commit(); cn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def edt_s(u,c): 
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    c.user_data['k']=u.message.text; await u.message.reply_text("متن:"); return EDIT_TEXT_INPUT
async def edt_i(u,c):
    cn=get_db(); cn.execute("INSERT OR REPLACE INTO dynamic_texts (key,content) VALUES (?,?)",(c.user_data['k'],u.message.text)); cn.commit(); cn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def liv_m(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    if "تنظیم" in u.message.text: await u.message.reply_text("عنوان\nلینک"); return SET_LIVE_LINK
    if "آپلود" in u.message.text: await u.message.reply_text("ویدیو:"); return UPLOAD_LIVE_FILE
    return MANAGE_LIVE_MENU
async def set_liv(u,c):
    l=u.message.text.split('\n'); cn=get_db(); cn.execute("UPDATE lives SET is_active=0"); cn.execute("INSERT INTO lives (title,link,is_active) VALUES (?,?,1)",(l[0],l[1])); cn.commit(); cn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL
async def up_liv(u,c):
    cn=get_db(); cn.execute("INSERT INTO lives (title,file_id,date_recorded,is_active) VALUES (?,?,?,0)",(u.message.caption or "Live",u.message.video.file_id,datetime.now().strftime("%Y-%m-%d"))); cn.commit(); cn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL
async def brd_m(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    cn=get_db(); usrs=cn.execute("SELECT user_id FROM users").fetchall(); cn.close()
    await u.message.reply_text("ارسال..."); 
    for x in usrs: 
        try: await u.message.copy(x[0]); await asyncio.sleep(0.05) 
        except: pass
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

def main():
    init_db(); keep_alive()
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH:[MessageHandler(filters.TEXT, admin_auth)], ADMIN_PANEL:[MessageHandler(filters.TEXT, admin_dispatch)],
            ADD_COURSE_DAY:[MessageHandler(filters.TEXT, add_c_d)], ADD_COURSE_PART:[MessageHandler(filters.TEXT, add_c_p)], ADD_COURSE_REFS:[MessageHandler(filters.TEXT, add_c_r)], ADD_COURSE_CONTENT:[MessageHandler(filters.ALL, add_c_c)],
            MANAGE_USER_INPUT:[MessageHandler(filters.TEXT, m_usr_i)], MANAGE_USER_ACTION:[MessageHandler(filters.TEXT, m_usr_a)],
            EDIT_TEXT_SELECT:[MessageHandler(filters.TEXT, edt_s)], EDIT_TEXT_INPUT:[MessageHandler(filters.TEXT, edt_i)],
            MANAGE_LIVE_MENU:[MessageHandler(filters.TEXT, liv_m)], SET_LIVE_LINK:[MessageHandler(filters.TEXT, set_liv)], UPLOAD_LIVE_FILE:[MessageHandler(filters.VIDEO, up_liv)],
            BROADCAST_MESSAGE:[MessageHandler(filters.ALL, brd_m)]
        }, fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("لغو", reply_markup=main_menu_keyboard()))]
    )
    app.add_handler(conv); app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler)); app.add_handler(MessageHandler(filters.TEXT, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
