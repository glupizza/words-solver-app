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
Запустить приложение docker.desktop

И в терминале из корня проекта:
```bash
docker build -t words-solver .
docker run --rm -p 8000:8000 words-solver
```
Открывай: http://localhost:8000
