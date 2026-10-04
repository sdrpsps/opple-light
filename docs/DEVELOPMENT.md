# 开发与部署

一室光的后端使用 Python 3.12 和 uv，前端使用 Vue 3、TypeScript、Tailwind CSS 4 和 Vite。`pyproject.toml` 声明运行与开发依赖，`uv.lock` 锁定完整依赖树；不再维护 requirements 文件。Docker 与 GitHub Actions 均使用 uv 0.12.19 和同一份锁文件。

## 本地开发

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 [pnpm](https://pnpm.io/installation)，然后在项目根目录执行：

```sh
uv sync --locked
pnpm install --frozen-lockfile
pnpm run build
uv run --locked pytest -q
```

也可以使用与 byteshare 同样命名的 Makefile 快捷命令：

```sh
make setup       # 使用 uv.lock 和 pnpm-lock.yaml 安装全部依赖
make dev         # 同时启动前后端，Ctrl+C 停止两者
make dev:api     # 只启动 FastAPI 热更新服务
make dev:web     # 只启动 Vue 开发服务
make start       # 构建前端后启动 FastAPI，无热更新
make build       # 构建前端静态资源
make test        # Python 与浏览器测试（浏览器测试需要 Chrome）
make lint        # 组件 250 行限制与 Prettier 格式检查
make help        # 查看所有命令
```

`make dev` 使用 `make -j2 dev:api dev:web` 并行启动 FastAPI 和 Vite，在终端按 Ctrl+C 停止。开发启动不执行前端构建或 TypeScript 类型检查，也不依赖 `frontend/dist/`；开发页面由 Vite 提供。`dev:api` 和 `start:api` 自动加载存在的 `.env` 文件；也可以通过 `ENV_FILE=路径` 指定其他文件。命令不会创建或覆盖已有配置。`make dev` 和 `make dev:api` 自动设置 `OPPLE_ENV=development`，无需填写 Pocket ID 配置或登录；`make start` 和生产部署仍需要按 `.env.example` 配置 Pocket ID。

默认监听 `127.0.0.1`，API 端口为 8080，Vue 端口为 5173，开发页面地址为 `http://127.0.0.1:5173/`。例如 `make dev API_PORT=8090 WEB_PORT=5174` 会同时调整 API、Vue 端口和前端代理目标。可以覆盖 `UV`、`PNPM`、`DOCKER`、`HOST`、`API_PORT`、`WEB_PORT` 和 `ENV_FILE` 变量。直接运行 `pnpm run dev` 时，代理默认指向 `127.0.0.1:8080`，也支持 `OPPLE_API_TARGET` 环境变量。

`make docker:up` 构建并启动 Compose 服务，`make docker:logs` 跟踪 `light` 服务日志，`make docker:down` 停止容器并保留数据卷。`make lock` 更新两套锁文件，`make lock:api`、`make lock:web` 可分别执行。

uv 创建项目内的 `.venv`。开发依赖默认安装；只有运行服务时可以使用 `uv sync --locked --no-dev`。添加依赖使用 `uv add 包名`，添加测试工具使用 `uv add --dev 包名`，移除依赖使用 `uv remove 包名`。升级时使用 `uv lock --upgrade-package 包名`，随后执行同步和测试。提交 `pyproject.toml` 与 `uv.lock`，不提交虚拟环境。

直接启动免登录的本地开发后端，也可以运行：

```sh
OPPLE_ENV=development uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

开发模式跳过 Pocket ID 初始化和 API 登录校验，页面直接进入控制界面，设置中隐藏退出登录。开发模式允许来自 `localhost`、`127.0.0.1` 和 `::1` 不同端口的 HTTP/HTTPS 页面提交操作，适配 Vite 开发代理；外部来源仍会被拦截。设备仍连接配置中的真实灯具；测试中的模拟设备和身份服务仅存在于 `tests/`。开发服务默认只监听本机，请仅在本地开发时使用 `OPPLE_ENV=development`。正常启动时不设置此变量，Pocket ID 登录需要从配置的 HTTPS 对外域名访问。

前端开发需要 Node.js 22.12 或更高版本和 pnpm 11.9.0（由 `package.json` 的 `packageManager` 固定）。源代码在 `frontend/src/`，`pnpm run build` 输出到 `frontend/dist/`，由 FastAPI 提供。开发时先启动后端，再运行 `pnpm run dev`；Vite 将 `/api` 和 `/auth` 转发到 `127.0.0.1:8080`。免登录由后端的 `OPPLE_ENV=development` 控制；单独启动 Vite 时，需配合 `make dev:api` 或上述开发后端命令。

所有 Vue 组件使用 `<script setup lang="ts">`，前端源码和 Vite 配置使用 TypeScript。`tsconfig.json` 开启严格类型检查，`pnpm run typecheck` 使用 vue-tsc 检查组件模板及 TypeScript；构建和 `make lint` 都会执行类型检查。`types.ts` 定义 API 数据及控制器状态类型。

Vue 组件按界面职责拆分，功能 hooks 自己持有状态并用 VueUse 的 `createSharedComposable` 在消费者之间共享实例，不需要统一控制器或 `provide/inject` 初始化。组件按需调用 `useLightSession`、`useLightSync`、`useLightCommands`、`useLightScenes`、`useLightTimer`、`useLightSettings` 和 `useLightUI`，分别管理会话、设备状态、操作队列、场景、倒计时、设置与备份、弹窗与通知。各 hook 自行调用必要的依赖；设置不会启动灯具轮询或加载场景。会话认证与失效、设备状态更新用 `createEventHook` 通知订阅者，倒计时完成提示由倒计时 hook 处理。灯光调节与场景应用共用操作队列。最后一个消费者释放时，共享作用域清理定时器、轮询和事件订阅，再次使用会创建新实例；选中灯具仍保存在本地存储。弹簧、即时按压反馈和移动端弹层手势在 `lib/motion.ts`。组件使用 Tailwind 工具类；`frontend/src/style.css` 只保留主题、基础规则与全局无障碍设置。工具类直接写在模板的 `class` 或 `:class` 中，不使用 `@apply` 或 `@reference`。组件专属的普通 CSS 放在各自的 `<style scoped>` 中；控制面板样式放在同目录的 `LightPanel.css`，通过 `<style scoped src="./LightPanel.css">` 加载，避免超过组件行数限制。弹窗表单的工具类直接写在各自模板中，品牌标记由 `BrandMark` 组件复用；灯具示意、原生滑块和材料效果使用少量 CSS。`pnpm run check:components` 检查每个 `.vue` 文件最多 250 行，每次构建都会执行，包含 template、script、style 和空行。VueUse 的 `useStorage` 保存选中灯具，`useIntervalFn` 管理轮询与倒计时时钟，`useEventListener` 监听 `visibilitychange`，在页面重新可见时刷新状态。`lib/api.ts` 使用 ky 发起请求，统一处理 12 秒超时、401、服务错误、204 和备份下载；关闭自动重试，避免重复提交操作。修改前端后需要重新构建，不能直接修改生成的 `frontend/dist/` 文件。该目录不提交到 Git；`app/` 只保留 Python 后端代码，包含登录失败在内的所有界面均由 Vue 渲染。开发和生产环境的页面入口都是 `/`，构建资源使用 `/assets/`，图标和 manifest 直接从根路径访问。

浏览器测试需要 Playwright 和 Chrome：

```sh
pnpm install --frozen-lockfile
PLAYWRIGHT_CHANNEL=chrome pnpm run test:browser
```

浏览器测试独立提供静态页面并拦截全部 API，覆盖 Pocket ID 登录入口、退出、会话过期、灯光调节、连续操作合并、关灯参数暂存、场景增删改与应用、倒计时、备份、离线状态、布局和动画，不连接真实身份服务或灯具。`tests/hooks.cjs` 另外在独立 effect scope 中测试 hook，无需挂载 App，验证状态共享、销毁后重建、按需依赖和轮询清理。产物写入被 Git 忽略的 `test-artifacts/`。

## 单容器 Docker 部署

原生 Linux / NAS 宿主机需要能够访问灯具局域网。项目只保留标准文件 `compose.yaml`。默认 Compose 使用 host 网络，由服务直接收发灯具 UDP 55001，无转发脚本或辅助容器：

```sh
docker compose up -d --build
docker compose ps
```

HTTP 监听 8080。启动前必须按 `.env.example` 配置 [Pocket ID](POCKET_ID.md)。配置灯具使用 `config/config.yaml`，修改后重启服务。升级旧版时需同步新的配置格式，删除原配置中的 `mode`、`default_kelvin` 和 `default_brightness` 字段；服务仅连接真实灯具。Mac 虚拟化容器的网络不保证能直连灯具，建议在原生 Linux 部署。

Docker 使用 Corepack 按 `packageManager` 安装 pnpm 11.9.0，前端构建阶段通过 `pnpm install --frozen-lockfile` 使用 `pnpm-lock.yaml` 安装依赖并编译 Vue 和 Tailwind，只把静态产物复制到运行镜像，不包含 Node.js 或前端源码。Python 构建阶段使用 `uv sync --locked --no-dev --no-install-project`，只安装锁定的运行依赖。运行镜像包含虚拟环境，不包含 uv、编译器或测试依赖；以非 root 用户启动，适配 Compose 的只读根文件系统。

只有一个 Dockerfile。如果 Docker Hub 访问困难，可指定可达的 Python 基础镜像：

```sh
docker build \
  --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim \
  -t opple-local:1.0.0 .
docker compose up -d --no-build
```

uv 默认从 `ghcr.io/astral-sh/uv:0.12.19` 复制构建工具；需要镜像时可同样设置 `--build-arg UV_IMAGE=镜像地址`，保持相同 uv 版本。前端默认基础镜像为 `node:22-alpine`，可用 `--build-arg NODE_IMAGE=镜像地址` 替换。

GitHub Actions 沿用现有发布工作流，通过 Dockerfile 使用 uv 和锁文件构建并推送 GHCR 镜像；文档更新不会触发发布。Python 测试使用上面的本地命令执行。

## 目录与数据

| 路径 | 用途 |
| --- | --- |
| `app/` | API、认证、直接 UDP 驱动和生成的静态网页 |
| `frontend/` | Vue 组件、Tailwind 样式与前端资源 |
| `scripts/` | 组件行数约束检查 |
| `config/` | 灯具配置 |
| `tests/` | Python 与浏览器测试 |
| `docs/` | 开发、部署与 Pocket ID 说明 |
| `screenshots/` | 当前页面的桌面与手机截图 |

`.env`、`data/`、`.venv/` 和 `test-artifacts/` 是本地配置或生成内容，均不进入 Git 与 Docker 构建上下文。清理代码不删除这些运行数据。Docker 数据卷保存状态、场景和倒计时；`docker compose down` 保留数据，需要保留数据时不要使用 `down -v`。
