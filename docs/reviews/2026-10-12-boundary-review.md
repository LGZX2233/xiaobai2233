---
record_id: BOUNDARY-REVIEW-20261012
record_version: 1
updated_at: 2026-10-12
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: documentation and skill revision only; runtime unchanged
status: static_review
requirement_ids: [REQ-BOUNDARY-01, REQ-BOUNDARY-02, REQ-BOUNDARY-03, REQ-BOUNDARY-04, REQ-BOUNDARY-05]
module_ids: [K-QUERIES, K-KNOWLEDGE, K-DELIVERY, K-CORPUS, K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# 对架构重校准评价的核对

“上下文工厂 + 执行编排”可以作为整体设计定位；它正确区分了事实留存、消费投影和外部效果。但当前核心也会同步调用 executor/checker/provider，不能把“外挂执行”解释为内核完全不参与执行用例。knowledge 仍未接 RPC，不能把目标定位写成完整上下文工厂已经运行。实现和验收状态仍以[内核现状](../architecture/current-state.md)为准。

本文针对用户粘贴的评价核对相关源码和文档，未重跑其声称的 620/19 项测试，未复现运行故障，也不是所有源码已逐文件完成审查的声明。原始冻结签字及证据不变。当前新增说明可阅读，不等于 SCM 接入或宿主接受。

## 最新三项建议是否正确

| 说法 | 判断 | 修正后的含义及依据 |
| --- | --- | --- |
| 两个消费者需要一致性级别声明 | 成立，但“前端可读未提交权威事实”不成立 | [QueryService._read_tx](../../src/project_kernel/data/queries/service.py) 与历史指针读取已提交水位。前端暂态可单独展示；模型固定输入、前端刷新已提交 head，两者不同步符合声明。 |
| 模型同一 revision 序列必然拼出同一上下文 | 条件不足 | 必须固定材料字节、组装器/配置/排序/预算及计量版本；snapshot digest 不能替代完整请求。[ContextResolver](../../src/project_kernel/knowledge/resolver.py) 是部分材料选择机制，不证明完整请求可再现。 |
| SCM 与内核效果需映射 | 成立，属于未来接入要求 | [delivery_request](../../src/project_kernel/application/delivery/service.py) 仍限定 bundle。先区分 local commit、push、merge，再绑定获批目标与精确对象/字节；不能把 Git hash 当作 manifest digest。 |
| Git 成功必需 execution_terminal=true | 过强 | 当前 applied 需 operation_id 与 verified_digest 匹配；terminal/fence 约束主要用于 absent_final。成功 SCM 判据另行定义，不能反推不存在的核心限制。 |
| 事实账本不直接等于训练语料 | 成立 | 需要样本构造、标注、审核和用途控制；拒绝、失败及未知不能自动变成质量标签。 |
| 内核没有训练设计钩子；样本构造必须在 corpus 之外 | 不成立或过强 | [Sample](../../src/project_kernel/corpus/models.py)、[record_sample/build](../../src/project_kernel/corpus/service.py)、[splits](../../src/project_kernel/corpus/splits.py) 已有来源、输入输出、标签、失败类型和按任务切分。缺的是通用 revision→样本构造器；上游可把 candidate Sample 交给可选 corpus。 |
| 真正缺口只有这三页 | 证据不足 | 三页是本轮设计范围，不能排除决定性字段演进、派生索引完整性、知识提升授权、上下文来源保留等独立问题。 |

三份主说明：[消费者一致性](../architecture/consumer-consistency.md)、[SCM 映射](../architecture/scm-effect-mapping.md)、[训练职责](../architecture/training-data-boundary.md)。它们是已有 23 节点的补充，不新增运行模块。

## 早期思路评价的修正

| 原判断 | 核对结论 |
| --- | --- |
| unknown 必须由内核设置 TTL 收敛 | 撤回。宿主负责观察调度和人工升级；证据未知不能随时间自动变成无效果或成功。提醒老化与效果确定性不同。 |
| commit_seq 只有一轴，迟到事实会必然落到错误帧 | 不能这样推断。as_of 表示提交时已知事实，迟到回执追加到新提交合理；若要业务发生时投影需另行定义，不是现有提交序错误的证据。 |
| knowledge/corpus 未接线证明能力开关没设计 | 撤回该推断。corpus 已有显式开关；未接线和未独立接受是真实成熟度限制，不证明整个开关设计缺失。 |
| 人类判断只有盖章，没有实体 | 撤回。[decision_record](../../src/project_kernel/application/delivery/service.py) 保存 decision revision/current head，包含 subject/target、digest、decided_by 和 reason；approval 另有失效/过期等状态。是否需要其他判断生命周期另论。 |
| 内核完全没有 lease，lease_token 只是去重键 | 撤回泛化。[DeliveryService](../../src/project_kernel/application/delivery/service.py) 已有 lease_until、claim/apply-start 和 epoch。exporter 的 operation_id 不证明不存在应用租约；外部 SCM fencing 仍需定义。 |
| 缺完整字节来源图 | 不能由此断言完全无追溯。[QueryService.project_trace](../../src/project_kernel/data/queries/service.py) 和精确 ObjectRef 已派生业务引用图，Sample 也有来源；从任意字节完整解释生成链仍不是已实现保证。 |
| 决定性字段白名单脆弱 | 是演进风险。[decisive_projection](../../src/project_kernel/domain/delivery/eligibility.py) 用显式字段投影；新增影响决策字段需同步依据计算和接受用例。不能据字段列表本身判定当前某个审批已错误失效。 |
| warn 的 unknown 静默证明 fail-safe 缺口 | 是待确认的规则语义选择。warn 是否应在未知时提示需按业务要求决定；不能把 warn 与 deny 同一安全义务默认等同。 |
| 永久幂等键必须 TTL | 未建立缺陷。永久重放避免旧请求重复产生效果；若需要新语义，应使用新键/请求身份，不能在未知效果时静默过期旧账本。保留容量与调用规范可独立评估。 |

## “实现缺陷清单仍然全部成立”不准确

| 条目 | 源码或文档核对与当前状态 |
| --- | --- |
| FLOW_DOMAIN 表建而完全不读 | 表述错误。[QueryService](../../src/project_kernel/data/queries/service.py) 读取 attempt_index/verification_index，[backup](../../src/project_kernel/evidence/backup.py) 使用 approval_index。相关写路径覆盖不足及 revision/索引混合读取值得复核；全表扫描也是容量风险，但本轮未做性能测量。 |
| 最新报告按 report_ref 排序 | 确认静态风险。`_describe_attempt` 索引分支 `ORDER BY report_ref DESC LIMIT 1` 无时间序保证，且未 as_of 过滤；存在索引行时可能取错报告或混入后续报告。正常写路径是否产生这些行、实际受影响场景仍需行为验证。本轮不修运行代码。 |
| task_terminate 报未知错误仍持久降级 CLAIMED | 撤回。修改发生在 UoW callback；[UnitOfWork.execute](../../src/project_kernel/data/store/uow.py) 捕获 KernelError 先 ROLLBACK，retryable 错误再抛出；相关状态不会因该事务异常提交。 |
| blocker 双写证明两个可独立提交的权威 | 不成立。[Blockers](../../src/project_kernel/data/store/blockers.py) 共用 Records 的连接且不自行 commit。派生表权威与重建说明可补，但同事务双写本身不是一致性破坏证据。 |
| 拒绝推进 seq 是隐藏副作用 | 不成立。UoW 明确规定稳定拒绝提交 receipt/audit、推进水位而不推进 entity head；消费者按 receipt.status/event 区分。这是留存事实语义。 |
| RPC 最终 null id 降级未文档化 | 撤回“未文档化”。[原修复记录](../records/tasks/2026-10-10-rpc-resilience.md) 明写固定 ASCII/null id 兜底；极端兜底失去关联仍是限制。修复仍未经行为验证，不能由静态阅读宣布已验证。 |
| requirement.save 自选 object_id 必然违反身份纪律 | 尚无依据支持“必然”。需对照冻结 schema 与服务标识义务；调用方选择对象 ID 本身不等于破坏项目身份隔离。 |
| rules_preview 的 next_commit_seq 读取必然 TOCTOU | 未证明。只读预览与正式发布/应用的授权检查需要分别核对；预览不是执行许可，时间差本身不是被并发写穿的复现。 |
| wheel 独立安装问题 | 确认完整源码树依赖。[pyproject.toml](../../pyproject.toml) 未声明外置 contracts/v1 资源，[digest.py](../../src/project_kernel/contracts/digest.py) 按仓库路径找文件。目录缺失时 glob 可产生空文件表，因此 compute_bundle_digest 不一定直接抛错，而可能生成错误空 bundle 摘要；schema 加载也依赖文件。尚未构建 wheel 实测。 |
| .venv/cache 在仓库等于已提交脏发行物 | 不能等同。工作树文件、Git 跟踪文件和 wheel 内容要分别核对；现有[目录整理记录](../development/repository-layout.md) 已记测试迁移和源码缓存清理，旧“2650+文件”不能作为当前测量。 |

其余性能、句柄过期、身份 pending 窗口和默认能力错误诊断的旧条目需要按具体调用路径继续复核；不从旧模型的结论继承已确认状态。索引、打包和授权的运行修复不是此次文档变更的已完成事项。

## 尚存的真实设计工作

主体方向成立，但“共用权威事实”要落实为可说明的历史查询、内容保留、组装版本和缺口语义。SCM 效果成功要同时证明获批目标与对象/字节映射，而不是只翻译状态字符串。训练与 skill 评分的解释权属于数据处理，不回流为执行权限；数据来源、反馈归因和撤回需要保持独立。

知识提升的 human_decision_ref 核验、先写 shared_sink 后持久意图及 store_id 守卫问题已有[静态审查](2026-10-10-design-review.md)；职责外置不消除这些接入前义务。无自动 worker 是职责选择，宿主是否真正履行对账和 flush 仍需验证。当前最需要的是具体消费者/宿主的完整接入与行为证据，而不是扩大内核状态机来假装时间会自动消除 unknown。
