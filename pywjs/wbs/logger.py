import abc
from pathlib import Path
from logsmal import logger

__all__ = ["ABC_loglevel", "ABC_logger", "defaultLogger"]


class ABC_loglevel(abc.ABC):
    def __call__(self, data: str, flags: list[str] = "") -> str: ...


class ABC_logger(abc.ABC):
    """Абстрактный класс(интерфейс) для логера"""
    success: ABC_loglevel
    info: ABC_loglevel
    debug: ABC_loglevel
    error: ABC_loglevel
    errordet: ABC_loglevel


class EmptyLogger:
    """Пустой логер. Вызовы логера будут игнорироваться"""
    success = lambda *args, **kwargs: None
    info = lambda *args, **kwargs: None
    debug = lambda *args, **kwargs: None
    error = lambda *args, **kwargs: None
    errordet = lambda *args, **kwargs: None


def defaultLogger(path_to_dir_log: Path) -> ABC_logger:
    """Логер по умолчанию"""
    #
    # Настройки логера. Используется https://pypi.org/project/logsmal/
    #
    # Путь к лог файлам.
    path_log: Path = path_to_dir_log / Path('log')
    # Обновление настроек логера, чтобы они также записывали сообщения в файл
    logger.success = logger.success.updateCopy(
        fileout=(path_log / 'info.log'), console_out=True, max_len_console=64
    )
    logger.info = logger.info.updateCopy(
        fileout=(path_log / 'info.log'), console_out=True, max_len_console=64
    )
    logger.debug = logger.debug.updateCopy(
        fileout=(path_log / 'info.log'), console_out=True, max_len_console=64
    )
    logger.error = logger.error.updateCopy(
        fileout=(path_log / 'error.log'), console_out=True, max_len_console=64
    )
    logger.errordet = logger.errordet.updateCopy(
        fileout=(path_log / 'detail_error.log'), console_out=True, max_len_console=64
    )
    return logger
