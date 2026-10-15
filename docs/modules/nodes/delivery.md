# 验收、审批与交付

| 字段 | 值 |
| --- | --- |
| node_id | `K-DELIVERY` |
| node_kind | `module` |
| document_version | 1.3.0 |
| updated_at | 2026-10-12 Asia/Shanghai |
| source_version | `1.0.0` |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | 已实现验收、选择、快照、批准、交付和关闭；本次新增记录，未作新验收 |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

`updated_at` 使用 Asia/Shanghai 日期精度；`source_revision` 是本文静态阅读的源码提交，文档版本单独递增。

## 职责与范围

本节点将候选和验收依据绑定到 verification，保存比较、选择和理由，冻结交付快照，发起批准申请并处理独立可信人类决定。交付先保存 claim 和 apply-start，再调用显式 provider；效果观察、回执恢复和对账只读取已有外部效果，不重放未知写入。task.close 根据已应用交付建立不可变 archive manifest 和待归档状态。

执行由 `K-EXECUTION` 提供。实际制品、文件导出和归档 sink 在 `K-EVIDENCE`；本节点负责授权、版本、状态、CAS、epoch 和效果结算。`DeliveryService` 目前仍直接使用项目 Store 及 SQL，不是完全隔离的数据访问层。

任务 phase、verification result/validity、approval status、delivery state 与 archive overall 各有独立含义。passed、accepted、approved、applied 和 archived 不能互相替代，也不能把一条模型说明写成这些事实。

## 节点关系

`depends_on = [K-CONTRACTS, K-STORAGE, K-LEDGER, K-QUERIES, K-IDENTITY, K-EVIDENCE]`。

`related_to = [K-DESIGN, K-EXECUTION, K-RULES, K-ENVIRONMENT, K-BOOTSTRAP, K-RPC, K-RECOVERY, K-RECORDS]`。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| 导航归属 | `K-CORE` | 执行后的验收到交付关闭流程 |
| 依赖 | `K-CONTRACTS` | acceptance/check DTO、snapshot schema、digest、状态和错误 |
| 依赖 | `K-STORAGE`、`K-LEDGER` | 精确 revision、head/CAS、事务、回执、epoch 与审计 |
| 依赖 | `K-QUERIES` | 读取已保存验收依据和来源水位，查询本身不改变批准 |
| 依赖 | `K-IDENTITY` | capability、独立 human entry、精确 digest 与 human interaction proof |
| 依赖 | `K-EVIDENCE` | 必需制品 ready/digest 检查、delivery provider、archive manifest 和效果观察 |
| 关联 | `K-DESIGN`、`K-RULES` | 固定需求、方案、验收、规则依据；关键发布使批准 superseded |
| 关联 | `K-EXECUTION`、`K-ENVIRONMENT` | exact attempt、mode、packet、环境和 candidate 构成交付快照 |
| 关联 | `K-BOOTSTRAP`、`K-RPC` | checker/provider、人审入口与发布后批准刷新装配 |
| 关联 | `K-RECOVERY` | 未知效果需对账；备份/恢复权限与交付批准不互通 |
| 关联 | `K-RECORDS` | 总结只引用验收/批准/交付事实，不能产生接受或发布权限 |

## 源码与接口

| 入口 | 符号 | 用途 |
| --- | --- | --- |
| [交付服务](../../../src/project_kernel/application/delivery/service.py) | `verification_run`、`record_review`、`check_validity` | 验收操作意图、报告、human_review 和依据有效性 |
| 同上 | `select_attempt`、`delivery_request`、`_freeze_snapshot` | 明确选择、构造固定快照和 pending 申请 |
| 同上 | `decide_approval`、`approval_revoke`、`refresh_approvals` | 当前 digest 的人审、撤回和关键输入变更评估 |
| 同上 | `claim_delivery`、`apply_start_delivery`、`apply_delivery`、`delivery_reconcile` | claim、apply-start、provider 调用及只读对账结算 |
| 同上 | `task_close`、`task_terminate`、`record_sink_result` | 关闭/终止、归档 manifest 与 sink 状态 |
| [纯状态规则](../../../src/project_kernel/domain/flow.py) | `evaluate_verification`、`acceptance_basis`、任务与审批状态函数 | 验收计算与状态检查，无 I/O |
| [依据比较](../../../src/project_kernel/domain/delivery/eligibility.py) | `decisive_projection`、`iter_refs` | 只比较影响交付决定的输入 |
| [效果分类](../../../src/project_kernel/domain/delivery/effect.py) | `classify_effect`、`delivery_state_for_effect` | matching digest/终态/fence 与 unknown 的判断 |
| [当前交付端口](../../../src/project_kernel/internal/delivery_provider_ports.py) | `DeliveryProvider.target_matches/apply/observe` | 冻结目标匹配、一次写入和独立只读观察 |
| [文件实现](../../../src/project_kernel/evidence/delivery_provider.py) | `BundleDeliveryProvider` | 文件输出 provider；不是应用层默认目标 |

