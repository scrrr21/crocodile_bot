import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
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

import game
from utils import user_link


bot = Bot(
    TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

admin_wait = set()

queue_data = {}


# ---------- КНОПКИ ----------

def game_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👁 Посмотреть слово",
                    callback_data="show_word"
                ),
                InlineKeyboardButton(
                    text="🔄 Новое слово",
                    callback_data="new_word"
                )
            ]
        ]
    )


def new_leader_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Хочу быть ведущим",
                    callback_data="become_leader"
                )
            ]
        ]
    )


def queue_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Встать в очередь",
                    callback_data="queue_join"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Показать очередь",
                    callback_data="queue_show"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Очистить очередь",
                    callback_data="queue_clear"
                )
            ]
        ]
    )


# ---------- УТИЛИТЫ ----------

def normalize(text):

    return (
        text.lower()
        .replace("ё", "е")
        .replace("-", "")
        .strip()
    )


# ---------- GAME ----------

@dp.message(Command("game"))
async def cmd_game(message: Message):

    chat = message.chat.id
    user = message.from_user

    if game.is_running(chat):

        await message.answer(
            "Раунд уже идет!",
            disable_web_page_preview=True
        )
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await message.answer(
        f"{user_link(user)} объясняет слово!",
        reply_markup=game_keyboard(),
        disable_web_page_preview=True
    )


# ---------- CALLBACK КНОПКИ ----------

@dp.callback_query(F.data == "show_word")
async def cb_show_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id != g["leader"]:

        await callback.answer(
            "Ты не ведущий!",
            show_alert=True
        )
        return

    await callback.answer(
        f"Слово: {g['word']}",
        show_alert=True
    )


@dp.callback_query(F.data == "new_word")
async def cb_new_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id != g["leader"]:

        await callback.answer(
            "Ты не ведущий!",
            show_alert=True
        )
        return

    game.new_word(chat)

    g = game.games.get(chat)

    await callback.answer(
        f"Новое слово: {g['word']}",
        show_alert=True
    )


@dp.callback_query(F.data == "become_leader")
async def cb_new_leader(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if game.is_running(chat):

        await callback.answer(
            "Раунд уже идет!",
            show_alert=True
        )
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await callback.message.answer(
        f"{user_link(user)} объясняет слово!",
        reply_markup=game_keyboard(),
        disable_web_page_preview=True
    )


# ---------- RATING ----------

@dp.message(Command("rating"))
async def cmd_rating(message: Message):

    top = await get_top(message.chat.id)

    if not top:

        await message.answer(
            "Рейтинг пока пуст.",
            disable_web_page_preview=True
        )
        return

    text = "🏆 <b>Рейтинг игроков</b>\n\n"

    for i, (name, score) in enumerate(top, start=1):

        medal = ""

        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"

        text += f"{medal} <b>{i}.</b> {name} — <b>{score}</b>\n"

    await message.answer(
        text,
        disable_web_page_preview=True
    )


# ---------- STATS ----------

@dp.message(Command("stats"))
async def cmd_stats(message: Message):

    user = message.from_user

    stats = await get_chat_stats(user.id, message.chat.id)

    explained = stats["explained"]
    guessed = stats["guessed"]
    leader = stats["leader"]

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👤 Игрок: {user_link(user)}\n\n"
        f"🎤 Ведущий: <b>{leader}</b>\n"
        f"🧠 Угадано: <b>{guessed}</b>\n"
        f"💬 Объяснено: <b>{explained}</b>"
    )

    await message.answer(
        text,
        disable_web_page_preview=True
    )


# ---------- BONUS ----------

@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):

    chat = message.chat.id
    user = message.from_user

    if not game.is_running(chat):

        await message.answer(
            "Сейчас нет активного раунда.",
            disable_web_page_preview=True
        )
        return

    g = game.games.get(chat)

    if user.id == g["leader"]:

        await message.answer(
            "Ведущий не может использовать бонус.",
            disable_web_page_preview=True
        )
        return

    bonuses = await get_bonuses(user.id, chat)

    if bonuses <= 0:

        await message.answer(
            "У тебя нет бонусов.",
            disable_web_page_preview=True
        )
        return

    await use_bonus(user.id, chat)

    hint = g["word"][:2] + "..."

    await message.answer(
        f"💡 Подсказка: <b>{hint}</b>",
        disable_web_page_preview=True
    )


# ---------- QUEUE ----------

@dp.message(Command("queue"))
async def cmd_queue(message: Message):

    await message.answer(
        "⚙️ <b>Меню очереди</b>",
        reply_markup=queue_keyboard(),
        disable_web_page_preview=True
    )


@dp.callback_query(F.data == "queue_join")
async def queue_join(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    queue = queue_data.setdefault(chat, [])

    if user.id not in queue:
        queue.append(user.id)

    await callback.answer("Ты добавлен в очередь!")


@dp.callback_query(F.data == "queue_show")
async def queue_show(callback: CallbackQuery):

    chat = callback.message.chat.id

    queue = queue_data.get(chat, [])

    if not queue:

        await callback.message.answer("Очередь пустая.")
        return

    text = "📜 <b>Очередь игроков</b>\n\n"

    for i, uid in enumerate(queue, start=1):

        text += f"{i}. <code>{uid}</code>\n"

    await callback.message.answer(text)


@dp.callback_query(F.data == "queue_clear")
async def queue_clear(callback: CallbackQuery):

    chat = callback.message.chat.id

    queue_data[chat] = []

    await callback.answer("Очередь очищена")


# ---------- ADMIN ----------

@dp.message(Command("admin"))
async def cmd_admin(message: Message):

    admin_wait.add(message.from_user.id)

    await message.answer("Введите admin код:")


# ---------- УГАДЫВАНИЕ ----------

@dp.message(F.text & ~F.text.startswith("/"))
async def guess_handler(message: Message):

    chat = message.chat.id
    user = message.from_user
    text = message.text

    if user.id in admin_wait:

        if text == ADMIN_CODE:

            admin_wait.remove(user.id)

            await message.answer("Админ доступ получен")

        else:

            await message.answer("Неверный код")

        return

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id == g["leader"]:
        return

    if normalize(text) == normalize(g["word"]):

        await add_guess(user, chat)
        await add_explained(g["leader"], chat)

        await message.answer(
            f"{user_link(user)} отгадал(-а) слово <b>{g['word']}</b>",
            reply_markup=new_leader_keyboard()
        )

        game.finish_game(chat)


# ---------- ЗАПУСК ----------

async def main():

    await init_db()

    me = await bot.get_me()

    print("Bot started:", me.username)

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
