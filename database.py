import aiosqlite

DB_NAME = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER,
            chat_id INTEGER,
            name TEXT,
            guessed INTEGER DEFAULT 0,
            led INTEGER DEFAULT 0,
            explained INTEGER DEFAULT 0,
            bonuses INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
        """)
        await db.commit()


async def add_guess(user, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT INTO stats (user_id, chat_id, name, guessed)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET guessed = guessed + 1,
        name = excluded.name
        """, (user.id, chat_id, user.full_name))

        await db.commit()

        # проверяем каждые 10 правильных ответов
        cursor = await db.execute("""
        SELECT guessed FROM stats
        WHERE user_id = ? AND chat_id = ?
        """, (user.id, chat_id))

        row = await cursor.fetchone()

        if row and row[0] > 0 and row[0] % 10 == 0:
            await db.execute("""
            UPDATE stats
            SET bonuses = bonuses + 1
            WHERE user_id = ? AND chat_id = ?
            """, (user.id, chat_id))

            await db.commit()


async def add_leader(user, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT INTO stats (user_id, chat_id, name, led)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, chat_id)
        DO UPDATE SET led = led + 1,
        name = excluded.name
        """, (user.id, chat_id, user.full_name))

        await db.commit()


async def add_explained(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        UPDATE stats
        SET explained = explained + 1
        WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))

        await db.commit()


async def get_bonuses(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT bonuses
        FROM stats
        WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))

        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else 0


async def use_bonus(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT bonuses
        FROM stats
        WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))

        row = await cursor.fetchone()

        if not row or row[0] is None or row[0] < 1:
            return False

        await db.execute("""
        UPDATE stats
        SET bonuses = bonuses - 1
        WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))

        await db.commit()
        return True


async def get_top(chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT name, guessed
        FROM stats
        WHERE chat_id = ?
        ORDER BY guessed DESC
        LIMIT 10
        """, (chat_id,))

        return await cursor.fetchall()


async def get_chat_stats(user_id, chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT led, explained, guessed, bonuses
        FROM stats
        WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))

        row = await cursor.fetchone()

        if not row:
            return (0, 0, 0, 0)

        return tuple(0 if value is None else value for value in row)


async def get_global_stats(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT SUM(led), SUM(explained), SUM(guessed), SUM(bonuses)
        FROM stats
        WHERE user_id = ?
        """, (user_id,))

        row = await cursor.fetchone()

        if not row:
            return (0, 0, 0, 0)

        return tuple(0 if value is None else value for value in row)