`KernelServices`、`build_server` 和 `build_human_server` 接受 `delivery_provider=`。文件部署可传 `bundle_exporter=` 由组合根包装，二者同时配置拒绝；缺 provider 返回 `CAPABILITY_UNAVAILABLE`，不创建默认目录。

## 数据与关键语义

| 对象 | 保存依据与语义 |
| --- | --- |
| `verification_operation.v1` | checker 前保存 running、candidate/acceptance/attempt 和 basis digest，异常保留 unknown |
| `verification.v1` | exact candidate/attempt/acceptance、check 结果、evidence_mode、passed、validity 与 incomplete 原因 |
| `selection.v1` | selected attempt、比较对象、选择理由，只有当前通过证据可进入 delivery_ready |
| `scope.v1`、`input_manifest.v1`、`context_manifest.v1` | 从 packet 构成交付申请中的固定上下文引用 |
| `delivery_snapshot.v1` | 固定 body、JCS digest、reference_digests 和 eligibility_basis；不包含后来 approval/operation 状态 |
| `approval.v1`、`decision.v1` | pending 与可信 human 决定、snapshot digest、失效/过期/撤回、operation 绑定 |
| `delivery.v1` | `claimed`、`applying`、`applied`、`failed`、`unknown`、claim lease、epoch 与 provider 观察 |
| `archive_manifest.v1`、`archive_status.v1` | 关闭时固定 snapshot/artifact/operation/sink 清单，单独保存 sink 与来源就绪状态 |

零必需项、skipped/unknown、旧候选、旧验收及未可信提交的 human_review 不能 passed。即使 checker 声称生产通过，持久化 test attempt/packet 仍不能正式 freeze。必需制品未 ready、缺失或内容改变时拒绝快照。

关键输入发布后可追加 superseded；名称、普通审计等无关字段不误失效。刷新由 RPC 发布 handler 在提交后触发，直接用例调用不隐含该 hook；决定、claim 和 apply-start 仍核对当前依据。重放原 receipt 保留原值，不恢复当前批准。

provider 返回不单独证明效果。目标存在且固定 digest 验证通过才为 applied；无目标且执行未证实终态/无 fence 时保留 unknown；旧 epoch 的结算只能审计。apply-start 后撤回返回取消待定，不能宣称无外部效果。

## 需求记录

既有要求的正式文字和分解保留在 [G2 第四轮条件表](../../acceptance/G2-round4/checks.json)。以下模块映射不更改冻结 schema、签字或 raw evidence。

| 记录 | 要求 | 当前落点 |
| --- | --- | --- |
| 冻结 `AC14`、`AC18` | 未检查不 pass；零必需项、skipped/unknown、旧候选/验收和模拟模式不能正式通过 | verification、validity 和 freeze 的独立检查 |
| 冻结 `AC19`、`AC20` | 明确选择到 delivery_ready，明确申请到 pending；机器/伪角色不能批准 | selection/request 与独立 human entry |
| 冻结 `AC21`、`AC22` | 关键变更失效，无关变化不失效；快照无循环 hash | eligibility_basis 与 immutable body |
| 冻结 `AC23`、`AC24` | claim 各崩溃点可对账，不盲重放；旧 epoch 和无 fence 不错误结算 | claim/apply-start/observe/reconcile |
| 冻结 `AC25`、`AC26` | bundle 真实完整、异 digest 不覆盖、同 digest 幂等；制品缺损不能 freeze | provider 和 artifact storage 的真实字节验证 |
| 冻结 `AC27`、`AC28` | CAS 只关闭一次，repair 只补 sink；数据库/文件/来源状态分开，manifest 不变 | close 建清单，`K-EVIDENCE` 导出/修复，archive_status 分开保存 |
| 新增 `REQ-CCR-01`、`REQ-CCR-02`、`REQ-CCR-03` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：明确节点、详细字段和有向关联，允许空和多对多 | 本文与 [关系索引](../registry.json)，本轮 conversation_refs 为空 |
| 新增 `REQ-CCR-04`、`REQ-CCR-05` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：任务/项目总结保留结论与未解决项 | `K-RECORDS` 文档与 [维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md) |
| 新增 `REQ-CCR-11` | 保持内核清晰与冻结证据保护 | 本次只增加文档，不向 DeliveryService 加学习/profile/文档同步逻辑 |
| 追加 `REQ-BOUNDARY-06/09` | 收尾已选 A：模型评分审阅并提出纳入方案，人类确认固定包与依据 | [执行流映射](../../architecture/execution-flow-mapping.md)、[模型收尾身份](../../architecture/model-review-identity.md)；设计已选，新增入库流程未实现 |
| 追加 `REQ-BOUNDARY-07/08` | 正式纳入项目的收敛条件；过程留存与未采用包不自动进入采用视图 | [双层存储](../../architecture/dual-layer-storage.md)、[并行分支](../../architecture/parallel-branches.md)；方案包与模块收敛未实现 |

