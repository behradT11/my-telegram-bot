mport logging
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
from telegram.error import BadRequest, NetworkError

# --- تنظیمات ---
# ✅ توکن جدید جایگزین شد
TOKEN = "8582244459:AAHJuWSrJVO0NQS6vAukbY1IV5WT5uIPUlE"
ADMIN_PASSWORD = "ParsTrade@2025!Secure#Admin"
OWNER_ID = 6735282633
CHANNEL_ID = -1002216477329
CHANNEL_LINK = "https://t.me/ParsTradeCommunity"

# --- سرور Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot V11 New Token is Running OK."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    try:
        t = threading.Thread(target=run_flask)
        t.daemon = True
        t.start()
    except Exception as e:
        print(f"Flask Error: {e}")

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- مراحل ---
(ADMIN_AUTH, ADMIN_PANEL, 
 ADD_COURSE_DAY, ADD_COURSE_PART, ADD_COURSE_REFS, ADD_COURSE_CONTENT,
 MANAGE_LIVE_MENU, SET_LIVE_LINK, UPLOAD_LIVE_FILE,
 MANAGE_USER_INPUT, MANAGE_USER_ACTION,
 EDIT_TEXT_SELECT, EDIT_TEXT_INPUT, BROADCAST_MESSAGE) = range(14)

# --- دیتابیس ---
def get_db():
    conn = sqlite3.connect("parstrade_v11.db", check_same_thread=False)
    return conn

def init_db():
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
    conn = get_db(); res = conn.execute("SELECT content FROM dynamic_texts WHERE key=?", (key,)).fetchone(); conn.close()
    try: return res[0].format(**kwargs) if res else ""
    except: return res[0] if res else ""

# --- چک کردن عضویت (فوق سریع) ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID: return True

    try:
        # لاگ برای دیباگ
        print(f"Checking membership for {user_id}...")
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        print(f"⚠️ Membership Error (Allowing user): {e}")
        # در صورت هرگونه خطا (مثل ادمین نبودن بات)، اجازه عبور می‌دهیم تا بات قفل نکند
        return True

