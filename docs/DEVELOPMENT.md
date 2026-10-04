# 开发与部署

一室光使用 Python 3.12 和 uv。`pyproject.toml` 声明运行与开发依赖，`uv.lock` 锁定完整依赖树；不再维护 requirements 文件。Docker 与 GitHub Actions 均使用 uv 0.12.19 和同一份锁文件。

## 本地开发

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后在项目根目录执行：

```sh
uv sync --locked
uv run --locked pytest -q
```

uv 创建项目内的 `.venv`。开发依赖默认安装；只有运行服务时可以使用 `uv sync --locked --no-dev`。添加依赖使用 `uv add 包名`，添加测试工具使用 `uv add --dev 包名`，移除依赖使用 `uv remove 包名`。升级时使用 `uv lock --upgrade-package 包名`，随后执行同步和测试。提交 `pyproject.toml` 与 `uv.lock`，不提交虚拟环境。

本地启动同样需要真实 Pocket ID 配置。先填写 `.env`，再运行：

```sh
uv run --locked --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8080
```

登录需要从配置的 HTTPS 对外域名访问。测试中的模拟设备和身份服务仅存在于 `tests/`，应用和 Docker 运行镜像不包含模拟模式。

浏览器测试需要 Node.js、Playwright 和 Chrome：

```sh
npm install --no-save --package-lock=false playwright
PLAYWRIGHT_CHANNEL=chrome node tests/browser.cjs
```

浏览器测试独立提供静态页面并拦截全部 API，覆盖 Pocket ID 登录入口、退出、会话过期、布局和动画，不连接真实身份服务或灯具。产物写入被 Git 忽略的 `test-artifacts/`。

## 单容器 Docker 部署

原生 Linux / NAS 宿主机需要能够访问灯具局域网。项目只保留标准文件 `compose.yaml`。默认 Compose 使用 host 网络，由服务直接收发灯具 UDP 55001，无转发脚本或辅助容器：

```sh
docker compose up -d --build
docker compose ps
```

HTTP 监听 8080。启动前必须按 `.env.example` 配置 [Pocket ID](POCKET_ID.md)。配置灯具使用 `config/config.yaml`，修改后重启服务。升级旧版时需同步新的配置格式，删除原配置中的 `mode`、`default_kelvin` 和 `default_brightness` 字段；服务仅连接真实灯具。Mac 虚拟化容器的网络不保证能直连灯具，建议在原生 Linux 部署。

Docker 构建使用 `uv sync --locked --no-dev --no-install-project`，只安装锁定的运行依赖。运行镜像包含虚拟环境，不包含 uv、编译器或测试依赖；以非 root 用户启动，适配 Compose 的只读根文件系统。

只有一个 Dockerfile。如果 Docker Hub 访问困难，可指定可达的 Python 基础镜像：

```sh
docker build \
  --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim \
  -t opple-local:1.0.0 .
docker compose up -d --no-build
```

uv 默认从 `ghcr.io/astral-sh/uv:0.12.19` 复制构建工具；需要镜像时可同样设置 `--build-arg UV_IMAGE=镜像地址`，保持相同 uv 版本。

GitHub Actions 沿用现有发布工作流，通过 Dockerfile 使用 uv 和锁文件构建并推送 GHCR 镜像；文档更新不会触发发布。Python 测试使用上面的本地命令执行。

## 目录与数据

| 路径 | 用途 |
| --- | --- |
| `app/` | API、认证、直接 UDP 驱动和静态网页 |
| `config/` | 灯具配置 |
| `tests/` | Python 与浏览器测试 |
| `docs/` | 开发、部署与 Pocket ID 说明 |
| `screenshots/` | 当前页面的桌面与手机截图 |

`.env`、`data/`、`.venv/` 和 `test-artifacts/` 是本地配置或生成内容，均不进入 Git 与 Docker 构建上下文。清理代码不删除这些运行数据。Docker 数据卷保存状态、场景和倒计时；`docker compose down` 保留数据，需要保留数据时不要使用 `down -v`。
