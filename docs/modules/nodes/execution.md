# 尝试执行与结果结算

| 字段 | 值 |
| --- | --- |
| node_id | `K-EXECUTION` |
| node_kind | `module` |
| document_version | `1.2.0` |
| updated_at | `2026-10-12 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `16410c9fbf4a8507445b4603e371e701614e4499` |
| implementation_status | 已实现尝试、取消和结算；G2 真实临时 subprocess 条件已历史接受，真实宿主未接受 |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

`updated_at` 使用 Asia/Shanghai 日期精度；`source_revision` 是本文静态阅读的源码提交，文档版本单独递增。

## 职责与范围

本节点在调用 executor 前保存 attempt 意图和 task phase，记录 provider 能力、精确 packet/root 引用、执行句柄、epoch 和真实结果。负责取消请求与可信来源结果结算；候选验收、方案选择和交付批准属于 `K-DELIVERY`。

执行必须引用 current 且未撤回的 packet，并使用该任务、策略和基准 root 下的独立实际目录。重试创建新 attempt，旧失败结果、stdout/stderr artifact 和消耗事实保留。未配置 executor 或 artifact storage 时返回 `CAPABILITY_UNAVAILABLE`，不追加伪 completed。

attempt 状态、取消状态、task phase 和命令回执分别保存。取消请求的 accepted 回执不表示执行已停；没有确认的取消保持 pending，结果未知保持 unknown，不自动重放 executor。

## 节点关系

`depends_on = [K-CONTRACTS, K-STORAGE, K-LEDGER, K-QUERIES, K-IDENTITY, K-EVIDENCE]`。

`related_to = [K-DESIGN, K-DELIVERY, K-ENVIRONMENT, K-RULES, K-BOOTSTRAP, K-RPC, K-RECORDS]`。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| 导航归属 | `K-CORE` | 已确认 packet 的实际尝试阶段 |
| 依赖 | `K-CONTRACTS` | `ExecutionHandle`、provider capabilities、命令 schema、状态和错误 |
| 依赖 | `K-STORAGE`、`K-LEDGER` | 意图先提交，结果再追加；幂等回执、审计和 head 更新 |
| 依赖 | `K-QUERIES` | 扫描历史精确 root 所关联的 attempts，阻止实际目录重叠 |
| 依赖 | `K-IDENTITY` | `attempt.execute`、来源 principal 和 provider 信任列表 |
| 依赖 | `K-EVIDENCE` | stdout/stderr 的真实字节 staging/publish 与 ArtifactRef |
| 关联 | `K-DESIGN`、`K-RULES` | 消费固定 packet；撤回必须先结束活动尝试 |
| 关联 | `K-ENVIRONMENT` | 环境就绪检查在 packet 确认阶段；executor 再校验沙盒能力 |
| 关联 | `K-DELIVERY` | verifier 引用 exact attempt 与候选；选择保留比较理由 |
| 关联 | `K-BOOTSTRAP`、`K-RPC` | 显式 executor 装配和 attempt.start/cancel/settle handler |
| 关联 | `K-RECORDS` | 总结记录失败、修复、未知结果和学习材料，引用已有 execution 事实 |

## 源码与接口

| 入口 | 符号 | 用途 |
| --- | --- | --- |
| [尝试服务](../../../src/project_kernel/application/attempt/service.py) | `AttemptService.attempt_start` | 目录、packet、mode、能力与状态检查，保存 starting 后调用 provider |
| 同上 | `_record_handle`、`_settle`、`_apply_attempt_status` | 保存 handle、制品、source_result 和 attempt 新 revision |
| 同上 | `attempt_cancel` | 先保存 pending，支持 provider cancel 时再记录真实返回 |
| 同上 | `attempt_settle` | 校验可信来源、provider、mode、handle 与 epoch 后结算 |
| [状态规则](../../../src/project_kernel/domain/flow.py) | `task_transition`、`attempt_transition`、`attempt_is_terminal` | 纯状态判断 |
| [执行端口](../../../src/project_kernel/ports/ports.py) | `ExecutorPort` | capabilities/start/cancel/poll/reconcile 接口；需核对当前消费端实际调用 |
| [组合根](../../../src/project_kernel/bootstrap.py) | `KernelServices`、`build_server` | executor、artifact storage 和结果 principal/provider 信任配置 |

支持完整 `ExecutorPort` 时保存 `ExecutionHandle` 并调用 start/poll；仅带 `run(strategy_id, path)` 的旧 test provider 只在 test mode 允许。当前用例没有后台 polling/reconcile worker，宿主仍需安排 provider 生命周期、后续结果导入和连接管理。

## 数据与隔离

| 记录 | 必须保留的事实 |
| --- | --- |
| `execution_packet` 引用 | mode、task、strategy、scope 的固定依据 |
| `execution_root` 引用 | task/strategy/parent_ref 和 `Path.resolve()` 后实际目录 |
| `attempt.v1` | attempt_id、packet/task/root 引用、provider capabilities、epoch、状态与 usage unknown reason |
| `ExecutionHandle` | execution_handle_id、provider_id、attempt_id、operation_id、epoch 和启动时间 |
| `source_result.v1` | provider/attempt/handle/epoch 与原结果；内核拥有的身份字段不从 provider 观察覆盖 |
| stdout/stderr `ArtifactRef` | 实际输出字节、sha256、size 与媒体类型 |

同任务同策略的终态尝试可在原目录创建新 attempt；其他任务或策略的目录不能相同或互为祖先/后代，即便旧 attempt 已完成。running/unknown 的目录继续占用，校验读取 attempt 保存的历史 root revision，改 root current 或换对象 ID 不解除占用。

`directory_only` 只证明工作目录分离，不限制 subprocess 在 OS 层读取或写入其他路径。请求更高沙盒级别时，executor 声明的能力不足必须拒绝。未知 usage 保持 `None` 和原因，不能为总结方便改成零。

## 需求记录

| 记录 | 来源与要求 | 当前落点 |
| --- | --- | --- |
| 冻结 `AC14` | [G2 条件表](../../acceptance/G2-round4/checks.json)：未执行不 completed，正式 freeze 拒模拟 | 缺 executor 拒绝；真实结果与 mode 持久化，生产交付另校验 |
| 冻结 `AC15` | A attempt 不能挂 B task；独立物理 root；隔离级别如实记录 | task/strategy/parent/path 检查与历史占用判断 |
| 冻结 `AC16` | 取消未确认继续 pending/unknown；重试新 attempt，保留失败 | cancel 意图与结果分离，追加 revision 与制品 |
| 冻结 `AC31` | unknown usage 不置零，历史读水位一致 | 执行结果留事实；统计和投影归 `K-QUERIES` |
| 冻结 `AC43` | test 闭环含两个方案、真实失败修复和重验 | G2 临时 subprocess 样本，不是 DSH/生产支持声明 |
| 新增 `REQ-CCR-01`、`REQ-CCR-02` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：节点提供事实、需求、验收和版本定位 | 本文与结构化模块索引 |
| 新增 `REQ-CCR-03` | 明确有向关系，允许空和多对多，本轮不关联对话 | 本文 depends_on/related_to 与 [关系索引](../registry.json) |
| 新增 `REQ-CCR-04`、`REQ-CCR-06` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：每任务总结结果、错误、修复与未解决项，整理术语和学习资料 | 关联 `K-RECORDS` 与 [维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)；不把 summary 写成 source_result 或执行证明 |
| 新增 `REQ-CCR-11` | 保持内核结构清晰与冻结证据 | 本次不加入 executor/provider 抽象或总结运行时代码 |
| 追加 `REQ-BOUNDARY-06/08/10` | 设计模型固定模块需求、范围与验收；隔离执行、多方案包和收尾技术审查 | [执行流映射](../../architecture/execution-flow-mapping.md)、[并行分支](../../architecture/parallel-branches.md)、[耦合度量](../../architecture/coupling-metric-boundary.md)；已有独立 root 多尝试基础，显式分支聚合与方案评分仍待实现 |

## 历史验收记录

下表映射 G2 第四轮对应的已有 accepted 条件。本次未运行测试，节点文档不是新的运行时验收；历史 scope 为 test mode、synthetic human proof、directory_only 的临时 subprocess，`release_approved=false`。

| AC 与条件 | 历史观察 | 原始证据或独立审查 |
| --- | --- | --- |
| `AC14` 未执行不 completed | 无 executor 的公开 `attempt.start` 返回 `CAPABILITY_UNAVAILABLE`，无 attempt revision | [缺 provider 场景][missing] |
| `AC15` 跨项目/跨任务隔离 | foreign packet 为 `SCOPE_MISMATCH`；错误 strategy root 为 `INVALID_INPUT`；不同 task 同策略不能共用目录 | [跨项目与方案][isolation]、[跨任务同策略][cross-task] |
| `AC15` 写方案独立 root | 两真实 subprocess 分别写 s1/s2 output；同目录/祖先/后代重叠拒绝 | [真实目录写入][isolation]、[目录同路径][overlap0]、[目录祖先][overlap1]、[目录后代][overlap2] |
| `AC15` 活动历史占用与如实记录 | root current 改版、换 ID 和重启后仍拒绝活动目录 alias；保存 `supported_sandbox_level=directory_only` | [历史占用样本][live-root]；其余五种样本见 [checks.json](../../acceptance/G2-round4/checks.json)；[独立目录审查][root-review] |
| `AC16` 取消未确认 | cancel 及原 key 重放保持 unknown/pending，provider 调用一次，相同路径重试拒绝 | [未知取消][cancel] |
| `AC16` 新 attempt 与旧失败保留 | 真实 exit 7 后新 key 修复生成不同 attempt；旧失败、stderr 字节和 compare 结果保持 | [失败与修复][retry] |
| `AC43` 真实执行闭环 | s1 失败后修复，s2 独立执行，总计三次真实 subprocess 与三次 verification；失败结果重启后可读 | [闭环证据][closed-loop]、[执行审查][execution-review] |

## 当前限制与待办

可信 source_result 结算要求显式配置 ingestion principal 和 provider 信任关系。provider 返回未知或句柄归属不符不能当成功；终态后的迟到结果只留审计。executor 的 reconcile 端口存在不表示有独立的后台恢复服务。

G3 仍需真实宿主 start/cancel/poll/结果来源、沙盒和重连验收。本次新增任务总结只维护文档与 skill，不新建 executor/provider 抽象或把学习资料塞入执行循环。

维护 `REQ-CCR-04/06` 时先引用 attempt 与 stderr 事实，再解释错误原因和修复适用范围；无法确定根因记录未确认，未知效果不能写成没有效果，未运行的复验不能写成已通过。

## 变更记录

| 日期 | 文档版本 | 源码依据 | 变更与验证 |
| --- | --- | --- | --- |
| 2026-10-10 | `1.0.0` | `0a619766162682606ad57a9aa4c1926d54c1b891` | 建立尝试节点，记录目录隔离、provider、取消、重试、历史 AC 和总结衔接；静态阅读，未运行测试 |
| 2026-10-12 | `1.1.0` | `16410c9fbf4a8507445b4603e371e701614e4499` | 校准执行流、模块范围及显式分支缺口；多尝试未被全局禁止并发，仅静态核对 |

[missing]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac14_rpc_missing_executio0/execution-evidence.json
[isolation]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_cross_project_an0/execution-evidence.json
[cross-task]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_same_strategy_cr0/execution-evidence.json
[overlap0]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_refuses_differen0/execution-evidence.json
[overlap1]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_refuses_differen1/execution-evidence.json
[overlap2]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_refuses_differen2/execution-evidence.json
[live-root]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac15_rpc_live_directory_r0/execution-evidence.json
[cancel]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac16_rpc_unconfirmed_canc0/execution-evidence.json
[retry]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac16_rpc_retry_is_new_att0/execution-evidence.json
[closed-loop]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac43_ac45_instrumented_pu0/closed-loop-evidence.json
[execution-review]: ../../reviews/2026-10-09-round4/execution-review.md
[root-review]: ../../reviews/2026-10-09-round4/root-isolation-peer-review.md

## R1 从零复现规格

文档版本 1.2.0：[详细规格](../../architecture/reproduction/02-orchestration.md)补充R1 分支、多实现包、目录占用、交互与恢复，对应 [REQ-BOUNDARY-13](../../requirements/2026-10-12-kernel-boundaries.md)。R1 参照源码 `16410c9fbf4a8507445b4603e371e701614e4499`，新增字段、接口与流程尚未实现或行为验收；实际本轮交付由[任务记录](../../records/tasks/2026-10-12-kernel-boundaries.md)拥有，不改变本节点的既有运行依赖或历史接受。
