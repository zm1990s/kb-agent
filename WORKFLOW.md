# 开发阶段协议 · KB-Agent

## /refine（需求澄清）
输入：需求描述
输出：更新 docs/PRD.md（目标用户、功能边界、验收标准）
通过条件：每条验收标准可观察、可量化

## /design（架构设计）
输入：PRD.md
输出：更新 DESIGN.md（API 契约、数据模型、引擎抽象）
通过条件：所有端点有明确入参/出参；所有表字段有类型和约束

## /plan（实现计划）
输入：DESIGN.md + ROADMAP.md
输出：分步实现计划（每步 ≤200 行改动）
通过条件：计划经用户确认

## /build（编写代码）
输入：计划
输出：代码文件 + 测试
通过条件：ruff + pyright + pytest 全绿

## /review（代码审查）
输入：diff
输出：两阶段报告（Spec Compliance → Code Quality）
通过条件：无 Critical 问题；重点核查 workspace 隔离与 LLM 出口唯一性

## /ship（发布）
输入：通过 review 的代码
输出：部署配置 + 上线检查
通过条件：健康检查通过；secret 未硬编码；公网暴露面已收敛

## 特别规则（本项目）
- 所有 LLM 调用改动，必须确认仍只经 `app/engine/`。
- 所有文档查询改动，必须确认仍带 workspace 权限过滤。
- 未来 skill 写操作改动，必须确认仍走 `pending_approval → approve`。
