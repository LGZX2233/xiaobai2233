# K-CORE：核心用例与调用接口

| 字段 | 值 |
| --- | --- |
| node_id | K-CORE |
| node_kind | aggregate |
| document_version | 1.0.0 |
| updated_at | 2026-10-10（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现核心阅读分组 |
| navigation_parent | K-ROOT |
| conversation_refs | [] |

## 职责与源码入口

本分组包括组合根、冻结协议、RPC、Node bridge、需求/规则、环境、执行、验收/审批/交付。源码从 [bootstrap.py](../../../src/project_kernel/bootstrap.py)进入；[domain/flow.py](../../../src/project_kernel/domain/flow.py)说明 task/attempt 状态转换，[application/security.py](../../../src/project_kernel/application/security.py)的 `require_scope` 是应用层授权检查。

主要输入是可信上下文、selector、精确 ObjectRef、expected_heads 与符合 Schema 的 payload；输出是命令回执、查询结果及明确失败。具体用例可以同步调用外部 provider；持久 accepted 不等于效果完成。

## 关系

`depends_on=[]`：聚合节点不伪造单一运行调用。`related_to=[K-BOOTSTRAP, K-CONTRACTS, K-RPC, K-BRIDGE, K-DESIGN, K-RULES, K-ENVIRONMENT, K-EXECUTION, K-DELIVERY, K-DATA]`；各成员的运行依赖在自己的节点声明。

## 需求、验收与变更

| 来源 | 范围与状态 |
| --- | --- |
| [原架构](../../architecture/kernel-architecture.md)、[第四轮条件](../../acceptance/G2-round4/checks.json) | 各具体 AC 在子节点映射；本分组不是额外获接受的能力 |
| [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 建立入口、关系与有界资料选取；本轮静态文档交付 |
| [设计审查](../../reviews/2026-10-10-design-review.md) | RPC 未处理问题保留；没有独立宿主调度/生命周期接受 |

| 日期 | 文档版本 | 变更 |
| --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立用例/调用导航分组，保留各节点数据与授权归属 |
