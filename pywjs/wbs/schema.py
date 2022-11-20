from enum import Enum

from pydantic import BaseModel


class DT_HelpAllowed(BaseModel):
    """
    Структура подсказки доступной функции
    """
    # Аннотация типов
    annotations: str
    # Документация в начале в тройных кавычках
    doc: str
    # Имя функции
    name: str
    # Полный путь к функции(Класс.ИмяФункции)
    qualname: str


# ----------------------------------------------------------------------


class WbsCloseStatus(Enum):
    # https://github.com/Luka967/websocket-close-codes
    # Нормальное закрытие
    normal = 1000
    # Покидание страницы, клиент закрыл вкладку
    lose_clients = 1001
    # Слишком большой ответ от сервера
    big_response = 1009
    # Зарыть соединение по причине ошибки внутренней сервера
    server_error = 1011
    # Закрыть соединение по причине перезагрузки сервера
    server_reload = 1012
    # Закрыть соединение с серверов чтобы потом снова его открыть
    server_again = 1013
    # Ошибка в TSL рукопожатие
    tls_error = 1015
    # 4000-4999 Свободные коды
    # Ошибка аутентификации
    authentication_error = 4001


class ClientsWbsRequest_Mod(Enum):
    """
    Модификации для запроса
    """
    # ClientsWbsRequest_GetInfoServer - Доступные функция для вызова
    info = 1
    # ClientsWbsRequest_AllowedFunc - Вызов доступной функции
    func = 2
    # ClientsWbsRequest_ExeCommand - Выполнить произвольную команду
    exec = 3
    # ClientsWbsRequest_ImportFromServer - Импорт на сервер указанных библиотек
    import_from_server = 4
    # ClientsWbsRequest_CreateSubscribe - Клиент создает событие
    event_create = 5
    # ClientsWbsRequest_SubscribeEvent - Клиент подписывается на событие
    event_sub = 6
    # ClientsWbsRequest_UnSubscribeEvent - Клиент подписывается на событие
    event_unsub = 7
    # ClientsWbsRequest_CacheAddKey - Записать пользовательский кеш по ключу
    cache_add_key = 8
    # ClientsWbsRequest_CacheReadKey - Прочитать пользовательский кеш по ключу
    cache_read_key = 9


class ClientsWbsRequest_ModAlternatives(Enum):
    """
    Альтернативные модификации для запроса, будут использоваться для замены модификаций `ClientsWbsRequest_Mod`
    на более специфичные
    """
    # Выполнить процедуру в режиме транзакции (ClientsWbsRequest_AllowedFunc)
    transaction_func = 101


class ClientsWbsRequest_ImportFromServer(BaseModel):
    """
    Импорт на сервер указанных библиотек
    """
    # Список библиотек
    import_sts_exe: str


class ClientsWbsRequest_AllowedFunc(BaseModel):
    """
    Исполнение разрешенных функций
    """
    # Какую функцию выполнить
    n_func: str
    # Позиционные аргументы
    args: list | None
    # Именованные аргументы
    kwargs: dict | None


class ClientsWbsRequest_CreateSubscribe(BaseModel):
    """
    Клиент создает событие на сервере
    """
    # Имя события на которое подписываетесь
    n_func: str
    # Модификация события,
    # например если нужно выполнить одну и туже функцию, но с разными
    # аргументами.
    mod: str
    # Позиционные аргументы
    args: list | None
    # Именованные аргументы
    kwargs: dict | None


class ClientsWbsRequest_SubscribeEvent(BaseModel):
    """
    Клиент подписывается на существующие события сервера
    """
    # Имя события на которое подписываетесь
    n_func: str
    # Модификация события,
    # например если нужно выполнить одну и туже функцию, но с разными
    # аргументами.
    mod: str


class ClientsWbsRequest_UnSubscribeEvent(BaseModel):
    """
    Клиент отписывается от события на сервере
    """
    # Имя события от которого отписываетесь
    n_func: str
    # Модификация события,
    # например если нужно выполнить одну и туже функцию, но с разными
    # аргументами.
    mod: str


class ClientsWbsRequest_CacheAddKey(BaseModel):
    """
    Записать пользовательский кеш по ключу
    """
    # Пользователь
    user: str
    # Ключ
    key: str
    # Значение
    value: str


class ClientsWbsRequest_CacheReadKey(BaseModel):
    """
    Прочитать пользовательский кеш по ключу
    """
    # Пользователь
    user: str
    # Ключ
    key: str


class ClientsWbsRequest_ExeCommand(BaseModel):
    """
    Исполнение произвольной команды
    """
    # Произвольная команда на языке Python, которая выполниться на сервера.
    exec: str


class ClientsWbsRequest_GetInfoServer_id(Enum):
    # Получить список доступных функций
    help_allowed = 1
    # Проверка токена
    check_token = 2
    # Получить информацию о запущенных "событий сервера"
    info_event = 3


class ClientsWbsRequest_GetInfoServer(BaseModel):
    """
    Получить информацию о сервере
    """
    # ID информационной команды
    id_r: ClientsWbsRequest_GetInfoServer_id
    # Текст для информационной команды
    text: str | None


class ClientsWbsRequest(BaseModel):
    """
    Запрос клиента, для сервера
    """
    # Модификации для запроса.
    mod: ClientsWbsRequest_Mod | ClientsWbsRequest_ModAlternatives
    # Нужен для того чтобы можно было разными способами обрабатывать ответ на
    # стороне клиента.
    h_id: int
    # Идентификатор команды, нужен если используется асинхронность
    uid_c: int
    # Тело запроса
    body: ClientsWbsRequest_ExeCommand | ClientsWbsRequest_GetInfoServer | ClientsWbsRequest_ImportFromServer | ClientsWbsRequest_CreateSubscribe | ClientsWbsRequest_AllowedFunc | ClientsWbsRequest_CacheAddKey | ClientsWbsRequest_CacheReadKey
    # Время отправки сообщения от клиента в UNIX формате.
    t_send: float
# ----------------------------------------------------------------------


class WbsResponseCode(Enum):
    """
    Список кодов ответа
    """
    # Ошибка валидации запроса от клиента
    error_parse_request_clients = 100
    # Ошибка выполнения команды на стороне сервера
    error_server = 101
    # Ошибка аутентификации по токену
    token_error = 102
    # Успешное выполнение
    ok = 200
    # Сообщение в качестве уведомления
    notify = 201
    # Произошел откат транзакции, по причине клиента(например превышено время
    # ожидания ответа)
    rollback_from_clients = 401
    # Произошел откат транзакции, по причине сервера
    rollback_from_server = 402


class ServerWbsResponse(BaseModel):
    """
    Ответ от сервера, для клиента
    """
    # Нужен для того чтобы можно было разными способами обрабатывать ответ на
    # стороне клиента.
    h_id: int
    # Идентификатор команды, нужен если используется асинхронность
    uid_c: int
    # Код ответа
    code: WbsResponseCode
    # Время отправки сообщения от клиента в UNIX формате.
    t_send: float
    # Время выполнения(t_send из запроса - t_send из ответа), заполняется на
    # стороне клиента.
    t_exec: float
    # Текст ошибки
    error: str
    # Ответ
    response: str
