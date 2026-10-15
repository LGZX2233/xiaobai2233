# K-IDENTITY：项目身份与绑定

本节点负责项目和 Store 的持久身份、创建对账以及宿主绑定。它不分析用户掌握的知识；用户学习画像属于持续记录工作流，不能从身份记录推断用户熟悉程度。

| 字段 | 值 |
| --- | --- |
| node_id | `K-IDENTITY` |
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
| [IdentityRegistry.begin_provision / provision / reconcile](../../../src/project_kernel/data/identity/registry.py) | 保存 provision 意图，创建项目库与 manifest，验证残留或已完成结果 |
| [IdentityRegistry.bind / require_active](../../../src/project_kernel/data/identity/registry.py) | 唯一宿主绑定和活跃项目检查 |
| [IdentityCommandLedger](../../../src/project_kernel/data/identity/command_ledger.py) | 身份域独立 store_id、commit_seq 和幂等回执 |
| [ProjectBindingService.project_bind](../../../src/project_kernel/application/project_service.py) | 项目域先记录绑定意图，调用身份域后结算；保留跨库操作身份 |
| [build_identity_server](../../../src/project_kernel/interfaces/rpc/identity_server.py) | 独立 provision/reconcile RPC 入口；可信调用上下文由宿主注册 |
| [require_scope](../../../src/project_kernel/application/security.py) | 校验项目/Store 与能力；不接受模型自述的角色授权 |

## 数据与入口配置

`shared.sqlite` 保存身份、项目注册、provision 和 binding；项目库另存 `project_meta`。provision 不是两个 SQLite 库之间的原子事务；reconcile 检查项目目录、manifest、schema 与数据库身份后恢复状态。未 active 的项目不能进行业务写入。

项目 RPC 只有配置 `identity_registry` 才注册 bind；项目创建和 reconcile 使用独立身份 server。存储目录拒绝符号链接和 Windows junction，项目 ID 的路径映射避免保留设备名及别名冲突。具体路径验证由 IdentityRegistry 所有。

## 节点关系

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| navigation_parent | [K-DATA](data.md) | 数据分组 |
| depends_on | [K-STORAGE](storage.md), [K-LEDGER](records.md), [K-CONTRACTS](contracts.md) | 创建并核对项目 Store；保存绑定意图；使用既有上下文和回执格式 |
| related_to | [K-LEDGER](records.md), `K-CORE`, `K-RECORDS` | 项目绑定意图在账本；组合根装配身份入口；用户学习记录单独维护 |
| conversation_refs | `[]` | 本轮不关联真实对话 |

## 需求记录

| 来源 | 记录 | 范围与状态 |
| --- | --- | --- |
| 历史冻结 | [AC20、AC43、AC45](../../acceptance/G2-round4/checks.json) | AC20覆盖可信人审身份入口；AC43/45覆盖双项目和测试数据隔离。它们不单独接受全部 provision 路径 |
| 当前运行参考 | [内核现状](../../architecture/current-state.md) | 身份 server、可选 bind 与跨库非原子说明 |
| 新增需求 | [REQ-CCR-01/02/03/10/11](../../requirements/2026-10-10-continuous-records.md) | 身份节点、源码/记录元数据、关系和有界上下文 |
| 新增需求 | [REQ-CCR-07](../../requirements/2026-10-10-continuous-records.md) | 描述式用户学习画像与身份职责分离；当前 IdentityRegistry 未实现画像读写或评分 |

## 验收记录

| 条件 | 历史状态 | 可定位证据与范围 |
| --- | --- | --- |
| AC20 可信 human | accepted | [条件裁决](../../acceptance/G2-round4/checks.json)和[交付审查](../../reviews/2026-10-09-round4/delivery-review.md)；verified synthetic test proof，不是真实宿主认证接受 |
| AC43 双项目隔离 | accepted | [闭环证据](../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac43_ac45_instrumented_pu0/closed-loop-evidence.json) |
| AC45 临时测试数据/产物 | accepted | [独立终审](../../reviews/2026-10-09-round4/ac45-final-peer-review.md) |
| 新增画像关系与节点文档 | `documented_not_newly_accepted` | 仅文档；没有新增画像服务、真实对话映射或新测试 |

## 当前限制与维护

身份库、项目库和文件创建分别产生效果；跨库对账不能描述为一次 ACID 提交。可信 principal、人类动作和真实宿主认证仍需宿主提供，G3 尚未由 G2 独立核心接受覆盖。[设计审查](../../reviews/2026-10-10-design-review.md)说明跨库、宿主和知识授权的区别。

更新用户学习记录时记录明确来源、时间与是否为推断；禁止复用项目 ID、能力列表或一次错误作为知识熟悉程度的证明。身份和学习资料可以存在多对多关联，但本轮关联可为空，不增加冻结身份字段。

## 版本与变更记录

| 日期 | 文档版本 | 记录 | 验收影响 |
| --- | --- | --- | --- |
| `2026-10-10 Asia/Shanghai` | `1.0.0` | 建立身份/绑定节点，标明与用户学习画像的职责区别 | 仅文档；未扩大真实身份接受范围 |
