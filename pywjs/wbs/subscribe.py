import asyncio
from collections import deque
import copy
from functools import partial
from types import FunctionType
from typing import Callable, Coroutine, NamedTuple
from websockets.legacy.server import WebSocketServerProtocol
from pywjs.wbs.schema import ClientsWbsRequest, ServerWbsResponse, WbsResponseCode
# Возьмем "logger" который проинициализируется в `wbs_main_loop`
import pywjs.wbs.server as baseWbs
import jsonpickle

__all__ = [
    "UserWbsSubscribe_Self",
    "ClientsSubscriber",
    "UserWbsSubscribeData",
    "UserWbsSubscribe"
]

# Переводить в UTF-8
jsonpickle.set_encoder_options('json', ensure_ascii=False)


class UserWbsSubscribe_Self(NamedTuple):
    """
    Структура локальных данных для пользовательского класса подписок
    """
    send: Callable
    name_event: str
    mod: str
    live: Coroutine


class ClientsSubscriber(NamedTuple):
    """Структура для подписчика"""
    wbs: WebSocketServerProtocol
    request_obj: ClientsWbsRequest

    def __getstate__(*args, **kwargs):
        """Переопределяем оператор сериализации класса"""
        return (args[0].wbs.id.hex, args[0].request_obj.h_id)

    def __repr__(self) -> str:
        return f"{self.wbs.id.hex}|{self.request_obj.json(ensure_ascii=False)}"


