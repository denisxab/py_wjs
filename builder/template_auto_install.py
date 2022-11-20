"""
Установка виртуального окружения `Python`, и зависимостей из файла `./requirements.txt`
"""

import sys
import venv
import subprocess
from pathlib import Path

setting = dict(
    major=3,
    minor=11,
    download_link='https://www.python.org/downloads/'
)


# 1. Проверить версию текущего python
def step1(path_app: Path):
    python_version = sys.version_info
    if python_version.major >= setting['major'] and python_version.minor >= setting['minor']:
        path_server = path_app / 'server'
        path_env = path_server / 'venv'
        path_python = step2(path_env=path_env)
        step3(
            path_python=path_python,
            path_requirements=path_server/'requirements.txt'
        )
        step4(
            path_env=path_env,
            path_uninstall=path_app / 'auto_uninstall.py'
        )
        step5(
            path_app, path_run=path_app/'auto_run.py',
            path_python=path_python, path_server=path_server
        )
        step6(path_gitignore=path_app/'.gitignore')
    else:
        print(
            f"Версия Python не подходит, необходимо иметь Python{setting['major']}.{setting['minor']}\nСсылка для скачивания:\t{setting['download_link']}")


# 2. Создать виртуальное окружение
def step2(path_env: Path):
    # Создаем виртуально окружение в папке `./venv`
    v = venv.EnvBuilder(with_pip=True, upgrade_deps=True)
    v.create(str(path_env))
    # Устанавливаем зависимости из `requirements.txt
    context = v.ensure_directories(str(path_env))
    return context.env_exec_cmd


# 3. Установить зависимости из файла `./requirements.txt` в ВО
def step3(path_python: str, path_requirements: Path):
    for lib in path_requirements.read_text().split('\n'):
        if lib:
            cmd = [path_python, '-m', 'pip', 'install', lib]
            subprocess.check_call(cmd)


# 4. Создать файл для удаления venv
def step4(path_env: Path, path_uninstall: Path):
    path_uninstall.write_text(f"""
import shutil
import time
env_dir = '''{path_env}'''

check_int = str(time.time_ns() % 100)
r = input(f'Для подтверждения удаления, введите число:\\n\\n{{check_int}}:\\t')
if r == check_int:
    shutil.rmtree(env_dir)
    print("\\nУспешное удаление")
else:
    print("\\nНе верное число, удаление отменено")
    """)


# 5. Создать файл для запуска программы
def step5(path_app: Path, path_run: Path, path_python: Path, path_server: Path):
    path_run.write_text(f"""
import webbrowser
import os
# Запустить html файл, в браузере по умолчанию
webbrowser.open('file://' + '{ path_app / 'client' / 'index.html'}')
# Запустить файл `main.py`
os.system('{path_python} {path_server/'main.py'}')
    """)


# 6. Создать `.gitignore`
def step6(path_gitignore: Path):
    path_gitignore.write_text("""
.vscode
__pycache__
log
server/venv
*.log
*.sqlite
    """)


if __name__ == '__main__':
    path_app = Path(__file__).parent.resolve()
    step1(path_app)
