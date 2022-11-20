from types import CoroutineType, FunctionType
from typing import Any, Callable
from websockets.legacy.server import WebSocketServerProtocol

from pywjs.wbs.schema import ClientsWbsRequest, DT_HelpAllowed, ServerWbsResponse, WbsResponseCode
# Возьмем "logger" который проинициализируется в `wbs_main_loop`
import pywjs.wbs.server as baseWbs

__all__ = ['UserWbsFunc','Transaction']


class UserWbsFunc():
    """
    Класс для реализации и хранения `доступных функций`
    """

    @classmethod
    def help_allowed(cls) -> dict[str, DT_HelpAllowed]:
        """
        Информация о доступных функциях
        """
        return {
            k: DT_HelpAllowed(
                annotations=str(v.__annotations__),
                doc=str(v.__doc__),
                name=str(v.__name__),
                qualname=str(v.__qualname__)
            ).dict()
            for k, v in cls.__dict__.items()
            if type(v) == FunctionType or type(v) == classmethod
        }

    @classmethod
    async def func(cls, name_func: str, args: list | None, kwargs: dict | None) -> object:
        """
        Выполняем конкретную функцию которая есть в списке доступных.
        """
        function = cls.__dict__.get(name_func, None)
        if function:
            match type(function):
                case _ as r if r == FunctionType or r == classmethod:
                    if not args:
                        args = ()
                    if not kwargs:
                        kwargs = {}
                    res = function(*args, **kwargs)
                    # Если это асинхронная функция
                    if type(res) == CoroutineType:
                        # То выполняем её
                        res = await res
                    return res
        else:
            raise KeyError(
                f'Вы не можете вызвать функцию "{name_func}" потому что она не существует')

    @classmethod
    async def transaction_func(cls, name_func: str, args: list | None, kwargs: dict | None) -> tuple[bool | BaseException, Any]:
        """
        Выполняем конкретную функцию которая есть в списке доступных. В режиме транзакции
        """
        function = cls.__dict__.get(name_func, None)
        if function:
            match type(function):
                case _ as r if r == FunctionType or r == classmethod:
                    if not args:
                        args = ()
                    if not kwargs:
                        kwargs = {}
                    res = function(*args, **kwargs)
                    # Если это не асинхронная функция
                    if type(res) != CoroutineType:
                        raise ValueError(
                            "Режим транзакции доступен только для асинхронных функций.")
                    # Если она создана без транзакционного декоратора
                    elif res.cr_code.co_name != 'transaction_dec':
                        raise ValueError(
                            "Функция '{name_func}' создана без транзакционного декоратора.")
                    # То выполняем её
                    return await res
        else:
            raise KeyError(
                f'Вы не можете вызвать функцию "{name_func}" потому что она не существует.')


class Transaction:
    """Класс для реализации транзакции"""

    class TransactionError(BaseException):
        ...

    async def send_notify(wbs: WebSocketServerProtocol, request_obj: ClientsWbsRequest):
        """
        Отправляем уведомление клиенту, что сервер получил команду.
        """
        result = ServerWbsResponse(
            h_id=request_obj.h_id,
            uid_c=request_obj.uid_c,
            code=WbsResponseCode.notify.value,
            response='',
            t_send=request_obj.t_send,
            t_exec=0,
            error=""
        ).json(ensure_ascii=False)
        await wbs.send(result)

    def _(rollback: Callable = lambda: None):
        """
        Декоратор для выполнения функции в режиме транзакции
        """
        def wrapper(fun):
            async def transaction_dec(*arg, **kwargs) -> tuple[bool | BaseException, Any]:
                res: tuple[bool, Any] = None
                try:
                    # Выполняем функцию в режиме транзакции
                    res = False, await fun(*arg, **kwargs)
                # При возникновение любой ошибки вызываем функцию отката.
                except Transaction.TransactionError as e:
                    baseWbs.logger.error(
                        e, ['Transaction', 'AllowFunction', 'Error'])
                    res = e, rollback()
                except BaseException as e:
                    baseWbs.logger.error(
                        e, ['Transaction', 'AllowFunction', 'Error'])
                    res = e, rollback()
                return res
            return transaction_dec
        return wrapper
