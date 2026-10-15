---
record_id: CCR-TASK-R1-S7-ACCEPTANCE
record_version: 1
updated_at: 2026-10-13
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: R1 参考实现 project_kernel_r1/tests/acceptance/（主会话落盘）
status: in_progress
requirement_ids: [REQ-BOUNDARY-13]
module_ids: [K-RECORDS]
acceptance_status: not_behaviorally_validated
parent_record: CCR-TASK-R1-IMPLEMENTATION
---

# R1 S6/S7 落地与验收矩阵登记任务记录

## 目标与范围

用户指示"启动 S6 → 执行 S7"。本任务：

1. **S6（SCM 效果与采用结算）**：在 `project_kernel_r1/application/scm/` 落地
   SCM intent 持久化（01 §9）、效果映射（docs/scm-effect-mapping）、结算
   编排（04 R1-AC-17..25），覆盖 5 阶段采用操作 + 未知不重放 + 发布
   冲突不重推 + 效果关联不直接 digest 相等。
2. **S7（验收矩阵登记）**：在 `project_kernel_r1/tests/acceptance/` 落地
   验收矩阵 runner + not_run 登记册（04 §7/§11 纪律），把 44 条
   R1-AC 行（04 §7 的 01..35 + 05 §8 的 M01..M09）逐项登记
   模式（synthetic|host）、状态、实际断言证据路径；8 条 host 行
   （需真实模型/沙盒/SCM/宿主重启）保持 not_run 并列入剩余差距。

纪律：独占写 `application/scm/` + `tests/scm/` + `tests/acceptance/`；
**不碰 v1 `src/project_kernel/`、`.venv`、`docs/architecture/` 冻结规格**；
`release_approved=false` 不变；R1-AC 行不因切片全绿而翻为 passed，
04 §11 要求真实宿主演练才能翻转。

## 输入与来源

- 冻结规格：`docs/architecture/reproduction/` 01–05 章 + 总指南
  `reproduction-blueprint.md`；
- S6 依据：`docs/architecture/scm-effect-mapping.md`（字节证据↔SCM 对象
  关联、回执与观察语义、接入前接受要求）；04 §8 崩溃点恢复动作表；
  01 §9 五阶段采用操作；
- S7 依据：04 §7 行为接受矩阵（R1-AC-01..35）+ 05 §8 迁移子行
  （R1-AC-M01..M09）+ 04 §11 完工报告三档声明纪律；
- 已落地切片：S0 `contracts/`、S1 `data/store/`、S2 `domain/+application/`、
  S3 `application/`、S4 `application/migration/`、S5 `context/`（全部
  265 passed）。

## 技术选择与结果

### S6 交付物

| 文件 | 职责 |
| --- | --- |
| `application/scm/__init__.py` | 包入口，声明 S6 纪律（release_approved=false、无 SCM 客户端、无 git 执行） |
| `application/scm/scm_intent.py` | 持久 SCM intent：`build_scm_intent` / `start_intent` / `mark_in_flight` / `record_external_effect`，pending→started→in_flight→settled 生命周期，`IntentReplayError` 拦重放 |
| `application/scm/scm_effect_mapping.py` | 效果关联：`correlate_effect`（固定 mapping_version、local commit 不能证明 remote ref 交付 R1-AC-21、tree↔manifest 不直接相等 R1-AC-22）+ `guard_no_direct_equality` 防误用 |
| `application/scm/scm_settle.py` | `settle_unknown_by_observation` 只读观察结算；`guard_no_reapply_unknown`（R1-AC-19/25）；发布冲突时外部效果成立不重推（R1-AC-23）；错 epoch/操作回执不能结算（R1-AC-24） |
| `tests/scm/test_s6_scm.py` | R1-AC-17/19/20/21/22/23/24/25 + intent 生命周期，11 项 |

### S7 交付物

| 文件 | 职责 |
| --- | --- |
| `tests/acceptance/r1_ac_matrix.py` | 44 行矩阵（04 §7 + 05 §8）；`load_matrix()` / `open_gaps()` / `render_registry()`；host 行 not_run，synthetic 行 `assertion_covered_not_run` 并指向真实测试节点 |
| `tests/acceptance/test_s7_acceptance.py` | 4 项自检：矩阵完整无虚构行 / host 行 not_run 且入差距清单 / synthetic 行证据测试名真实存在于收集套件（按文件 collect，避免一个模块 import 错误遮蔽兄弟）/ 登记册只落 S7 独占目录不落 docs |
| `tests/acceptance/acceptance_registry.md` | 渲染产物（read-only 运行，仅当显式传入 out_path 才写） |

