"""
Управление кешем пользователя
"""

import hashlib
from typing import Any, Callable
import aiosqlite

__all__ = ["Cache"]


class SQLite:
    """Взаимодействие с SQLite"""

    def __init__(self, dbfile: str) -> None:
        self.dbfile = dbfile

    def sql_get_db(self):
        """
        Декоратор для поучения соединение с БД

        dbfile: Путь к Бд SQLite
        """
        def wrapper(func: Callable):
            async def transaction_dec(*arg, **kwargs) -> tuple[bool | BaseException, Any]:
                async with aiosqlite.connect(self.dbfile) as db:
                    kwargs['db'] = db
                    return await func(*arg, **kwargs)
            return transaction_dec
        return wrapper

    async def sql_write(self, query: str, args: dict = {}, RETURNING: bool = False) -> bool:
        """Выполнить команду на запись

        :param dbfile: файл к БД
        :param query: Команда
        :param args: Аргументы в строку запроса
        :param RETURNING: Нужно ли получать ответ после вставки записи
        """
        async with aiosqlite.connect(self.dbfile) as db:
            if RETURNING:
                res = await db.execute(query, args)
                r = await res.fetchone()
                await db.commit()
                return r
            else:
                await db.execute(query, args)
                return await db.commit()

    async def sql_read(self, query: str, args: dict = {}) -> list[tuple]:
        """Выполнить команду на чтение

        :param dbfile: файл к БД
        :param query: SQL запрос
        """
        async with aiosqlite.connect(self.dbfile) as db:
            async with db.execute(query, args) as cursor:
                return await cursor.fetchall()


class Cache:

    def __init__(self, dbfile: str) -> None:
        self.dbfile = dbfile
        self.sql = SQLite()

    async def cache_add_key(self, user_name: str, key: str, value: str) -> tuple[int, str]:
        """
        Добавить если его нет, или обновить, если хеш разный, ключ в пользовательском кеши

        return:
            - (-1) - Запись уже существует, но она не обновлена
            - (-2) - Запись уже существует, и она обновлена
            - (>=0)- `idkey` новой записи
        """
        #
        # Проверяем наличия пользователя в Таблице users, если его нет то добавляем
        #
        iduser: int = await Cache._check_or_add_user(user_name)
        #
        # Получаем хеш значения
        #
        hash_sha256: str = hashlib.sha256(value.encode('utf-8')).hexdigest()
        # Проверка наличие такого хеша
        query = """
        select count(1),coalesce(d.idkey,-1),m.idkey
        from main m
        left join data d on m.idkey = d.idkey and d.hash = :hash
        where m.user=:iduser and m.key=:key
        """
        is_exist_row = await self.sql.sql_read(query, {"iduser": iduser, "key": key, "hash": hash_sha256})
        # Если запись не существует в БД
        if is_exist_row[0][0] == 0:
            # Сначала записываем пользовательские данные, получем id новой записи
            idkey = await self.sql.sql_write("insert into data (json,hash) values (:value,:hash) RETURNING idkey;", {"value": value, "hash": hash_sha256}, RETURNING=True)
            idkey: int = idkey[0]
            if idkey:
                #
                # Потом записываем в связующую таблицу
                #
                query = f"""insert into main (user, key, idkey) VALUES (:user, :key, :idkey)"""
                await self.sql.sql_write(query, {"user": iduser, "key": key, "idkey": idkey})
                return idkey, "idkey новой записи"
            else:
                raise ValueError("Ошибка при добавление в таблицу 'data'")
        # Если запись существует, но хеш разный
        elif is_exist_row[0][1] < 0:
            if not is_exist_row[0][2]:
                raise ValueError('Нет idkey')
            # Обновляем только данные, не трогая связующие таблицу
            await self.sql.sql_write("""update data set json=:value, hash=:hash where idkey=:idkey""", {"value": value, "hash": hash_sha256, "idkey": is_exist_row[0][2]})
            return -2, "Запись уже существует, и она обновлена"
        # Если запись существует, и хеш одинаковый
        else:
            return -1, "Запись уже существует, но она не обновлена"

    async def cache_read_key(self, user_name: str, key: str) -> str:
        """
        Прочитать ключ из пользовательского кеша
        """
        query = """
        select d.json
        from main
        join data d on d.idkey=main.idkey
        join users u on u.name=:user
        where key=:key
        """
        res = await self.sql.sql_read(query, {"user": user_name, "key": key})
        if res:
            return res[0][0]
        # Выясняем почему пустой ответ
        else:
            # Проверяем наличие пользователя
            if not await Cache._check_or_add_user(user_name, CREATE_NEW_USER=False):
                raise ValueError(f"Пользователь '{user_name}' не существует")
            # Проверяем наличие ключа
            if not await Cache._check_exist_key(user_name, key):
                raise ValueError(f"Ключ'{key}' не существует")
        return res

    async def _createBaseTableIfNotExist(self):
        """
        Создать базовые таблицы в БД, если их нет
        """
        query = """
        SELECT
            name
        FROM
            sqlite_schema
        WHERE
            type ='table' AND
            name NOT LIKE 'sqlite_%';
        """
        res = await self.sql.sql_read(query)

        if not res and [x[0] for x in res] != ['users', 'main', 'data']:
            # Хранение имени пользователя
            users = """
            CREATE TABLE IF NOT EXISTS users (
                iduser INTEGER NOT NULL,
                name   TEXT    NOT NULL,

                PRIMARY KEY (iduser)
            );
            """
            # Связка ключа с данными
            main = """
            CREATE TABLE IF NOT EXISTS main (
                user  INTEGER  NOT NULL,
                key   TEXT     NOT NULL,
                idkey INTEGER  NOT NULL,

                PRIMARY KEY (user,key)
            );
            """
            # Хранение данных
            data = """
            CREATE TABLE IF NOT EXISTS data (
                idkey INTEGER NOT NULL,
                hash  TEXT,
                json  TEXT,

                PRIMARY KEY (idkey)
            );
            """
            # Дополнительные индексы в таблицы
            index = """CREATE UNIQUE INDEX users_name ON users (name);"""
            # По умолчанию создаем пользователя `base`
            default_user = """insert into users (name) values ('base');"""
            #
            #
            #
            for table in users, main, data, *index.split(';'), *default_user.split(';'):
                await self.sql.sql_write(table)
            return True
        return False

    @staticmethod
    async def _check_or_add_user(self, user_name: str, CREATE_NEW_USER=True) -> int:
        iduser = await self.sql.sql_read("select iduser from users where name=:name", {"name": user_name})
        # Если такого пользователя нет
        if not iduser:
            # и разрешено создание нового пользователя
            if CREATE_NEW_USER:
                # То создаем нового пользователя
                iduser = await self.sql.sql_write("insert into users (name) values (:name) RETURNING iduser;", {"name": user_name}, RETURNING=True)
                iduser: int = iduser[0]
            else:
                return None
        else:
            iduser: int = iduser[0][0]
        return iduser

    @staticmethod
    async def _check_exist_key(self, user_name: str, key: str) -> int:
        res = await self.sql.sql_read('select count(1) from main where user=:user and  key=:key', {"user": user_name, "key": key})
        if res:
            return res[0][0]
