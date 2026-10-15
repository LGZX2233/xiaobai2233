# K-STORAGE：项目 SQLite 存储

本节点定义项目数据库的打开、迁移、身份验证与连接关闭。连接是 Store 的资源；版本写入和命令事务属于 [K-LEDGER](records.md)。

| 字段 | 值 |
| --- | --- |
| node_id | `K-STORAGE` |
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
| [Store.open_project / close](../../../src/project_kernel/data/store/store.py) | 打开或关闭项目连接；验证持久 project_id/store_id；可写文件库持有共享维护租约 |
| [PROJECT_MIGRATIONS](../../../src/project_kernel/data/store/store.py) | 明确列出项目初始、流程、legacy/knowledge三组迁移 |
| [apply_migrations / verify_migrations](../../../src/project_kernel/data/store/migrations.py) | 迁移执行与已提交迁移 checksum 核对；当前 `SCHEMA_VERSION=1.0.0` |
| [PROJECT_DDL / FLOW_DOMAIN_DDL / LEGACY_KNOWLEDGE_DDL](../../../src/project_kernel/data/store/schema.py) | 项目表与领域记录声明 |
| [ProjectAccessFence](../../../src/project_kernel/data/store/access_fence.py) | 内核写连接与受控离线替换之间的协作维护租约 |

可写连接启用外键、WAL 和 busy timeout。只读连接使用 SQLite `mode=ro` 与 `query_only`，不应用新迁移；无持久身份或不兼容 schema stamp 时拒绝打开。Store 的 `get_revision`、`get_head`、`head_as_of` 和 `get_receipt` 提供精确读入口。

## 数据与资源

`project_meta` 保存项目和 Store 身份；`schema_migration` 保存迁移名、checksum 和版本。`entity/revision`、heads、事件与回执的语义在 [K-LEDGER](records.md)。SQLite 文件、WAL/SHM 与维护租约由连接生命周期管理，不能把复制活动数据库主文件当作一致备份。

`Store.close` 关闭连接并释放维护租约。只读连接不参与写者共享租约；直接 SQLite 客户端也不参加本内核租约，不能据此宣称全宿主写者已停止。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-CONTRACTS](contracts.md) | 精确 ObjectRef 与错误分类 |
| related_to | [K-LEDGER](records.md), [K-IDENTITY](identity.md), [K-RECOVERY](recovery.md), [K-QUERIES](queries.md) | 账本和查询消费连接；身份创建项目库；恢复需要写者关闭 |
| conversation_refs | `[]` | 本轮无对话映射 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC29](../../acceptance/G2-round4/checks.json) | 已提交 WAL 一致备份、恢复维护租约和历史保存；不包含生产恢复 |
| 历史冻结 | [AC43、AC45](../../acceptance/G2-round4/checks.json) | 双项目隔离和显式临时测试 DB/WAL/SHM；不等于任意宿主 sandbox |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 建立可检索的存储节点与有向关系，记录版本和验收，保护内核与冻结输入 |
| 追加需求 | [REQ-BOUNDARY-07/09](../../requirements/2026-10-12-kernel-boundaries.md) | [项目/模块架构需求与存储分工](../../architecture/dual-layer-storage.md)；事实留存与正式纳入分开，A 路线人类确认后纳入；物理分库仍为候选 |

## 验收记录

| 条件 | 历史状态 | 可定位证据 |
| --- | --- | --- |
| AC29 已提交 WAL、验证与恢复 fence | accepted | [WAL备份与受控恢复](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac29_rpc_wal_backup_and_f0/data-evidence.json)、[数据独立审查](../../reviews/2026-10-09-round4/data-evidence-review.md) |
| AC43 双项目隔离 | accepted | [闭环证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac43_ac45_instrumented_pu0/closed-loop-evidence.json) |
| AC45 测试数据隔离 | accepted | [保护输入](../../acceptance/G2-round4/protected-inputs.json)、[独立终审](../../reviews/2026-10-09-round4/ac45-final-peer-review.md) |
| 本轮节点详情 | `documented_not_newly_accepted` | 未运行测试，文档不新增数据库行为；[第四轮条件裁决](../../acceptance/G2-round4/checks.json)保持原范围 |

## 当前限制与维护

Store 仍是项目 SQLite 写入的持有者；部分 application 直接使用它的连接执行 SQL，不能称为已经完全隔离 SQL 的可替换 repository 层。维护租约只覆盖合作内核写者，生产停写与回滚制度见[设计审查](../../reviews/2026-10-10-design-review.md)。

修改 schema 或迁移时，保持已提交迁移代际和 checksum 的含义，明确新版本与消费者。持续记录和用户学习文档不应直接改变冻结 schema；采用新的持久化服务前需另列设计与接受记录。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立连接、迁移、身份验证与维护租约节点 | 仅文档；未新增接受 |
| `2026-10-12 Asia/Shanghai` | `1.1.0` | 项目/模块分工、过程留存及 A 路线纳入条件；不把未验收事实排除于账本 | 仅静态文档；新存储/收敛未实现 |

## R1 从零复现规格

文档版本 1.2.0：[详细规格](../../architecture/reproduction/01-data-and-transactions.md)补充R1 逻辑分区、参考 DDL、制品及并发事务，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
