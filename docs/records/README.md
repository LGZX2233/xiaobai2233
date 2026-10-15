---
record_id: CCR-INDEX
record_version: 9
updated_at: 2026-10-15
timezone: Asia/Shanghai
source_revision: 16410c9fbf4a8507445b4603e371e701614e4499
source_worktree: consumer, SCM, training and skill documentation; runtime unchanged
status: active
requirement_ids: [REQ-CCR-04, REQ-CCR-05, REQ-CCR-06, REQ-CCR-07, REQ-CCR-09, REQ-CCR-10, REQ-SG-02, REQ-SG-03, REQ-SG-04, REQ-SG-05, REQ-SG-06, REQ-RPC-04, REQ-RPC-05]
module_ids: [K-RECORDS]
acceptance_status: not_behaviorally_validated
---

# 项目记录与学习资料

从这里了解项目进展、回看任务结果，或按需要查阅学习资料和已确认的沟通偏好。记录会随工作更新；每份记录顶部保留版本、日期、来源和状态，详细职责见[持续记录架构](../architecture/continuous-records.md)。

## 当前记录

| 入口 | 适合查找什么 | 稳定 ID |
| --- | --- | --- |
| [本轮内核与材料整理](tasks/2026-10-15-kernel-cleanup.md) | README、设计图、视频、目录整理与发布检查 | KERNEL-CLEANUP-20261015 |
| [持续整洁与 headless 计划](../plans/kernel-hygiene-and-headless.md) | 输出治理、低耦合整改与无 UI skills 待办 | KERNEL-GROWTH-20261015 |
| [项目总结](project-summary.md) | 当前目标、能力位置、重要限制和维护方向 | CCR-PROJECT |
| [RPC 修复与交付](tasks/2026-10-10-rpc-resilience.md) | 当前 RPC 修复、文档同步及主分支交付结果 | RPC-TASK-20261010 |
| [布局与技能成长任务](tasks/2026-10-10-layout-and-skill-growth.md) | 当前文档、目录与可复用技能的改进结果 | SG-TASK-20261010 |
| [原内核维护任务](tasks/2026-10-10-kernel-maintenance.md) | 模块树及持续记录建立时的范围与结果 | CCR-TASK-20261010 |
| [模块树与规则学习资料](learning/2026-10-10-modules-and-rules.md) | 树与图、多对多、事实与推断、规则与技能 | CCR-LEARN-20261010 |
| [术语与错误资料](terms-and-errors.md) | 项目术语、静态发现的错误条件及处理原则 | CCR-TERMS |
| [用户学习画像](user-learning-profile.md) | 已确认偏好和学习需要；知识未知时保留未知，无评分 | CCR-USER |
| [任务记录参考](templates/task-record.md) | 新任务需要保留的事实字段，按具体工作组织内容 | CCR-TASK-TEMPLATE |
| [R1 设计评价任务](tasks/2026-10-13-r1-design-review.md) | R1 复现规格的设计评审结论与实施前置事项 | CCR-TASK-R1-DESIGN-REVIEW |
| [R1 参考实现 S0–S5 任务](tasks/2026-10-13-r1-implementation.md) | R1 切片代码落地、S1+S5 汇合与全量测试结果 | CCR-TASK-R1-IMPLEMENTATION |
| [R1 S6/S7 落地与验收矩阵任务](tasks/2026-10-13-r1-s6-s7-acceptance.md) | S6 SCM 效果结算、S7 验收矩阵 44 行登记与 8 项 host 剩余差距 | CCR-TASK-R1-S7-ACCEPTANCE |
| [AGH 适配与前端进度任务](tasks/2026-10-13-agh-adapter-frontend.md) | 内核接入 AGH 的前端设计规格、新增查询服务、演示视频素材与被拒操作 | CCR-TASK-AGH-ADAPTER-FRONTEND |
| [技能版本索引](skills/registry.json)、[反馈复核](skills/2026-10-10-maintain-records-review.md) | 方法适用范围、版本状态、真实评价及改进依据 | 索引中的 skill_id |

要定位某项能力，进入[模块目录](../modules/README.md)；本组记录的详细模块入口是 [K-RECORDS](../modules/nodes/continuous-records.md)。记录可以关联多个节点和需求，也可以暂时为空；当前没有对话节点关联。

## 阅读与改进

