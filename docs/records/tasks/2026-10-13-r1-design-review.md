---
record_id: CCR-TASK-R1-DESIGN-REVIEW
record_version: 4
updated_at: 2026-10-13
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: R1 规格设计评价（文档），runtime 未改
status: in_progress
requirement_ids: [REQ-BOUNDARY-13]
module_ids: [K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# R1 复现规格设计评价任务

## 目标与范围

用户指示"先评价设计"，随后确认：不复现，按需求继续完善，可分发执行，完成后留档更新记录。本任务对 [R1 总指南](../../architecture/reproduction-blueprint.md) 及四章规格做设计评审，产出：

1. 评价文档：[R1 设计评价](../../reviews/2026-10-13-r1-design-review.md)；
2. 评价结论更新入口：[项目总结](project-summary.md)；
3. 本任务记录。

评价对象为文档与静态规格，不运行行为测试，不改变 `release_approved=false`。

## 输入与来源

- 总指南 `reproduction-blueprint.md` 与 `reproduction/01`–`04`（v1.0.0，2026-10-12）；
- 现有 v1 源码（UoW、attempt、delivery、artifact、knowledge resolver、schema）静态阅读；
- 用户执行流需求（设计/执行/收尾分工、项目模块两套数据、保留数据用途、公司代码管理）。

## 技术选择与结果

评价结论（静态判断，未行为验证）：

- **保留项**：12 不变式 + 故障矩阵 + 33 验收项构成可机械验证的负向行为体系；六层"完成"分层是最高价值架构决策；制品两阶段发布与 v1 同构可直接平移；包→验证→评分单向 DAG 正确；R1/v1 显式隔离避免假兼容。
- **硬伤**：
  1. `host_work` 表越权——宿主调度状态写进内核 DDL，与 02 章"业务结论只读 attempt/report/operation 与审计"纪律自相矛盾；建议移出内核 DDL，内核只留不可变 audit 事件，宿主自管队列，以精确引用 + operation_key 对齐。
  2. 表单"编辑暂态由宿主管理"是留白——暂态过期、宿主崩溃恢复、多宿主编辑规则未定义，实时交互功能无规格可依。
  3. `model_exchange` 投递/唤醒机制只有一句"宿主实时通道"，不定义则退化为轮询。
  4. 三套评分（方案评价 / knowledge ScoreEngine / skill 四维）只有散文纪律防混，应下沉到 schema（review evaluator 只接受 ModelSpec）。
  5. exact 计量模式对多数 provider 不可用，需写进 provider capability 声明；R1 参考实现默认 estimated。
  6. 33 项验收缺"模块多分支并发写时项目查询锁等待与增长后索引行为"。
- **实施顺序建议**：先处置 host_work 归属与表单暂态规则（改 01/02 章），再对齐计量 capability（03 章），然后按 04 章 S0→S7 分发实施。

### 本轮分发执行（用户指示“全部分发执行，有问题统一问我”，2026-10-13）

已按评价 §3 处置六项前置，修订 R1 规格正文（均为文档/静态，未实施、未行为验收，R1-AC 与 R1-AC-M 全部保持 not_run）：

1. **新建 [05 迁移适配接口](../../architecture/reproduction/05-migration.md)**：`migration.adapt` 命令族（target_ref/scan_ref/adaptation_plan_ref/mode record|live/trust_producer）；两级回退无模型关键词 `method=keyword`/有模型 `method=model` 产出同构 `project_scan`；粒度降级显式 `granularity=directory`；内核不代跑 git，`TargetSpec(effect_kind=scm_remote|local_backup)` 只声明+观察；导入表单（workspace_scope/scan_method/scan_ref/mapping_granularity/quarantine_review/baseline_init/backup_target/confirm_gate）宿主暂态→提交 CAS；新增 R1-AC-M01~M08 全部 not_run。
2. **01/02 章 host_work 边界**：明确 R1 默认形态为宿主自有持久队列、内核不持有该表；共享库时启用可选协调投影，定义可变列白名单（status/holder/lease_until/attempt_count/last_error_json/updated_seq 可变，request_json/subject_ref_json/operation_key/epoch/kind/created_seq 不可变）与对账规则（宿主队列为调度权威，镜像冲突重对齐，不以镜像放行外部重放）。
3. **02 章表单暂态生命周期**：补按键暂态 TTL、宿主崩溃恢复（未 flush 丢失可接受、回最近已提交版）、多宿主同表单编辑（提交侧 CAS 串行化、冲突返回双方引用）、暂态与已提交边界标记。
4. **02 章 model_exchange 唤醒机制**：宿主实时通道订阅内核提交事件为唤醒权威依据，至少一次投递+游标/revision 去重，目标会话不活跃则通知挂起不丢弃，恢复后按游标补读；不把唤醒做成轮询异步留言。
5. **03 章 exact 计量 capability 声明**：R1 参考实现默认 estimated+margin，exact 仅对声明稳定计数接口的 provider 开放；capability 必写 meter_mode/input_limit_source/counter_spec/exact_available 字段。
6. **03 章评分三套 schema 防混**：`implementation_review.evaluator` 只接受 ModelSpec，不可引用 knowledge/skill 记录；knowledge/skill 记录不得被方案比较/路由/自动重试消费；三套量表独立不互代，约束下沉到 schema 类型字段。
7. **04 章补 R1-AC-34/35**：模块多分支并发写时项目查询锁等待阈值与增长后类型索引不退化为全表扫描（分实测）；迁移适配验收指向 05 章 R1-AC-M。总指南目录增第 5 行链接 05 章。

### 待用户裁决的分叉（未自行拍板）

- **备份“本地备份”形态**：内核是否管理一个 `backup_manifest` 不可变对象，还是纯宿主侧文件。这决定 05 章表单 `backup_target=local_backup` 的 TargetSpec 是只记 `declared_ref` 路径标识（内核不读文件），还是需内核登记本地备份 manifest 并做 tree 双向核验。当前 05 章按“内核只声明+观察、不读文件字节”写，待确认。
- **05 章是否并入 02 章**：当前独立为 05 章并挂总指南目录第 5 行；若希望保持四章结构可改为并入 02 章迁移节。

### 用户裁决结果（2026-10-13，统一答复“B，当前”）

- **本地备份取形态 B**：内核登记不可变 `backup_manifest` + tree/digest 双向核验。已落实到 05 章 §4（新增 backup_manifest 字段闭集：target_spec_ref/baseline_ref/entry_tree/tree_digest/verify_state，verify_state=verified|mismatch|unknown，mismatch 保留缺口不自动补写、不宣称已备份）、§6 流程图、§8 新增 R1-AC-M09、§9 衔接；01 章 §3 对象闭集增补 `backup_manifest` 行；04 章 R1-AC-35 措辞纳入 backup_manifest 核验。内核仍不代跑备份写文件，只把宿主上报的 tree/digest 与期望树比对并登记（形态 B 的账本侧职责）。
- **05 章保持独立（当前）**：不并入 02 章，挂总指南目录第 5 行。

两项裁决后，05 章与六项前置修订已冻结为实施契约；后续可再按 04 章 S0→S7 分发实施。

## 错误与学习资料

无执行失败。静态发现：host_work 双份状态风险、表单暂态留白属规格自身矛盾（01 章 DDL 与 02 章纪律冲突），已记录于评价文档。

## 验收与限制

- 本次交付 = 评价文档 + 05 章新建 + 01/02/03/04 章修订 + 总指南目录；未修改 runtime 代码，未运行任何行为场景，R1-AC 与 R1-AC-M 全部保持 not_run。
- 下一步：两项分叉已裁决（本地备份 B、05 章独立）；05 章与修订项冻结为实施契约，可再按 04 章 S0→S7 分发实施。

## 交接与修订

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-13 | 建立评价任务记录，登记 R1 设计评价结论 |
| 2 | 2026-10-13 | 分发执行：新建 05 章、处置 host_work/表单暂态/问答唤醒/计量 capability/评分防混/并发增长验收六项前置；登记两项待用户裁决分叉 |
| 3 | 2026-10-13 | 用户裁决：本地备份取 B（内核登记 backup_manifest + tree/digest 双向核验）、05 章保持独立；同步 01/04 章与 05 章 |
| 4 | 2026-10-13 | 规格冻结后按 04 章 S0–S5 分发实施；落地与测试结果另见 [R1 参考实现 S0–S5 任务](2026-10-13-r1-implementation.md)，本记录保持设计评价职能 |
