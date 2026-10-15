# CR-001：P02/P05 领域表与归档表 DDL 合入

- 状态：已批准并合入（P00/P13 批准；P01 执行）
- 迁移：`0002_flow_domain_tables`（见 src/project_kernel/data/store/schema.py）
- 问题：P02（task/blocker/execution_packet/requirement_acceptance/design_option）、
  P05（archive_manifest/sink_receipt）、P04（attempt/verification/snapshot/approval/
  delivery/artifact/location）需要类型化索引表承载状态与查询，而 DDL 由 P01 独占。
- 变更字段/语义：新增 16 张索引/归档表，payload 真值仍在 `revision` 账本。
- 受影响消费者：P02、P03、P04、P05、P06。
- 迁移/测试：全量 pytest 100 passed（新增迁移在临时库 apply/verify 通过）。
- 备注：`schema_migration.schema_version` 由 UNIQUE 改为非唯一（按迁移行记录，
  避免同一 schema_version 多迁移冲突），随本 CR 一并修正。
