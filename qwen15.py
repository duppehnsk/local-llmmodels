import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.filters import Command
import asyncio
import time
import json

API_TOKEN = "BOT_TOKEN"
LMSTUDIO_URL = "URL"
MODEL_NAME = "qwen1.5-7b-chat"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Хранилище контекста для каждого пользователя
user_contexts = {}

def get_main_keyboard():
    """Создает основную клавиатуру с кнопкой сброса контекста"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Сбросить контекст")]
        ],
        resize_keyboard=True,  # Клавиатура подстраивается под размер экрана
        one_time_keyboard=False  # Клавиатура не скрывается после использования
    )
    return keyboard

async def query_lmstudio_chat_stream(user_id: int, prompt: str) -> tuple[str, int, float, float]:
    headers = {"Content-Type": "application/json"}
    
    # Получаем историю сообщений пользователя или создаем новую
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    
    # Добавляем новое сообщение пользователя в контекст
    user_contexts[user_id].append({"role": "user", "content": prompt})
    
    # Формируем payload с всей историей диалога
    payload = {
        "messages": user_contexts[user_id],
        "max_tokens": 1500,
        "temperature": 0.5,
        "stream": True
    }

    full_response = ""
    tokens_generated = 0
    start_time = time.time()
    first_token_time = None
    last_token_time = start_time

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LMSTUDIO_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data: '):
                            data_str = line[6:]  # Убираем 'data: '
                            if data_str == '[DONE]':
                                break
                            
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and len(data['choices']) > 0:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        token_content = delta['content']
                                        full_response += token_content
                                        tokens_generated += 1
                                        last_token_time = time.time()
                                        
                                        # Фиксируем время первого токена
                                        if first_token_time is None and tokens_generated == 1:
                                            first_token_time = last_token_time
                                            
                            except json.JSONDecodeError:
                                continue
                    
                    end_time = time.time()
                    total_time = end_time - start_time
                    
                    # Добавляем ответ ассистента в контекст
                    if full_response:
                        user_contexts[user_id].append({"role": "assistant", "content": full_response})
                    
                    # Вычисляем метрики
                    time_to_first_token = first_token_time - start_time if first_token_time else total_time
                    generation_time = end_time - (first_token_time if first_token_time else start_time)
                    
                    # Токенов в секунду (только время генерации, без ожидания первого токена)
                    tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0
                    
                    return full_response, tokens_generated, tokens_per_second, time_to_first_token, total_time
                else:
                    error_text = f"Ошибка сервера LM Studio: {resp.status}"
                    return error_text, 0, 0, 0, 0
    except Exception as e:
        error_text = f"Ошибка соединения: {str(e)}"
        return error_text, 0, 0, 0, 0

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    # Сбрасываем контекст при старте
    if user_id in user_contexts:
        user_contexts[user_id] = []
    
    welcome_text = (
        "Привет! Я бот с локальной моделью LM Studio.\n\n"
        "Отправь мне сообщение, и я отвечу!\n"
        "Используй кнопку 'Сбросить контекст' на клавиатуре для очистки истории диалога."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command(commands=["reset"]))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    user_contexts[user_id] = []
    await message.answer("Контекст диалога сброшен! 🧹", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔄 Сбросить контекст")
async def reset_context_handler(message: Message):
    user_id = message.from_user.id
    user_contexts[user_id] = []
    await message.answer("Контекст диалога сброшен! 🧹 История очищена.", reply_markup=get_main_keyboard())

@dp.message()
async def handle_message(message: Message):
    user_text = message.text
    user_id = message.from_user.id
    
    # Игнорируем нажатия на кнопку сброса (они обрабатываются отдельным хэндлером)
    if user_text == "🔄 Сбросить контекст":
        return
    
    if not user_text:
        await message.answer("Пожалуйста, отправь текстовое сообщение.", reply_markup=get_main_keyboard())
        return
    
    await message.chat.do('typing')
    
    # Получаем ответ с streaming
    response, tokens_count, tokens_per_second, first_token_time, total_time = await query_lmstudio_chat_stream(user_id, user_text)
    
    if response:
        # Формируем информацию о скорости
        speed_info = f"\n\n⚡ Скорость генерации: {tokens_per_second:.2f} токенов/сек"
        speed_info += f"\n⏱ Общее время: {total_time:.2f} сек"
        speed_info += f"\n🚀 Первый токен через: {first_token_time:.2f} сек"
        speed_info += f"\n🎯 Сгенерировано токенов: {tokens_count}"
        
        full_response = response + speed_info
        await message.answer(full_response, reply_markup=get_main_keyboard())
    else:
        await message.answer("Извините, ответ не получен.", reply_markup=get_main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
