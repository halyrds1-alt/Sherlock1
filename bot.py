import telebot
from telebot import types
from telethon import TelegramClient, errors
import asyncio
import threading

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8011676411:AAF5i2CFK3R52e2cCbMjrOMX9zLsVgzkVos'
ADMIN_ID = 6747528307
API_ID = 31759422
API_HASH = 'dd3d4b558b40b5c7e0ef513aeef8bd9f'
PHONE = '+79826167749'
PASSWORD = '1505'
TARGET_BOT = '@bogatii_27_bot'

bot = telebot.TeleBot(BOT_TOKEN)
user_client = TelegramClient('user_session', API_ID, API_HASH)

# Хранилище состояний (простой FSM)
user_state = {}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def is_admin(m):
    return m.from_user.id == ADMIN_ID

def run_async(coro):
    """Запуск асинхронных функций Telethon в отдельном потоке или цикле"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# --- КЛАВИАТУРА ---
def main_menu():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔗 Привязать аккаунт", callback_data="auth"))
    markup.row(types.InlineKeyboardButton("📊 Статус", callback_data="status"))
    markup.row(types.InlineKeyboardButton("🔎 Сделать запрос", callback_data="query"))
    return markup

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def start(m):
    if not is_admin(m): return
    bot.send_message(m.chat.id, "💎 Панель управления OSINT-ботом", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not is_admin(call): return
    
    if call.data == "status":
        authorized = run_async(user_client.is_user_authorized()) if user_client.is_connected() else False
        text = "🟢 Аккаунт готов" if authorized else "🔴 Требуется авторизация"
        bot.answer_callback_query(call.id, text, show_alert=True)

    elif call.data == "auth":
        bot.send_message(call.message.chat.id, "⏳ Проверяю соединение...")
        run_async(user_client.connect())
        if run_async(user_client.is_user_authorized()):
            bot.send_message(call.message.chat.id, "✅ Аккаунт уже привязан!")
        else:
            run_async(user_client.send_code_request(PHONE))
            user_state[call.message.chat.id] = 'wait_code'
            bot.send_message(call.message.chat.id, "📩 Введи код подтверждения из Telegram:")

    elif call.data == "query":
        user_state[call.message.chat.id] = 'wait_query'
        bot.send_message(call.message.chat.id, "📝 Отправь данные для поиска (ID/Phone/User):")

@bot.message_handler(func=lambda m: is_admin(m))
def handle_text(m):
    state = user_state.get(m.chat.id)

    # Ввод кода подтверждения
    if state == 'wait_code':
        try:
            run_async(user_client.sign_in(PHONE, m.text))
            bot.send_message(m.chat.id, "✅ Вход выполнен!")
        except errors.SessionPasswordNeededError:
            run_async(user_client.sign_in(password=PASSWORD))
            bot.send_message(m.chat.id, "✅ Вход выполнен (2FA)!")
        except Exception as e:
            bot.send_message(m.chat.id, f"❌ Ошибка: {e}")
        user_state[m.chat.id] = None

    # Ввод запроса для Шерлока
    elif state == 'wait_query':
        status_msg = bot.send_message(m.chat.id, "⏳ Работаю с ботом...")
        
        async def perform_search():
            if not user_client.is_connected():
                await user_client.connect()
            
            await user_client.send_message(TARGET_BOT, '/start')
            await asyncio.sleep(3)

            # Клики по кнопкам
            async for msg in user_client.iter_messages(TARGET_BOT, limit=1):
                await msg.click(text="Искать")
            await asyncio.sleep(2)

            async for msg in user_client.iter_messages(TARGET_BOT, limit=1):
                await msg.click(text="Telegram (Шерлок)")
            await asyncio.sleep(1)

            # Отправка самого запроса
            await user_client.send_message(TARGET_BOT, m.text)
            bot.edit_message_text("⏳ Жду ответ (15 сек)...", m.chat.id, status_msg.message_id)
            await asyncio.sleep(15)

            # Сбор результата
            res = []
            async for msg in user_client.iter_messages(TARGET_BOT, limit=2):
                if msg.text: res.append(msg.text)
            return "\n\n---\n\n".join(res)

        try:
            result_text = run_async(perform_search())
            bot.send_message(m.chat.id, f"🎯 **Результат:**\n\n{result_text}")
        except Exception as e:
            bot.send_message(m.chat.id, f"❌ Ошибка поиска: {e}")
        
        user_state[m.chat.id] = None

# Запуск бота
if __name__ == '__main__':
    print("[*] Бот управления запущен...")
    bot.infinity_polling()