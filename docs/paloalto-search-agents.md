# Chat 的 Palo Alto 检索 Agent

在消息输入框上方勾选「空间文档」「Palo Alto KB」「LIVEcommunity」，可以组合使用。
默认仅开启空间文档；空间的「自动」模式仍使用全部授权空间的完整索引，不按产品或空间名称预筛。
取消所有来源时使用模型已有知识回答。选择会在当前标签页刷新后保留，打开历史会话时恢复最后一次提问的来源选择。

## 数据与引用

- 两个外部 Agent 共用一次关键词生成和公开搜索配置发现；仅向搜索服务发送问题关键词，不发送空间文档正文。
- 使用 KB 首页发布的访客搜索配置和 Palo Alto 的 Coveo 公开索引。无需自行填写 API Key；访客搜索 token 仅保留在单次请求的内存中，不写入数据库、日志、前端或模型上下文。
- 查询明确限制为 `Salesforce - Knowledge - Public` 或 `LIVEcommunity Public`。禁用默认门户查询 pipeline，使用标准搜索；访客 token 的权限过滤仍然生效。仅接受对应官网 HTTPS 域名的结果链接，不跟随重定向。
- KB 优先读取文章页正文；社区读取公开搜索索引保存的正文。正文不可读时保留实际搜索片段，标记为「官网索引片段」，不虚构全文。
- 每条引用保留原文 URL、来源类型、实际片段、产品与版本（如可用）、索引/更新时间（如可用）及检索时间。KB 标记为官方知识库，社区帖子标记为社区内容。
- 索引可能滞后；检索时间不代表文章更新时间。社区回复不等同于官方认可的解决方案。模型综合回答时需区分这两类材料与版本差异。
- 外部搜索与本地空间检索并行运行。单个 Agent 失败不会丢弃其他来源的证据；全部检索失败会显示检索错误，不伪装成「没有结果」。正常搜索无命中时沿用已有知识回答。
- 空间上传记录查询仍使用数据库；混合检索时数据库记录与外部证据一起参与综合回答。

## 部署与接口

环境变量（见 `.env.example`）：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `PALOALTO_SEARCH_ENABLED` | `true` | 是否提供这两个可选 Agent |
| `PALOALTO_SEARCH_TOP_K` | `5` | 每个站点最多读取的候选文章数，范围 1–10 |

服务需能通过 HTTPS 访问 `knowledgebase.paloaltonetworks.com` 和
`paloaltonetworksintranet.org.coveo.com`。如果官网公开搜索配置或页面结构改变，需更新连接器。

`GET /chat/agents` 返回当前可用能力。`POST /chat` 与 `POST /chat/stream` 均支持：

```json
{
  "message": "如何配置多个 GlobalProtect 网关的证书？",
  "workspace_id": null,
  "retrieval_sources": ["workspace", "paloalto_kb", "paloalto_live"]
}
```

省略 `retrieval_sources` 等同于 `["workspace"]`，不会自动开启外部搜索；`[]` 表示使用已有知识。
未知来源返回请求校验错误，管理员禁用的外部来源返回 403。空间权限仍由服务端检查。
该选项从 API 传递至后台流式任务，并随用户消息保存；来源证据随助手回答保存在历史中。

本项目生产模式的代码编译进镜像，更新后需重建 backend / frontend（`make dev` 不会更新正在运行的生产镜像）。