项目总结适合快速了解全貌，任务记录适合回看一次工作的结果，学习资料适合解释具体概念。摘要与主文档不一致时，以主文档和对应证据为准；历史 G2 结果仍由原验收记录拥有。

发现有用的方法时，可以用[技能成长方法](../architecture/skill-growth.md)逐步改进它的适用条件、例子和局限；技能可以评价，用户画像不评分。项目内 [kernel-maintain-records](../../.agents/skills/kernel-maintain-records/SKILL.md) 与 [kernel-grow-skills](../../.agents/skills/kernel-grow-skills/SKILL.md) 由当前 Codex 工作流应用，没有内核运行服务或自动同步。

原记录建立需求见[持续记录要求](../requirements/2026-10-10-continuous-records.md)，当前改进要求见[布局与技能成长](../requirements/2026-10-10-clean-layout-and-skill-growth.md)。

## 修订记录

| 记录版本 | 更新时间 | 内容 |
| --- | --- | --- |
| 1 | 2026-10-10 | 建立持续记录入口、当前摘要、学习资料与任务模板；运行集成未实施 |
| 2 | 2026-10-10 | 按项目、任务、学习与画像组织阅读入口，补充技能成长资料 |
| 3 | 2026-10-10 | 增加 RPC 修复任务和当前交付来源 |
| 4 | 2026-10-12 | 增加架构边界、消费者/SCM/训练/skill 范围任务记录 |
| 5 | 2026-10-13 | 增加 R1 设计评价任务与评价记录入口 |
| 6 | 2026-10-13 | 增加 R1 参考实现 S0–S5 落地任务记录入口 |
| 7 | 2026-10-13 | 增加 R1 S6/S7 落地与验收矩阵登记任务记录入口；S0–S7 全切片落盘，8 项 host 行保持 not_run |
| 8 | 2026-10-13 | 增加 AGH 适配与前端进度任务记录入口；前端设计规格已写成，浏览器验证与视频合成未完成 |
| 9 | 2026-10-15 | 整合设计与问题治理，记录输出清理及无界面计划，更新材料与本轮结果入口 |

## 2026-10-12 当前补充

[架构边界、skill 范围与失败分析](tasks/2026-10-12-kernel-boundaries.md)记录本次文档交付、静态核对和未完成范围。消费者权威视图读已提交事实；SCM 仍是待设计接入；corpus 已有候选样本/审核/切分，但默认关闭。评分与失败总结只有数据处理用途，不接入执行；发布状态与真实宿主验证缺口不变。

## 2026-10-13 当前补充

[R1 设计评价](../reviews/2026-10-13-r1-design-review.md)确认 R1 规格 12 不变式与六层完成分层为最强部分；列出六项实施前置（host_work 归属、表单暂态、问答唤醒、评分防混、计量模式、并发增长验收），修订 01/02/03 章后再按 S0→S7 分发实施。主记录见[任务](tasks/2026-10-13-r1-design-review.md)；无实现或行为验收，`release_approved=false` 不变。

同日 [R1 参考实现 S0–S5 落地](tasks/2026-10-13-r1-implementation.md)：六切片代码与切片测试在 `project_kernel_r1/` 落地，S1+S5 汇合后 skip 清零，全量 265 passed；S6/S7 未启动，R1-AC 与 R1-AC-M 全部保持 not_run，`release_approved=false` 不变。

同日 [R1 S6/S7 落地与验收矩阵登记](tasks/2026-10-13-r1-s6-s7-acceptance.md)：S6 在 `application/scm/` 落地 SCM intent/效果映射/结算编排（R1-AC-17..25 规则层）；S7 在 `tests/acceptance/` 落地 44 行验收矩阵（04 §7 + 05 §8）runner + not_run 登记册，36 项 synthetic 断言已覆盖、8 项 host（R1-AC-25/26/28/29/30/31/32/34）保持 not_run 入剩余差距；全量 280 passed，`release_approved=false` 不变。

同日 [AGH 适配与前端进度](tasks/2026-10-13-agh-adapter-frontend.md)：为适配器补充 6 个只读查询服务（仅语法检查，未运行）并写成前端多视图设计规格，交由 GPT 实现；演示视频的画面与解说词已生成，配音与 mp4 合成因操作被拒未完成。前端未在浏览器验证，适配器未安装到 AGH 实例，无新增验收，`release_approved=false` 不变。
