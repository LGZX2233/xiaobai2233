# 声明式规则与可插拔约束

| 字段 | 值 |
| --- | --- |
| node_id | `K-RULES` |
| node_kind | `module` |
| document_version | `1.0.0` |
| updated_at | `2026-10-10 Asia/Shanghai` |
| source_version | `1.0.0` |
| source_revision | `0a619766162682606ad57a9aa4c1926d54c1b891` |
| implementation_status | 已实现版本化数据规则；新增可插拔约束为文档与 skill 工作流，未作新运行时验收 |
| navigation_parent | `K-CORE` |
| conversation_refs | `[]` |

`updated_at` 使用 Asia/Shanghai 日期精度；`source_revision` 是本文静态阅读的源码提交，文档版本单独递增。

## 职责与范围

本节点保存、预览和发布声明式项目规则，并在派发确认时评价 packet 固定的规则版本。规则不是 Python 插件代码：条件只读取已声明 fact path，允许组合 `all`、`any`、`not` 与有限比较运算；当前 effect 为 `deny`、`require_human`、`warn`。

`deny` 命中或缺少所需事实时阻断；`require_human` 命中或事实未知时令 `passed=false`；`warn` 命中时返回规则理由。不存在 `allow` effect，禁用可选 data rule 不能覆盖内核项目归属、capability、可信身份、证据、沙盒和交付效果检查。

本次新增约束采用可独立维护的规则记录和 skill 方法，复用现有 DSL 描述可表达的条件。未实现任意插件加载器、动态 fact 注册器、自动人审续跑或规则热更新服务。

## 节点关系

`depends_on = [K-CONTRACTS, K-STORAGE, K-LEDGER, K-QUERIES, K-IDENTITY]`。

`related_to = [K-DESIGN, K-EXECUTION, K-DELIVERY, K-ENVIRONMENT, K-BOOTSTRAP, K-RECORDS, K-EXTENSIONS]`。

| 关系 | 目标 | 含义 |
| --- | --- | --- |
| 导航归属 | `K-CORE` | 规则支持执行流，不能改写固有安全检查 |
| 依赖 | `K-CONTRACTS` | `Condition`、命令 schema 与有限 effect/operator 集合 |
| 依赖 | `K-STORAGE`、`K-LEDGER` | draft/current、精确 rules revision、CAS、影响预览和发布审计 |
| 依赖 | `K-QUERIES` | `rules.preview` 按显式 source_as_of 读取 task |
| 依赖 | `K-IDENTITY` | 规则写入、预览、发布要求 `rules.publish` capability |
| 关联 | `K-DESIGN` | 同一服务提供 rules.save/preview/publish；dispatch.confirm 消费规则 |
| 关联 | `K-ENVIRONMENT`、`K-EXECUTION` | 环境和 provider 事实可能参与约束；具体 facts 由调用点提供 |
| 关联 | `K-DELIVERY`、`K-BOOTSTRAP` | 关键规则发布可刷新批准，旧 packet 不变 |
| 关联 | `K-RECORDS`、`K-EXTENSIONS` | 保存新增规则的目的、适用范围、启停、版本和确认记录；新增 runtime 扩展另行验收 |

## 源码与接口

| 入口 | 符号 | 用途 |
| --- | --- | --- |
| [纯规则 evaluator](../../../src/project_kernel/domain/design/rules.py) | `DataRule`、`RuleEvaluation` | rule_id、enabled、when、effect、reason 与评价结果 |
| 同上 | `resolve_fact`、`evaluate_condition`、`evaluate_rules` | 点路径解析、三值条件评价、effect 汇总 |
| [设计服务](../../../src/project_kernel/application/design/service.py) | `_RULE_PATHS`、`_condition`、`_rules` | 当前应用允许的 facts 与 schema 转换 |
| 同上 | `rules_save`、`rules_preview`、`rules_publish` | 版本化保存、读水位影响预览、固定草稿发布 |
| 同上 | `dispatch_confirm` | 使用固定 rules revision 的派发检查 |
| [输入 schema](../../../contracts/v1/command-payloads.schema.json) | rules.save/preview/publish payload | 冻结规则字段与 condition/operator/effect 范围 |

允许的 fact path 为 `task.phase`、`task.mode`、`packet.mode`、`mode`、`scope.required_sandbox_level`、`environment.status`、`provider.supported_sandbox_level`、`provider.can_cancel`。合法路径不保证每个评价点都有该事实；缺少事实保持 unknown。

`rules.preview` 当前事实为 task 和 scope mode；`dispatch.confirm` 当前事实包含 task、packet、scope、environment 和 mode，没有自动装入 provider 能力。依赖 provider facts 的阻断规则可能评价为 unknown，不能把预览的缺事实写成已测得 provider 不满足。

## 数据与发布语义

| 对象 | 当前记录 |
| --- | --- |
| `rules.v1` | 规则集与 data_rules；单集 rule_id 不重复；保存发布 draft |
| `rule_impact_preview.v1` | exact draft_ref/draft_digest、source_as_of、每项 task 的 blocked/require_human/decisions |
| `rules` current head | 发布要求预览引用与草稿 revision/digest 对应，CAS 更新 current |
| 发布审计 | `effective_seq` 与 `existing_packets_unchanged=true` |