## 历史验收记录

下表逐项定位已历史接受的对应条件，详细观察、exact JUnit case 和独立签字以 [checks.json](../../acceptance/G2-round4/checks.json) 为准。本次没有运行测试；G2 的 test 接受不能推导新文档功能或整个交付模块已全面接受，`release_approved=false`。

| AC 与具体条件 | 历史结论 | 原始证据 |
| --- | --- | --- |
| `AC14` 未检查不 pass、正式 freeze 拒 simulation | 无 checker 时 incomplete；test check 或 test attempt/packet 不能 production freeze | [缺 provider][missing]、[production verification][production-check]、[持久 mode][production-mode] |
| `AC18` 零必需/skipped/unknown/旧候选/旧验收五条件 | 五个公开反例均 passed=false，不能 delivery_ready | [零必需][verification0]、[skipped][verification1]、[unknown][verification2]、[旧候选][verification3]、[旧验收][verification4] |
| `AC19` 通过后明确选择；明确申请 pending | 选择后 queue 为空；request 后 pending、无 operation，未批准 apply 拒绝 | [申请场景][request] |
| `AC20` machine/伪角色拒绝；独立 human 绑定 current digest | 错 digest 拒绝；synthetic verified human 记录 exact SHA256 批准 | [人审场景][human] |
| `AC21` 关键发布 supersede、重放/查询不写、无关变化不失效 | pending/approved 的关键变更追加 superseded；原回执不能恢复，名称/普通审计不改 digest | [pending][supersede0]、[approved][supersede1]、[无关变更][unrelated] |
| `AC22` 重算 digest 一致，新增批准/操作/归档不改变 body | JCS digest 与人审依据一致；交付和关闭后 immutable body 相同 | [快照 digest][snapshot] |
| `AC23` claim 前、claim 后、start 后、效果后回执前四崩溃点 | 分别保留无 claim、claimed、unknown、applied 的事实；补查/重放/reconcile 不重复导出 | [claim 前][crash0]、[claim 后][crash1]、[start 后][crash2]、[效果后][crash3] |
| `AC24` 旧 epoch、不带 fence 的未知效果、start 后撤回 | 旧结算仅审计；无目标不自动接管；撤回 `CANCEL_PENDING`，保持 apply_started | [旧 epoch][epoch]、[未知与撤回][revoke] |
| `AC25` 真实 bundle 完整、异 digest 不覆盖、同 digest 幂等 | manifest 与实际字节匹配；已有异内容保留；同 key 只有一次 exporter 调用 | [真实输出与幂等][bundle0]、[不覆盖][bundle1] |
| `AC26` staged-only、缺失、改内容不能 freeze | 三种情况无 snapshot/approval；改内容隔离保存坏字节 | [未 ready][artifact0]、[缺失][artifact1]、[改内容][artifact2] |
| `AC27` CAS 只一次 close，repair 不执行任务 | 双 Store race 一提交一拒绝、单清单；repair 恢复制品不改 manifest，不增 executor 调用 | [close/repair][close] |
| `AC28` 分状态、partial 修复、manifest 不变、显式 false 不提升 | 文件与来源缺口各自可见；来源补齐后显式 repair 才重新评估，false 仍 partial | [sink 与 gap][archive]、[false close][flush0]、[false callback][flush1] |

