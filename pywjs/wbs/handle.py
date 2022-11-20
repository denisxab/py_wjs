import abc
import json
import re
import time
from pathlib import Path
from typing import Optional
from pydantic import ValidationError
from websockets.legacy.server import WebSocketServerProtocol
from pywjs.wbs.logger import ABC_logger
from pywjs.wbs.allowed_func import Transaction, UserWbsFunc
from pywjs.wbs.subscribe import UserWbsSubscribe
from pywjs.wbs.cache import cache_add_key, cache_read_key, createBaseTableIfNotExist
from pywjs.wbs.schema import ClientsWbsRequest, ClientsWbsRequest_GetInfoServer_id, ClientsWbsRequest_Mod, ClientsWbsRequest_ModAlternatives, ServerWbsResponse, WbsResponseCode
# pip install jsonpickle
import jsonpickle

__all__ = ['WbsHandle']


# Переводить в UTF-8
jsonpickle.set_encoder_options('json', ensure_ascii=False)


class WbsHandle:
    """
    Реализация протокол взаимодействия клиентов с Python
    """

    @property
    @abc.abstractmethod
    # Доступные токены для подключения к серверу
    def allowed_token(self) -> set[str]: ...

    @property
    @abc.abstractmethod
    # Класс для хранения доступных функций
    def allowed_func(self) -> UserWbsFunc: ...

    @property
    @abc.abstractmethod
    # Класс для хранения доступных подписок
    def allowed_subscribe(self) -> UserWbsSubscribe: ...

    @property
    @abc.abstractmethod
    # Путь для БД с кешем пользователей
    # (если вам не нужно работать с кешем пользователей то не указывайте путь)
    def path_user_cache(self) -> Optional[Path]: ...

    @property
    @abc.abstractmethod
    # Логер
    def logger(self) -> ABC_logger: ...

    ############################################
    # Клиенты которые могут использовать сервер.
    _allowed_clients: set[str] = set()
    # Черный список для клиентов. Эти клиенты не смогут подключиться к серверу
    # на протяжение некоторого количества времени.
    _back_list: set[str] = set()
    # Через сколько секунд будут отчищен черный список.
    _wait_clear_back_list = 5.0
    # Хранит подписки клиентов.
    _subscribe_dist: dict[str, set] = dict()
    ############################################

    def __init__(self):
        # Список объектов из динамически импортированных модулей, в функции `WbsHandle._import_from_server`
        # Этот список будем использовать для исполнения произвольных команд, в
        # функции `WbsHandle._exec_command`
        self._from_import_dict: dict[str, object] = {}

    async def after_init(self):
        # Если указан путь для кеша пользователя, то инициализируем таблицы для
        # этого.
        if self.path_user_cache:
            # Инициализируем Таблицы для кеша пользователей, если их нет.
            await createBaseTableIfNotExist(dbfile=self.path_user_cache)
        return self

    async def handle(self, wbs: WebSocketServerProtocol, msg: str) -> tuple[str, str]:
        """
        Обработка запроса клиента

        return: (Ответ,Ошибки)
        """
        #######################################################################
        #
        # Валидация запроса клиента
        #
        try:
            request_obj = ClientsWbsRequest.parse_raw(msg)
        except ValidationError as e:
            # Если при парсинге возникла ошибка
            error = e.json()  # (ensure_ascii=False)
            return ServerWbsResponse(
                h_id=-1,
                uid_c=-1,
                code=WbsResponseCode.error_parse_request_clients.value,
                response="",
                t_send=time.time(),
                t_exec=0,
                error=error,
            ).json(ensure_ascii=False), error
        #######################################################################
        #
        # Аутентификация клиента по токену
        #
        wbs_uuid: str = wbs.id.hex
        # Проверка аутентификации подключения, через проверку токена
        if not self._check_token(wbs_uuid, request_obj):
            return ServerWbsResponse(
                h_id=-1,
                uid_c=-1,
                code=WbsResponseCode.token_error.value,
                response="",
                t_send=request_obj.t_send,
                t_exec=0,
                error=f'Не верный токен. Выполнение команд запрещено. Ваше подключение будет заблокированное в течение: {self._wait_clear_back_list} секунд'
            ).json(ensure_ascii=False), ''
        #######################################################################
        #
        # Обработка запроса клиента
        #
        try:
            response: str = ""
            # Обработка модификаторов запроса
            match request_obj.mod:
                case ClientsWbsRequest_Mod.info:
                    # Команда на получения информации об сервере
                    match request_obj.body.id_r:
                        case ClientsWbsRequest_GetInfoServer_id.help_allowed:
                            # Список доступных функций
                            response = self._help_allowed()
                        case ClientsWbsRequest_GetInfoServer_id.check_token: response = '["Successful Token"]'
                        case ClientsWbsRequest_GetInfoServer_id.info_event:
                            # Информация о "событиях сервера"
                            response = self._help_events()
                        case _:
                            raise ValueError(
                                "Не доступный модификатор для информации об сервере")
                case ClientsWbsRequest_Mod.func:
                    # Выполняем доступную функцию
                    response = await self._func(
                        request_obj.body.n_func,
                        request_obj.body.args,
                        request_obj.body.kwargs
                    )
                case ClientsWbsRequest_ModAlternatives.transaction_func:
                    # Выполняем доступную функцию в режиме транзакции
                    response = await self._transaction_func(
                        wbs,
                        request_obj,
                        request_obj.body.n_func,
                        request_obj.body.args,
                        request_obj.body.kwargs
                    )
                case ClientsWbsRequest_Mod.exec:
                    # Выполняем произвольную команду
                    response = self._exec(request_obj.body.exec)
                case ClientsWbsRequest_Mod.import_from_server:
                    # Выполняем импорты переданных библиотек
                    response = '["Successful Import"]'
                    self._import_from_server(
                        request_obj.body.import_sts_exe)
                case ClientsWbsRequest_Mod.event_create:
                    # Клиент создает "событие на сервере"
                    # Выполняем доступную функцию
                    response = json.dumps(await self._event_create(
                        wbs,
                        request_obj,
                        request_obj.body.n_func,
                        request_obj.body.mod,
                        request_obj.body.args,
                        request_obj.body.kwargs
                    ))
                case ClientsWbsRequest_Mod.event_sub:
                    # Клиент подписывается на существующие "событие на сервере"
                    response = json.dumps(await self._event_sub(
                        wbs,
                        request_obj,
                        request_obj.body.n_func,
                        request_obj.body.mod,
                    ))
                case ClientsWbsRequest_Mod.event_unsub:
                    # Клиент отписывается от "события на сервере"
                    response = json.dumps(await self._event_unsub(
                        wbs,
                        request_obj,
                        request_obj.body.n_func,
                        request_obj.body.mod,
                    ))
                case ClientsWbsRequest_Mod.cache_add_key:
                    # Клиент отписывается от "события на сервере"
                    response = await self._cache_add_key(
                        request_obj.body.user,
                        request_obj.body.key,
                        request_obj.body.value,
                    )
                case ClientsWbsRequest_Mod.cache_read_key:
                    # Клиент отписывается от "события на сервере"
                    response = await self._cache_read_key(
                        request_obj.body.user,
                        request_obj.body.key,
                    )
                case _:
                    raise ValueError("Не доступный модификатор")
            # Формируем успешный ответ
            return ServerWbsResponse(
                h_id=request_obj.h_id,
                uid_c=request_obj.uid_c,
                code=WbsResponseCode.ok.value,
                response=response,
                t_send=request_obj.t_send,
                t_exec=0,
                error=""
            ).json(ensure_ascii=False), ""
        except BaseException:
            # Если во время выполнения команды возникла ошибка
            #
            # Подробно логируем ошибку
            #
            error = self.logger.errordet(f"wbs={wbs_uuid}")
            #
            # Отправляем сообщение ошибки клиенту
            #
            return ServerWbsResponse(
                h_id=request_obj.h_id,
                uid_c=request_obj.uid_c,
                code=WbsResponseCode.error_server.value,
                response="",
                t_send=request_obj.t_send,
                t_exec=0,
                error=error
            ).json(ensure_ascii=False), error

    ##################################################################
    #
    # Доступные функции
    #

    @classmethod
    def _help_allowed(cls) -> str:
        """
        Информация о доступных функциях
        """
        return json.dumps(cls.allowed_func.help_allowed(), ensure_ascii=False)

    @classmethod
    async def _func(cls, name_func: str, args: list | None, kwargs: dict | None) -> str:
        """
        Выполняем конкретную функцию которая есть в списке доступных.
        """
        return jsonpickle.encode(await cls.allowed_func.func(name_func, args, kwargs))

    @classmethod
    async def _transaction_func(
            cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_func: str, args: list | None, kwargs: dict | None) -> str:
        """
        Выполняем конкретную функцию которая есть в списке доступных. В режиме транзакции
        """
        # Отправляем уведомление клиенту, что сервер получил команду.
        await Transaction.send_notify(wbs, request_obj)
        # Выполняем команды от клиента.
        error, res = await cls.allowed_func.transaction_func(name_func, args, kwargs)
        if error:
            raise error
        return jsonpickle.encode(res)
    ##################################################################
    #
    # События
    #

    @classmethod
    def _help_events(cls) -> str:
        """Информация о `событиях сервера`"""
        # Кодируем в JSON. Используем библиотек jsonpickle для авто конвертации
        # множеств и пользовательских классов
        return jsonpickle.encode(
            cls.allowed_subscribe.help_events(), unpicklable=False)

    @classmethod
    async def _event_create(cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_func: str, mod: str, args: list | None, kwargs: dict | None) -> str:
        """
        Клиент создает событие на сервере
        """
        # Создать отдельную задачу
        return cls.allowed_subscribe.event_create(
            wbs, request_obj, name_func, mod, args, kwargs
        )

    @classmethod
    async def _event_sub(cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_func: str, mod: str,) -> str:
        """
        Клиент подписывается на существующие событие на сервере
        """
        return cls.allowed_subscribe.event_sub(
            wbs, request_obj, name_func, mod,
        )

    @classmethod
    async def _event_unsub(cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_func: str, mod: str,) -> str:
        """
        Клиент отписывается от событие на сервере
        """
        return cls.allowed_subscribe.event_unsub(
            wbs, request_obj, name_func, mod,
        )
    ##################################################################
    #
    # Произвольные команды
    #

    def _exec(self, command: str) -> str:
        """
        Клиент должен в запросе объявить переменную по имени `res`.
        В эту переменную сохраниться ответ
        """
        # Импортируем объекты которые могли сформировать в функции `WbsHandle._import_from_server`
        # чтобы они были доступны в `exec()`.
        if self._from_import_dict:
            locals().update(self._from_import_dict)
        # Выполняем команду
        # Последня строка(не перенос строки) является результатом, которая
        # сохраняется в переменную по имени `_`
        exec(re.sub('(.+)[\n\t]*$', f'_=\\g<1>', command))
        #  Получаем результат из переменной по имени  `_`
        # json.dumps(eval("_"), ensure_ascii=False)
        return jsonpickle.encode(eval("_"))

    def _import_from_server(self, command: str) -> str:
        """
        Выполняем импорты указных файлов
        """
        re_import: str = 'import[\t ](?P<import_a>[\\w\\d_]+)|from[\t ]+(?P<from_n>[\\w\\d_]+)[\t ]+import[\t ]+(?P<from_v>(?:[\\w\\_]+,?[\t ]*)+)'
        for r in re.finditer(re_import, command):
            match r.groupdict():
                # Импорт модуля
                case {'import_a': import_a} if import_a:
                    exec(f"import {import_a}")
                    globals()[import_a] = eval(import_a)
                # Импорт объекта из модуля и заносим их в переменную
                # `_from_import_dict`, эти объекты буду доступны в функции
                # `WbsHandle._exec_command`
                case {"from_n": from_n, "from_v": from_v} if from_n and from_v:
                    exec(f"from {from_n} import {from_v}")
                    for x in re.split(',[\t]+', from_v):
                        # Не переписывать на генератор так как в нем будет
                        # локальная область памяти которая не будет видеть
                        # импорты
                        self._from_import_dict[x] = eval(x)

    ##################################################################
    #
    #   Кеш Пользователя
    #
    async def _cache_add_key(self, user: str, key: str, value: str) -> str:
        """
        Добавить ключ в пользовательский кеш
        """
        if not self.path_user_cache:
            raise ValueError(
                "Вы пытаетесь использовать пользовательский кеш не указав путь для БД в атрибут 'path_user_cache'")
        res = await cache_add_key(self.path_user_cache, user, key, value)
        return json.dumps(res)

    async def _cache_read_key(self, user: str, key: str) -> str:
        """
        Прочитать ключ из пользовательского кеша
        """
        if not self.path_user_cache:
            raise ValueError(
                "Вы пытаетесь использовать пользовательский кеш не указав путь для БД в атрибут 'path_user_cache'")
        res = await cache_read_key(self.path_user_cache, user, key)
        return json.dumps(res)

    ##################################################################
    #
    #   Другое
    #

    def _check_token(self, wbs_uuid, request_obj):
        """
        Проверка аутентификации подключения, через проверку токена
        """
        if not wbs_uuid in self._allowed_clients:
            # Если это не аутентифицированное подключение
            # Аутентификации клиента по токену
            authentication: bool = False
            if request_obj.mod == ClientsWbsRequest_Mod.info and request_obj.body.id_r == ClientsWbsRequest_GetInfoServer_id.check_token:
                if request_obj.body.text in self.allowed_token:
                    # Токен верный. Заносим подключение в разрешенные - которые
                    # могут использовать север
                    self._allowed_clients.add(wbs_uuid)
                    authentication = True
                else:
                    # Токен не верный. Заносим подключение в черный список
                    self._back_list.add(wbs_uuid)
                    authentication = False
            if not authentication:
                return False
        return True
