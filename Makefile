COMPOSE      := docker compose -f docker/app/docker-compose.yml --env-file .env
SERVICE      ?= api relay consumer
POETRY       := poetry run

.DEFAULT_GOAL := help

.PHONY: help env build up down restart ps logs scale migrate revision downgrade \
        run-api run-consumer run-relay test test-integration lint fmt \
        shell psql rabbit-queues clean

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Использование: make \033[36m<target>\033[0m\n\n"} \
		/^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Создать .env из .env.example
	@test -f .env || (cp .env.example .env && echo ".env создан из .env.example")

build: env ## Собрать образ
	$(COMPOSE) build

up: env ## Поднять весь стек (с пересборкой)
	$(COMPOSE) up -d --build

down: ## Остановить стек (данные сохраняются)
	$(COMPOSE) down

restart: ## Перезапустить сервисы: make restart SERVICE="api consumer"
	$(COMPOSE) restart $(SERVICE)

ps: ## Статус контейнеров
	$(COMPOSE) ps

logs: ## Логи: make logs SERVICE=consumer
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

scale: ## Масштабирование: make scale s=consumer n=3
	@test -n "$(s)" -a -n "$(n)" || (echo "Использование: make scale s=<service> n=<count>"; exit 1)
	$(COMPOSE) up -d --no-recalc --scale $(s)=$(n) $(s)

shell: ## Shell в контейнере: make shell SERVICE=api
	$(COMPOSE) exec $(firstword $(SERVICE)) sh

psql: ## psql в контейнере postgres
	$(COMPOSE) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

rabbit-queues: ## Очереди RabbitMQ: сообщения и consumers (смотри payments.dead)
	$(COMPOSE) exec rabbitmq rabbitmqctl list_queues name messages consumers

clean: ## Удалить контейнеры И volumes (БД и очереди будут стёрты)
	@read -p "Удалить все данные postgres и rabbitmq? [y/N] " ans; [ "$$ans" = "y" ] || exit 1
	$(COMPOSE) down -v --remove-orphans

migrate: ## Применить миграции в docker
	$(COMPOSE) run --rm migrate

revision: ## Создать миграцию: make revision m="add column"
	@test -n "$(m)" || (echo 'Использование: make revision m="message"'; exit 1)
	$(POETRY) alembic revision --autogenerate -m "$(m)"

downgrade: ## Откатить последнюю миграцию (локально)
	$(POETRY) alembic downgrade -1

run-api: ## API локально с автоперезагрузкой
	$(POETRY) uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

run-consumer: ## Consumer локально
	$(POETRY) faststream run src.workers.consumer:app --reload

run-relay: ## Outbox relay локально
	$(POETRY) python -m src.workers.relay

test: ## Unit-тесты
	$(POETRY) pytest -m "not integration"

test-integration: ## Интеграционные тесты (нужен запущенный postgres)
	RUN_INTEGRATION=1 $(POETRY) pytest -m integration

lint: ## Проверка ruff
	$(POETRY) ruff check src tests
	$(POETRY) ruff format --check src tests

fmt: ## Автоформатирование
	$(POETRY) ruff check --fix src tests
	$(POETRY) ruff format src tests