class UserWbsSubscribeData:
    """
    Структура данных для работы с подписками клиентов
    """

    def __init__(self):
        # Список активных "Событий на сервере": {ИмяФункции:set(Модификация_N)}
        self._live_subscribers: dict[str, set[str]] = {}
        # Используется для отправки сообщений клиентам:
        # {ИмяФункции:{Модификация:{WbsID:ClientsSubscriber}}}
        self._send_subscribers: dict[str, dict[str,
                                               dict[str, deque[ClientsSubscriber]]]] = {}
        # На что подписан указанный пользователь:
        # {WbsID:{ИмяФункции:set(Модификация)}}
        self._user_subscriber: dict[str, dict[str, set[str]]] = {}

    def event_create(
        self,
        class_,
        wbs: WebSocketServerProtocol,
        request_obj: ClientsWbsRequest,
        mod: str, name_event: str
    ) -> tuple[str, UserWbsSubscribe_Self]:
        """Создать событие, или если оно уже есть, то подписаться на него текущего клиента"""
        # Инициализируем `_live_subscribers,_send_subscribers` если они пустые.
        if not self._live_subscribers and not self._send_subscribers:
            # Берем все функции класса
            for _name_event in class_.__dict__.keys():
                if isinstance(class_.__dict__[_name_event], FunctionType):
                    self._live_subscribers[_name_event] = set()
                    self._send_subscribers[_name_event] = {}
        # Проверка: Имени события должно существовать.
        if self._live_subscribers.get(name_event, None) is None:
            raise KeyError(
                f'Имя событие "{name_event}" не существует.'
            )
        # Проверка: Если событие с такой модификацией уже существует.
        if mod in self._live_subscribers[name_event]:
            # то просто подписываемся на существующие.
            self.subscriber_event(wbs, request_obj, name_event, mod)
            return "Subscription", None
        # Если событие не создано, то создаем его.
        else:
            # Разрешаем выполнение события, с указанной модификацией.
            self._live_subscribers[name_event].add(mod)
            # Создаем список для подписчиков данного события и модификации.
            self._send_subscribers[name_event][mod] = {}
            # Подписываем текущего клиента, который создал событие, на это же
            # событие.
            self.subscriber_event(wbs, request_obj, name_event, mod)
            # Формируем данные для пользовательской функций, которая выполняет
            # обработку события.
            self_ = UserWbsSubscribe_Self(
                send=partial(
                    class_.send_all_subscribers,
                    name_event=name_event, mod=mod
                ),
                name_event=name_event,
                mod=mod,
                live=partial(class_.live, name_event=name_event, mod=mod)
            )
            return "Create", self_

    def check_subscriber(self, wbs_id: str, name_event: str,
                         mod: str, user_sub: bool):
        """
        Проверяем существования такой подписки

        user_sub: Проверка для существующего подписчика(Да/Нет)
        """
        # Проверить то, что такая подписка существует
        if self._send_subscribers.get(name_event, None) is None:
            raise KeyError(f'События "{name_event}" не существует')
        # Если указан модификатор, но он не существует
        elif self._send_subscribers[name_event].get(mod, None) is None:
            raise KeyError(
                f'События "{name_event}" существует, но не существует модификатор "{mod}"')
        # Если пользователь не подписан на событие с указанны модификатором
        elif user_sub == True and self._send_subscribers[name_event][mod].get(wbs_id, None) is None:
            raise KeyError(
                f'Вы не подписаны на событие "{name_event}" с модификацией "{mod}"')

    def subscriber_event(self, wbs: WebSocketServerProtocol,
                         request_obj: ClientsWbsRequest, name_event: str, mod: str):
        """
        Добавить клиента в подписчики для события(name_event) с модификацией(mod)
        """
        wbs_id: str = wbs.id.hex
        #
        # Проверяем существования такой подписки
        #
        self.check_subscriber(wbs_id, name_event, mod, user_sub=False)
        #
        # Заполняем структуру по которой можно определить на что подписан пользователь.
        #
        # Если это первая подписка у пользователя на новое событие.
        if self._user_subscriber.get(wbs_id, None) is None:
            self._user_subscriber[wbs_id] = {name_event: set([mod])}
        # Если это вторая и более подписка, на новое событие.
        elif self._user_subscriber[wbs_id].get(name_event, None) is None:
            self._user_subscriber[wbs_id][name_event] = set([mod])
        # Если это вторая и более подписка, на тоже самое событие, но с другим
        # модификатором
        elif mod not in self._user_subscriber[wbs_id][name_event]:
            self._user_subscriber[wbs_id][name_event].add(mod)
        # Если пользователь пытается повторно подписаться на тоже самое событие
        # с тем же модификатором
        else:
            raise ValueError(
                f'Вы уже подписаны на это событие "{name_event}", с таким модификатором "{mod}"'
            )
        #
        # Добавляем клиента в подписчики чтобы он получал сообщения.
        #
        self._send_subscribers[name_event][mod][wbs_id] = ClientsSubscriber(
            wbs=wbs, request_obj=request_obj)
        baseWbs.logger.success(
            wbs_id, ["Subscriber", "Подписка", 'Успешно'])
        return True

    def unsubscriber_event(self, wbs_id: str, name_event: str, mod: str):
        """
        Отписаться от события(name_event), с модификацией(mod).

        При этом будет происходить проверка, для автоматической отчистки и остановки
        событий у которых больше нет подписчиков
        """
        #
        # Проверки наличия подписки у клиента.
        #
        self.check_subscriber(wbs_id, name_event, mod, user_sub=True)
        #
        # Удаление модификации(отписка).
        #
        # Удаляем модификацию в `self._user_subscriber`
        self._user_subscriber[wbs_id][name_event].remove(mod)
        # Удаляем модификацию в `_send_subscribers`
        del self._send_subscribers[name_event][mod][wbs_id]
        #
        # Автоматическая отчистка и остановка событий у которых нет модификацией.
        #
        # Если у события теперь нет модификаций
        if len(self._user_subscriber[wbs_id][name_event]) == 0:
            # то удаляем событие
            del self._user_subscriber[wbs_id][name_event]
            baseWbs.logger.debug(
                name_event,
                ["Subscriber", "Отписка", "user_subscriber", "Удаление события"])
            # Если у клиента нет подписок на событие
            if len(self._user_subscriber[wbs_id]) == 0:
                # то удаляем клиента
                del self._user_subscriber[wbs_id]
                baseWbs.logger.debug(
                    wbs_id,
                    ["Subscriber", "Отписка", "user_subscriber", "Удаление клиента"])
        # Если теперь нет подписчиков у модификации
        if len(self._send_subscribers[name_event][mod]) == 0:
            # то удаляем модификацию
            del self._send_subscribers[name_event][mod]
            baseWbs.logger.debug(
                mod,
                ["Subscriber", "Отписка", "send_subscribers", "Удаление модификации"])
            # и прекращаем отслеживания(выполнение события)
            self._live_subscribers[name_event].remove(mod)
            baseWbs.logger.debug(
                mod,
                ["Subscriber", "Отписка", "live_subscribers", "Остановка модификации"])
            # Если теперь у события нет модификаций.
            if len(self._send_subscribers[name_event]) == 0:
                # То не чего не делаем
                baseWbs.logger.debug(
                    name_event,
                    ["Subscriber", "Отписка", "send_subscribers",
                        "У события нет модификаций"]
                )
        baseWbs.logger.success(
            wbs_id, ["Subscriber", "Отписка", "Успешно"])
        return True

    def get_send_subscribers(self, name_event: str, mod: str):
        """
        Получить всех подписчиков для указного события и модификации.
        Используется для отправки сообщения к подписчикам.
        """
        return self._send_subscribers[name_event][mod]

    def is_live(self, name_event: str, mod: str) -> bool:
        """Проверить возможность исполнения события"""
        return True if mod in self._live_subscribers[name_event] else False
    # ----------------------------------------


