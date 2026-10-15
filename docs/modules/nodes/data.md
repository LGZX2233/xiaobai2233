# K-DATA：项目事实与数据

本节点是数据模块的导航参考，聚合身份、存储、不可变账本、证据、恢复和查询。各子节点拥有自己的实现与记录；聚合节点不增加写者、后台任务或另一套业务数据库。

| 字段 | 值 |
| --- | --- |
| node_id | `K-DATA` |
| node_kind | `aggregate` |
| document_version | 1.1.0 |
| updated_at | 2026-10-12（Asia/Shanghai，日期精度） |
| source_version | `1.0.0` |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | `implemented_aggregate` |
| navigation_parent | `K-ROOT` |
| conversation_refs | `[]` |

## 责任与源码入口

项目事实沿用现有 SQLite 版本账本，实际字节由证据 provider 保存。需求、任务和审批由业务用例写入；本节点定义它们共用的数据服务，不接管这些业务用例。

| 子节点 | 责任 | 源码入口 |
| --- | --- | --- |
| [K-STORAGE](storage.md) | 项目库连接、身份验证、迁移和写者维护租约 | [Store.open_project](../../../src/project_kernel/data/store/store.py) |
| [K-LEDGER](records.md) | 版本追加、head CAS、审计、幂等回执和事务 | [Records / UnitOfWork](../../../src/project_kernel/data/store/uow.py) |
| [K-IDENTITY](identity.md) | 身份库、项目 provision/reconcile 和跨库绑定 | [IdentityRegistry](../../../src/project_kernel/data/identity/registry.py) |
| [K-EVIDENCE](evidence.md) | 制品字节、归档清单、各 sink 效果 | [EvidenceService](../../../src/project_kernel/application/evidence_service.py) |
| [K-RECOVERY](recovery.md) | 一致备份、业务版本恢复与 test 离线维护 | [ControlledStoreRecovery](../../../src/project_kernel/evidence/recovery.py) |
| [K-QUERIES](queries.md) | as_of、覆盖、来源水位、追溯与只读重建 | [QueryService](../../../src/project_kernel/data/queries/service.py) |

## 节点关系

`navigation_parent` 只决定浏览位置。`contains` 是聚合关系，不表示子节点互相依赖；实际依赖由各子节点的 `depends_on` 记录。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | `K-ROOT` | 独立内核总览下的数据分组 |
| contains | `K-STORAGE`, `K-LEDGER`, `K-IDENTITY`, `K-EVIDENCE`, `K-RECOVERY`, `K-QUERIES` | 六个数据职责节点，可单独读取 |
| depends_on | [K-CONTRACTS](contracts.md) | 共用精确引用、错误、Schema 和摘要规则 |
| related_to | `K-CORE`, `K-RECORDS` | 核心用例使用数据服务；持续记录工作流引用项目事实 |
| conversation_refs | `[]` | 本轮没有关联 agent 对话 |

同一源码文件可以被多个节点引用；例如 `EvidenceService` 同时参与制品、归档和恢复。它们的节点文档按责任分开，代码仍保留原有事务和效果顺序。

## 需求记录

需求映射是多对多关系，不以树的父子层级推断覆盖。

| 来源 | 记录 | 本节点范围与状态 |
| --- | --- | --- |
| 历史冻结 | [G2条件 AC26–31、AC43、AC45](../../acceptance/G2-round4/checks.json) | 数据证据、恢复、查询与隔离；接受范围由具体条件限制 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 文档树、节点详情、有向关系、按节点取上下文、结构与冻结保护；本页提供静态记录 |
| 新增需求 | [REQ-CCR-04/05/06/07](../../requirements/2026-10-10-continuous-records.md) | 任务/项目总结、学习资料、用户学习画像可引用本节点事实；记录工作流不因此成为已接线的数据服务 |

## 验收记录

| 记录 | 状态 | 依据与限制 |
| --- | --- | --- |
| 历史 G2 核心 | `accepted_g2` | [第四轮报告](../../acceptance/G2-round4-report.md)与[条件裁决](../../acceptance/G2-round4/checks.json)；独立核心 test 接受，`release_approved=false` |
| 数据代表场景 | 历史 accepted | [AC27并发 close/repair](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac27_rpc_concurrent_close0/data-evidence.json)、[AC29 WAL备份](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac29_rpc_wal_backup_and_f0/data-evidence.json)、[AC31读水位](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac31_rpc_watermarks_unkno0/data-evidence.json) |
| 隔离终审 AC45 | 历史 accepted | [独立终审](../../reviews/2026-10-09-round4/ac45-final-peer-review.md)；不证明生产用户数据处理 |
| 本轮节点与持续记录 | `documented_not_newly_accepted` | 本轮只建立文档，未运行测试，未新增或重签冻结条件 |

## 当前限制与维护

身份库与项目库分别提交；真实宿主 flush、生产恢复、自动对账 worker 和持久投影 worker 不在当前已装配能力中。具体限制见子节点与[现状参考](../../architecture/current-state.md)，未处理问题见[静态设计审查](../../reviews/2026-10-10-design-review.md)。

修改本分组时，先定位拥有行为的子节点，再更新该节点的源码入口、需求和验收关系。新增总结和画像资料保持在文档工作流中；不能绕过 Store 新建项目事实写者，也不能重建旧 manifest 来掩盖维护文档变化。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立数据聚合、子节点与需求映射；源码基线为顶部 revision | 无新增接受；历史冻结材料不修改 |

## 2026-10-12 设计补充

[数据处理评分与失败总结约定](../../architecture/skill-growth.md#数据处理接口与评分范围)对应 [REQ-BOUNDARY-04/05](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.1.0：补充消费者、外部效果或数据处理职责；无新增行为接受。
