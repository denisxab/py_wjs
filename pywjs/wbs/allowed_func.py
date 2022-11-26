from asyncio import create_subprocess_shell
from functools import wraps
import hashlib
import os
from pathlib import Path
import subprocess
from types import CoroutineType, FunctionType
from typing import Any, Callable, Literal
from websockets.legacy.server import WebSocketServerProtocol

from pywjs.wbs.schema import ClientsWbsRequest, DT_HelpAllowed, ServerWbsResponse, WbsResponseCode
# Возьмем "logger" который проинициализируется в `wbs_main_loop`
import pywjs.wbs.server as baseWbs

__all__ = ['AllowWbsFunc', 'Transaction', 'StdAllowWbsFunc']


class AllowWbsFunc():
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
                module=str(v.__module__),
                qualname=str(v.__qualname__),
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
    """Класс для реализации транзакции в функциях"""

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
            @wraps(fun)
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


class StdAllowWbsFunc:
    """Сборник функций для решения часто встречаемых задач, при создание десктопных программ"""

    # Асинхронная функция
    async def os_exe_async(command: str) -> dict:
        """
        Запустить/выполнить внешнюю команду(command) в оболочке, в асинхронном режиме.
        """
        # Выполняем команду
        p = await create_subprocess_shell(
            cmd=command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Получить результат выполнения команды
        stdout, stderr = await p.communicate()
        return dict(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            cod=p.returncode,
            cmd=command,
        )

    def createLinkToFile(pathFile: str, pathDirLinks: str, extendsFile: Literal['txt', 'pdf', 'png', 'jpg', 'webp']) -> str:
        """Создать символьную ссылку на файл `pathFile`, и поместить ей в путь `pathDirLinks`

        :param pathFile: Путь к файлу на который нужно сделать символьную ссылку
        :param pathDirLinks: Путь к папке в которую нужно поместить символьную ссылку
        :return: Имя символьного файла
        """

        pathFile = Path(pathFile).resolve()
        pathDirLinks = Path(pathDirLinks).resolve()
        # Создаем путь если его нет
        if not os.path.exists(pathDirLinks):
            os.makedirs(pathDirLinks)
        # Имя ссылки = `link_ЗахешированныйПолныйПутьMD5__ИсходноеРасширениеФайла_.расширение`
        nameLinkFile: str = f"link_{hashlib.md5(str(pathFile).encode('utf-8')).hexdigest()}__{pathFile.suffix.lower().replace('.','_')}.{extendsFile}"
        absPathLink = pathDirLinks/nameLinkFile

        if absPathLink.exists():
            if not absPathLink.is_symlink():
                absPathLink.symlink_to(pathFile)
        else:
            absPathLink.symlink_to(pathFile)
        return str(absPathLink.name)

    def clearDirByTemplate(pathDirLinks: str, template='link_*'):
        """Удалить все файлы в директории, которые соответствуют шаблону `template`

        По умолчанию, шаблон удаляет все символьные файлы, которые созданы через функцию `createLinkToFile`

        :param pathLink: Путь к папке.
        """
        pLink = Path(pathDirLinks).resolve()
        for f in pLink.glob(template):
            os.remove(f)
        return True
