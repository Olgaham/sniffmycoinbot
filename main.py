import os
import json
import time
import threading
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    Filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

WATCHLIST_FILE = "watchlist.json"
PRICES_FILE = "targets.json"
THRESHOLD = 8  # % для сигналов о росте/падении

# ============ JSON ============
def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ============ Получение данных ============
def get_token_data(token_name):
    url = f"https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "ids": token_name.lower()}
    r = requests.get(url, params=params)
    if r.status_code == 200 and r.json():
        d = r.json()[0]
        return {
            "name": d["name"],
            "price": d["current_price"],
            "change": d["price_change_percentage_24h"],
            "cap": d["market_cap"],
            "volume": d["total_volume"]
        }
    return None

def format_token_data(data):
    return (
        f"📊 {data['name']}:\n"
        f"💵 Цена: ${data['price']:.6g}\n"
        f"📉 24ч: {data['change']:.2f}%\n"
        f"🏦 Капа: ${data['cap']:,}\n"
        f"📦 Объём: ${data['volume']:,}"
    )

# ============ Обработчики ============
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить токен", callback_data="check")],
        [InlineKeyboardButton("📈 График", callback_data="chart")],
        [InlineKeyboardButton("🏆 Топ-10 мемкоинов", callback_data="top")],
        [InlineKeyboardButton("🆕 Новые токены", callback_data="new")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выбери команду или введи токен:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == "check":
        query.edit_message_text("🔍 Введи название токена (например: `shiba`):")
        context.user_data["awaiting_token"] = True
    elif query.data == "chart":
        token = context.user_data.get("last_token", "")
        if token:
            url = f"https://dexscreener.com/search/{token}"
            query.edit_message_text(f"📉 График: {url}")
        else:
            query.edit_message_text("⚠️ Сначала проверь токен.")
    elif query.data == "top":
        msg = "🏆 Топ-10 мемкоинов:\n"
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usd", "category": "memes", "order": "market_cap_desc", "per_page": 10}
        r = requests.get(url, params=params)
        if r.status_code == 200:
            for i, coin in enumerate(r.json(), 1):
                msg += f"{i}. {coin['name']} — ${coin['current_price']} (кап. ${coin['market_cap']})\n"
        else:
            msg = "⚠️ Ошибка получения данных."
        query.edit_message_text(msg)
    elif query.data == "new":
        r = requests.get("https://api.coingecko.com/api/v3/coins/list")
        if r.status_code == 200:
            last_tokens = r.json()[-10:]
            msg = "🆕 Новые токены:\n"
            for t in last_tokens:
                msg += f"• {t['name']} ({t['symbol']})\n"
            query.edit_message_text(msg)
        else:
            query.edit_message_text("⚠️ Не удалось получить токены.")

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.lower()

    if context.user_data.get("awaiting_token"):
        data = get_token_data(text)
        if data:
            update.message.reply_text(f"✅ Токен {data['name']} добавлен!\n{format_token_data(data)}")
            context.user_data["last_token"] = text

            watchlist = load_json(WATCHLIST_FILE)
            prices = load_json(PRICES_FILE)

            watchlist[text] = update.message.chat_id
            prices[text] = data["price"]

            save_json(WATCHLIST_FILE, watchlist)
            save_json(PRICES_FILE, prices)
        else:
            update.message.reply_text("❌ Токен не найден.")
        context.user_data["awaiting_token"] = False
    else:
        update.message.reply_text("🤖 Я не понял. Нажми кнопку или введи название токена.")

# ============ Мониторинг ============
def monitor_prices():
    while True:
        watchlist = load_json(WATCHLIST_FILE)
        prices = load_json(PRICES_FILE)

        for token, chat_id in watchlist.items():
            data = get_token_data(token)
            if not data:
                continue
            old_price = prices.get(token, data["price"])
            new_price = data["price"]

            change = ((new_price - old_price) / old_price) * 100
            if abs(change) >= THRESHOLD:
                text = f"📢 {token.upper()} изменился на {change:.2f}%\n{format_token_data(data)}"
                context.bot.send_message(chat_id=chat_id, text=text)
                prices[token] = new_price
                save_json(PRICES_FILE, prices)

        time.sleep(60 * 5)  # каждые 5 минут

# ============ Запуск ============
def main():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    threading.Thread(target=monitor_prices, daemon=True).start()

    print("🤖 Бот работает...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
