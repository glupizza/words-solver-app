# Words Solver (PWA)

Проект разработан в рамках выпускной квалификационной работы.

PWA-приложение: загружаешь фото игрового поля 5x5, бэкенд распознает буквы и находит слова по словарю.

## Стек

- Frontend: Vue + Vite
- Backend: Python + Flask
- Deploy: Docker + Gunicorn

## Запуск в dev-режиме

### Backend

В терминале из корня проекта:

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r backend/requirements.txt
python -m backend.app
```
Бэкенд стартует на: http://127.0.0.1:8000

По умолчанию обычный решатель и оба этапа поиска Грааля используют словарь
`backend/assets/cleaned_filtered_russian_words_no_past.json`. Путь можно заменить
переменной окружения `DICTIONARY_PATH`; резервный словарь находится в
`backend/assets/cleaned_filtered_russian_words.json`. Отладочный pipeline и benchmark
используют тот же словарь по умолчанию и учитывают ту же переменную.

### Frontend

Во втором терминале из корня проекта:

```bash
cd frontend
npm install
npm run dev
```

Vite покажет URL (обычно http://localhost:5173).

### Тесты и линтинг

### Backend

```bash
source .venv/bin/activate
pip install -r backend/requirements-dev.txt

python -m ruff check backend
python -m ruff format --check backend
python -m pytest -q
```

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run build
```

### Docker

Для локального запуска сначала создайте отдельный env-файл с непустыми
`FLASK_SECRET_KEY`, `ADMIN_PASSWORD_HASH` и
`REJECTED_WORDS_DB_PATH=/data/rejected_words.sqlite3`. Файл должен находиться вне
репозитория и иметь права 600. Подготовьте отдельный существующий каталог данных.
Команды ниже принимают абсолютные пути, выбранные для локального запуска:

```bash
export WORDER_ENV_FILE=/абсолютный/путь/к/worder.env
export WORDER_DATA_DIR=/абсолютный/путь/к/каталогу-данных
docker build -t words-solver .
docker run --rm -p 127.0.0.1:8000:8000 --env-file "$WORDER_ENV_FILE" \
  --mount "type=bind,src=$WORDER_DATA_DIR,dst=/data" words-solver
```

Приложение доступно на http://localhost:8000. Для Compose можно задать те же
`WORDER_ENV_FILE` и `WORDER_DATA_DIR`; серверные значения по умолчанию указаны в
`docker-compose.yml`. В Compose переменные среды берутся из env-файла, чтобы
сохранить существующие значения OCR и лимита загрузки.

## Администрирование и постоянное хранилище

Основной JSON остаётся неизменным. SQLite содержит исключённые слова и служебные
данные административного доступа. Для каждого поиска читается один снимок базы;
потоковый запрос использует его для всех партий. Изменения действуют со следующего
поиска. `/admin` открывается только напрямую; `/` остаётся обычным режимом.
Результат в текущей вкладке сохраняется в sessionStorage максимум на час (до 2 МБ),
без фотографий и пароля. Если хранилище отключено, войдите до поиска.

Приложение требует непустые `FLASK_SECRET_KEY` и `ADMIN_PASSWORD_HASH` и доступный
`REJECTED_WORDS_DB_PATH`; ошибка открытия базы останавливает запуск. Для локальной
разработки задайте абсолютный путь в существующий каталог вне репозитория; cookie
администратора требует HTTPS (для localhost браузеры обычно делают исключение).
Потеря доступа к базе во время работы приводит к ошибке поиска, а не к пустому списку.
Gunicorn в текущем Dockerfile работает от root; при переходе на другого пользователя
нужно выдать ему права на каталог `/data` и его содержимое.

### Ограничение попыток и доверенный Nginx

Лимит — пять попыток за 15 минут на адрес клиента; он общий для Gunicorn workers и
хранится в SQLite. `X-Forwarded-For` не используется. По умолчанию приложение берёт
адрес непосредственного TCP-клиента, не доверяя переданным заголовкам. За Nginx это
может объединить посетителей в один лимит, поэтому перед включением production
необходимо настроить и проверить доверенную цепочку:

