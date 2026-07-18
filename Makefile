# Makefile for Zest-Agent development
# Targets:
#   make install   - install all backend deps + frontend deps + pre-commit
#   make dev       - start all three services in background (via scripts/start-dev.sh)
#   make stop      - stop all dev services
#   make status    - show running state
#   make infra     - start Redis + MySQL via docker compose
#   make up        - start full stack (Redis + MySQL + three services) via compose
#   make down      - stop docker compose stack
#   make logs      - tail dev logs
#   make lint      - run ruff on backend
#   make test      - run pytest across backend workspaces
#   make web-build - build frontend production bundle
#   make clean     - clean caches

ROOT := $(shell pwd)
LOG_DIR := $(ROOT)/.tmp

.PHONY: install dev stop status infra up down logs lint test web-build clean

install:
	uv sync
	cd zest-web && pnpm install
	pre-commit install

infra:
	docker compose up -d

up:
	docker compose --profile app up -d

down:
	docker compose down

dev:
	./scripts/start-dev.sh start

stop:
	./scripts/start-dev.sh stop

status:
	./scripts/start-dev.sh status

logs:
	tail -f $(LOG_DIR)/zest-*.log

lint:
	uv run ruff check zest-app-server zest-agent-server zest-common

test:
	uv run pytest zest-common zest-agent-server/zest-sdk zest-agent-server/zest-tools zest-agent-server/zest-service zest-app-server -q

web-build:
	cd zest-web && pnpm build

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} +
	rm -rf zest-web/dist zest-web/node_modules/.vite
