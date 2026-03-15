import asyncio
import re
import time

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

from utils import user_link
import game


bot = Bot(
    TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

queue_states = {}
pending_queue_input = set()

admin_sessions = set()
pending_admin_login = set()
pending_broadcast = set()

known_chats = set()

QUEUE_TIMEOUT = 900
QUEUE_TURN_TIMEOUT = 90


# ---------- КНОПКИ ----------

def game_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Посмотреть слово", callback_data="show"),
                InlineKeyboardButton(text="Новое слово", callback_data="new")
            ]
        ]
    )


def help_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Правила", callback_data="help_rules")],
            [InlineKeyboardButton(text="🎮 Начать игру", callback_data="help_game")]
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


def queue_ready():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я готов!", callback_data="queue_ready")]
        ]
    )


def admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Сделать объявление", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats")]
        ]
    )


# ---------- ВСПОМОГАТЕЛЬНЫЕ ----------

def normalize(text):
    return text.lower().replace("ё", "е").replace("-", "").strip()


def parse_queue(text):

    usernames = re.findall(r'@\w+', text)

    seen = set()
    result = []

    for u in usernames:
        if u.lower() not in seen:
            seen.add(u.lower())
            result.append(u)

    return result


# ---------- ОЧЕРЕДЬ ----------

async def start_queue_turn(chat):

    state = queue_states.get(chat)

    if not state or not state["users"]:
        return

    username = state["users"][state["index"]]

    state["waiting"] = True
    state["current"] = username
    state["last_activity"] = time.time()

    await bot.send_message(
        chat,
        f"Очередь: {username}\nУ него есть 90 секунд",
        reply_markup=queue_ready(),
        disable_web_page_preview=True
    )

    async def timeout():

        await asyncio.sleep(QUEUE_TURN_TIMEOUT)

        s = queue_states.get(chat)

        if not s or not s["waiting"]:
            return

        await bot.send_message(
            chat,
            "Игрок пропущен (AFK)",
            disable_web_page_preview=True
        )

        s["waiting"] = False
        s["index"] = (s["index"] + 1) % len(s["users"])

        await start_queue_turn(chat)

    state["task"] = asyncio.create_task(timeout())


async def next_queue(chat):

    state = queue_states.get(chat)

    if not state:
        return

    state["waiting"] = False
    state["index"] = (state["index"] + 1) % len(state["users"])

    await start_queue_turn(chat)


async def queue_afk_checker():

    while True:

        now = time.time()

        for chat, state in list(queue_states.items()):

            if now - state["last_activity"] > QUEUE_TIMEOUT:

                await bot.send_message(
                    chat,
                    "Очередь удалена из-за неактивности",
                    disable_web_page_preview=True
                )

                queue_states.pop(chat)

        await asyncio.sleep(60)


# ---------- HELP ----------

@dp.message(Command("help"))
async def help_cmd(message: Message):

    await message.answer(
        "ℹ️<b>Помощь по боту</b>\n\n"
        "- Узнать правила: /rules\n"
        "- Сообщить об ошибке/предложить идею: @scripterworkss\n"
        "- Стать спонсором: @scr1re\n"
        "- Инфо: @CroCodil21bot\n\n"
        "<i>При активном поиске ошибок вы гарантированно получите звезды Telegram!</i>\n\n"
        "Beta V. 0.03.45",
        reply_markup=help_menu(),
        disable_web_page_preview=True
    )


@dp.callback_query(F.data == "help_rules")
async def help_rules(callback: CallbackQuery):

    await rules_cmd(callback.message)


@dp.callback_query(F.data == "help_game")
async def help_game(callback: CallbackQuery):

    await game_cmd(callback.message)


# ---------- RULES ----------

@dp.message(Command("rules"))
async def rules_cmd(message: Message):

    await message.answer(
        "▶️<b>Правила</b>\n\n"
        "«КроКодил» — игра на объяснение слов и фраз с помощью слов!\n"
        "В игре может участвовать от 2 человек — можно играть индивидуально или командами.\n\n"
        "В игре существует режим очереди, система бонусов и другие механики.\n\n"
        "<b>Краткое объяснение команд:</b>\n"
        "/game — начать раунд\n"
        "/rating — рейтинг чата\n"
        "/help — <i>помощь по боту</i>\n"
        "/rules — правила игры\n"
        "/stats — личная статистика\n"
        "/bonus — использовать бонус\n"
        "/queue — настройки очереди\n"
        "/admin — панель управления (admins only)",
        disable_web_page_preview=True
    )


# ---------- GAME ----------

@dp.message(Command("game"))
async def game_cmd(message: Message):

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
        f"{user_link(user)} начинает раунд!",
        reply_markup=game_kb(),
        disable_web_page_preview=True
    )


# ---------- КНОПКИ ИГРЫ (АЛЕРТ) ----------

@dp.callback_query(F.data == "show")
async def show_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id != g["leader"]:
        await callback.answer("Ты не ведущий!", show_alert=True)
        return

    await callback.answer(
        f"Слово: {g['word']}",
        show_alert=True
    )


@dp.callback_query(F.data == "new")
async def new_word(callback: CallbackQuery):

    chat = callback.message.chat.id
    user = callback.from_user

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id != g["leader"]:
        await callback.answer("Ты не ведущий!", show_alert=True)
        return

    game.new_word(chat)

    g = game.games.get(chat)

    await callback.answer(
        f"Новое слово: {g['word']}",
        show_alert=True
    )


# ---------- GUESS ----------

@dp.message()
async def guess(message: Message):

    chat = message.chat.id
    user = message.from_user
    text = message.text

    if not game.is_running(chat):
        return

    g = game.games.get(chat)

    if user.id == g["leader"]:
        return

    if normalize(text) == normalize(g["word"]):

        await add_guess(user, chat)
        await add_explained(g["leader"], chat)

        await message.answer(
            f"{user_link(user)} угадал слово <b>{g['word']}</b>",
            disable_web_page_preview=True
        )

        game.finish_game(chat)

        if chat in queue_states:
            await next_queue(chat)


# ---------- ЗАПУСК ----------

async def main():

    await init_db()

    asyncio.create_task(queue_afk_checker())

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