独立复核包括 [delivery-review.md](../../reviews/2026-10-09-round4/delivery-review.md)、[approval-peer-review.md](../../reviews/2026-10-09-round4/approval-peer-review.md) 与 [source-flush-peer-review.md](../../reviews/2026-10-09-round4/source-flush-peer-review.md)。这些签字属于已有 G2，不能移作本次新增需求的接受记录。

## 当前限制与待办

G2 人审凭据是 synthetic verified test proof；真实宿主用户动作、provider 生命周期、Session/Jobs、取消和 final flush 属 G3。交付未知效果没有后台自动对账 worker，需要显式查询及 `delivery.reconcile`。

文件 provider 隔离了交付路径处理，但 archive/backup/restore 需要独立 evidence provider；配置一个 delivery provider 不自动获得恢复能力。文件 bundle 不是 Git commit/push 或安装包发布 provider。

close 的 `source_flushed` 是本地采集就绪且单独保存请求事实，host `session_flush` 缺证仍 not_configured；task closed 不等于所有归档 sink 完成。维修归档只补 sink，不再次执行 task 或 delivery。

新增任务总结与项目总结在 `K-RECORDS` 维护；未验收的新能力保持“待接受”，文档不修改本节点历史批准。具体静态审查未处理问题保留在 [设计审查](../../reviews/2026-10-10-design-review.md)。

## 变更记录

| 日期 | 文档版本 | 源码依据 | 变更与验证 |
| --- | --- | --- | --- |
| 2026-10-10 | `1.0.0` | `0a619766162682606ad57a9aa4c1926d54c1b891` | 建立验收/审批/交付节点，逐项关联历史 AC、关系和新增记录要求；静态阅读，未运行测试 |

[missing]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac14_rpc_missing_executio0/execution-evidence.json
[production-check]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac14_rpc_production_verif0/execution-evidence.json
[production-mode]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac14_rpc_production_canno0/execution-evidence.json
[verification0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_0/delivery-evidence.json
[verification1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_1/delivery-evidence.json
[verification2]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_2/delivery-evidence.json
[verification3]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_3/delivery-evidence.json
[verification4]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac18_public_verification_4/delivery-evidence.json
[request]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac19_public_request_is_ex0/delivery-evidence.json
[human]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac20_public_human_proof_a0/delivery-evidence.json
[supersede0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_public_requirement_c0/delivery-evidence.json
[supersede1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_public_requirement_c1/delivery-evidence.json
[unrelated]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_unrelated_task_name_0/delivery-evidence.json
[snapshot]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac22_public_snapshot_dige0/delivery-evidence.json
[crash0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac23_public_crash_points_0/delivery-evidence.json
[crash1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac23_public_crash_points_1/delivery-evidence.json
[crash2]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac23_public_crash_points_2/delivery-evidence.json
[crash3]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac23_public_crash_points_3/delivery-evidence.json
[epoch]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac24_public_old_epoch_set0/delivery-evidence.json
[revoke]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac24_public_started_witho0/delivery-evidence.json
[bundle0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac25_public_real_bundle_c0/delivery-evidence.json
[bundle1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac25_public_real_bundle_c1/delivery-evidence.json
[artifact0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno0/delivery-evidence.json
[artifact1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno1/delivery-evidence.json
[artifact2]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac26_public_request_canno2/delivery-evidence.json
[close]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac27_rpc_concurrent_close0/data-evidence.json
[archive]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac28_rpc_sink_failure_and0/data-evidence.json
[flush0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac28_explicit_false_sourc0/data-evidence.json
[flush1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac28_explicit_false_sourc1/data-evidence.json

## 2026-10-12 设计补充

[当前 bundle 与未来 SCM 效果映射](../../architecture/scm-effect-mapping.md)对应 [REQ-BOUNDARY-02](../../requirements/2026-10-12-kernel-boundaries.md)。静态复核与限制见[本轮复核](../../reviews/2026-10-12-boundary-review.md)，实际交付和核对见[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)。本次只改文档与 skill；评分/总结保留在数据处理，不增加执行依赖或运行接口。

文档版本 1.1.0：补充消费者、外部效果或数据处理职责；无新增行为接受。

文档版本 1.2.0：路线 A 已选；方案评分与 skill 评估分开，人类确认正式纳入，已有审批不等于新模块入库流程已经实现。仅静态文档校准，无新增行为接受。

## R1 从零复现规格

文档版本 1.3.0：[详细规格](../../architecture/reproduction/02-orchestration.md)补充组合候选、集成验收、路线 A 与外部效果后发布采用，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
