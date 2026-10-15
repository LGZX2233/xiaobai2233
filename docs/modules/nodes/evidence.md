# K-EVIDENCE：制品与归档证据

本节点负责真实制品字节、不可变归档清单及各 sink 的效果观察。它保存已经产生的证据，不把未执行任务或未知结果补成通过。

| 字段 | 值 |
| --- | --- |
| node_id | `K-EVIDENCE` |
| node_kind | `module` |
| document_version | `1.0.0` |
| updated_at | `2026-10-10 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | `implemented` |
| navigation_parent | `K-DATA` |
| conversation_refs | `[]` |

## 责任与源码入口

| 入口 | 责任 |
| --- | --- |
| [ArtifactStorage.stage / register / verify / require_ready](../../../src/project_kernel/evidence/artifact_store.py) | staging 到摘要定位的 ready 文件；按实际字节验证，损坏制品隔离 |
| [ScopedArtifactStorage](../../../src/project_kernel/evidence/artifact_store.py) | 为制品调用增加项目作用域和精确 staged 引用 |
| [ArchiveManifest / BundleExporter.export / repair](../../../src/project_kernel/evidence/archive.py) | 清单摘要、真实文件导出、已存在目标校验和缺失补齐 |
| [SinkReceiptStore](../../../src/project_kernel/evidence/archive.py) | 各 manifest/sink 的文件回执与状态 |
| [EvidenceService.artifact_register / archive_export / archive_repair / reconcile](../../../src/project_kernel/application/evidence_service.py) | 授权、持久意图、效果调用和结算，核验 provider 回执身份及摘要 |
| [FileEvidenceProvider](../../../src/project_kernel/evidence/provider.py) | 显式文件制品、archive、backup/restore provider 配置 |
| [EvidenceEffects](../../../src/project_kernel/internal/provider_ports.py) | 应用层实际消费的证据效果接口 |

## 数据与效果顺序

制品保存为 staging/ready 字节；业务账本保存 artifact、archive_manifest、archive_status 与 evidence_operation 的精确版本。文件回执与项目状态分别记录，不把数据库提交当成文件导出成功。

EvidenceService 在 UnitOfWork 中保存 claimed 操作与 outbox lease 后调用 provider，再追加结算版本。原键重放通过 `did_commit` 避免重复效果。archive 的 provider 回执必须匹配 manifest_id、sink_id、digest、state，并为成功提供 verified；不匹配的结果保持 unknown。

repair 固定原 manifest 和 sink，只补归档目标；不能重新执行任务、生成新候选或重新交付。归档清单本体保持不可变，来源就绪和各 sink 状态可以追加新观察。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-LEDGER](records.md), [K-STORAGE](storage.md), [K-QUERIES](queries.md), [K-CONTRACTS](contracts.md) | 保存操作和精确引用，读取归档状态，验证字节/结构摘要 |
| related_to | [K-RECOVERY](recovery.md), [K-QUERIES](queries.md), `K-CORE`, `K-RECORDS` | 备份校验制品；查询读取 sink 状态；用例消费证据；学习资料引用历史结果 |
| conversation_refs | `[]` | 不把归档内容自动关联到对话 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC22、AC25、AC26、AC27、AC28](../../acceptance/G2-round4/checks.json) | 稳定快照与清单、真实输出、required ready、repair 和分 sink/flush 状态 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 节点记录与关系、按节点检索、保护冻结证据；本轮不改变 provider |
| 新增需求 | [REQ-CCR-04/05/06](../../requirements/2026-10-10-continuous-records.md) | 总结与错误/学习资料引用可定位证据；没有证据时标未知，不授予新的验收状态 |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC26 required未ready/缺失/改内容 | accepted | [未ready](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno0/delivery-evidence.json)、[缺失](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno1/delivery-evidence.json)、[内容变化](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno2/delivery-evidence.json) |
| AC27 repair不再次执行任务 | accepted | [并发close与repair](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac27_rpc_concurrent_close0/data-evidence.json) |
| AC28 sink状态、partial、稳定manifest | accepted | [sink故障与repair](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac28_rpc_sink_failure_and0/data-evidence.json) |
| AC28 显式未flush不提升 | accepted | [false来源状态](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac28_explicit_false_sourc0/data-evidence.json)、[独立复核](../../reviews/2026-10-09-round4/source-flush-peer-review.md) |
| 本轮文档与证据引用 | `documented_not_newly_accepted` | 未运行测试；[冻结条件裁决](../../acceptance/G2-round4/checks.json)与签字不变 |

## 当前限制与维护

`source_flushed` 是本地观察，真实 host final flush 缺少证明时仍为 `not_configured`。默认 provider 缺失不会生成虚假的成功；自动 reconciliation worker 尚未装配。真实宿主来源与生产导出声明需独立接受，见[设计审查](../../reviews/2026-10-10-design-review.md)。

原第三轮/第四轮原始证据、签字、manifest 和既有 ZIP 是历史记录。节点文档可引用这些文件；更改文档后不能重写旧摘要、替换原字节，或将本轮总结当成旧条件已覆盖的证据。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立制品、归档和sink节点，关联错误/总结资料 | 仅文档；原始证据不修改 |
