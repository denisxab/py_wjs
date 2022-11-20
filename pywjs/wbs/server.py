
import asyncio
import ssl
import time
from typing import Callable
import websockets
from websockets.legacy.server import WebSocketServerProtocol
from pywjs.wbs.subscribe import UserWbsSubscribe

from pywjs.wbs.schema import WbsCloseStatus
from pywjs.wbs.handle import WbsHandle

__all__ = ['wbs_main_loop']

logger = None


async def request_clients(wbs: WebSocketServerProtocol, handle_request: Callable[[WebSocketServerProtocol, str], str]):
    """
    Обработчик сообщений от клиента
    """
    try:
        async for message in wbs:
            start = time.time()
            if not wbs.id.hex in WbsHandle._back_list:
                logger.success(
                    message, ['Request Clients', 'Запрос клиента', wbs.id])
                # Обрабатываем запрос от клиента
                result, error = await handle_request(wbs, message)
                if error:
                    logger.error(
                        error,
                        [
                            'Request Clients', 'Ошибка при обработке запроса', wbs.id
                        ]
                    )
                else:
                    logger.success(
                        "%s:" % (time.time() - start),
                        ['Request Clients', 'Запрос успешная обработан', wbs.id]
                    )
                await wbs.send(result)
            else:
                await wbs.close(WbsCloseStatus.authentication_error.value, 'Вы в черном списке')
            # (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"{wbs.close_code}:{wbs.close_reason}", [
                    "CLOSE", 'Error', wbs.id])
        UserWbsSubscribe.all_unsubscribe_event(wbs)
    logger.info(f"{wbs.close_code}:{wbs.close_reason}",
                ["CLOSE", 'Ok', wbs.id])
    UserWbsSubscribe.all_unsubscribe_event(wbs)


async def clear_back_list():
    """
    Отчистка черного списка, через указанный интервал
    """
    while WbsHandle._wait_clear_back_list:
        if WbsHandle._back_list:
            # Отчистка черного списка
            WbsHandle._back_list.clear()
            logger.info('Отчистка черного списка', ['Отчистка черного списка'])
        await asyncio.sleep(WbsHandle._wait_clear_back_list)


async def run_server(host: str, port: int, handle: Callable[[WebSocketServerProtocol, str], str], *, ssl: ssl.SSLContext | None = None):
    async with websockets.serve(lambda wbs: request_clients(wbs, handle), host, port, ssl=ssl): await asyncio.Future()


async def wbs_main_loop(host: str, port: int, class_handle: WbsHandle):
    #
    # Переопределяем логер на то что указан в классе
    #
    global logger
    logger = class_handle.logger
    #
    # Создаем задачу
    #
    class_handle_obj = await class_handle().after_init()
    tasks = [
        run_server(
            host,
            port,
            class_handle_obj.handle),
        clear_back_list()]
    # Выполняем задачу
    return await asyncio.gather(*tasks)
