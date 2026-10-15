# K-LEGACY：test-only 旧数据迁移

| 字段 | 值 |
| --- | --- |
| node_id | K-LEGACY |
| node_kind | module |
| document_version | 1.0.0 |
| updated_at | 2026-10-10（Asia/Shanghai，日期精度） |
| source_version | 1.0.0 |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | test-only，须显式 legacy_config |
| navigation_parent | K-EXTENSIONS |
| conversation_refs | [] |

## 职责与入口

[LegacyImportEntry.import_legacy](../../../src/project_kernel/application/legacy_service.py)验证目标 project/store、可信 snapshot producer、计划作者、精确 snapshot/plan 引用与输入摘要；只允许 test 模式。payload 使用引用，不接收任意路径或旧库连接。外部 `snapshot_provider.read_snapshot` 提供不可变来源。

[source.py](../../../src/project_kernel/migration/legacy/source.py)定义 `LegacySnapshot`、`LegacyRecord`；[manifest.py](../../../src/project_kernel/migration/legacy/manifest.py)定义来源清单；[mapper.py](../../../src/project_kernel/migration/legacy/mapper.py)、[importer.py](../../../src/project_kernel/migration/legacy/importer.py)、[quarantine.py](../../../src/project_kernel/migration/legacy/quarantine.py)、[reconcile.py](../../../src/project_kernel/migration/legacy/reconcile.py)负责分类、计划、隔离与对账。

输出为导入回执、映射/报告、保留原来源摘要的 revision 与孤儿 quarantine。原源 hash 不变，相同 key 重放不产生重复导入；旧信息缺少验收、审批或费用事实时不补造。数据仍由现有 UnitOfWork 管理，不另开 runtime writer。

## 关系与需求

`depends_on=[K-CONTRACTS, K-STORAGE, K-LEDGER, K-IDENTITY]`；`related_to=[K-BOOTSTRAP, K-QUERIES, K-EVIDENCE]`。

| 来源 | 要求与状态 |
| --- | --- |
| [P07 交接](../../handoffs/P07.md)、[AC32](../../acceptance/G2-round4/checks.json) | 不修改原源、幂等、孤儿隔离、不补 pass/批准/费用；历史指定条件接受 |
| [第四轮报告](../../acceptance/G2-round4-report.md)、[迁移样本](../../../fixtures/legacy/) | 原接受针对合成不可变 snapshot，非生产数据导入声明 |
| [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 节点导航、详细记录与有界上下文；本轮文档已建立，无运行验收 |

## 限制、接受和变更记录

实际 AC32 条件、JUnit 与原始证据路径以[checks.json](../../acceptance/G2-round4/checks.json)为准；本节点不重新裁决整个迁移模块。`legacy_config` 缺失时入口未注册；生产模式仍拒绝。直接把用户学习文档导入业务 ledger 不属于此机制。

| 日期 | 文档版本 | 变更 | 验证 |
| --- | --- | --- | --- |
| 2026-10-10 | 1.0.0 | 建立迁移节点，记录可信来源和 test-only 接受范围 | 静态阅读，未运行导入或测试 |
