# K-LEDGER：不可变版本与命令账本

本节点定义项目事实的版本追加、head 发布、提交顺序、审计和幂等回执。它与持续总结和学习资料的 `K-RECORDS` 是不同节点：前者是 SQLite 业务账本，后者是本轮文档维护工作流。

| 字段 | 值 |
| --- | --- |
| node_id | `K-LEDGER` |
| node_kind | `module` |
| document_version | `1.2.0` |
| updated_at | `2026-10-12 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | `implemented` |
| navigation_parent | `K-DATA` |
| conversation_refs | `[]` |

## 责任与源码入口

| 入口 | 责任 |
| --- | --- |
| [Records.append_revision](../../../src/project_kernel/data/store/records.py) | 在调用方事务中追加 payload、schema、摘要、父引用、提交序号和 principal；返回精确 ObjectRef |
| [Records.publish_head / read](../../../src/project_kernel/data/store/records.py) | head_version CAS、head_history；按精确版本或 as_of/pointer 读取 |
| [UnitOfWork.execute / Handles](../../../src/project_kernel/data/store/uow.py) | `BEGIN IMMEDIATE` 内分配 commit_seq，组织 Records/Outbox/审计并提交命令回执 |
| [Outbox.enqueue / claim / ack / fail](../../../src/project_kernel/data/store/outbox.py) | 持久效果意图、lease token 和状态；不自带后台执行 worker |
| [SourceIngest.ingest / bounded_missing_sequences](../../../src/project_kernel/data/store/source.py) | 来源键、同序号去重/冲突、连续水位与有界 gap |
| [Blockers.open / resolve](../../../src/project_kernel/data/store/blockers.py) | 追加阻断和解决版本，保留精确任务及解决引用 |

## 数据与写入保证

`entity` 标识对象；`revision` 保存不可变版本；`entity_head` 是当前指针；`head_history` 保存发布历史。`commit_log`、`command_receipt`、`audit_event` 和 `outbox` 与一次业务提交共同记录。`source_event/source_cursor` 保存宿主来源与本地连续观察。

Records 不打开新写连接、不自行 commit。head 更新要求 expected_head_version，冲突返回 `STALE_REVISION`。同 principal 与幂等键返回原回执，输入 hash 不同则冲突；调用方需用 `UnitOfWork.did_commit` 区分新提交和重放，避免重复外部效果。

`accepted` 回执是命令接受事实，不代表进程完成、交付成功或 sink 已 flush。未知提交或未知外部效果须保留区别，由读取原回执和效果观察处理。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-STORAGE](storage.md), [K-CONTRACTS](contracts.md) | 使用项目连接、ObjectRef、摘要与回执格式 |
| related_to | [K-EVIDENCE](evidence.md), [K-RECOVERY](recovery.md), [K-QUERIES](queries.md), `K-RECORDS` | 效果先记意图；恢复保留历史；查询读取版本；文档记录引用事实 |
| conversation_refs | `[]` | 本轮无对话映射 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC12、AC22、AC27、AC38](../../acceptance/G2-round4/checks.json) | 精确派发版本、稳定快照、一次 close 和原键补查回执；业务行为由各用例共同实现 |
| 历史变更 | [CR-004提交序号](../../changes/CR-004-commit-seq-under-write-lock.md)、[CR-007重放](../../changes/CR-007-uow-replay.md) | 账本写锁和重放的既有决定记录 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 精确账本节点、上下文引用及冻结保护；本轮没有增加账本表 |
| 新增需求 | [REQ-CCR-04/05](../../requirements/2026-10-10-continuous-records.md) | 任务/项目总结可引用账本事实；当前总结文档不自动写回 SQLite，也不替代原审计 |
| 追加需求 | [REQ-BOUNDARY-07/08/09](../../requirements/2026-10-12-kernel-boundaries.md) | [过程留存与正式纳入](../../architecture/dual-layer-storage.md)分开；失败与未采用方案可留存，人类确认正式采用；新对象与收敛待实现 |
| 追加需求 | [REQ-BOUNDARY-11](../../requirements/2026-10-12-kernel-boundaries.md) | [模型交换](../../architecture/agent-exchange-and-live-forms.md)候选：回答引用已存问题，后续汇总关联问答，不回填不可变旧正文 |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC12 精确派发版本不变 | accepted | [派发证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac12_rpc_packet_freezes_b0/execution-evidence.json) |
| AC27 CAS仅一次 close | accepted | [并发 close与repair](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac27_rpc_concurrent_close0/data-evidence.json) |
| AC38 原 key 补查 receipt | accepted | [重连回执证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac38_public_receipt_survi0/receipt-reconnect-evidence.json) |
| 本轮节点与总结关联 | `documented_not_newly_accepted` | 只建立文档关系；未运行测试；所有历史结论以[条件裁决](../../acceptance/G2-round4/checks.json)为准 |

## 当前限制与维护

业务服务的部分 SQL、字段与事务仍集中在较大文件。按职责拆分时必须保留一次 UnitOfWork 的原子提交，不能因节点分组而拆成独立写事务。[设计审查](../../reviews/2026-10-10-design-review.md)记录这种维护风险及可选知识提升绕过持久意图的缺口，后者不是本节点已经提供的安全效果流程。

修改任务或审批事实应追加新 revision 并明确发布指针；维护文档的版本历史不伪装成原账本 revision。对模型可见的总结须保留来源引用，无法证实的部分写为未知或待核实。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立不可变账本节点，明确与持续记录工作流的区别 | 仅文档；未新增接受 |
| `2026-10-12 Asia/Shanghai` | `1.1.0` | 保留过程事实，区分方案留存和正式纳入；纠正不可变问答引用时序 | 仅静态文档；新对象未实现 |

## R1 从零复现规格

文档版本 1.2.0：[详细规格](../../architecture/reproduction/01-data-and-transactions.md)补充R1 精确引用、同事务回执、CAS、历史查询与索引，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
