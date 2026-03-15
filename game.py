import random
import time
from config import ROUND_TIMEOUT, WORDS_FILE

games = {}

# 15 минут
LEAD_TIMEOUT = 900


def load_words():

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return [i.strip() for i in f if i.strip()]


words = load_words()


def start_game(chat_id, leader_id):

    word = random.choice(words)

    games[chat_id] = {
        "leader": leader_id,
        "word": word,
        "finished": False,
        "start": time.time(),
        "leader_taken": True
    }


def new_word(chat_id):

    games[chat_id]["word"] = random.choice(words)

    return games[chat_id]["word"]


def get_word(chat_id):
    return games[chat_id]["word"]


def finish_game(chat_id):

    if chat_id in games:
        games[chat_id]["finished"] = True


def is_running(chat_id):

    if chat_id not in games:
        return False

    game = games[chat_id]

    # если игра уже закончена
    if game["finished"]:
        return False

    # если прошло время раунда — завершаем его
    if time.time() - game["start"] > ROUND_TIMEOUT:
        game["finished"] = True
        return False

    return True


# проверка кнопки "Хочу быть ведущим!"
def can_take_leader(chat_id):

    if chat_id not in games:
        return True

    game = games[chat_id]

    # если раунд закончился
    if game["finished"]:
        return True

    # если прошло больше 15 минут
    if time.time() - game["start"] > LEAD_TIMEOUT:
        return True

    return False