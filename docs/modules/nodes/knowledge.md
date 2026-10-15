# K-KNOWLEDGE：可选上下文与知识 library

| 字段 | 值 |
| --- | --- |
| node_id | K-KNOWLEDGE |
| node_kind | module |
| document_version | 1.2.0 |
| updated_at | 2026-10-12 Asia/Shanghai |
| source_version | 1.0.0 |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | 已有 library，未装配到核心 RPC；G2-K 待接受 |
| navigation_parent | K-EXTENSIONS |
| conversation_refs | [] |

## 职责与源码入口

| 入口 | 职责 |
| --- | --- |
| [models.py](../../../src/project_kernel/knowledge/models.py) | ContextRequest/SourceMaterial/ContextManifest、知识版本、使用/结果与提升记录 |
| [resolver.py](../../../src/project_kernel/knowledge/resolver.py) `ContextResolver.resolve` | mandatory 材料不可静默裁剪，optional 超预算留 exclusion，项目范围检查 |
| [service.py](../../../src/project_kernel/knowledge/service.py) `KnowledgeService` | record/revise/read、记录 use/outcome、resolve_context、score 和 promote |
| [scoring.py](../../../src/project_kernel/knowledge/scoring.py) | 原有可选知识反馈分数，不是用户画像能力等级 |
| [token_meter.py](../../../src/project_kernel/knowledge/token_meter.py) | TokenMeterPort 与估算实现，精确度需明确标记 |

输入为项目范围、精确来源版本、材料有效性、预算和反馈来源键。输出为清单、排除原因、知识/反馈回执。持久类型是 `knowledge`、`knowledge_use`、`knowledge_outcome`、`promotion_task` 和 `knowledge_checkpoint`，通过通用 revision/UoW；不是新用户画像表。

## 关系

`depends_on=[K-CONTRACTS, K-STORAGE, K-LEDGER]`；`related_to=[K-CORPUS, K-BOOTSTRAP, K-RECORDS]`。当前 bootstrap 未构造 KnowledgeService，K-RECORDS 也不自动调用它。共享提升依赖显式 shared_sink，其授权与效果次序尚有缺口。

## 需求与接受记录

| 来源 | 范围 | 状态 |
| --- | --- | --- |
| [P08 交接](../../handoffs/P08.md) | AC33/34/35/36 对应的原上下文/反馈/提升设计及 library 实现 | 历史子任务资料；不在冻结25项 G2 独立接受范围中 |
| [G2 限制](../../acceptance/G2-round4/limitations.md) | 可选知识与语料的 G2-K 接受另行处理 | 当前不宣称已通过 G2-K |
| [REQ-CCR-06/07/09/10/11](../../requirements/2026-10-10-continuous-records.md) | 无评分学习文档、skill 与按节点资料选择 | 本轮由 K-RECORDS 文档工作流满足；不改 ScoreEngine、不把原分数转成用户评价 |

## 当前问题与后续记录

[静态设计审查](../../reviews/2026-10-10-design-review.md)指出 promote 未读取并核验 human_decision_ref，先执行 shared_sink.write 再写持久意图，且 `_guard` 缺 store_id 检查。开放前需完整授权及持久意图/效果/观察设计；本轮保留未接线状态，未修改代码或运行探针。

ContextResolver 当前主要输出身份/摘要清单，实际内容与 token 计量仍由消费者提供；文档按节点选择流程不是已接入运行 ContextManifest。未来自动摘要、画像持久化、训练导出均需新需求和接受。

| 日期 | 文档版本 | 变更 | 验证 |
| --- | --- | --- | --- |
| 2026-10-10 | 1.0.0 | 区分旧知识评分、未接线 library 与新描述式学习记录 | 静态阅读；没有新行为接受 |

## 2026-10-12 设计补充

[上下文材料、组装与输入再现](../../architecture/consumer-consistency.md)对应 [REQ-BOUNDARY-01/04](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.1.0：补充消费者、外部效果或数据处理职责；无新增行为接受。

## R1 从零复现规格

文档版本 1.2.0：[详细规格](../../architecture/reproduction/03-context-and-evaluation.md)补充R1 完整上下文请求、模型调用记录、评分与数据消费，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