async def force_join_msg(update: Update):
    kb = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_LINK)],
          [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]]
    msg = "⛔️ دسترسی محدود!\nبرای استفاده از ربات لطفاً عضو کانال شوید."
    if update.callback_query:
        try: await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb))
        except: pass
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"🚀 START command received from {update.effective_user.id}") # لاگ مهم
    
    # 1. پاسخ سریع
    msg = await update.message.reply_text("⏳ ...")

    user = update.effective_user
    try:
        conn = get_db()
        if not conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone():
            ref = int(context.args[0]) if (context.args and context.args[0].isdigit() and int(context.args[0])!=user.id) else None
            conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?,?,?,?,?)",
                         (user.id, user.full_name, user.username, ref, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

    try: await msg.delete()
    except: pass

    if not await check_membership(update, context):
        await force_join_msg(update)
        return

    await show_main_menu(update, user)

def main_kb():
    return ReplyKeyboardMarkup([["🎓 آموزش (VIP)", "🔴 لایو ترید"], ["🏆 تورنمنت", "👤 پروفایل من"], ["ℹ️ درباره ما", "📞 پشتیبانی"]], resize_keyboard=True)

async def show_main_menu(update, user):
    txt = get_text("welcome", name=user.first_name)
    await update.message.reply_text(txt, reply_markup=main_kb(), parse_mode=ParseMode.MARKDOWN)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if not t: return
    
    # لاگ پیام
    print(f"📩 Message received: {t}")

    if not await check_membership(update, context): await force_join_msg(update); return
    
    u = update.effective_user
    if t=="👤 پروفایل من":
        conn=get_db(); d=conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?",(u.id,)).fetchone(); conn.close()
        cnt = d[0] if d else 0
        lnk=f"https://t.me/{context.bot.username}?start={u.id}"
        await update.message.reply_text(f"👤 پروفایل\nدعوت‌ها: {cnt}\nلینک:\n`{lnk}`", parse_mode=ParseMode.MARKDOWN)
    elif t=="🎓 آموزش (VIP)":
        conn=get_db(); days=conn.execute("SELECT DISTINCT day FROM courses ORDER BY day").fetchall(); conn.close()
        if not days: await update.message.reply_text("خالی است."); return
        kb=[[InlineKeyboardButton(f"روز {d[0]}", callback_data=f"day_{d[0]}")] for d in days]
        await update.message.reply_text("انتخاب روز:", reply_markup=InlineKeyboardMarkup(kb))
    elif t=="🔴 لایو ترید":
        conn=get_db(); act=conn.execute("SELECT title,link FROM lives WHERE is_active=1").fetchone()
        arc=conn.execute("SELECT id,title FROM lives WHERE is_active=0 ORDER BY id DESC LIMIT 5").fetchall(); conn.close()
        kb=[]
        if act: kb.append([InlineKeyboardButton("ورود به لایو", url=act[1])])
        for a in arc: kb.append([InlineKeyboardButton(f"🎥 {a[1]}", callback_data=f"glive_{a[0]}")])
        msg = f"لایو زنده: {act[0]}" if act else "لایو زنده نیست."
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    elif t=="🏆 تورنمنت": await update.message.reply_text("به زودی...")
    elif t=="ℹ️ درباره ما": await update.message.reply_text(get_text("about"))
    elif t=="📞 پشتیبانی": await update.message.reply_text(get_text("support"))
    elif t == "/admin": await admin_start(update, context) # هندل کردن ادمین اگر دکمه نبود

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    if d=="check_join":
        if await check_membership(update, context):
            await q.answer("✅"); await q.message.delete(); await show_main_menu(q.message, q.from_user)
        else: await q.answer("❌ هنوز عضو نیستید (یا ربات ادمین نیست)", show_alert=True)
        return

    if not await check_membership(update, context): await q.answer("عضو شوید!", show_alert=True); return

    if d.startswith("day_"):
        day=d.split("_")[1]; conn=get_db()
        parts=conn.execute("SELECT id,part,req_refs FROM courses WHERE day=? ORDER BY part",(day,)).fetchall()
        refs_data=conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?",(q.from_user.id,)).fetchone()
        refs = refs_data[0] if refs_data else 0
        conn.close()
        kb=[]
        for p in parts:
            btn_txt = f"✅ قسمت {p[1]}" if refs>=p[2] else f"🔒 قسمت {p[1]} ({p[2]} دعوت)"
            cb = f"gc_{p[0]}" if refs>=p[2] else f"al_{p[2]}"
            kb.append([InlineKeyboardButton(btn_txt, callback_data=cb)])
        await q.message.edit_text(f"روز {day} - دعوت‌های شما: {refs}", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("al_"): await q.answer(f"نیاز به {d.split('_')[1]} دعوت.", show_alert=True)
    elif d.startswith("glive_"):
        l=get_db().execute("SELECT file_id,title FROM lives WHERE id=?",(d.split("_")[1],)).fetchone()
        if l: await q.message.reply_video(l[0], caption=l[1])
        await q.answer()
    elif d.startswith("gc_"):
        c=get_db().execute("SELECT content_type,file_id,caption FROM courses WHERE id=?",(d.split("_")[1],)).fetchone()
        if c:
            if c[0]=='text': await q.message.reply_text(c[2])
            elif c[0]=='video': await q.message.reply_video(c[1], caption=c[2])
            elif c[0]=='photo': await q.message.reply_photo(c[1], caption=c[2])
            elif c[0]=='document': await q.message.reply_document(c[1], caption=c[2])
        await q.answer()

# --- ادمین ---
async def admin_start(u,c): await u.message.reply_text("رمز:", reply_markup=ReplyKeyboardRemove()); return ADMIN_AUTH
async def admin_auth(u,c): 
    if u.message.text==ADMIN_PASSWORD: await admin_panel(u,c); return ADMIN_PANEL
    await u.message.reply_text("غلط."); return ADMIN_AUTH
async def admin_panel(u,c):
    kb=[["➕ آموزش", "🔴 لایو"], ["👥 کاربر", "📝 متن"], ["📢 پیام همگانی", "❌ خروج"]]
    await u.message.reply_text("مدیریت:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def admin_dispatch(u,c):
    t=u.message.text
    if t=="❌ خروج": await u.message.reply_text("بای", reply_markup=main_kb()); return ConversationHandler.END
    if t=="➕ آموزش": await u.message.reply_text("روز:"); return ADD_COURSE_DAY
    if t=="👥 کاربر": await u.message.reply_text("آیدی:"); return MANAGE_USER_INPUT
    if t=="📝 متن": await u.message.reply_text("key:", reply_markup=ReplyKeyboardMarkup([["welcome","about","rules"],["بازگشت"]],resize_keyboard=True)); return EDIT_TEXT_SELECT
    if t=="🔴 لایو": await u.message.reply_text("...", reply_markup=ReplyKeyboardMarkup([["تنظیم لینک","آپلود آرشیو"],["بازگشت"]],resize_keyboard=True)); return MANAGE_LIVE_MENU
    if t=="📢 پیام همگانی": await u.message.reply_text("پیام:"); return BROADCAST_MESSAGE
    return ADMIN_PANEL

# توابع ادمین
async def ac_d(u,c): c.user_data['d']=u.message.text; await u.message.reply_text("قسمت:"); return ADD_COURSE_PART
async def ac_p(u,c): c.user_data['p']=u.message.text; await u.message.reply_text("رفرال:"); return ADD_COURSE_REFS
async def ac_r(u,c): c.user_data['r']=u.message.text; await u.message.reply_text("فایل:"); return ADD_COURSE_CONTENT
async def ac_c(u,c):
    tp,fid='text',None
    if u.message.video: tp,fid='video',u.message.video.file_id
    elif u.message.photo: tp,fid='photo',u.message.photo[-1].file_id
    elif u.message.document: tp,fid='document',u.message.document.file_id
    conn=get_db(); conn.execute("INSERT INTO courses (day,part,req_refs,content_type,file_id,caption) VALUES (?,?,?,?,?,?)",(c.user_data['d'],c.user_data['p'],c.user_data['r'],tp,fid,u.message.caption or u.message.text or "")); conn.commit(); conn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def mu_i(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    c.user_data['uid']=u.message.text; x=get_db().execute("SELECT full_name,referrals_confirmed FROM users WHERE user_id=?",(u.message.text,)).fetchone()
    if not x: await u.message.reply_text("نیست"); return ADMIN_PANEL
    await u.message.reply_text(f"{x[0]} : {x[1]}", reply_markup=ReplyKeyboardMarkup([["➕","➖"],["بازگشت"]],resize_keyboard=True)); return MANAGE_USER_ACTION
async def mu_a(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    n=1 if u.message.text=="➕" else -1; cn=get_db(); cn.execute("UPDATE users SET referrals_confirmed=max(0, referrals_confirmed+?) WHERE user_id=?",(n,c.user_data['uid'])); cn.commit(); cn.close()
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def es(u,c): c.user_data['k']=u.message.text; await u.message.reply_text("متن:"); return EDIT_TEXT_INPUT
async def ei(u,c): cn=get_db(); cn.execute("INSERT OR REPLACE INTO dynamic_texts (key,content) VALUES (?,?)",(c.user_data['k'],u.message.text)); cn.commit(); cn.close(); await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

async def lm(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    if "لینک" in u.message.text: await u.message.reply_text("عنوان\nلینک"); return SET_LIVE_LINK
    await u.message.reply_text("ویدیو:"); return UPLOAD_LIVE_FILE
async def sll(u,c): l=u.message.text.split('\n'); cn=get_db(); cn.execute("UPDATE lives SET is_active=0"); cn.execute("INSERT INTO lives (title,link,is_active) VALUES (?,?,1)",(l[0],l[1])); cn.commit(); cn.close(); await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL
async def ulf(u,c): cn=get_db(); cn.execute("INSERT INTO lives (title,file_id,date_recorded,is_active) VALUES (?,?,?,0)",(u.message.caption or "Live",u.message.video.file_id,datetime.now().strftime("%Y-%m-%d"))); cn.commit(); cn.close(); await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL
async def bm(u,c):
    if u.message.text=="بازگشت": await admin_panel(u,c); return ADMIN_PANEL
    us=get_db().execute("SELECT user_id FROM users").fetchall(); await u.message.reply_text("..."); 
    for x in us: 
        try: await u.message.copy(x[0]); await asyncio.sleep(0.05)
        except: pass
    await u.message.reply_text("✅"); await admin_panel(u,c); return ADMIN_PANEL

# --- تابع راه‌اندازی (Startup) ---
async def post_init(application: Application):
    print("🧹 Cleaning up old webhooks and updates...")
    # این دستور حیاتی است: وب‌هوک‌های قبلی را پاک می‌کند تا Polling کار کند
    await application.bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook deleted. Bot is ready and polling...")

# --- Main ---
def main():
    init_db(); keep_alive()
    
    # استفاده از post_init برای پاکسازی
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH:[MessageHandler(filters.TEXT, admin_auth)], ADMIN_PANEL:[MessageHandler(filters.TEXT, admin_dispatch)],
            ADD_COURSE_DAY:[MessageHandler(filters.TEXT, ac_d)], ADD_COURSE_PART:[MessageHandler(filters.TEXT, ac_p)], ADD_COURSE_REFS:[MessageHandler(filters.TEXT, ac_r)], ADD_COURSE_CONTENT:[MessageHandler(filters.ALL, ac_c)],
            MANAGE_USER_INPUT:[MessageHandler(filters.TEXT, mu_i)], MANAGE_USER_ACTION:[MessageHandler(filters.TEXT, mu_a)],
            EDIT_TEXT_SELECT:[MessageHandler(filters.TEXT, es)], EDIT_TEXT_INPUT:[MessageHandler(filters.TEXT, ei)],
            MANAGE_LIVE_MENU:[MessageHandler(filters.TEXT, lm)], SET_LIVE_LINK:[MessageHandler(filters.TEXT, sll)], UPLOAD_LIVE_FILE:[MessageHandler(filters.VIDEO, ulf)],
            BROADCAST_MESSAGE:[MessageHandler(filters.ALL, bm)]
        }, fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("لغو", reply_markup=main_kb()))]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))
    
    print("⏳ Starting bot engine...")
    app.run_polling()

if __name__ == "__main__":
    main()