1. В действующем `location`, проксирующем Worder, задайте
   `proxy_set_header X-Real-IP $remote_addr;`. Nginx должен **перезаписывать**
   заголовок, а не передавать значение клиента. Проверьте конфигурацию
   `sudo nginx -t` и примените её штатным способом.
2. Установите в защищённом `/opt/worder/worder.env` параметр
   `TRUSTED_PROXY_CIDRS` равным точному IP-адресу Nginx, видимому Gunicorn как
   TCP-peer (например, `172.17.0.1/32`, только если этот адрес действительно
   подтверждён на данном сервере). Docker-сеть может менять этот адрес; проверьте
   его после изменений сети. Допускается список через запятую.
3. Ограничьте доступ к опубликованному порту и Docker-сети доверенными локальными
   процессами: любой клиент с доверенного адреса способен подделать `X-Real-IP`.
   Проверьте, что разные внешние адреса получают независимые лимиты, а прямой
   запрос с недоверенного адреса не может подделать IP заголовком.

Без подтверждённой настройки оставьте `TRUSTED_PROXY_CIDRS` пустым: тогда заголовок
игнорируется, но посетители за одним прокси имеют общий лимит. Пользователи за одним
NAT также делят лимит; распределённый перебор требует дополнительных мер на Nginx.

### Подготовка сервера

Следующие команды предназначены для будущего развёртывания, не запускаются автоматически.
Сначала сохраните **все существующие** переменные OCR и иные параметры контейнера в
`/opt/worder/worder.env` (без вывода значений в терминал). Следующая команда перенесёт
текущие переменные окружения существующего контейнера и добавит секреты; пароль
вводится без отображения. Секретный файл доступен только владельцу.

```bash
sudo install -d -m 700 /opt/worder/data
sudo sh -c 'umask 077; docker inspect words-solver-v2 > /opt/worder/worder-inspect.tmp'
sudo python3 - <<'PY'
import getpass, json, os, secrets
from pathlib import Path
inspection = Path('/opt/worder/worder-inspect.tmp')
config = json.loads(inspection.read_text())[0]['Config']['Env']
values = dict(item.split('=', 1) for item in config if '=' in item)
password = getpass.getpass('Пароль администратора: ')
if not password or password != getpass.getpass('Повторите пароль: '):
    raise SystemExit('Пароли пусты или не совпадают')
# Хеш создаётся внутри установленного контейнера отдельно командой ниже.
values['FLASK_SECRET_KEY'] = secrets.token_hex(32)
values['REJECTED_WORDS_DB_PATH'] = '/data/rejected_words.sqlite3'
values.pop('ADMIN_PASSWORD_HASH', None)
path = Path('/opt/worder/worder.env')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    for key, value in values.items():
        if '\n' in value or '\r' in value:
            raise SystemExit('Многострочные переменные нужно перенести вручную')
        output.write(f'{key}={value}\n')
# Передайте пароль через stdin существующему контейнеру, не через аргументы процесса.
import subprocess
result = subprocess.run(['docker', 'exec', '-i', 'words-solver-v2', 'python', '-c',
    'import sys; from werkzeug.security import generate_password_hash; print(generate_password_hash(sys.stdin.read()))'],
    input=password, text=True, capture_output=True, check=True)
with path.open('a') as output:
    output.write('ADMIN_PASSWORD_HASH=' + result.stdout.strip() + '\n')
inspection.unlink()
PY
```

Если подготовка прервалась, удалите временный `/opt/worder/worder-inspect.tmp` и
неполный env-файл, затем повторите. Файл inspect также содержит секреты. Сохраните
`worder.env` в защищённой резервной копии: смена `FLASK_SECRET_KEY` завершит все
сессии, смена `ADMIN_PASSWORD_HASH` отзовёт ранее выданные сессии. Для смены пароля
создайте новый хеш аналогично через `getpass` и stdin, обновите env-файл и пересоздайте
контейнер. Не передавайте пароль аргументом команды и не записывайте его в историю.

