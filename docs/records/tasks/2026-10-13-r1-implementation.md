---
record_id: CCR-TASK-R1-IMPLEMENTATION
record_version: 2
updated_at: 2026-10-13
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: R1 参考实现 project_kernel_r1/（未提交，主会话落盘）
status: in_progress
requirement_ids: [REQ-BOUNDARY-13]
module_ids: [K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# R1 参考实现 S0–S5 落地任务记录

## 目标与范围

用户指示"全部分发执行，不用分布问我"。本任务按 04 章 §2 分发 S0–S5（S6 暂不启动），在 `D:/deepseekhannes/kernel_next/project_kernel_r1/` 落地 R1 参考实现切片代码与切片测试。纪律：各切片独占写目录 + 切片测试；跨切片只经 S0 `contracts/` 冻结契约对齐；**不提交/不推送/不改 v1 `src/project_kernel/`、`.venv`、`docs/`**；`release_approved=false` 不变。

4 个待裁决分叉已按用户裁决落地（JCS 向量 R1 自有 / backup 形态 B / model 版本原因自由文本 / TargetSpec 与 backup_target 词表独立），无需再问。

## 输入与来源

- 冻结规格：`docs/architecture/reproduction/` 01–05 章 + 总指南 `reproduction-blueprint.md`（12 不变式）；
- S0 交接文件 `docs/handoffs/2026-10-13-r1-s0-s7-handoff.md`（权限实况：主会话 shell/write 可写 `D:/`，仅子代理隔离域 `E_FS_DENIED`）；
- 既有 v1 冻结代码 `src/project_kernel/`（只读对照，未改）。

## 技术选择与结果

**落地目录**（仅 `project_kernel_r1/` 内，未碰 v1/docs）：

| 切片 | 目录 | 交付物 |
| --- | --- | --- |
| S0 | `contracts/` | errors（稳定错误码闭集）/ ids（Id/Digest/Revision/JSON 整数范围）/ jcs（JCS 规范化 + 自持 golden 向量 6 条 + tree_digest）/ types（核心对象 + backup_manifest 形态 B + 枚举闭集 + 路径逃逸校验）/ objects（envelope + 闭集 payload）/ refs / v1_bridge |
| S1 | `data/store/` | schema（DDL + 不可变触发器）/ uow（幂等双查 + CAS）/ artifacts（两阶段 publish）/ receipts / queries（QueryStore 精确读 + 事件游标） |
| S2 | `domain/` + `application/`（dispatch_*/branch_*/attempt_*/package_*） | 领域规则 + 编排层，错误统一包装 |
| S3 | `application/`（verify_*/review_*/integration_*/adoption_*/human_decision_* + s3_kit） | 验收/评分/人审/采用，attest 只覆盖自身 acceptance_ids（R1-AC-33）、单槽位占用（R1-AC-18） |
| S4 | `application/migration/` | adapt_command / adaptation_rules / backup_target / form_submit / model_exchange，覆盖 R1-AC-M01~M09 |
| S5 | `context/` | assembler / readview（含 QueryStoreReadView）/ budget / manifest / reproduce / scoring_guard / model_call_events |

**全量测试**：`python -m pytest project_kernel_r1/tests/` → **265 passed, 0 skipped, 0 failed**。
**JCS 向量自持**：`contracts/jcs_vectors.json` 可复算，`verify_vectors()==[]`（0 mismatches）。

### S1+S5 汇合（skip 清零）

原 "pending S1 汇合" 的 `pytest.skip` 标记已删除。新增 `context/querystore_view.py`（`QueryStoreReadView` 把 S1 `QueryStore` 适配成 S5 `ReadView` 协议）+ `tests/context/test_s5_s1_convergence.py`（走 S1 真实 SQLite 账本 + UoW 提交，3 个真实用例：精确读回 / 未来修订拒而不替 R1-AC-04 / 缺失 pinned revision 为显式 gap 不回填当前 head）。

### 本轮关键修复（根因均定位）

1. `ref()` 第 4 位参数误传：fixtures 把 digest 塞进 `project_id` 形参 → 改 keyword `digest_hex=`，清理正则带入的多余括号；
2. `_RecorderMeter.describe` 属性遮蔽 `describe()` 方法 → 改真方法；
3. `InMemoryReadView`：`row.commit_seq > as_of` 原判 `READ_VIEW_GAP`，规格语义是 `FUTURE_REVISION` → 已改；
4. pre-tool 失败形状：03 §4.1 全-basis-null + failed 与"decided 需 command_id"冲突 → `model_call_events.validate_result` 排除全-null 形状，交由 `_enforce_pre_tool_failure_shape`；
5. 非 hex digest 字符 `"r"*64` → 改合法 hex `"ab"*32`；
6. 测试用了规格外枚举 `absent` → 对齐 01 EFFECT_OUTCOME 的 `absent_final`。

## 错误与学习资料

子代理分发多次因隔离域 `E_FS_DENIED`（允许域缺 `D:/`）或并发上限失败/卡住，无落盘；改由主会话 shell/write 直接落盘 S0/S1/S4 与修通 S2/S3/S5。S5 测试文件存在 mojibake（`Â§` 等）与 CRLF，用行号/字节替换规避，未整体重写。

## 验收与限制

- 本次交付 = S0–S5 切片实现 + 切片测试 + S1+S5 汇合；**未运行端到端行为场景**，R1-AC 与 R1-AC-M 全部保持 not_run（按 04 章纪律，"切片全绿" ≠ "验收通过"，翻转需 S7 真实宿主演练）；
- S6（SCM intent/apply-start/observe/finalize + 当前采用结算）与 S7（集成 + 端到端示例 + 故障恢复）尚未启动；
- `release_approved=false` 不变，无 commit/push，未改 v1。

## 交接与修订

- 交接文件已同步更新 §二-b 进度快照、§三分叉落地状态、§四恢复步骤（划掉 S0–S5，指向 S6/S7）：`docs/handoffs/2026-10-13-r1-s0-s7-handoff.md`。
- 下一步：启动 S6（依赖 S3 adoption + 05 backup_target 双形态，均已就绪）→ S7 集成 + 端到端 CSV 示例（04 章 §4）+ R1-AC 矩阵逐项登记实际结果；完成后回填 `docs/records/tasks/` 与 `docs/records/README.md`、`project-summary.md`。

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-13 | 建立 R1 参考实现 S0–S5 落地任务记录：6 切片 + 测试 + S1+S5 汇合，全量 265 passed；登记 6 项根因修复；S6/S7 未启动 |
| 2 | 2026-10-13 | S6/S7 已落地，转指独立任务记录 `tasks/2026-10-13-r1-s6-s7-acceptance.md`（CCR-TASK-R1-S7-ACCEPTANCE）；本记录保持 S0–S5 落地职能，不重复登记 S6/S7 细节 |
