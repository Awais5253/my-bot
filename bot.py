import os
import random
import psycopg2
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask
from faker import Faker
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# ==========================================
# 1. FLASK WEB SERVER SETUP
# ==========================================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running live on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# ==========================================
# 2. TELEGRAM BOT SETUP
# ==========================================
TOKEN = "8906333193:AAG4bjuCEwAAttfdR9FXkZmzPyG_KmfUMrk"
ADMIN_ID = 7208292353 
fake = Faker()

import os
DB_URL = os.environ.get("DATABASE_URL")

def init_db():
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        chat_id BIGINT PRIMARY KEY,
        user_id BIGINT,
        balance INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        email TEXT,
        status TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS referrals (
        chat_id BIGINT PRIMARY KEY,
        referrer_id BIGINT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS referral_earnings (
        id SERIAL PRIMARY KEY,
        referrer_id BIGINT,
        amount INTEGER,
        date TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT,
        amount INTEGER,
        method TEXT,
        status TEXT
    )''')
    conn.commit()
    conn.close()

CHOOSE_METHOD, ENTER_NUMBER, ENTER_AMOUNT = range(3)

def get_main_menu():
    keyboard = [["New Account", "My accounts"], ["Balance", "Withdraw"], ["Profile", "My referrals"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    args = context.args
    referrer_id = None
    if args and args[0].isdigit():
        referrer_id = int(args[0])

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM users WHERE chat_id = %s", (chat_id,))
    user_exists = cursor.fetchone()
    
    if not user_exists:
        cursor.execute("SELECT MAX(user_id) FROM users")
        max_id_res = cursor.fetchone()
        max_id = max_id_res[0] if max_id_res and max_id_res[0] is not None else None
        uid = max_id + 1 if max_id else 8866482000
        
        cursor.execute("INSERT INTO users (chat_id, user_id, balance) VALUES (%s, %s, %s)", (chat_id, uid, 0))
        
        if referrer_id and referrer_id != chat_id:
            cursor.execute("SELECT chat_id FROM users WHERE chat_id = %s", (referrer_id,))
            if cursor.fetchone():
                cursor.execute("INSERT INTO referrals (chat_id, referrer_id) VALUES (%s, %s) ON CONFLICT (chat_id) DO NOTHING", (chat_id, referrer_id))
    
    conn.commit()
    conn.close()

    welcome_text = (
        "👋 Welcome!\n\nMega Gmail Task Bot is an official and trusted platform under the leadership of its Founder, Awais Irshad. Our mission is to provide a 100% genuine and secure environment where users can easily earn daily rewards by completing simple micro-tasks with complete transparency and honesty. You can earn money here without any investment!"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu())

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    # Check if there is already a pending withdrawal
    cursor.execute("SELECT id FROM withdrawals WHERE chat_id = %s AND status = 'Pending'", (chat_id,))
    pending_request = cursor.fetchone()
    
    if pending_request:
        conn.close()
        await update.message.reply_text("⚠️ You already have a pending withdrawal request. Please wait for the admin to approve it.", reply_markup=get_main_menu())
        return ConversationHandler.END

    cursor.execute("SELECT balance FROM users WHERE chat_id = %s", (chat_id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0
    conn.close()
    
    if balance < 30:
        await update.message.reply_text("Minimum withdrawal limit is 30 RS.", reply_markup=get_main_menu())
        return ConversationHandler.END
        
    await update.message.reply_text("Select your payment method:", reply_markup=ReplyKeyboardMarkup([["EasyPaisa", "JazzCash"], ["Cancel"]], resize_keyboard=True))
    return CHOOSE_METHOD

async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END
    context.user_data['method'] = update.message.text
    await update.message.reply_text("Please enter your 11-digit account number:", reply_markup=ReplyKeyboardMarkup([["Cancel"]], resize_keyboard=True))
    return ENTER_NUMBER

async def enter_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END
    if not (update.message.text.isdigit() and len(update.message.text) == 11):
        await update.message.reply_text("Invalid number. Please enter exactly 11 digits.")
        return ENTER_NUMBER
    context.user_data['number'] = update.message.text
    await update.message.reply_text("Please enter amount to withdraw (Min 30):", reply_markup=ReplyKeyboardMarkup([["Cancel"]], resize_keyboard=True))
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END
    try:
        amount = int(update.message.text)
        chat_id = update.effective_chat.id
        
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT balance, user_id FROM users WHERE chat_id = %s", (chat_id,))
        res = cursor.fetchone()
        balance, uid = (res[0], res[1]) if res else (0, "N/A")
        
        if amount < 30 or amount > balance:
            conn.close()
            await update.message.reply_text("Invalid amount. Check your balance.")
            return ENTER_AMOUNT
        
        context.user_data['amount'] = amount
        
        cursor.execute("INSERT INTO withdrawals (chat_id, amount, method, status) VALUES (%s, %s, %s, %s)", 
                       (chat_id, amount, context.user_data['method'], "Pending"))
        conn.commit()
        conn.close()
        
        report = f"Withdrawal Request:\nUser: {update.effective_user.first_name}\nID: {uid}\nMethod: {context.user_data['method']}\nNumber: `{context.user_data['number']}`\nAmount: {amount} RS"
        
        keyboard = [
            [InlineKeyboardButton("✅ Done", callback_data=f"wd_{chat_id}_{amount}"), 
             InlineKeyboardButton("❌ Reject", callback_data=f"wrej_{chat_id}_{amount}")]
        ]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        await update.message.reply_text("Submitted for review!", reply_markup=get_main_menu())
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a valid number, not text.")
        return ENTER_AMOUNT

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if text == "My referrals":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={chat_id}"
        
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = %s", (chat_id,))
        total_refs = cursor.fetchone()[0]
        
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT SUM(amount) FROM referral_earnings WHERE referrer_id = %s AND date >= %s", (chat_id, thirty_days_ago))
        earned_30d = cursor.fetchone()[0] or 0
        conn.close()
        
        msg = (
            f"👥 **Total referrals:** `{total_refs}`\n"
            f"💰 **Earned in last 30 days:** `{earned_30d} RS`\n\n"
            f"🔗 **Your referral link:**\n`{ref_link}`\n\n"
            f"ℹ️ *You will receive 10 RS bonus for each referral when they complete their task and it gets approved by the Admin!*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    elif text == "Profile":
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE chat_id = %s", (chat_id,))
        res = cursor.fetchone()
        uid = res[0] if res else chat_id
        conn.close()
        await update.message.reply_text(f"👤 Your profile:\n\n🆔 ID: {uid}\n👤 Name: {user.first_name}")
        
    elif text == "Balance":
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE chat_id = %s", (chat_id,))
        res = cursor.fetchone()
        bal = res[0] if res else 0
        conn.close()
        await update.message.reply_text(f"You have RS {bal} available balance.")
        
    elif text == "My accounts":
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT email, status FROM accounts WHERE chat_id = %s ORDER BY id DESC LIMIT 6", (chat_id,))
        accounts = cursor.fetchall()
        accounts.reverse()
        
        cursor.execute("SELECT amount, method, status FROM withdrawals WHERE chat_id = %s ORDER BY id DESC LIMIT 1", (chat_id,))
        last_withdrawal = cursor.fetchone()
        conn.close()
        
        if not accounts and not last_withdrawal:
            await update.message.reply_text("You have no account or withdrawal history yet.")
        else:
            msg = ""
            if accounts:
                msg += "📝 Your Account History (Last 6):\n\n"
                for acc in accounts:
                    msg += f"Email: {acc[0]}\nStatus: {acc[1]}\n\n"
            
            if last_withdrawal:
                msg += "💸 Your Latest Withdrawal:\n\n"
                msg += f"Amount: {last_withdrawal[0]} RS ({last_withdrawal[1]})\nStatus: {last_withdrawal[2]}\n\n"
                    
            await update.message.reply_text(msg)
            
    elif text == "New Account":
        first, last = fake.first_name(), fake.last_name()
        email = f"{first.lower()}{last.lower()}{random.randint(10000000, 99999999)}@gmail.com"
        
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM accounts")
        total_accs = cursor.fetchone()[0]
        conn.close()
        
        reg_id = f"G{total_accs + 1}"
        
        dob_year = random.randint(1995, 2006)
        dob_month = random.randint(1, 12)
        dob_day = random.randint(1, 28) 
        dob = f"{dob_day:02d}/{dob_month:02d}/{dob_year}"
        
        context.user_data['last_task'] = {"email": email, "full_info": f"ID: {reg_id}\nName: {first} {last}\nDOB: {dob}\nEmail: {email}\nPassword: aass1122"}
        msg = f"Task ID: `{reg_id}`\n\nName: `{first} {last}`\nDOB: `{dob}`\nEmail: `{email}`\nPassword: `aass1122`\n\nPrice: RS 30"
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["✅ Done", "❌ Cancel"]], resize_keyboard=True), parse_mode="Markdown")
        
    elif text == "❌ Cancel":
        if 'last_task' in context.user_data:
            del context.user_data['last_task']
        await update.message.reply_text("Task Cancelled.", reply_markup=get_main_menu())
        
    elif text == "✅ Done":
        task_data = context.user_data.get('last_task')
        if task_data:
            email = task_data['email']
            
            conn = psycopg2.connect(DB_URL)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO accounts (chat_id, email, status) VALUES (%s, %s, %s)", (chat_id, email, "Pending"))
            cursor.execute("SELECT user_id FROM users WHERE chat_id = %s", (chat_id,))
            res = cursor.fetchone()
            uid = res[0] if res else "N/A"
            conn.commit()
            conn.close()
            
            report = f"New Task from {user.first_name} (ID: {uid}):\n\n{task_data['full_info']}"
            keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{chat_id}_{email}"), InlineKeyboardButton("❌ Reject", callback_data=f"rej_{chat_id}_{email}")] ]
            await context.bot.send_message(chat_id=ADMIN_ID, text=report, reply_markup=InlineKeyboardMarkup(keyboard))
            await update.message.reply_text("Submitted for review!", reply_markup=get_main_menu())
            del context.user_data['last_task']
    else:
        await update.message.reply_text("Please select an option from the menu.")

async def button_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('_')
    
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    if data[0] == "wd":
        user_id, amount = int(data[1]), int(data[2])
        cursor.execute("UPDATE users SET balance = GREATEST(0, balance - %s) WHERE chat_id = %s", (amount, user_id))
        cursor.execute("UPDATE withdrawals SET status = 'Approved' WHERE chat_id = %s AND amount = %s AND status = 'Pending'", (user_id, amount))
        conn.commit()
        await context.bot.send_message(chat_id=user_id, text="Congratulations! Your withdrawal has been received. Please Check your Easypaisa/JazzCash account.")
        await query.edit_message_text(text="Withdrawal Approved and amount deducted.")
    
    elif data[0] == "wrej":
        user_id, amount = int(data[1]), int(data[2])
        cursor.execute("UPDATE withdrawals SET status = 'Rejected' WHERE chat_id = %s AND amount = %s AND status = 'Pending'", (user_id, amount))
        conn.commit()
        await context.bot.send_message(chat_id=user_id, text="Your withdrawal request has been rejected. Check your account number and try again.")
        await query.edit_message_text(text="Withdrawal Rejected.")
            
    elif data[0] in ["app", "rej"]:
        user_id, email, action = int(data[1]), data[2], data[0]
        
        cursor.execute("SELECT status FROM accounts WHERE chat_id = %s AND email = %s", (user_id, email))
        account_status = cursor.fetchone()
        
        if not account_status or account_status[0] != "Pending":
            await query.answer("This task is already processed!", show_alert=True)
            conn.close()
            return
            
        if action == "app":
            cursor.execute("UPDATE accounts SET status = 'Approved' WHERE chat_id = %s AND email = %s", (user_id, email))
            cursor.execute("UPDATE users SET balance = balance + 30 WHERE chat_id = %s", (user_id,))
            cursor.execute("SELECT referrer_id FROM referrals WHERE chat_id = %s", (user_id,))
            ref_res = cursor.fetchone()
            referrer_id = ref_res[0] if ref_res else None
            if referrer_id:
                cursor.execute("UPDATE users SET balance = balance + 10 WHERE chat_id = %s", (referrer_id,))
                cursor.execute("INSERT INTO referral_earnings (referrer_id, amount, date) VALUES (%s, %s, %s)", (referrer_id, 10, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            await context.bot.send_message(chat_id=user_id, text=f"Task {email} Approved! 30 RS added.")
            await query.edit_message_text(text=f"Task Approved: {email}")
            if referrer_id:
                try: await context.bot.send_message(chat_id=referrer_id, text="🎉 Congratulations! Your referral's task was approved and you earned a 10 RS bonus!")
                except: pass
        else:
            cursor.execute("UPDATE accounts SET status = 'Rejected' WHERE chat_id = %s AND email = %s", (user_id, email))
            conn.commit()
            await context.bot.send_message(chat_id=user_id, text=f"Task {email} Rejected.")
            await query.edit_message_text(text=f"Task Rejected: {email}")
    
    conn.close()
    await query.answer()

def main():
    Thread(target=run_flask, daemon=True).start()
    init_db()
    application = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(["Withdraw"]), withdraw_start)],
        states={
            CHOOSE_METHOD: [MessageHandler(filters.Text(["EasyPaisa", "JazzCash", "Cancel"]), choose_method)],
            ENTER_NUMBER: [MessageHandler(filters.TEXT, enter_number)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT, enter_amount)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_query))
    
    print("Bot is running...")
    while True:
        try:
            application.run_polling(drop_pending_updates=False)
        except Exception as e:
            print(f"Bot error: {e}. Restarting...")
            import time
            time.sleep(5)

if __name__ == '__main__':
    main()
