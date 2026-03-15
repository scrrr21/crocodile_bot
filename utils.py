def user_link(user):

    name = user.full_name

    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'

    return name


def win_word(n):

    if n % 10 == 1 and n % 100 != 11:
        return "победа"

    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "победы"

    return "побед"