# SSO 联合登录对接指南

KB-Agent 支持基于授权码流程的联合登录（SSO），允许其他应用复用 KB 的用户认证体系，认证完成后获取用户的 ID、邮箱、角色和用户组。

---

## 前置配置（KB 管理员操作）

1. 进入管理后台 → 系统设置 → 联合登录
2. 开启「联合登录」开关
3. 在「允许的回调 URI」中添加你的应用来源，如 `https://app.example.com`（前缀匹配，填到 origin 级别即可）

---

## 流程概览

```
外部应用                        KB
   |                            |
   |-- 1. 重定向用户到 KB 登录页 -->|
   |                            |-- 用户登录（已登录则跳过）
   |                            |
   |<-- 2. 携带 code 跳回回调地址 --|
   |                            |
   |-- 3. 后端用 code 换用户信息 -->|
   |<------- 返回用户信息 ----------|
```

---

## 第一步：发起登录跳转

将用户浏览器重定向到 KB 登录页，附带以下参数：

```
GET https://<KB_HOST>/login?redirect_uri=<YOUR_CALLBACK_URL>&state=<RANDOM_STATE>
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `redirect_uri` | 是 | 认证完成后跳回的地址，必须以管理员登记的 URI 前缀开头 |
| `state` | 推荐 | 随机字符串，原样带回，用于防 CSRF |

**示例：**
```
https://kb.example.com/login?redirect_uri=https://app.example.com/sso/callback&state=abc123
```

---

## 第二步：接收回调

用户登录成功后，KB 将浏览器重定向回你的 `redirect_uri`，附带：

```
GET https://app.example.com/sso/callback?code=<CODE>&state=<STATE>
```

| 参数 | 说明 |
|---|---|
| `code` | 一次性授权码，60 秒内有效 |
| `state` | 原样返回，需校验与发起时一致 |

> **安全提示：** 收到回调后立即校验 `state`，防止 CSRF 攻击。

---

## 第三步：换取用户信息

由**你的后端服务器**调用（不要在前端发起，避免 code 泄露）：

```
POST https://<KB_HOST>/api/sso/token
Content-Type: application/json

{
  "code": "<CODE>"
}
```

**响应（200）：**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "role": "user",
  "groups": ["销售团队", "华南区"]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string (UUID) | KB 用户唯一 ID |
| `email` | string | 用户邮箱 |
| `role` | string | `admin` 或 `user` |
| `groups` | string[] | 用户所属的用户组名称列表 |

**错误响应：**

| HTTP 状态 | detail | 含义 |
|---|---|---|
| 400 | `invalid_code` | code 不存在或格式错误 |
| 400 | `code_already_used` | code 已被使用（一次性） |
| 400 | `code_expired` | code 已过期（超过 60 秒） |
| 403 | `sso_disabled` | SSO 功能未开启 |
| 403 | `user_inactive` | 用户账号已被禁用 |

---

## 查询 SSO 是否启用

可在登录页显示前提前查询，避免无效跳转：

```
GET https://<KB_HOST>/api/sso/status
```

**响应：**
```json
{ "enabled": true }
```

---

## 完整示例（Node.js）

```js
// 1. 生成 state 并发起跳转
app.get('/login', (req, res) => {
  const state = crypto.randomBytes(16).toString('hex');
  req.session.ssoState = state;
  const redirectUri = 'https://app.example.com/sso/callback';
  res.redirect(
    `https://kb.example.com/login?redirect_uri=${encodeURIComponent(redirectUri)}&state=${state}`
  );
});

// 2. 接收回调，换取用户信息
app.get('/sso/callback', async (req, res) => {
  const { code, state } = req.query;

  // 校验 state
  if (state !== req.session.ssoState) return res.status(400).send('invalid state');

  // 后端换取用户信息
  const resp = await fetch('https://kb.example.com/api/sso/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!resp.ok) return res.status(401).send('sso failed');

  const user = await resp.json();
  // { id, email, role, groups }

  req.session.user = user;
  res.redirect('/dashboard');
});
```

---

## 安全说明

- **code 一次性**：每个 code 只能使用一次，重复使用返回 400
- **code 有效期 60 秒**：超时后返回 400，需重新发起登录
- **换 token 在后端完成**：`/sso/token` 设计为服务端对服务端调用，勿在浏览器前端直接调用
- **redirect_uri 白名单**：使用前缀匹配，KB 管理员需提前登记你的应用来源
- **state 参数**：强烈建议使用，防止 CSRF 攻击
