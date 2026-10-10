# WA DOT Login Automation

基于 Python 的 Western Australia Department of Transport（WA DOT）在线服务登录会话管理工具。

项目通过模拟浏览器 HTTP 请求，实现登录流程、Cookie 会话维护以及重定向处理，支持 JavaServer Faces（JSF）应用的特殊响应机制。

## Features

- **Session Management**：自动维护 HTTP 会话及 Cookies
- **Dual JSESSIONID Support**：支持同一域名下不同 Path 的多个 `JSESSIONID`
- **Automatic Cookie Updates**：根据 Cookie 的 Name、Domain、Path 自动更新
- **SSL Certificate Handling**：使用系统证书存储处理 HTTPS 连接
- **HTTP Redirects**：处理标准 HTTP 302 重定向
- **JSF AJAX Redirects**：识别并处理 JSF `partial-response` 重定向
- **Reusable Architecture**：封装通用请求逻辑，减少重复代码

## Requirements

- Python 3.10+
- requests
- truststore

安装依赖：

```bash
pip install requests truststore
```

## Project Structure

建议项目结构：

```text
wa-dot-login/
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

其中：

- `main.py`：登录及 HTTP 会话管理逻辑
- `requirements.txt`：Python 依赖
- `README.md`：项目文档
- `.gitignore`：忽略本地敏感文件及缓存

实际文件名以项目代码为准。

## Architecture

项目核心采用 `TransportSession` 类管理登录状态。

| Method | Description |
|---|---|
| `get_login_page()` | 获取登录页面并初始化会话 |
| `login()` | 提交登录请求及处理登录响应 |
| `request()` | 对外提供统一 HTTP 请求入口 |
| `_send()` | 执行底层 HTTP 请求及响应处理 |

设计目标是集中管理 Cookie、SSL 和重定向逻辑，避免在不同请求方法中重复实现。

## Cookie Management

### Dual JSESSIONID

WA DOT 登录过程中，可能出现同一域名下两个具有不同 Path 的 `JSESSIONID`。

例如：

```http
Cookie: JSESSIONID=session_A; JSESSIONID=session_B
```

这两个 Cookie 虽然名称相同，但可能属于不同的路径作用域。

因此，不能简单地使用 Cookie 名称作为唯一标识。

### Cookie Identity

Cookie 唯一标识采用：

```python
(name, domain, path)
```

例如：

```text
("JSESSIONID", "online.transport.wa.gov.au", "/tso")
("JSESSIONID", "online.transport.wa.gov.au", "/tso/selfservice")
```

以上路径仅用于说明，并非实际抓包数据。

### Cookie Update Rules

当服务器返回新的 `Set-Cookie` 时：

1. 解析 Cookie 名称、Domain 和 Path。
2. 查找具有相同 `(name, domain, path)` 的 Cookie。
3. 如果存在，则更新其值。
4. 如果不存在，则保存新的 Cookie。
5. 不覆盖其他 Path 下的同名 Cookie。

这样可以确保一个 `JSESSIONID` 更新时，不会意外删除另一个有效会话 Cookie。

发送请求时，应按照请求 URL 对 Cookie 的作用域进行匹配，保留所有适用的 Cookie，包括名称相同但路径不同的 Cookie。

## SSL Certificate Handling

部分 Python 环境访问 WA DOT HTTPS 服务时，可能出现 SSL 证书验证错误，例如：

```text
SSLError: CERTIFICATE_VERIFY_FAILED
```

项目使用 `truststore` 配合系统证书存储进行 TLS 验证。

其目的是解决 Python 运行环境与系统信任证书链之间的兼容问题。

**Security Note**

不建议直接使用：

```python
verify=False
```

关闭 SSL 验证可能导致中间人攻击风险。

## Redirect Handling

项目需要处理两种不同的重定向机制。

### 1. Standard HTTP Redirect

服务器可能返回：

```http
HTTP/1.1 302 Found
Location: /tso/selfservice/overview.jsf
```

程序应解析 `Location`，按照 HTTP 重定向规则继续发送请求，并保留适用的会话 Cookie。

### 2. JSF AJAX Redirect

WA DOT 使用 JavaServer Faces（JSF），部分 AJAX 请求不会返回标准的 HTTP 302，而是返回 XML：

```xml
<partial-response>
    <redirect url="../overview.jsf"></redirect>