class UserWbsSubscribe:
    """
    Базовый класс, для "событие на сервере"
    """
    # Переменная для хранения и управления подписок
    o_UserWbsSubscribeData = UserWbsSubscribeData()

    @classmethod
    async def live(cls, sleep: int = 0, *, name_event: str, mod: str):
        """
        Проверить что указанное событие по имени(name_event) с модификацией(mod)
        может исполнятся.

        ```
        ... # Инициализация локальных переменных
        while await self_.live(sleep=СколькоЖдать): # Бесконечный не блокирующий цикл событий, которые будет выполнятся через каждые `sleep`
            ... # Отслеживания события
            if ... : # Условия срабатывания события
                await self_.send(...)  # Отправка сообщения подписчикам
        ```
        """
        if cls.o_UserWbsSubscribeData.is_live(name_event, mod):
            await asyncio.sleep(sleep)
            return True
        else:
            return False

    @classmethod
    def help_events(cls) -> UserWbsSubscribeData:
        """Информация о событиях на сервере"""
        return cls.o_UserWbsSubscribeData.__dict__

    @classmethod
    def event_create(
            cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_event: str, mod: str, args: list | tuple,
            kwargs: dict
    ) -> tuple[str, asyncio.Task | None]:
        """
        Создать обработку события на сервере, или если она уже есть, то подписать текущего пользователя
        """
        res, self_ = cls.o_UserWbsSubscribeData.event_create(
            cls,
            wbs, request_obj, mod, name_event
        )
        self_: UserWbsSubscribe_Self
        if res == "Create":
            # Запускаем событие в отдельной задаче
            return asyncio.create_task(
                cls.__dict__[name_event](self_, *args, **kwargs)
            ).get_name(), "Create"
        elif res == "Subscription":
            return res, None

    @classmethod
    def event_sub(
            cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_event: str, mod: str
    ) -> str:
        """
        Клиент подписывается на существующие событие на сервере
        """
        return cls.o_UserWbsSubscribeData.subscriber_event(
            wbs, request_obj, name_event, mod)

    @classmethod
    def event_unsub(
            cls, wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest, name_event: str, mod: str
    ) -> str:
        """
        Клиент отписывается от событие на сервере
        """
        return cls.o_UserWbsSubscribeData.unsubscriber_event(
            wbs.id.hex, name_event, mod)

    @classmethod
    def all_unsubscribe_event(cls, wbs: WebSocketServerProtocol):
        """Отписка клиента от всех событий. Например используется если связь с клиентом прекращена"""
        wbs_id: str = wbs.id.hex
        # Проверяем что у клиента есть подписчики.
        if cls.o_UserWbsSubscribeData._user_subscriber.get(
                wbs_id, None) is not None:
            # Должна быть копия словаря иначе ошибка "RuntimeError: Set changed
            # size during iteration"
            cp1 = copy.deepcopy(
                cls.o_UserWbsSubscribeData._user_subscriber[wbs_id])
            for _name in cp1.keys():
                # Должна быть копия множества иначе ошибка "RuntimeError: Set
                # changed size during iteration"
                cp2 = copy.deepcopy(
                    cls.o_UserWbsSubscribeData._user_subscriber[wbs_id][_name])
                # то отписываемся текущего клиента от всех событий, со всеми
                # модификациями.
                for _mod in cp2:
                    cls.o_UserWbsSubscribeData.unsubscriber_event(
                        wbs_id, _name, _mod)
        return True

    @classmethod
    async def send_all_subscribers(cls, msg: str, *, name_event: str, mod: str):
        """
        Отправляем сообщение все подписчикам, для указного события(name_event) с указной модификацией(mod)
        """
        for wbs_id, subscriber in cls.o_UserWbsSubscribeData.get_send_subscribers(
                name_event, mod).items():
            result = ServerWbsResponse(
                h_id=subscriber.request_obj.h_id,
                uid_c=subscriber.request_obj.uid_c,
                code=WbsResponseCode.ok.value,
                response=jsonpickle.encode(msg),
                t_send=subscriber.request_obj.t_send,
                t_exec=0,
                error=""
            ).json(ensure_ascii=False)
            await subscriber.wbs.send(result)
