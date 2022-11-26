"""
Установка виртуального окружения `Python`, и зависимостей из файла `./pyproject.toml`
"""

import re
import sys
import venv
import subprocess
from pathlib import Path

setting = dict(
    major=3,
    minor=11,
    download_link='https://www.python.org/downloads/'
)

path_app = Path(__file__).parent.resolve()
path_server = path_app / 'server'
path_env = path_server / 'venv'
venv_obj = venv.EnvBuilder(with_pip=True, upgrade_deps=True)
venv_context = venv_obj.ensure_directories(str(path_env))
path_python = venv_context.env_exec_cmd


# 1. Проверить версию текущего python
def step1(path_app: Path):
    python_version = sys.version_info
    if python_version.major >= setting['major'] and python_version.minor >= setting['minor']:
        step2(path_env=path_env)
        step3(
            path_python=path_python,
            path_server=path_server
        )
        step4(
            path_uninstall=path_app / 'auto_uninstall.py'
        )
        step5(
            path_run=path_app/'auto_run.py',
            path_python=path_python
        )
        step6(path_gitignore=path_app/'.gitignore')
    else:
        print(
            f"Версия Python не подходит, необходимо иметь Python{setting['major']}.{setting['minor']}\nСсылка для скачивания:\t{setting['download_link']}")


# 2. Создать виртуальное окружение
def step2(path_env: Path):
    # Создаем виртуально окружение в папке `./venv`
    venv_obj.create(str(path_env))


# 3. Установить зависимости из файла `./pyproject.toml` в ВО
def step3(path_python: str, path_server: Path):
    # Установка `poetry`
    subprocess.check_call([path_python, '-m', 'pip', 'install', 'poetry'])
    # Обновить файлы блокировки
    subprocess.run(
        [path_python, '-m', 'poetry', 'lock'], cwd=path_server,
    )
    # Синхронизируем модули с файлом `pyproject.toml`
    subprocess.run(
        [path_python, '-m', 'poetry', 'install', '--sync'], cwd=path_server,
    )


# 4. Создать файл для удаления venv
def step4(path_uninstall: Path):
    path_uninstall.write_text(f"""
from pathlib import Path
import shutil
import time
env_dir = Path(__file__).parent / 'server' / 'venv'

check_int = str(time.time_ns() % 100)
r = input(f'Для подтверждения удаления, введите число:\\n\\n{{check_int}}:\\t')
if r == check_int:
    shutil.rmtree(env_dir)
    print("\\nУспешное удаление")
else:
    print("\\nНе верное число, удаление отменено")
    """)


# 5. Создать файл для запуска программы
def step5(path_run: Path, path_python: Path):
    # Относительный путь к venv
    path_python = re.sub('.+(venv.+)', '\g<1>', path_python)
    path_run.write_text(f"""
from pathlib import Path
import webbrowser
import os

sdir = Path(__file__).parent 
# Запустить html файл, в браузере по умолчанию
webbrowser.open(f"file://{{sdir / 'client' / 'index.html'}}")
# Запустить файл `main.py`
os.system(f"{{sdir / 'server' / '{path_python}'}} {{sdir /'server'/ 'main.py'}}")
    """)


# 6. Создать `.gitignore`
def step6(path_gitignore: Path):
    path_gitignore.write_text("""
.vscode
__pycache__
log
server/venv
server/plagins
*.log
*.sqlite
    """)

# 7. Создать файл для автоматического обновления


def step7(path_auto_update: Path):
    path_auto_update.write_text('''
""" 
Автоматическое обновление программы
"""

import subprocess
from datetime import datetime
from auto_install import step3, path_server, path_python


def syncGit():
    """Синхронизация проекта"""
    origin = 'origin'
    # Получить имя текущей ветки, оно будет считаться именем для удаленной ветки.
    select_branch: str = subprocess.run(
        'git --no-pager branch --no-color --show-current', shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8'
    ).stdout
    if not select_branch:
        raise ValueError("Пустая ветка")
    # Проверить синхронизацию текущего локального проекта(даже если изменения небыли за комичены), с удаленной веткой.
    diff: str = subprocess.run(
        f'git --no-pager diff {origin}/{select_branch} --raw --name-status', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8'
    ).stdout
    if diff:
        #
        # Если есть различия в локальной и удаленной ветки
        #
        # Делаем коммит текущих локальных изменений.
        subprocess.run('git add -A', check=True)
        subprocess.run(
            f"git commit -m 'CommitByAutoUpdate:{datetime.now()}'", check=True)
        # Получаем всю информацию об изменениях на удаленной ветки.
        subprocess.run('git fetch --all', shell=True, check=True)
        # Принудительно(во всех спорных случая берем данные из удаленной ветки) синхронизируем локальную ветку с удаленной.
        subprocess.run(
            f'git reset --hard {origin}/{select_branch}', shell=True)
        # Выполняем синхронизацию зависимостей в виртуальном окружение `Python`
        syncPyVenvDependents()
    else:
        # Нет различий локальной ветки от удаленной. Или не удалось узнать различий с удаленной веткой, из за отсутствия связи.
        ...

def syncPyVenvDependents():
    """Синхронизация зависимостей для виртуального окружения Python"""
    step3(path_python=path_python, path_server=path_server)

    ''')


if __name__ == '__main__':
    step1(path_app)
