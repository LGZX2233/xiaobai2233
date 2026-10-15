# K-BOOTSTRAP：显式组合根

| 字段 | 值 |
| --- | --- |
| node_id | K-BOOTSTRAP |
| node_kind | module |
| document_version | 1.0.0 |
| updated_at | 2026-10-10（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现核心装配，无动态插件加载 |
| navigation_parent | K-CORE |
| conversation_refs | [] |

## 职责与源码入口

[bootstrap.py](../../../src/project_kernel/bootstrap.py)的 `KernelServices`、`build_server`、`build_human_server`装配服务、可信上下文、provider 和命令/查询 handler；[identity_server.py](../../../src/project_kernel/interfaces/rpc/identity_server.py)的 `build_identity_server` 是独立身份入口。组合根不拥有新业务账本或宿主线程调度器。

输入为 Store、mode、InvocationContextRegistry、executor、check_provider、environment_provider、delivery_provider/bundle_exporter、artifact_root、evidence 配置及显式可选配置；输出为可调用的 ProtocolServer。`delivery_provider` 与 `bundle_exporter` 二选一。交付自定义 provider 不自动提供 archive/backup/restore。

## 关系

`depends_on=[K-CONTRACTS, K-RPC, K-DESIGN, K-EXECUTION, K-DELIVERY, K-ENVIRONMENT, K-EVIDENCE, K-QUERIES, K-IDENTITY, K-LEGACY, K-CORPUS]` 是当前装配依赖（后两项和身份依配置启用）。`related_to=[K-KNOWLEDGE, K-RECORDS]` 仅提示未接线/文档能力，不表示加载它们。

## 需求与验收记录

| 来源 | 要求及范围 | 状态 |
| --- | --- | --- |
| [P13 交接](../../handoffs/P13.md)、[CR-010](../../changes/CR-010-delivery-provider.md) | 显式 provider 装配与 machine/human 分离 | 原实现记录；交接不是完整当前操作手册 |
| [AC14/20/43](../../acceptance/G2-round4/checks.json) | 缺执行不虚构完成、machine 不批准、合成完整场景 | 历史指定条件接受，非真实宿主兼容性认证 |
| [REQ-CCR-01/02/03/11](../../requirements/2026-10-10-continuous-records.md) | 入口可追溯，新文档不增运行耦合 | 本轮静态文档交付 |

## 限制与变更

核心 handler 可以注册但因缺 provider 返回 `CAPABILITY_UNAVAILABLE`；未注册入口为 `UNSUPPORTED_COMMAND`。`initialize.provider_capabilities` 未聚合真实 provider 声明。knowledge 没有装配，持续记录不是装配服务。宿主负责调度、关闭、可信身份和 final flush。

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 记录真实装配依赖、可选开关和宿主责任 |
