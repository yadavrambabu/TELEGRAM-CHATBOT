import os
import sqlite3
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import google.generativeai as genai

# ================= LOAD ENV =================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("Environment variables missing")

ADMIN_IDS = {7476976785}
DB_NAME = "ashvi.db"

logging.basicConfig(level=logging.INFO)

# ================= DATABASE =================
def get_db():
    return sqlite3.connect(DB_NAME)

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            banned INTEGER DEFAULT 0
        )""")

        db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )""")

def ensure_user(user_id, name):
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO users (user_id, name) VALUES (?,?)",
            (user_id, name)
        )

def is_banned(user_id):
    with get_db() as db:
        cur = db.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row and row[0] == 1

def set_ban(user_id, value):
    with get_db() as db:
        db.execute("UPDATE users SET banned=? WHERE user_id=?", (value, user_id))

def save_message(user_id, role, text):
    with get_db() as db:
        db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?,?,?)",
            (user_id, role, text)
        )

def get_history(user_id, limit=8):
    with get_db() as db:
        cur = db.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        return cur.fetchall()[::-1]

def total_users():
    with get_db() as db:
        return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

# ================= AI =================
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are Ashvi — a smart, friendly AI assistant from Patna.
Speak in Hinglish.
Be honest and helpful.
Avoid unsafe or illegal content.
Correct users politely.
Remember conversation context.
"""

model = genai.GenerativeModel("gemini-1.5-flash")

def ai_response(user_id, text):
    history = [{"role": "user", "parts": [SYSTEM_PROMPT]}]

    for role, content in get_history(user_id):
        history.append({"role": role, "parts": [content]})

    chat = model.start_chat(history=history)
    response = chat.send_message(
        text,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=250
        )
    )
    return response.text.strip()

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "User")

    await update.message.reply_text(
        "👋 Namaste!\n"
        "Main Ashvi hoon — tumhari AI dost 🤖\n"
        "Bas message bhejo, baat shuru!"
    )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    ensure_user(user.id, user.first_name or "User")

    if is_banned(user.id):
        return

    save_message(user.id, "user", text)

    try:
        reply = ai_response(user.id, text)
    except Exception:
        reply = "⚠️ Thoda issue aa gaya, phir try karo."

    save_message(user.id, "model", reply)
    await update.message.reply_text(reply)

# ================= ADMIN =================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Admin only")
            return
        return await func(update, context)
    return wrapper

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Ashvi Stats\n\n"
        f"👥 Total users: {total_users()}"
    )

@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(context.args[0])
        set_ban(uid, 1)
        await update.message.reply_text(f"🚫 User {uid} banned")
    except:
        await update.message.reply_text("Usage: /ban user_id")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(context.args[0])
        set_ban(uid, 0)
        await update.message.reply_text(f"✅ User {uid} unbanned")
    except:
        await update.message.reply_text("Usage: /unban user_id")

# ================= MAIN =================
def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("🚀 Ashvi Bot is LIVE")
    app.run_polling()

if __name__ == "__main__":
    main()
