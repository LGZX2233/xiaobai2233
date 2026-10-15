# K-ROOT：独立内核

| 字段 | 值 |
| --- | --- |
| node_id | K-ROOT |
| node_kind | aggregate |
| document_version | 1.5.0 |
| updated_at | 2026-10-15 Asia/Shanghai |
| source_version | 1.0.0 |
| source_revision | `c36453981a2151c7652b54301c0cb5a7a1840856` |
| source_worktree_changes | RPC 修复及维护已提交并推送 main；后续变动为同步文档 |
| implementation_status | 独立核心已实现，发布未批准 |
| navigation_parent | null |
| conversation_refs | [] |

## 职责与入口

独立内核保存项目事实并执行从需求到交付的受控流程。宿主适配和 UI 属于外部项目。它的三个阅读分组是[K-CORE](core.md)、[K-DATA](data.md)和[K-EXTENSIONS](extensions.md)；分组不增加运行包。

源码入口：[bootstrap.py](../../../src/project_kernel/bootstrap.py) 的 `KernelServices`、`build_server`、`build_human_server`；部署元数据：[pyproject.toml](../../../pyproject.toml)。具体输入输出和持久对象进入对应节点，不在此重复完整目录。

## 关系

`depends_on=[]`，根聚合不表达运行调用。`related_to=[K-CORE, K-DATA, K-EXTENSIONS]` 表示主要阅读分组。节点导航与有向关系以[总树](../README.md)和[关系定义](../relationships.md)为准。

## 需求与验收记录

| 来源 | 范围 | 当前记录 |
| --- | --- | --- |
| [原架构与职责](../../architecture/kernel-architecture.md) | 独立执行流与项目数据，外部宿主通过显式接口接入 | 已有实现；实际支持范围见[现状](../../architecture/current-state.md) |
| [REQ-CCR-01/02/03/11](../../requirements/2026-10-10-continuous-records.md) | 文档树、详细节点、关系、干净结构 | 本轮文档交付，不改运行核心 |
| [REQ-SG-01至07](../../requirements/2026-10-10-clean-layout-and-skill-growth.md) | 测试布局、技能成长与阅读入口 | 新增维护交付，实际静态结果见[任务记录](../../records/tasks/2026-10-10-layout-and-skill-growth.md) |
| [REQ-RPC-01至05](../../requirements/2026-10-10-rpc-resilience.md) | RPC 异常处理修复、静态记录与普通主分支同步 | 修复已实施；未行为验证，同步进度由[任务记录](../../records/tasks/2026-10-10-rpc-resilience.md)拥有 |
| [第四轮报告](../../acceptance/G2-round4-report.md) | 原25项/87条件 | 历史 `accepted_g2`，`release_approved=false`；本轮没有新验收 |

## 当前问题与变更

[静态设计审查](../../reviews/2026-10-10-design-review.md)发现的 RPC 解析/编码问题已在当前工作树实施修复，仅静态审查、未行为验证，见[RPC 修复记录](../../records/tasks/2026-10-10-rpc-resilience.md)。可选 knowledge 提升仍待开放前整改，且未接入核心 RPC。真实宿主、工作台和生产恢复不属于当前核心接受范围；本次修复不形成“内核没有问题”的结论，也不扩大历史接受范围。用户已授权修复后更新文档并普通提交/推送 main，实际同步状态由任务记录拥有。

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立根节点和分组，关联现状、原接受与新增要求 |
| 2026-10-10 | 1.1.0 | 关联测试布局和技能成长要求及后续任务 |
| 2026-10-10 | 1.2.0 | 关联 RPC 修复与当前同步授权，保留未验证及可选能力限制 |
| 2026-10-10 | 1.3.0 | 标注已提交源码与主分支交付结果 |

## R1 从零复现规格

文档版本 1.4.0：[详细规格](../../architecture/reproduction-blueprint.md)补充R1 总体职责、参考选择、章节和验收入口，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，规格建立时新增字段、接口与流程尚未实现；后续独立 R1 S0–S7 切片见[任务](../../records/tasks/2026-10-13-r1-s6-s7-acceptance.md)，不等于 v1 新增能力或真实宿主验收；规格建立时的交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。

文档版本 1.5.0：[设计、问题治理与无界面接入计划](../../architecture/kernel-design-and-growth.md)补充完整目标流程、模型输出垃圾治理、模块化低耦合和 headless agent 路线。该文档是设计与维护基线，不能把计划或静态判断当成新运行能力；本轮记录见[内核目录整理任务](../../records/tasks/2026-10-15-kernel-cleanup.md)。
