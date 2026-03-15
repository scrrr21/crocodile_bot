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
    get_bonuses,
    use_bonus
)

from utils import user_link
import game


bot = Bot(
    TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

admin_wait = set()


# ---------- КНОПКИ ----------

def game_kb():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Посмотреть слово",
                    callback_data="show_word"
                ),
                InlineKeyboardButton(
                    text="Новое слово",
                    callback_data="new_word"
                )
            ]
        ]
    )


def new_leader_kb():

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

def normalize(text: str):

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
            "Раунд уже идет",
            disable_web_page_preview=True
        )
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await message.answer(
        f"{user_link(user)} объясняет слово!",
        reply_markup=game_kb(),
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

    if not g:
        return

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

    if not g:
        return

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
            "Раунд уже идет",
            show_alert=True
        )
        return

    game.start_game(chat, user.id)

    await add_leader(user, chat)

    await callback.message.answer(
        f"{user_link(user)} объясняет слово!",
        reply_markup=game_kb(),
        disable_web_page_preview=True
    )


# ---------- КОМАНДЫ ----------

@dp.message(Command("rating"))
async def cmd_rating(message: Message):

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

    await message.answer(
        text,
        disable_web_page_preview=True
    )


@dp.message(Command("bonus"))
async def cmd_bonus(message: Message):

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
            "У тебя нет бонусов",
            disable_web_page_preview=True
        )
        return

    await use_bonus(user.id, chat)

    hint = g["word"][:2] + "..."

    await message.answer(
        f"Подсказка: {hint}",
        disable_web_page_preview=True
    )


@dp.message(Command("queue"))
async def cmd_queue(message: Message):

    await message.answer(
        "Меню очереди:",
        reply_markup=queue_menu(),
        disable_web_page_preview=True
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):

    admin_wait.add(message.from_user.id)

    await message.answer(
        "Введите admin код:",
        disable_web_page_preview=True
    )


# ---------- УГАДЫВАНИЕ ----------

@dp.message(F.text & ~F.text.startswith("/"))
async def guess_handler(message: Message):

    chat = message.chat.id
    user = message.from_user
    text = message.text

    # ADMIN LOGIN

    if user.id in admin_wait:

        if text == ADMIN_CODE:

            admin_wait.remove(user.id)

            await message.answer(
                "Админ панель активирована",
                disable_web_page_preview=True
            )

        else:

            await message.answer(
                "Неверный код",
                disable_web_page_preview=True
            )

        return

    # GAME

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if not g:
        return

    if user.id == g["leader"]:
        return

    if normalize(text) == normalize(g["word"]):

        await add_guess(user, chat)
        await add_explained(g["leader"], chat)

        await message.answer(
            f"{user_link(user)} отгадал(-а) слово <b>{g['word']}</b>",
            reply_markup=new_leader_kb(),
            disable_web_page_preview=True
        )

        game.finish_game(chat)


# ---------- ЗАПУСК ----------

async def main():

    await init_db()

    me = await bot.get_me()

    print("Бот запущен:", me.username)

    while True:

        try:

            await dp.start_polling(bot)

        except Exception as e:

            print("Ошибка:", e)

            await asyncio.sleep(5)


if __name__ == "__main__":

    asyncio.run(main())
