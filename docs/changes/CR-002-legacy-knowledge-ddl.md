# CR-002：P07/P08 专用表 DDL 合入（0003 + identity 0002）

- 状态：已批准并合入（P00/P13 批准；P01 执行）
- 迁移：`0003_legacy_knowledge_tables`（project.sqlite）、`0002_shared_knowledge_domain`（shared.sqlite）
- 来源：P07（imported_fact/legacy_source_snapshot/legacy_import_batch）、P08（use_event/outcome/
  promotion_task、shared_knowledge）
- 受影响消费者：P07（幂等/对账查询）、P08（DB 级唯一约束与共享复制）、P06（对账/知识查询）。
- 迁移/测试：p01_store + p07_migration + p08_knowledge 全绿。
- 备注：P08 的跨库共享复制与 SharedKnowledgeRef 持久化（CR-2 原案）为后置（需 P11 宿主/共享
  store 语义），本迁移仅落 shared_knowledge 表结构；复制逻辑待 P13/P11 后置阶段。
