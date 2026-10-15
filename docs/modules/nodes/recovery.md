# K-RECOVERY：备份与受控恢复

本节点定义一致备份、已验证恢复源、业务版本恢复和离线 test-store 替换。普通 RPC 不替换自己的活动项目库；生产灾难恢复未获支持或接受。

| 字段 | 值 |
| --- | --- |
| node_id | `K-RECOVERY` |
| node_kind | `module` |
| document_version | `1.0.0` |
| updated_at | `2026-10-10 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | `implemented_test_only` |
| navigation_parent | `K-DATA` |
| conversation_refs | `[]` |

## 责任与源码入口

| 入口 | 责任 |
| --- | --- |
| [backup_create / verify_backup_file / BackupManifest](../../../src/project_kernel/evidence/backup.py) | SQLite一致备份；integrity/FK、迁移、引用、制品与文件hash验证 |
| [EvidenceService.backup_create / restore_plan / restore_apply](../../../src/project_kernel/application/evidence_service.py) | 保存备份与恢复意图，核验 project.admin 和批准的计划 |
| [authorized_restore_inputs / authorize_restore](../../../src/project_kernel/application/recovery_authorization.py) | 核验当前计划、human决定、action、subject digest、target及来源digest |
| [FileEvidenceProvider.restore / reconcile_restore](../../../src/project_kernel/evidence/provider.py) | 显式配置隔离目标，恢复副本并观察结果 |
| [ControlledStoreRecovery.apply / reconcile](../../../src/project_kernel/evidence/recovery.py) | 所有内核写者关闭后，通过独占维护租约进行配置好的 test-store 替换 |
| [ProjectAccessFence](../../../src/project_kernel/data/store/access_fence.py) | 协作内核写者与离线维护之间的访问协调 |

## 数据与恢复种类

备份使用 SQLite backup API，包含已经提交在 WAL 中的事实。BackupManifest 保存 Store、schema、文件摘要和各项验证结果；项目账本另存 backup_manifest 与 evidence_operation。

`business_revision` 只恢复 requirement/design/rules 为新的 draft revision，保留源 parent_ref，不回退已发布事实。`disaster_recovery` 的 RPC 路径只操作明确配置的 test 隔离副本。`ControlledStoreRecovery` 是独立离线维护入口；它要求配置的 test 项目管理员、可信恢复决定、精确目标和备份摘要。

离线替换先保存意图、原库及恢复前历史，回执和恢复审计置于被替换数据库外。未完成审计目录触发显式检查，不能通过重放替换掩盖未知结果。原键重放返回既有回执；payload不同拒绝。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-EVIDENCE](evidence.md), [K-STORAGE](storage.md), [K-LEDGER](records.md), [K-CONTRACTS](contracts.md) | 验证制品、维护租约、源版本/批准和摘要 |
| related_to | [K-IDENTITY](identity.md), [K-QUERIES](queries.md), `K-RECORDS` | 验证持久身份；查询操作状态；维护记录说明恢复原因与限制 |
| conversation_refs | `[]` | 本轮无对话映射 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC29](../../acceptance/G2-round4/checks.json) | 已提交WAL、一致备份验证、恢复fence与历史保存；只接受显式test范围 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 恢复节点详情、上下文来源与冻结保护；不新增恢复入口 |
| 新增需求 | [REQ-CCR-04/05/06](../../requirements/2026-10-10-continuous-records.md) | 维护任务/项目总结与恢复错误学习资料；文档解释不能替代真实授权 |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC29 WAL、验证、fence及历史 | accepted | [WAL备份与离线恢复证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac29_rpc_wal_backup_and_f0/data-evidence.json) |
| AC29 隔离副本恢复 | accepted | [隔离恢复证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac29_rpc_isolated_restore0/data-evidence.json) |
| AC29 独立评审 | accepted | [数据证据审查](../../reviews/2026-10-09-round4/data-evidence-review.md)、[条件裁决](../../acceptance/G2-round4/checks.json) |
| 本轮文档与学习引用 | `documented_not_newly_accepted` | 未运行测试；未新增生产或活动库RPC恢复接受 |

## 当前限制与维护

ProjectAccessFence 只约束合作的 Kernel 写者；直接 SQLite 客户端不受该租约管理。生产恢复还需明确所有写者、停写、真实授权、回滚和审计制度，见[设计审查](../../reviews/2026-10-10-design-review.md)。`implementation_status` 的 test 限定主要指灾难恢复部署；业务版本新 draft 的逻辑仍按其既有用例工作。

学习资料与任务总结可以说明恢复步骤和错误，但不提供 project.admin、人类批准或 target_ref。对失效计划、更换备份、目标变化与未知效果，必须保留原记录，重新取得当前依据，不将文档修订当作批准重签。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立备份/恢复节点，区分draft、隔离副本和离线替换 | 仅文档；生产恢复保持未接受 |