Команды ниже сохраняют параметры из имеющегося `docker-compose.yml`: лимит загрузки,
OCR-переменные переносятся через env-file, логирование и healthcheck указаны явно.
Перед заменой сравните `docker inspect words-solver-v2` с ними и перенесите любые
дополнительные параметры, специфичные для сервера, включая сети, тома, ограничения
ресурсов и параметры запуска; если они не перенесены, приведённая команда не
гарантирует сохранение конфигурации. Изучите `sudo systemctl cat
words-solver-watchdog.timer words-solver-watchdog.service` и убедитесь, что нет
другого механизма автоматического запуска. Не меняйте сами unit-файлы. На время
замены контейнера остановите таймер и дождитесь остановки service; после проверки
контейнера запустите таймер снова, если он работал до обслуживания.

```bash
cd /opt/worder
sudo docker build -t words-solver-app:v2 .
sudo systemctl stop words-solver-watchdog.timer
sudo systemctl stop words-solver-watchdog.service
sudo docker stop words-solver-v2
sudo docker rm words-solver-v2
sudo docker run -d --name words-solver-v2 --restart unless-stopped \
  -p 127.0.0.1:8000:8000 --env-file /opt/worder/worder.env \
  --mount type=bind,src=/opt/worder/data,dst=/data \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()\"" \
  --health-interval 30s --health-timeout 3s --health-retries 3 \
  words-solver-app:v2
# После проверки контейнера, если таймер был активен до обслуживания:
sudo systemctl start words-solver-watchdog.timer
```

Каталог на хосте переживает перезапуск и пересоздание контейнера и образа. Не удаляйте
его при обновлении. До удаления старого контейнера проверьте образ и резервную копию.

### Резервная копия и восстановление

На хосте Python `sqlite3.Connection.backup` создаёт согласованную копию даже при
активных записях. Каталог резервных копий должен быть защищён и находиться на
независимом носителе. Пример (файл назначения не должен существовать):

```bash
sudo install -d -m 700 /opt/worder/backups
sudo python3 - <<'PY'
import datetime, os, sqlite3
source = sqlite3.connect('file:/opt/worder/data/rejected_words.sqlite3?mode=ro', uri=True)
name = '/opt/worder/backups/rejected-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3'
fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
with sqlite3.connect(name) as target:
    source.backup(target)
    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Ошибка проверки копии')
source.close()
print('Копия создана:', name)
PY
```

Для восстановления сначала проверьте, был ли активен таймер, и изучите unit-файлы.
Остановите таймер, дождитесь остановки service и остановите контейнер. Не запускайте
watchdog обратно до завершения восстановления и проверки контейнера. Если имеется
другой механизм автоматического запуска, его также нужно временно остановить.
Исходный каталог `/opt/worder/data` сохраняется: замена самого каталога может нарушить
существующее bind-монтирование контейнера. Команды ниже предполагают, что архивный
каталог ещё не существует; при любой ошибке остановитесь и не запускайте контейнер.

```bash
sudo systemctl is-active words-solver-watchdog.timer
sudo systemctl stop words-solver-watchdog.timer
sudo systemctl stop words-solver-watchdog.service
sudo docker stop words-solver-v2
sudo install -d -m 700 /opt/worder/backups
sudo mkdir -m 700 /opt/worder/backups/data-before-restore
for suffix in '' -wal -shm; do
  path="/opt/worder/data/rejected_words.sqlite3${suffix}"
  if sudo test -e "$path"; then sudo mv "$path" /opt/worder/backups/data-before-restore/; fi
done
sudo python3 - /opt/worder/backups/ИМЯ_КОПИИ.sqlite3 <<'PY_RESTORE'
import os, sqlite3, sys
from pathlib import Path
source = sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True)
if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
    raise SystemExit('Копия повреждена')
path = '/opt/worder/data/rejected_words.sqlite3'
with sqlite3.connect(path) as target:
    source.backup(target)
    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Восстановленная база повреждена')
os.chmod(path, 0o600)
source.close()
PY_RESTORE
sudo docker start words-solver-v2
# После проверки контейнера, если таймер был активен до обслуживания:
sudo systemctl start words-solver-watchdog.timer
```

После восстановления проверьте `/ready`, административный список и права на файлы.
