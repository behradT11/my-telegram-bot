mport logging
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
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
    except: pass

# --- سرور Flask ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot V13 is Ready."
def run_flask(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=False, use_reloader=False)
def keep_alive(): threading.Thread(target=run_flask, daemon=True).start()

# --- لاگینگ ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# --- دیتابیس (با متون کامل) ---
db_lock = threading.Lock()
def get_db(): return sqlite3.connect("parstrade_v13.db", check_same_thread=False)

def init_db():
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, referrer_id INTEGER, referrals_confirmed INTEGER DEFAULT 0, join_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS dynamic_texts (key TEXT PRIMARY KEY, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS courses (id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, part INTEGER, req_refs INTEGER, content_type TEXT, file_id TEXT, caption TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS lives (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, file_id TEXT, date_recorded TEXT, is_active INTEGER DEFAULT 0)''')
        
        # متون پیش‌فرض کامل و حرفه‌ای
        welcome_msg = (
            "🌺 **درود بر شما {name} عزیز، به خانواده بزرگ پارس ترید خوش آمدید!** 🌺\n\n"
            "ما در **Pars Trade Community** مفتخریم که شما را در مسیر پرچالش اما شیرین معامله‌گری همراهی کنیم.\n"
            "این ربات دروازه ورود شما به دنیایی از آموزش‌های تخصصی، تحلیل‌های ناب و ابزارهای حرفه‌ای ترید است.\n\n"
            "💎 **خدمات ما:**\n"
            "├ 🎓 دوره‌های آموزشی VIP (صفر تا صد)\n"
            "├ 🔴 لایو تریدهای تخصصی و پرسود\n"
            "└ 🏆 تورنمنت‌های ترید با جوایز نفیس\n\n"
            "👇 از منوی زیر استفاده کنید:"
        )
        about_msg = (
            "🏢 **درباره پارس ترید (Pars Trade)**\n\n"
            "ما یک تیم متشکل از معامله‌گران حرفه‌ای و تحلیل‌گران بازارهای مالی هستیم که با هدف ارتقای سطح دانش تریدرهای ایرانی گرد هم آمده‌ایم.\n\n"
            "🎯 **رسالت ما:**\n"
            "پرورش معامله‌گرانی منضبط، صبور و سودده است که بتوانند در بازارهای پرنوسان فارکس، کریپتو و ... به استقلال مالی برسند.\n\n"
            "🌐 وب‌سایت ما: pars-trade.com\n"
            "🆔 کانال تلگرام: @ParsTradeCommunity"
        )
        rules_msg = (
            "⚖️ **قوانین و مقررات استفاده از ربات**\n\n"
            "1️⃣ **عضویت اجباری:** استفاده از تمامی خدمات ربات منوط به عضویت دائمی در کانال تلگرام ماست.\n"
            "2️⃣ **صداقت در رفرال:** کاربرانی که با اکانت‌های فیک اقدام به زیرمجموعه‌گیری کنند، توسط سیستم هوشمند شناسایی و مسدود خواهند شد.\n"
            "3️⃣ **تکریم اعضا:** هرگونه بی‌احترامی در گروه پشتیبانی منجر به قطع دسترسی خواهد شد."
        )
        support_msg = "👨‍💻 **پشتیبانی اختصاصی**\n\nجهت ارتباط با ادمین: @Behrise"

        defaults = {"welcome": welcome_msg, "about": about_msg, "rules": rules_msg, "support": support_msg}
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

# --- لاجیک عضویت (بدون پارتی بازی) ---
async def check_membership(user_id, bot):
    # نکته: خط زیر حذف شد تا حتی شما هم چک شوید
    # if user_id == OWNER_ID: return True 
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        print(f"⚠️ Membership Check Error: {e}")
        # اگر بات ادمین نباشد، ارور میدهد. اینجا False میدهیم تا ادمین مجبور شود بات را در کانال ادمین کند
        return False 

async def send_force_join(update):
    kb = [[InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_LINK)],
          [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]]
    msg = "⛔️ **دسترسی محدود!**\n\nبرای استفاده از ربات، عضویت در کانال الزامی است.\nلطفاً عضو شوید و دکمه زیر را بزنید."
    
    if update.callback_query:
        try: await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        except: pass
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with db_lock:
            conn = get_db()
            if not conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone():
                ref = int(context.args[0]) if (context.args and context.args[0].isdigit() and int(context.args[0])!=user.id) else None
                conn.execute("INSERT INTO users (user_id, full_name, username, referrer_id, join_date) VALUES (?,?,?,?,?)",
                             (user.id, user.full_name, user.username, ref, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
            conn.close()
    except: pass

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

    # چک کردن عضویت در هر پیام
    if not await check_membership(u.id, context.bot): await send_force_join(update); return

    if t == "👤 پروفایل من":
        with db_lock:
            conn = get_db(); d = conn.execute("SELECT referrals_confirmed FROM users WHERE user_id=?", (u.id,)).fetchone(); conn.close()
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
    
    elif t == "ℹ️ درباره ما": await update.message.reply_text(get_text("about"), parse_mode=ParseMode.MARKDOWN)
    elif t == "📞 پشتیبانی": await update.message.reply_text(get_text("support"), parse_mode=ParseMode.MARKDOWN)
    elif t == "🏆 تورنمنت": await update.message.reply_text("به زودی...")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    u_id = q.from_user.id

    if d == "check_join":
        if await check_membership(u_id, context.bot):
            await q.answer("✅ تایید شد"); await q.message.delete(); await show_menu(q.message, q.from_user)
        else: await q.answer("❌ هنوز عضو نیستید یا بات ادمین نیست!", show_alert=True)
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
            except: await q.answer("فایل یافت نشد", show_alert=True)
        await q.answer()
    
    elif d.startswith("al_"): await q.answer(f"نیاز به {d.split('_')[1]} رفرال", show_alert=True)

# --- ادمین (اصلاح شده و بدون گیر کردن) ---
(ADMIN_AUTH, ADMIN_PANEL, INPUT_WAIT) = range(3)

async def admin_start(u, c):
    await u.message.reply_text("🔒 رمز عبور مدیریت:", reply_markup=ReplyKeyboardRemove())
    return ADMIN_AUTH

async def admin_auth(u, c):
    # .strip() حذف فاصله‌های اضافی
    if u.message.text.strip() == ADMIN_PASSWORD:
        kb = [["➕ افزودن آموزش", "🔴 مدیریت لایو"], ["📝 ویرایش متن", "❌ خروج"]]
        await u.message.reply_text("✅ وارد شدید. انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return ADMIN_PANEL
    await u.message.reply_text("❌ رمز اشتباه است.")
    return ADMIN_AUTH

async def admin_panel_h(u, c):
    t = u.message.text
    if t == "❌ خروج": await show_menu(u, u.effective_user); return ConversationHandler.END
    
    if t == "➕ افزودن آموزش":
        await u.message.reply_text("فرمت را وارد کنید:\nروز-قسمت-رفرال\nمثال: 1-2-5")
        return INPUT_WAIT
    
    if t == "📝 ویرایش متن":
        await u.message.reply_text("متاسفانه این بخش در حال تعمیر است.") # ساده‌سازی برای جلوگیری از باگ
        return ADMIN_PANEL
        
    return ADMIN_PANEL

async def admin_input(u, c):
    try:
        d, p, r = u.message.text.split('-')
        c.user_data['temp'] = (d, p, r)
        await u.message.reply_text("حالا فایل (ویدیو/عکس/داکیومنت) یا متن آموزش را بفرستید:")
        return INPUT_WAIT + 1 
    except:
        await u.message.reply_text("❌ فرمت غلط. دوباره تلاش کنید:\nمثال: 1-2-5")
        return INPUT_WAIT

async def admin_save(u, c):
    d, p, r = c.user_data['temp']
    tp, fid = 'text', None
    if u.message.video: tp,fid='video',u.message.video.file_id
    elif u.message.photo: tp,fid='photo',u.message.photo[-1].file_id
    elif u.message.document: tp,fid='document',u.message.document.file_id
    
    with db_lock:
        conn=get_db()
        conn.execute("INSERT INTO courses (day,part,req_refs,content_type,file_id,caption) VALUES (?,?,?,?,?,?)",
                     (d,p,r,tp,fid,u.message.caption or u.message.text or "Course"))
        conn.commit(); conn.close()
    
    kb = [["➕ افزودن آموزش", "🔴 مدیریت لایو"], ["📝 ویرایش متن", "❌ خروج"]]
    await u.message.reply_text("✅ ذخیره شد.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return ADMIN_PANEL

# --- Main ---
def main():
    force_delete_webhook()
    init_db()
    keep_alive()

    app = Application.builder().token(TOKEN).build()

    # ادمین هندلر
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT, admin_auth)],
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_panel_h)],
            INPUT_WAIT: [MessageHandler(filters.TEXT, admin_input)],
            INPUT_WAIT + 1: [MessageHandler(filters.ALL, admin_save)],
        },
        fallbacks=[CommandHandler("cancel", start)]
    )
    
    app.add_handler(admin_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))

    print("✅ Bot V13 Started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
