VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup setup-backend setup-frontend dev dev-backend dev-frontend test lint fmt docker docker-run

setup: setup-backend setup-frontend

setup-backend:
	python3 -m venv $(VENV)
	$(PIP) install -r backend/requirements.txt
	$(PIP) install -r backend/requirements-dev.txt

setup-frontend:
	cd frontend && npm ci

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(PY) -m flask --app backend.app:app run --host 0.0.0.0 --port 8000 --debug

dev-frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 5173

test:
	$(PY) -m pytest -q

lint: lint-backend lint-frontend

lint-backend:
	$(PY) -m ruff check backend
	$(PY) -m ruff format --check backend

fmt:
	$(PY) -m ruff format backend

lint-frontend:
	cd frontend && npm run lint

docker:
	docker build -t words-solver:local .

docker-run:
	docker run --rm -p 127.0.0.1:8000:8000 --env-file "$${WORDER_ENV_FILE:?Set WORDER_ENV_FILE}" \
	  --mount "type=bind,src=$${WORDER_DATA_DIR:?Set WORDER_DATA_DIR},dst=/data" words-solver:local