**全量测试**：`python -m pytest project_kernel_r1/tests/` → **280 passed, 0 skipped**
（S6 +11，S7 +4，原 265 + S1+S5 汇合 3 = 276 → 本轮 280）。
**JCS 向量自持**：`verify_vectors()==[]`（0 mismatches）不变。

### S7 验收矩阵结果（44 行）

- **synthetic 断言已覆盖（36 行）**：R1-AC-01..24 + 27 + 33 + 35 + M01..M09，
  全部指向具体测试节点（`test_xxx` 函数名，非"测试绿了"）。04 §7 要求记录
  mode/provider/输入版本/断言/证据，本登记满足"证据路径真实可查"。
- **host 保持 not_run（8 行）**：R1-AC-25/26/28/29/30/31/32/34——需真实模型
  调用、真实沙盒、真实 SCM、wheel 隔离安装、宿主关闭/flush/重启完整性、
  生产采用拒绝 test 检查、模型崩溃/回执丢失恢复、多分支并发+索引退化的
  双计时实测。04 §11 明确：这些行不继承任何历史 accepted，须真实宿主
  演练后才能翻转。

## 错误与学习资料

1. **`build_scm_intent` 与 S0 `validate_target_spec` 的 mapping_spec 形状**：
   S0 规定 `mapping_spec` 是一个 `validate_artifact_ref`（需 digest/size/
   media_type 三字段），S6 最初测试 fixture 写成空 `{}` → 触发
   `UnknownRequiredFieldError`。修正：fixture 补三字段；`scm_intent` 本身
   另取一个 `mapping_spec` 参数（含 mapping_version/path_normalisation/
   manifest_digest）用于效果关联，二者不同字段，不冲突。
2. **S6 `guard_no_reapply_unknown` 的触发条件**：初版只查
   `external_effect is None`；但 R1-AC-19 语义是"in_flight 且尚未终端
   结算的 unknown 不能重放"，而 `record_external_effect(outcome=unknown)`
   会让 `external_effect` 非 None。修正：改为查"未结算"
   （effect None 或 outcome==unknown 或 not terminal）。
3. **S7 collect-only 子进程 cwd**：从 `project_kernel_r1/` 包根 collect
   时 `tests/context/__init__.py` 导入 `project_kernel_r1.contracts.errors`
   报 `ModuleNotFoundError`（包根不在 sys.path）；且整目录 collect 时
   一个模块的 import 错误会遮蔽兄弟模块（stdout 只剩 45 节点而非 280）。
   修正：子进程 `cwd` 改到 `kernel_next` 仓库根（保证 `project_kernel_r1`
   可导入）+ 按单个 `test_*.py` 文件 collect（一个文件错误不影响其他）。
   这是 04 §7"证据必须真实"的机械保证——若某行证据指向不存在的测试名，
   该自检会直接 fail，而不是静默登记假路径。

## 验收与限制

- 本次交付 = S6 行为层 + S7 验收矩阵登记 + 全量 280 passed；
- **host 行 8 项保持 not_run**（R1-AC-25/26/28/29/30/31/32/34），需真实
  宿主/provider 演练，本会话无真实模型 SDK、无 SCM 客户端、无宿主重启
  能力，不声称已验证；
- 04 §11 三档声明：本实现覆盖**文档可复现**（规格/对象/命令/状态/事务
  无冲突解释）+ **运行可复现**（源码、合成 fixture、可执行测试证据）；
  **生产适用**未达成（无真实宿主/provider 验收）；
- `release_approved=false` 不变，无 commit/push，未改 v1。

## 交接与修订

- 下一步：若要翻转 8 条 host 行，需在具备真实模型 SDK + 真实 SCM 目标 +
  可重启宿主的环境跑 04 §6 端到端 CSV 场景（独立临时项目 + 临时 SCM），
  并把 mode=host 的 R1-AC 行逐条登记实际 provider/输入版本/断言/证据路径；
- `docs/handoffs/2026-10-13-r1-s0-s7-handoff.md` 的 §四 恢复步骤：S0–S7
  全切片落盘，剩 host 行演练 + 完工报告（04 §11）三项声明归档；
- 登记册产物 `project_kernel_r1/tests/acceptance/acceptance_registry.md`
  是 read-only 运行时的输出，可随时 `render_registry()` 重算。

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-13 | 建立 S6/S7 落地与验收矩阵登记任务记录：S6 scm 包 4 文件 + 11 测试；S7 矩阵 44 行 + 4 自检 + 登记册，全量 280 passed；8 host 行 not_run 入剩余差距；3 项根因修复 |
