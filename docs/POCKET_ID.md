# Pocket ID 登录与 API 授权

此集成使用 Pocket ID 的 OIDC 和 APIs and permissions 功能。一室光不创建本地用户、密码或角色表。用户与客户端授权在 Pocket ID 中管理，灯具、场景和倒计时仍是共享的。

以下用 `https://light.example.com` 表示一室光，用 `https://auth.example.com` 表示 Pocket ID。替换为自己的域名。当前实现要求一室光使用独立 HTTPS 域名，不支持 `/light` 子路径。

## 1. 注册 API

在 Pocket ID 的 Administration → APIs 中创建：

| 设置 | 值 |
| --- | --- |
| 名称 | 一室光 API |
| Resource | `https://light.example.com/api` |
| Permission key | `lights:read` |
| Permission key | `lights:control` |

Resource 是令牌的 audience 标识，不需要提供对应的网页。必须与 `OPPLE_OIDC_RESOURCE` 完全一致。读取灯具、场景、操作记录及导出需要 `lights:read`；修改灯光、场景、倒计时和主动刷新需要 `lights:control`。

## 2. 注册网页登录客户端

创建一个保密 OIDC 客户端，名称如“一室光网页”。配置回调 URL：

```
https://light.example.com/auth/callback
```

保留 Client ID 和 Client Secret。在该客户端 Access → API access 中添加一室光 API，启用 **User-delegated access**，授予 `lights:read` 和 `lights:control`。网页登录需要这两项权限。可以使用 Pocket ID 的 Allowed user groups 限定哪些用户可以登录。

登录采用授权码流程、PKCE S256、state 和 nonce 校验；通行密钥验证由 Pocket ID 完成。浏览器只收到随机的 HttpOnly、Secure、SameSite=Lax Cookie，JWT 和客户端密钥不会存入浏览器。服务只保存会话摘要、主体标识、显示名、权限和期限。会话期限取 ID token、access token 到期时间与八小时上限中的最短值；到期后重新登录，没有自动刷新。

## 3. 配置并启动

在服务目录的 `.env` 中填写以下内容，Client Secret 只在服务器上填写，不提交 Git：

```dotenv
OPPLE_PUBLIC_URL=https://light.example.com
OPPLE_OIDC_ISSUER=https://auth.example.com
OPPLE_OIDC_CLIENT_ID=填写网页客户端ID
OPPLE_OIDC_CLIENT_SECRET=填写网页客户端密钥
OPPLE_OIDC_RESOURCE=https://light.example.com/api
```

```sh
chmod 600 .env
docker compose up -d --build
```

Pocket ID 是唯一认证方式。缺少配置或启动时身份服务不可用会导致启动失败，不会退回匿名访问。旧的认证模式、口令和演示环境变量均已移除。

Cloudflare Tunnel 将一室光域名转发到部署机的 `http://127.0.0.1:8080`，Pocket ID 域名转发到其原有服务。用户通过 HTTPS 的一室光域名登录。此模式同时保护内网 IP 的 API；HTTP 内网地址不能承载 Secure 登录 Cookie。服务宿主机仍需要能访问灯具所在局域网。

直接运行而不使用默认 Compose 时，可用 `OPPLE_OIDC_CLIENT_SECRET_FILE` 指向容器内的只读密钥文件。默认 Compose 使用 `.env` 注入密钥；若选用 Docker secrets，需要自行添加 secret 挂载和 `_FILE` 环境变量。

## 4. 苹果快捷指令

另建一个保密 OIDC 客户端，名称如“一室光快捷指令”。在 Access → API access 中添加一室光 API，启用 **Client access (M2M)** 并授予两项权限。它与网页登录客户端分别管理和撤销。

快捷指令先执行“获取 URL 内容”：

- URL：`https://auth.example.com/api/oidc/token`
- 方法：POST。
- 请求体：表单。
- `grant_type`：`client_credentials`。
- `client_id` 和 `client_secret`：快捷指令客户端的凭证。
- `resource`：`https://light.example.com/api`。
- `scope`：`lights:read lights:control`。

从返回字典取 `access_token`，再执行“获取 URL 内容”：

- URL：`https://light.example.com/api/v1/lights/bedroom/state`。
- 方法：PATCH。
- 请求头 `Authorization`：`Bearer ` 加上 access_token。
- 请求体：JSON，例如 `{"power":true,"color_temperature_kelvin":4000,"brightness_percent":70}`。

成功接受命令返回 HTTP 202，响应 `id` 是操作 ID。可继续 GET `/api/v1/operations/{id}` 查看执行结果，需要 `lights:read`。每次运行先取新令牌即可，无需模拟网页登录或在自动化时验证通行密钥。快捷指令含客户端密钥，不应作为公开模板分享；撤销此客户端即可停止它获取新令牌，已签发令牌在到期前仍有效。

Pocket ID 的管理 API Key（`X-API-KEY`）用于管理身份服务，不是灯光凭证。一室光只接受 audience 与权限正确的 OAuth access token，不接受管理 API Key 或 ID token。

## 验证与运行行为

JWT 使用 PyJWT 验证 RS256 签名、issuer、audience、有效期和权限。公钥缓存五分钟并支持 key ID 轮换；日常 API 请求不需要逐次回访 Pocket ID。退出登录删除一室光的服务端会话，不执行 Pocket ID 全局退出。身份服务撤销授权不会即时撤销已签发的 JWT 或现有网页会话，权限变化生效存在剩余令牌期限。

登录事务和会话保存在数据卷 `auth.db`，控制数据仍在 `service.db`。网页导出不包含认证数据。真实首次联调顺序：匿名 API 返回 401 → 登录成功 → 状态读取成功 → 退出后 401 → 快捷指令令牌读取成功。确认上述步骤后再测试一次真实灯具写入。

参考：[Pocket ID APIs and permissions](https://pocket-id.org/docs/guides/apis)、[OIDC client authentication](https://pocket-id.org/docs/guides/oidc-client-authentication)、[Pocket ID 管理 REST API](https://pocket-id.org/docs/api)。