</partial-response>
```

即使 HTTP 状态为 `200 OK`，该响应仍然要求客户端导航到新页面。

处理步骤：

1. 检查响应是否为 JSF Partial Response。
2. 解析 XML 中的 `redirect` 元素。
3. 提取 `url` 属性。
4. 使用当前请求 URL 解析相对路径。
5. 向目标 URL 发起 GET 请求。
6. 继续维护会话与 Cookie。

例如：

```text
POST /tso/selfservice/public/login.jsf
        |
        v
HTTP 200 + JSF partial-response
        |
        v
Extract ../overview.jsf
        |
        v
Resolve redirect URL
        |
        v
GET /tso/selfservice/overview.jsf
```

JSF XML Redirect 和 HTTP 302 是两种不同的响应机制，需要分别识别，但可以共用后续请求处理逻辑。

## Login Workflow

整体流程如下：

```text
Start
  |
  v
Initialize TransportSession
  |
  v
GET Login Page
  |
  v
Initialize Cookies / Session
  |
  v
POST Login Request
  |
  v
Receive Response
  |
  +---- Set-Cookie --------> Update Cookie Jar
  |
  +---- HTTP 302 ----------> Follow Location
  |
  +---- JSF Redirect ------> Parse XML and GET Target
  |
  v
Verify Authenticated Page
  |
  v
Reuse Authenticated Session
```

需要注意，收到重定向并不一定代表登录成功，仍需通过目标页面或其他明确的认证状态进行验证。

## Usage

基本使用方式示意：

```python
from main import TransportSession

session = TransportSession()

session.get_login_page()

# 使用项目实际定义的参数提交登录
# session.login(...)

# 通过统一入口发送后续请求
# response = session.request(...)
```

以上是接口使用示意，具体构造函数参数、登录字段和返回值需要与最终 Python 源码对应。

## Troubleshooting

### SSL Certificate Verify Failed

可能原因：

- Python 证书链配置不完整
- 系统证书与 Python 环境不同步
- HTTPS 代理或证书信任配置异常

建议检查系统证书、`truststore` 配置以及运行环境。

### Missing JSESSIONID

可能原因：

- 按 Cookie Name 去重，导致同名 Cookie 被覆盖
- Cookie Path 或 Domain 不匹配
- 自行构造 Cookie Header 时遗漏了有效 Cookie

应检查 Cookie Jar 内的完整 Name、Domain、Path 和 Value。

### Login Redirect Not Working

可能原因：

- 只处理了 HTTP 302
- 未解析 JSF XML
- 相对重定向 URL 解析错误
- 重定向后未正确保留 Cookies

### HTTP 200 But Login Does Not Continue

检查响应体中是否存在：

```xml
<partial-response>
```

以及：

```xml
<redirect url="...">
```

因为 JSF 应用可能通过 HTTP 200 携带客户端重定向指令。

## Security

- 不在代码中硬编码用户名和密码
- 不将账号密码、Session ID 或完整 Cookie 日志上传至公开仓库
- 不在调试日志中直接输出敏感认证参数
- 建议将配置和凭据保存在环境变量中
- 保持 HTTPS 证书验证开启
- 仅对本人账号或明确获得授权的账号执行自动化操作
- 遵守 WA DOT 的服务使用条款

建议 `.gitignore`：

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.env
.env.*
*.log
```

## Disclaimer

This project is an independent Python automation and session-management implementation.

It is not affiliated with, endorsed by, or officially supported by the Western Australia Department of Transport.

The software is intended for educational purposes and authorised personal automation only.

## License

No license has been specified. All rights are reserved unless a license is added to the repository.