旧 execution packet 继续引用旧规则版本，既有 packet 内容不随规则集 current 更新。当前 `unknown_paths` 实际保存 unknown deny 的 rule ID，不应把它当作完整 fact path 清单。`require_human` 当前只产生评价结果并阻断派发，没有同一规则中的人工批准凭据消费流程。

## 需求记录

| 记录 | 来源与要求 | 当前落点 |
| --- | --- | --- |
| 冻结 `AC12` | [G2 条件表](../../acceptance/G2-round4/checks.json)：packet 的 rules 固定 | packet 保存 exact rule_refs，发布不回写 |
| 冻结 `AC13` | 非法 fact path/表达式拒绝；unknown 不通行；固有红线不可关 | 有限 schema、path allowlist、三值评价与独立内核检查 |
| 冻结 `AC21` | 决定性规则发布使批准失效，无关审计不误失效 | RPC 发布后刷新与 `K-DELIVERY` 依据比较 |
| 新增 `REQ-CCR-01`、`REQ-CCR-02` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：明确规则节点、源码及版本/验收关系 | 本文与模块索引 |
| 新增 `REQ-CCR-03` | 明确有向关系，允许空和多对多，本轮不关联对话 | 本文 depends_on/related_to 与 [关系索引](../registry.json) |
| 新增 `REQ-CCR-08` | [持续记录需求](../../requirements/2026-10-10-continuous-records.md)：约束可插拔，增加规则并记录适用范围、原因和变更 | 规则记录与 skill 工作流；可表达条件复用既有 DSL，新增 runtime 注册器未实现 |
| 新增 `REQ-CCR-09`、`REQ-CCR-11` | 用项目 skill 持续维护，保持核心清晰和冻结证据 | [维护 skill](../../../.agents/skills/kernel-maintain-records/SKILL.md)；未增加运行时插件或修改 v1 schema |

新增规则记录应保存规则 ID/版本、更新时间、适用项目或任务、触发条件、事实来源、允许继续/阻断/需要确认的判断、理由、启用状态和证据引用。文档工作流中的“允许继续”只是没有新增阻断理由的描述，不能转换为覆盖内核检查的 `allow` effect。

## 历史验收记录

下表只定位 G2 第四轮已有 `accepted` 条件。[checks.json](../../acceptance/G2-round4/checks.json) 和[独立裁决](../../reviews/2026-10-09-round4/independent-decisions.json)保留签字与 exact 证据绑定；本次记录不构成新验收，`release_approved=false`。

| AC 与条件 | 历史观察 | 原始证据或审查 |
| --- | --- | --- |
| `AC13` 非法 fact path/表达式拒绝 | `environment.__class__`、expression variant、eval operator 返回 `INVALID_INPUT`，未新增 rules draft | [非法路径][illegal-path]、[表达式][illegal-expression]、[operator][illegal-operator] |
| `AC13` unknown 不通行 | `provider.supported_sandbox_level` 缺事实，preview 为 blocked/deny-unknown，confirm 为 `REQUIRED_FACT_UNKNOWN`，未发布 packet | [unknown 与不可关闭检查][unknown-rule] |
| `AC13` 红线不可关 | 关闭可选 data rule 后 machine approval 仍拒绝；跨项目引用仍为 `SCOPE_MISMATCH` | [unknown 与不可关闭检查][unknown-rule]、[执行审查][execution-review] |
| `AC12` 固定规则版本 | 新规则合法发布后已保存 packet 仍指向旧 rules revision | [packet 场景][packet] |
| `AC21` 普通预览审计不误失效 | `rules.preview` 审计与 task 名称变化不改变冻结批准 digest | [无关变更场景][unrelated] |

## 当前限制与待办

现有规则不是通用约束插件系统。需要新 fact path、effect、插件载入、规则复用包或审批凭据时，先确定调用点、可信 facts 来源和版本策略，再按独立需求修改接口；不能直接修改冻结 v1 schema。

`REQ-CCR-08` 的文档规则可以立即随任务维护，必须说明它由 agent 阅读执行还是由 runtime 强制执行。仅有文档或 skill 的规则不能标为机器强制；未实现的插件事实和人工续跑保持待办。

规则同时关联需求、环境、执行和交付，可为空或多对多；关联变化更新模块索引及规则记录。运行时 rules revision 仍由 `K-LEDGER` 保存，不能被可编辑 Markdown 历史覆盖。

## 变更记录

| 日期 | 文档版本 | 源码依据 | 变更与验证 |
| --- | --- | --- | --- |
| 2026-10-10 | `1.0.0` | `0a619766162682606ad57a9aa4c1926d54c1b891` | 建立规则节点；说明 DSL、未知事实、固有检查和新增可插拔规则记录；静态阅读，未运行测试 |

[illegal-path]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac13_rpc_rejects_illegal_0/execution-evidence.json
[illegal-expression]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac13_rpc_rejects_illegal_1/execution-evidence.json
[illegal-operator]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac13_rpc_rejects_illegal_2/execution-evidence.json
[unknown-rule]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac13_rpc_unknown_deny_blo0/execution-evidence.json
[packet]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac12_rpc_packet_freezes_b0/execution-evidence.json
[unrelated]: ../../acceptance/G2-round4/evidence/scenarios-acceptance-final/g2-acceptance-final/test_ac21_unrelated_task_name_0/delivery-evidence.json
[execution-review]: ../../reviews/2026-10-09-round4/execution-review.md
