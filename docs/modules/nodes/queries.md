# K-QUERIES：读水位、覆盖与追溯

本节点定义项目事实的只读查询。运行时 `project.trace` 图描述业务版本间的引用，本轮模块树描述代码责任和文档关系，两者不自动共享节点 ID 或验收范围。

| 字段 | 值 |
| --- | --- |
| node_id | `K-QUERIES` |
| node_kind | `module` |
| document_version | 1.3.0 |
| updated_at | 2026-10-12 Asia/Shanghai |
| source_version | `1.0.0` |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | `implemented` |
| navigation_parent | `K-DATA` |
| conversation_refs | `[]` |

## 责任与源码入口

| 入口 | 责任 |
| --- | --- |
| [QueryService.project_overview / project_timeline](../../../src/project_kernel/data/queries/service.py) | 按固定as_of读取总览和时间线，保留引用与分页信息 |
| [QueryService.requirements_coverage / project_trace](../../../src/project_kernel/data/queries/service.py) | 包含零链接需求的覆盖分母、明确N/A、多跳精确版本追溯 |
| [QueryService.attempts_compare / approvals_queue / environment_report / archive_status](../../../src/project_kernel/data/queries/service.py) | 各用例只读视图，保留未知、旧版本、partial与gaps |
| [QueryService.command_receipt / operation_status / events_read](../../../src/project_kernel/data/queries/service.py) | 按principal+key补查回执，读取操作和提交事件 |
| [QueryService.rebuild_read_model / list_revisions / latest_revisions](../../../src/project_kernel/data/queries/service.py) | as_of只读重建和版本查询；重建返回 `persisted=false` |
| [ReadEnvelope / encode_page_token / decode_page_token](../../../src/project_kernel/data/queries/watermarks.py) | 查询水位、来源水位、freshness、completeness、gaps与分页上下文 |
| [build_graph / walk / iter_refs](../../../src/project_kernel/data/queries/links.py) | 从精确ObjectRef派生业务引用图，按方向及有界节点数遍历 |

## 数据与读取语义

查询读取 revision、head_history、commit/audit/source 和对应领域记录。短读事务固定第一页水位；下一页 token 绑定 query、project_id、store_id、filters、as_of与position，不因后来提交切换到当前事实。无法恢复的历史必须报告不可用。

QueryEnvelope 将 `source_watermarks/freshness/completeness/gaps/next_page_token` 与数据一同返回；未知用量不转换为零。只读重建核对 heads并计算派生视图，不新增持久checkpoint或推进写入。token 的公开摘要校验不代替授权。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-LEDGER](records.md), [K-STORAGE](storage.md), [K-CONTRACTS](contracts.md) | 读取同项目版本/水位和既有查询格式 |
| related_to | [K-EVIDENCE](evidence.md), [K-RECOVERY](recovery.md), `K-CORE`, `K-RECORDS` | 展示证据/恢复状态；业务消费者；文档总结可引用查询事实 |
| conversation_refs | `[]` | 本轮未建立对话查询映射 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC30、AC31、AC38](../../acceptance/G2-round4/checks.json) | 覆盖分母与多跳图、as_of/unknown/只读重建、原key补查回执 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 静态模块节点和有向关系、有界读取文档上下文、冻结保护；不以AC30替代新模块树接受 |
| 新增需求 | [REQ-CCR-04/05](../../requirements/2026-10-10-continuous-records.md) | 总结可引用查询的项目事实与明确水位；当前没有自动生成或实时刷新总结的worker |
| 追加需求 | [REQ-BOUNDARY-11](../../requirements/2026-10-12-kernel-boundaries.md) | [表单和模型交换](../../architecture/agent-exchange-and-live-forms.md)：已有 events_read/list_revisions 游标增量基础，模块对象 diff 另待设计；实时推送归编排层 |
| 追加需求 | [REQ-BOUNDARY-10](../../requirements/2026-10-12-kernel-boundaries.md) | 耦合度量作为可复现的只读投影（度量进内核、裁决进模型） |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC30 零链接、N/A、多跳、同名异类型 | accepted | [覆盖与业务图证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac30_rpc_coverage_and_typ0/data-evidence.json) |
| AC31 as_of、落后、unknown、重建 | accepted | [水位与只读重建证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac31_rpc_watermarks_unkno0/data-evidence.json)、[独立数据审查](../../reviews/2026-10-09-round4/data-evidence-review.md) |
| AC38 原key补查receipt | accepted | [重连回执证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac38_public_receipt_survi0/receipt-reconnect-evidence.json) |
| 本轮模块文档与总结关联 | `documented_not_newly_accepted` | 未运行测试；旧接受只涵盖[冻结条件](../../acceptance/G2-round4/checks.json)的运行时业务图 |

## 当前限制与维护

QueryService 集中了多类视图，图和投影派生存在扫描/排序成本；目前没有持久投影worker、`projection.rebuild` RPC或生产容量接受。此项是部署评估风险，不是凭代码体量确认的性能故障，见[设计审查](../../reviews/2026-10-10-design-review.md)。

按模块取上下文时先选本节点及直接依赖，再按具体问题取源码、需求和证据；避免将全项目历史、全部对话或整份大制品默认为必要上下文。文档选择由持续记录工作流维护，不改 QueryService 的查询协议。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立只读查询节点，区分业务图和模块文档图 | 仅文档；无新RPC或接受 |

## 2026-10-12 设计补充

[消费者历史水位与上下文再现](../../architecture/consumer-consistency.md)对应 [REQ-BOUNDARY-01](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.1.0：补充消费者、外部效果或数据处理职责；无新增行为接受。

文档版本 1.2.0：区分已装配的事件增量与未实现的模块变化投影，引用本轮 A 路线及交换方案；只读静态核对，无新增行为接受。

## R1 从零复现规格

文档版本 1.3.0：[详细规格](../../architecture/reproduction/01-data-and-transactions.md)补充R1 固定水位、游标、类型索引及可重建投影，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
