import asyncio
import re
import time

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from config import TOKEN, ADMIN_CODE
from database import (
    init_db,
    add_guess,
    add_leader,
    add_explained,
    get_top,
    get_chat_stats,
    get_bonuses,
    use_bonus
)

from utils import user_link
import game


bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

queue_states = {}

admin_sessions = set()

QUEUE_TIMEOUT = 900
QUEUE_TURN_TIMEOUT = 90


# ---------- КНОПКИ ----------

def game_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Посмотреть слово", callback_data="show_word"),
                InlineKeyboardButton(text="Новое слово", callback_data="new_word")
            ]
        ]
    )


def new_leader_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Хочу быть ведущим", callback_data="become_leader")]
        ]
    )


def admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Объявление", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
        ]
    )


def queue_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать очередь", callback_data="queue_create")],
            [InlineKeyboardButton(text="Встать в очередь", callback_data="queue_join")],
            [InlineKeyboardButton(text="Какая очередь?", callback_data="queue_list")],
            [InlineKeyboardButton(text="Остановить очередь", callback_data="queue_stop")]
        ]
    )


# ---------- УТИЛИТЫ ----------

def normalize(text):
    return text.lower().replace("ё", "е").strip()


# ---------- GAME ----------

@dp.message(Command("game"))
async def game_cmd(message: Message):

    chat = message.chat.id
    user = message.from_user

    if not user:
        return

    if game.is_running(chat):
        await message.answer(
            "Раунд уже идет",
            disable_web_page_preview=True
        )
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await message.answer(
        f"{user_link(user)} начинает раунд!",
        reply_markup=game_kb(),
        disable_web_page_preview=True
    )


# ---------- КНОПКИ СЛОВ ----------

@dp.callback_query(F.data == "show_word")
async def show_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if not g:
        return

    if user.id != g["leader"]:
        await callback.answer("Ты не ведущий!", show_alert=True)
        return

    await callback.answer(
        f"Слово: {g['word']}",
        show_alert=True
    )


@dp.callback_query(F.data == "new_word")
async def new_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if not g:
        return

    if user.id != g["leader"]:
        await callback.answer("Ты не ведущий!", show_alert=True)
        return

    game.new_word(chat)

    g = game.games.get(chat)

    await callback.answer(
        f"Новое слово: {g['word']}",
        show_alert=True
    )


# ---------- УГАДЫВАНИЕ ----------

@dp.message()
async def guess(message: Message):

    if not message.text:
        return

    chat = message.chat.id
    user = message.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if not g:
        return

    if user.id == g["leader"]:
        return

    if normalize(message.text) == normalize(g["word"]):

        await add_guess(user, chat)
        await add_explained(g["leader"], chat)

        await message.answer(
            f"{user_link(user)} угадал слово <b>{g['word']}</b>",
            reply_markup=new_leader_kb(),
            disable_web_page_preview=True
        )

        game.finish_game(chat)


# ---------- НОВЫЙ ВЕДУЩИЙ ----------

@dp.callback_query(F.data == "become_leader")
async def become_leader(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not user:
        return

    if game.is_running(chat):
        await callback.answer("Раунд уже идет", True)
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await callback.message.answer(
        f"{user_link(user)} начинает новый раунд!",
        reply_markup=game_kb(),
        disable_web_page_preview=True
    )


# ---------- RATING ----------

@dp.message(Command("rating"))
async def rating_cmd(message: Message):

    top = await get_top(message.chat.id)

    if not top:
        await message.answer(
            "Пока нет рейтинга",
            disable_web_page_preview=True
        )
        return

    text = "<b>Рейтинг игроков</b>\n\n"

    for i, (name, score) in enumerate(top, start=1):
        text += f"{i}. {name} — {score}\n"

    await message.answer(text, disable_web_page_preview=True)


# ---------- BONUS ----------

@dp.message(Command("bonus"))
async def bonus_cmd(message: Message):

    chat = message.chat.id
    user = message.from_user

    if not game.is_running(chat):
        await message.answer(
            "Игра не идет",
            disable_web_page_preview=True
        )
        return

    g = game.games.get(chat)

    if user.id == g["leader"]:
        await message.answer(
            "Ты ведущий",
            disable_web_page_preview=True
        )
        return

    bonuses = await get_bonuses(user.id, chat)

    if bonuses <= 0:
        await message.answer(
            "Нет бонусов",
            disable_web_page_preview=True
        )
        return

    await use_bonus(user.id, chat)

    word = g["word"]

    hint = word[:2] + "..."

    await message.answer(
        f"Подсказка: {hint}",
        disable_web_page_preview=True
    )


# ---------- QUEUE ----------

@dp.message(Command("queue"))
async def queue_cmd(message: Message):

    await message.answer(
        "Настройки очереди:",
        reply_markup=queue_menu(),
        disable_web_page_preview=True
    )


# ---------- ADMIN ----------

@dp.message(Command("admin"))
async def admin_cmd(message: Message):

    await message.answer(
        "Введите admin код:",
        disable_web_page_preview=True
    )

    admin_sessions.add(message.from_user.id)


@dp.message()
async def admin_login(message: Message):

    user = message.from_user.id

    if user not in admin_sessions:
        return

    if message.text != ADMIN_CODE:

        await message.answer(
            "Неверный код",
            disable_web_page_preview=True
        )
        return

    admin_sessions.remove(user)

    await message.answer(
        "Админ панель",
        reply_markup=admin_menu(),
        disable_web_page_preview=True
    )


# ---------- ЗАПУСК ----------

async def main():

    await init_db()

    me = await bot.get_me()

    print("Бот запущен:", me.username)

    while True:

        try:
            await dp.start_polling(bot)

        except Exception as e:

            print("Ошибка polling:", e)

            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
