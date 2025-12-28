import logging
import sqlite3
import asyncio
import threading
import os
import requests
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

# --- تنظیمات ---
TOKEN = "8582244459:AAHJuWSrJVO0NQS6vAukbY1IV5WT5uIPUlE"
ADMIN_PASSWORD = "ParsTrade@2025!Secure#Admin"
OWNER_ID = 6735282633
CHANNEL_ID = -1002216477329
CHANNEL_LINK = "https://t.me/ParsTradeCommunity"

# --- پاکسازی دستی وب‌هوک (شوک اولیه) ---
def force_delete_webhook():
    """این تابع قبل از هر کاری وب‌هوک را با زور پاک می‌کند"""
    print("⚡️ Attempting to force delete webhook...")
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True"
        response = requests.get(url)
        print(f"⚡️ Webhook Reset Result: {response.text}")
    except Exception as e:
        print(f"⚡️ Warning: Could not manual reset webhook: {e}")

# --- سرور Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot V12 is Running Strong."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- دیتابیس (Thread Safe) ---
db_lock = threading.Lock()

def get_db():
    return sqlite3.connect("parstrade_v12.db", check_same_thread=False)

def init_db():
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                     user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT,
                     referrer_id INTEGER, referrals_confirmed INTEGER DEFAULT 0, join_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (key TEXT PRIMARY KEY, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS courses (
                     id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, part INTEGER, req_refs INTEGER,
                     content_type TEXT, file_id TEXT, caption TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS lives (
                     id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, file_id TEXT,
                     date_recorded TEXT, is_active INTEGER DEFAULT 0)''')
        
        defaults = {"welcome": "درود {name} عزیز، خوش آمدید.", "about": "درباره ما...", "rules": "قوانین...", "support": "@Behrise"}
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO dynamic_texts (key, content) VALUES (?, ?)", (k, v))
        conn.commit()
        conn.close()

def get_text(key, **kwargs):
    with db_lock:
        conn = get_db()
        res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone()
        conn.close()
    try: return res[0].format(**kwargs) if res else ""
    except: return res[0] if res else ""

# --- لاجیک عضویت ---
async def check_membership(user_id, bot):
    if user_id == OWNER_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        print(f"⚠️ Membership check error for {user_id}: {e}")
        # در صورت خطا، سخت‌گیری نمیکنیم تا بات گیر نکند (موقتا)
        return True 

async def send_force_join(update):
    kb = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_LINK)],
          [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]]
    msg = "⛔️ دسترسی محدود!\nلطفاً جهت حمایت و استفاده از ربات، عضو کانال شوید."
    if update.callback_query:
        try: await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    print(f"🚀 START from {user.id}")

    # ثبت نام در دیتابیس
    try:
        with db_lock:
            conn = get_db()
            if not conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone():
                ref = None
                if context.args and context.args[0].isdigit() and int(context.args[0]) != user.id:
                    ref = int(context.args[0])
                conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?,?,?,?,?)",
                             (user.id, user.full_name, user.username, ref, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
            conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

    if not await check_membership(user.id, context.bot):
        await send_force_join(update)
        return

    await show_menu(update, user)

def main_kb():
    return ReplyKeyboardMarkup([["🎓 آموزش (VIP)", "🔴 لایو ترید"], ["🏆 تورنمنت", "👤 پروفایل من"], ["ℹ️ درباره ما", "📞 پشتیبانی"]], resize_keyboard=True)

async def show_menu(update, user):
    txt = get_text("welcome", name=user.first_name)
    await update.message.reply_text(txt, reply_markup=main_kb(), parse_mode=ParseMode.MARKDOWN)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    u = update.effective_user
    if not t: return

    if not await check_membership(u.id, context.bot): await send_force_join(update); return

    if t == "👤 پروفایل من":
        with db_lock:
            conn = get_db()
            d = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (u.id,)).fetchone()
            conn.close()
        cnt = d[0] if d else 0
        lnk = f"https://t.me/{context.bot.username}?start={u.id}"
        await update.message.reply_text(f"👤 **پروفایل**\nدعوت‌ها: {cnt}\nلینک:\n`{lnk}`", parse_mode=ParseMode.MARKDOWN)
    
    elif t == "🎓 آموزش (VIP)":
        with db_lock:
            conn=get_db(); days=conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall(); conn.close()
        if not days: await update.message.reply_text("هنوز آموزشی نیست."); return
        kb=[[InlineKeyboardButton(f"روز {d[0]}", callback_data=f"day_{d[0]}")] for d in days]
        await update.message.reply_text("انتخاب روز:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif t == "🔴 لایو ترید":
        with db_lock:
            conn=get_db()
            act=conn.execute("SELECT title,link FROM lives WHERE is_active=1").fetchone()
            arc=conn.execute("SELECT id,title FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall()
            conn.close()
        kb=[]
        if act: kb.append([InlineKeyboardButton("ورود به لایو", url=act[1])])
        for a in arc: kb.append([InlineKeyboardButton(f"🎥 {a[1]}", callback_data=f"glive_{a[0]}")])
        msg = f"لایو زنده: {act[0]}" if act else "لایو زنده نیست."
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    elif t == "/admin":
        await update.message.reply_text("رمز مدیریت:", reply_markup=ReplyKeyboardRemove())
        return 0 # ADMIN_AUTH state code manually
    
    elif t in ["ℹ️ درباره ما", "📞 پشتیبانی", "🏆 تورنمنت"]:
         await update.message.reply_text("بخش " + t)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    u_id = q.from_user.id

    if d == "check_join":
        if await check_membership(u_id, context.bot):
            await q.answer("✅"); await q.message.delete(); await show_menu(q.message, q.from_user)
        else: await q.answer("❌ تایید نشد", show_alert=True)
        return

    if not await check_membership(u_id, context.bot): await q.answer("عضو شوید", show_alert=True); return

    if d.startswith("day_"):
        day=d.split("_")[1]
        with db_lock:
            conn=get_db()
            parts=conn.execute("SELECT id,part,req_refs FROM courses WHERE day=? ORDER BY part",(day,)).fetchall()
            refs=conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?",(u_id,)).fetchone()[0]
            conn.close()
        kb=[]
        for p in parts:
            cb = f"gc_{p[0]}" if refs>=p[2] else f"al_{p[2]}"
            txt = f"✅ Q{p[1]}" if refs>=p[2] else f"🔒 Q{p[1]} ({p[2]})"
            kb.append([InlineKeyboardButton(txt, callback_data=cb)])
        await q.message.edit_text(f"Day {day} - Refs: {refs}", reply_markup=InlineKeyboardMarkup(kb))
    
    elif d.startswith("gc_"):
        cid = d.split("_")[1]
        with db_lock:
            conn=get_db(); c=conn.execute("SELECT content_type,file_id,caption FROM courses WHERE id=?",(cid,)).fetchone(); conn.close()
        if c:
            try:
                if c[0]=='text': await q.message.reply_text(c[2])
                elif c[0]=='video': await q.message.reply_video(c[1], caption=c[2])
                elif c[0]=='photo': await q.message.reply_photo(c[1], caption=c[2])
                elif c[0]=='document': await q.message.reply_document(c[1], caption=c[2])
            except Exception as e: await q.answer(f"Error sending file: {e}", show_alert=True)
        await q.answer()
    
    elif d.startswith("al_"): await q.answer(f"نیاز به {d.split('_')[1]} رفرال", show_alert=True)

# --- ادمین ساده شده (برای جلوگیری از پیچیدگی) ---
(ADMIN_AUTH, ADMIN_PANEL, INPUT_WAIT) = range(3)

async def admin_auth(u, c):
    if u.message.text == ADMIN_PASSWORD:
        await u.message.reply_text("پنل:", reply_markup=ReplyKeyboardMarkup([["➕ افزودن آموزش", "❌ خروج"]], resize_keyboard=True))
        return ADMIN_PANEL
    return ADMIN_AUTH

async def admin_panel_h(u, c):
    if u.message.text == "❌ خروج": await show_menu(u, u.effective_user); return ConversationHandler.END
    if u.message.text == "➕ افزودن آموزش":
        await u.message.reply_text("فرمت: روز-قسمت-رفرال\nمثال: 1-2-5")
        return INPUT_WAIT
    return ADMIN_PANEL

async def admin_input(u, c):
    try:
        d, p, r = u.message.text.split('-')
        c.user_data['temp_course'] = (d, p, r)
        await u.message.reply_text("فایل را بفرستید:")
        return INPUT_WAIT + 1 # Hacky state extension
    except:
        await u.message.reply_text("فرمت غلط. مثال: 1-2-5")
        return INPUT_WAIT

async def admin_save(u, c):
    d, p, r = c.user_data['temp_course']
    tp, fid = 'text', None
    if u.message.video: tp,fid='video',u.message.video.file_id
    elif u.message.photo: tp,fid='photo',u.message.photo[-1].file_id
    elif u.message.document: tp,fid='document',u.message.document.file_id
    
    with db_lock:
        conn=get_db()
        conn.execute("INSERT INTO courses (day,part,req_refs,content_type,file_id,caption) VALUES (?,?,?,?,?,?)",
                     (d,p,r,tp,fid,u.message.caption or "Course"))
        conn.commit(); conn.close()
    await u.message.reply_text("ذخیره شد.")
    await u.message.reply_text("پنل:", reply_markup=ReplyKeyboardMarkup([["➕ افزودن آموزش", "❌ خروج"]], resize_keyboard=True))
    return ADMIN_PANEL

# --- استارتاپ ---
async def on_startup(app: Application):
    print("🤖 Bot is starting up...")
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text="🤖 **Bot V12 Started Successfully on Render!**\nIf you see this, I am alive.")
    except Exception as e:
        print(f"⚠️ Could not send startup message: {e}")

def main():
    force_delete_webhook() # پاکسازی دستی قبل از هر چیزی
    init_db()
    keep_alive()

    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{ADMIN_PASSWORD}$"), admin_auth)], # میانبر رمز
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT, admin_auth)],
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_panel_h)],
            INPUT_WAIT: [MessageHandler(filters.TEXT, admin_input)],
            INPUT_WAIT + 1: [MessageHandler(filters.ALL, admin_save)],
        },
        fallbacks=[CommandHandler("cancel", start)]
    )

    # هندل کردن لاجیک ورود به ادمین به صورت دستی در message_handler انجام شده بود، اینجا برای کانورسیشن تمیزتر:
    # ما یک هندلر کلی برای متن داریم که اگر رمز بود وارد ادمین شود
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # ادمین هندلر جداگانه
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^/admin$"), lambda u,c: u.message.reply_text("رمز:", reply_markup=ReplyKeyboardRemove()) or ADMIN_AUTH)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT, admin_auth)],
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_panel_h)],
            INPUT_WAIT: [MessageHandler(filters.TEXT, admin_input)],
            INPUT_WAIT+1: [MessageHandler(filters.ALL, admin_save)]
        }, fallbacks=[CommandHandler("cancel", start)]
    )
    app.add_handler(admin_conv)
    
    app.add_handler(MessageHandler(filters.TEXT, message_handler))

    print("🟢 Polling started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
