import logging
import base64
from io import BytesIO
from aiogram.types import FSInputFile, BufferedInputFile
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio

API_TOKEN = "BOT_TOKEN"
SD_API_URL = "URL"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def generate_image(prompt: str, negative_prompt: str = "") -> BytesIO:
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": 20,
        "cfg_scale": 7,
        "width": 512,
        "height": 512,
        "sampler_name": "Euler a",
        "seed": -1,
        "enable_hr": False
    } 
    # Используем синхронный запрос, запускаем в пуле потоков, чтобы не блокировать asyncio
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.post(SD_API_URL, json=payload)
    )
    response.raise_for_status()
    result = response.json()
    img_data = result["images"][0]
    img_bytes = base64.b64decode(img_data)
    return BytesIO(img_bytes)

@dp.message(Command(commands=["start", "help"]))
async def send_welcome(message: types.Message):
    await message.answer("Привет! Отправь любой текст — я сгенерирую изображение по промпту. \n [Главный объект], [описание внешности/формы/позы], [действие], [окружение], [стиль], [освещение], [цветовая палитра], [ракурс], [дополнительно]")

@dp.message()
async def handle_prompt(message: types.Message):
    prompt = message.text.strip()
    if not prompt:
        await message.answer("Обнаружен пустой промпт.")
        return

    await message.answer("Генерирую изображение, подожди немного...")

    try:
        image_io = await generate_image(prompt)
        image_io.name = "result.png"
        image_io.seek(0)
        input_file = BufferedInputFile(file=image_io.read(), filename="result.png")

        await message.answer_photo(photo=input_file, caption=f"Вот изображение для промпта:\n{prompt}")
        print(f"[LOG] Отправлено пользователю: {message.from_user.full_name} "
              f"(@{message.from_user.username}, ID: {message.from_user.id})\n"
              f"Промпт: {prompt}\n")

    except Exception as e:
        await message.answer(f"Ошибка при генерации: {e}")
        print(f"[ERROR] Ошибка у пользователя {message.from_user.id}: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
