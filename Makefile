SHELL := /bin/sh

UV ?= uv
PNPM ?= pnpm
DOCKER ?= docker
HOST ?= 127.0.0.1
API_PORT ?= 8080
WEB_PORT ?= 5173
ENV_FILE ?= .env

.DEFAULT_GOAL := help

.PHONY: help setup dev dev\:api dev\:web sync\:api install\:web start start\:api test test\:api test\:web lint lint\:web format\:web lock lock\:api lock\:web build build\:web docker\:up docker\:down docker\:logs

help: ## 显示可用命令
	@printf '%s\n' \
		'  setup         安装 API 与 Web 依赖（使用锁文件）' \
		'  dev           同时启动 API 与 Web，Ctrl+C 停止两者' \
		'  dev:api       只启动 FastAPI 热更新服务（默认 8080）' \
		'  dev:web       只启动 Vue 开发服务（默认 5173）' \
		'  sync:api      使用 uv 同步 Python 依赖' \
		'  install:web   使用 pnpm 安装前端依赖' \
		'  start         构建前端并启动服务（无热更新）' \
		'  start:api     与 start 相同，由 FastAPI 提供前端与 API' \
		'  test          运行 Python 与浏览器测试' \
		'  test:api      运行 Python 测试' \
		'  test:web      构建前端并运行浏览器测试（需要 Chrome）' \
		'  lint          检查 Vue 组件行数与前端格式' \
		'  lint:web      与 lint 相同' \
		'  format:web    格式化前端源码与构建脚本' \
		'  lock          更新 Python 与前端锁文件' \
		'  lock:api      更新 uv.lock' \
		'  lock:web      更新 pnpm-lock.yaml' \
		'  build         构建 Vue 与 Tailwind 静态资源' \
		'  build:web     与 build 相同，产物位于 frontend/dist/' \
		'  docker:up     构建并启动生产容器' \
		'  docker:down   停止容器（保留数据卷）' \
		'  docker:logs   跟踪服务日志' \
		'' \
		'可覆盖变量：UV、PNPM、DOCKER、HOST、API_PORT、WEB_PORT、ENV_FILE。' \
		'本地 dev 命令免登录；正常启动前请按 .env.example 填写 Pocket ID 配置。'

setup: ## 安装全部依赖
	$(MAKE) sync:api install:web

sync\:api: ## 同步 Python 依赖
	$(UV) sync --locked

install\:web: ## 安装前端依赖
	$(PNPM) install --frozen-lockfile

dev: ## 使用 Make 并行启动前后端
	$(MAKE) -j2 dev:api dev:web

dev\:api: ## 启动 FastAPI 热更新服务；存在 ENV_FILE 时加载
	@set --; \
	if [ -f "$(ENV_FILE)" ]; then set -- --env-file "$(ENV_FILE)"; fi; \
	exec $(UV) run --locked "$$@" env OPPLE_ENV=development uvicorn app.main:app --reload --reload-dir app --host "$(HOST)" --port "$(API_PORT)"

dev\:web: ## 启动 Vue 开发服务，代理指向当前 API 端口
	OPPLE_API_TARGET="http://$(HOST):$(API_PORT)" $(PNPM) run dev --host "$(HOST)" --port "$(WEB_PORT)" --strictPort

start:
	$(MAKE) start:api

start\:api: ## 构建前端后启动 FastAPI
	$(MAKE) build:web
	@set --; \
	if [ -f "$(ENV_FILE)" ]; then set -- --env-file "$(ENV_FILE)"; fi; \
	exec $(UV) run --locked "$$@" uvicorn app.main:app --host "$(HOST)" --port "$(API_PORT)" --workers 1 --no-access-log

test: ## 运行全部测试
	$(MAKE) test:api test:web

test\:api:
	$(MAKE) build:web
	$(UV) run --locked pytest -q

test\:web:
	$(PNPM) run test:browser

lint:
	$(MAKE) lint:web

lint\:web:
	$(PNPM) run typecheck
	$(PNPM) run check:components
	$(PNPM) exec prettier --check frontend/src frontend/index.html vite.config.ts scripts/check-components.mjs

format\:web:
	$(PNPM) exec prettier --write frontend/src frontend/index.html vite.config.ts scripts/check-components.mjs

lock:
	$(MAKE) lock:api lock:web

lock\:api:
	$(UV) lock

lock\:web:
	$(PNPM) install --lockfile-only --no-frozen-lockfile

build:
	$(MAKE) build:web

build\:web:
	$(PNPM) run build

docker\:up:
	$(DOCKER) compose up -d --build

docker\:down:
	$(DOCKER) compose down

docker\:logs:
	$(DOCKER) compose logs -f light
